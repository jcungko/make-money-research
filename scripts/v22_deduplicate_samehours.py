#!/usr/bin/env python3
"""Second-stage V22 portfolio de-duplication by SAME symbol set, near-identical
entry windows, overlapping EA clusters and strongly correlated monthly returns.
The initial screen checked exact trade-overlap and EA returns; this stage
purges same-hours multi-asset variants that remained because slightly different
exit lengths prevented trade-level similarity classifications.
"""
import csv,json,math
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import v22_nov2026_filter as core

ROOT=Path('results/v22_deduplicated')
INPUT=ROOT/'distinct_portfolios.csv'
OUT=Path('results/v22_deduplicated_final')
CLUSTER_MIN_FRACTION=0.60
HOUR_MATCH_MIN_FRACTION=0.80
HOUR_SEPARATION_MAX=1
MONTHLY_CORRELATION_THRESHOLD=0.86
ALTERNATIVE_MONTHLY_CORRELATION_THRESHOLD=0.96

def csvread(path):
    with path.open('r',newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def corr_months(a,b):
    x=np.asarray([float(a[f'pnl_{month}_bps']) for month in MONTHS])
    y=np.asarray([float(b[f'pnl_{month}_bps']) for month in MONTHS])
    if np.std(x)<1e-8 or np.std(y)<1e-8:return 0.
    return float(np.corrcoef(x,y)[0,1])
MONTHS=[y*100+m for y in (2025,2026) for m in range(1,13 if y==2025 else 11)]

def quality(row):
    return (int(row['months_profitable']),
            min(float(row[f'pnl_{m}_bps']) for m in MONTHS),
            float(row['nov_2026_bps']),float(row['total_bps']),
            -int(row['n_strategies']))

def prepare(row):
    specs=[core.parse_component(v) for v in row['components'].split(' | ')]
    clusters=row['signals_after_ea_dedup'].split(';')
    symbols=row['symbols'].split('+')
    assert len(specs)==len(clusters)==len(symbols)
    return {s:dict(cluster=c,hour=spec['hour'],window=spec['window'],
                   direction=spec['orientation']) for s,c,spec in zip(symbols,clusters,specs)}

def compare(a,b):
    specs_a=a['_specs'];specs_b=b['_specs']
    if set(specs_a)!=set(specs_b):return None
    n=len(specs_a)
    if n<2:return None
    same_clusters=sum(specs_a[s]['cluster']==specs_b[s]['cluster'] for s in specs_a)
    near_hours=sum(abs(specs_a[s]['hour']-specs_b[s]['hour'])<=HOUR_SEPARATION_MAX
                   for s in specs_a)
    cluster_fraction=same_clusters/n
    near_fraction=near_hours/n
    if near_fraction<HOUR_MATCH_MIN_FRACTION:return None
    p_corr=corr_months(a,b)
    same_or_similar=(
        (cluster_fraction>=CLUSTER_MIN_FRACTION and
         p_corr>=MONTHLY_CORRELATION_THRESHOLD) or
        (near_fraction>=HOUR_MATCH_MIN_FRACTION and
         p_corr>=ALTERNATIVE_MONTHLY_CORRELATION_THRESHOLD)
    )
    if not same_or_similar:return None
    return dict(same_ea_clusters=same_clusters,assets=n,same_ea_fraction=round(cluster_fraction,4),
                entry_hours_within_one_hour=near_hours,entry_hour_overlap=round(near_fraction,4),
                monthly_profit_correlation=round(p_corr,5),
                reason='same_assets_overlapping_hours_similar_ea_and_returns'
                 if cluster_fraction>=CLUSTER_MIN_FRACTION else 'same_assets_nearly_identical_monthly_returns')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original=csvread(INPUT)
    if len(original)!=367:raise AssertionError(f'Unexpected first-stage filtered count {len(original)}')
    for row in original:row['_specs']=prepare(row)
    source=ROOT/'dedup_summary.json'
    previous=json.loads(source.read_text())
    baseline=previous['input']
    retained=[]
    dropped=[]
    by_symbol_sets=defaultdict(list)
    for candidate in sorted(original,key=lambda r:(quality(r),r['id']),reverse=True):
        label=tuple(sorted(candidate['_specs']))
        duplicate=None
        for keep in by_symbol_sets[label]:
            match=compare(candidate,keep)
            if match:
                duplicate=(keep['id'],match)
                break
        if duplicate:
            dropped.append((candidate,*duplicate))
        else:
            retained.append(candidate)
            by_symbol_sets[label].append(candidate)
    retained.sort(key=lambda r:(quality(r),r['id']),reverse=True)
    columns=[x for x in original[0] if not x.startswith('_')]
    with (OUT/'final_distinct_portfolios.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=columns)
        writer.writeheader()
        for r in retained:writer.writerow({key:r[key] for key in columns})
    with (OUT/'removed_same_hours_portfolios.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=columns+
          ['replacement_id','same_ea_clusters','assets','same_ea_fraction',
           'entry_hours_within_one_hour','entry_hour_overlap',
           'monthly_profit_correlation','reason'])
        writer.writeheader()
        for r,replace,why in dropped:
            writer.writerow({**{key:r[key] for key in columns},
                             'replacement_id':replace,**why})
    all_by_type={str(n):{'initial_1860':previous['by_portfolio_size'][str(n)]['before'],
                         'after_trade_dedup':previous['by_portfolio_size'][str(n)]['retained'],
                         'after_time_window_dedup':sum(int(r['n_strategies'])==n for r in retained)}
                 for n in (1,2,3,4,5)}
    months_counts={str(n):{'original_1860':previous['by_months_positive'][str(n)]['before'],
                           'after_trade_dedup':previous['by_months_positive'][str(n)]['retained'],
                           'after_time_window_dedup':sum(int(r['months_profitable'])==n for r in retained)}
                   for n in (17,18,19,20)}
    report=dict(
       version='V22-PORTFOLIO-DISTINCT-FINAL',
       data_cutoff_utc=previous['data_cutoff_utc'],
       starting_portfolios=baseline,
       first_stage_trade_overlap_kept=previous['retained'],
       first_stage_trade_overlap_removed=previous['removed'],
       first_stage_unique_eas=previous['unique_eas_before'],
       first_stage_distinct_ea_signal_clusters=previous['distinct_ea_signal_clusters'],
       second_stage_same_hours_removed=len(dropped),
       final_distinct_portfolios=len(retained),
       total_removed=baseline-len(retained),
       assets_must_match_exactly=True,
       definition='A multi-symbol portfolio is near duplicate if the same asset set has >=80% of time windows within 1 hour and (>=60% same trade-pattern EA clusters with 22-month pnl correlation>=0.86 OR 22-month pnl correlation>=0.96). Keep strongest by profitable-month count, worst monthly pnl, then Nov, then total.',
       thresholds=dict(min_fraction_ea_clusters=CLUSTER_MIN_FRACTION,
                       min_fraction_matching_hours=HOUR_MATCH_MIN_FRACTION,
                       max_hour_difference=HOUR_SEPARATION_MAX,
                       min_monthly_pnl_correlation=MONTHLY_CORRELATION_THRESHOLD,
                       alternate_monthly_pnl_correlation=ALTERNATIVE_MONTHLY_CORRELATION_THRESHOLD),
       by_number_of_components=all_by_type,
       by_historic_positive_months=months_counts,
       top20=[{k:r[k] for k in ('id','symbols','n_strategies','months_profitable',
                        'nov_2026_bps','total_bps','profit_2025_bps','profit_2026_bps',
                        'components')} for r in retained[:20]],
       removal_examples=[dict(id=r['id'],replacement_id=key,**metrics) for r,key,metrics in dropped[:30]],
       created_at_utc=datetime.now(timezone.utc).isoformat()
    )
    if len(retained)+len(dropped)!=len(original):raise AssertionError('Conservation failed')
    (OUT/'final_summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('FINAL',json.dumps({k:report[k] for k in ('starting_portfolios','first_stage_trade_overlap_kept',
                 'second_stage_same_hours_removed','final_distinct_portfolios','total_removed',
                 'by_number_of_components','by_historic_positive_months')}),flush=True)

if __name__=='__main__':main()
