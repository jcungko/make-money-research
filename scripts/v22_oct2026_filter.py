#!/usr/bin/env python3
"""V22: filter all >=17/22 configurations by actual simulated 2026-10 net P&L.

Replays EXACT previous candidate universe, retains complete configuration-level
audit rather than only top-1000 portfolio exports.
"""
import argparse, collections, csv, json
from pathlib import Path
from datetime import datetime, timezone
import v22_17to20_month_screen as source

MONTH_INDEX=source.MONTH_ID[202610]
CAPTURED=collections.defaultdict(list)
_original=source.combo_record

def capture(pool, group):
    item=_original(pool,group)
    if item is not None:
        CAPTURED[len(group)].append(item)
    return item

def row(x, category):
    comp=x.get('components', [x])
    values=x['monthly_bps']
    month_good=sum(float(v)>1e-8 for v in values)
    if month_good != int(x['months_positive']):
        raise AssertionError("bad positive month sum")
    if len(values)!=22:
        raise AssertionError("expected 22 monthly P&L values")
    return dict(
        id='', category=category, n_strategies=len(comp),
        months_profitable=month_good,
        oct_2026_bps=round(float(values[MONTH_INDEX]),5),
        profit_2025_bps=x['pnl_2025_bps'],
        profit_2026_bps=x['pnl_2026_bps'],
        total_bps=x['total_bps'],
        min_month_bps=x['min_month_bps'],
        losing_months=';'.join(str(source.MONTHS[i]) for i,v in enumerate(values) if float(v)<-1e-8),
        zero_months=';'.join(str(source.MONTHS[i]) for i,v in enumerate(values) if abs(float(v))<=1e-8),
        symbols='+'.join(z['symbol'] for z in comp),
        components=' | '.join(
            f"{z['symbol']} {z['tf']} {z['family']} {z['orientation']} "
            f"{z['regime']} entry_{z['entry_start_utc']:02d}:00_UTC "
            f"window_{z['entry_window_hours']}h hold_{z['hold_minutes']}min"
            for z in comp
        ),
        **{f'pnl_{month}_bps':round(float(values[i]),5) for i,month in enumerate(source.MONTHS)}
    )

def screen(root,out):
    out.mkdir(parents=True,exist_ok=True)
    source.combo_record=capture
    # Rerun exact historical V22 17-20 baseline. Does not change universe.
    baseline=out/'baseline'
    source.screen(root,baseline)
    with (baseline/'screen_summary.json').open() as f:
        base=json.load(f)
    with (baseline/'qualified_singles.json').open() as f:
        singles=json.load(f)
    data={'single':singles,'pair':CAPTURED[2],'triple':CAPTURED[3],'quad':CAPTURED[4],'quint':CAPTURED[5]}
    input_counts={k:len(v) for k,v in data.items()}
    expected={'single':base['single_at_least_17_months'],'pair':base['pairs_at_least_17_months'],
              'triple':base['triples_at_least_17_months'],'quad':base['quads_at_least_17_months'],
              'quint':base['quints_at_least_17_months']}
    assert input_counts==expected,(input_counts,expected)
    all_rows=[row(v,k) for k,records in data.items() for v in records]
    assert len(all_rows)==3726,(len(all_rows),'baseline V22 expected count changed')
    keep=[r for r in all_rows if r['oct_2026_bps']>=-1e-8]
    drop=[r for r in all_rows if r['oct_2026_bps']< -1e-8]
    profitable=[r for r in all_rows if r['oct_2026_bps']>1e-8]
    zero=[r for r in all_rows if abs(r['oct_2026_bps'])<=1e-8]
    keep.sort(key=lambda r:(-r['months_profitable'],-r['oct_2026_bps'],-r['total_bps'],r['symbols'],r['components']))
    drop.sort(key=lambda r:(-r['months_profitable'],-r['total_bps'],r['symbols']))
    for index,r in enumerate(keep,1):r['id']=f'V22-K{index:04}'
    for index,r in enumerate(drop,1):r['id']=f'V22-X{index:04}'
    fields=list(all_rows[0])
    for name,rows in [('kept_not_losing_2026_10.csv',keep),('removed_losing_2026_10.csv',drop)]:
        with (out/name).open('w',newline='',encoding='utf-8-sig') as file:
            writer=csv.DictWriter(file,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    categories=list(data)
    summary={
      'version':'V22-2026-10-FILTER',
      'source_version':base['version'],
      'baseline_configs':len(all_rows),
      'october_index':MONTH_INDEX,
      'rule':'remove monthly_bps[202610]<0, keep >=0; >0 subset also counted',
      'comparison':'in-sample, historical Exness CFD bid/ask research with baseline fee/slippage assumptions',
      'all_22months_2025_2026':source.MONTHS,
      'by_type':{
          key:{
              'before':input_counts[key],
              'kept_oct_not_losing':sum(r['category']==key for r in keep),
              'kept_oct_profitable':sum(r['category']==key for r in profitable),
              'removed_oct_losing':sum(r['category']==key for r in drop),
          } for key in categories},
      'thresholds':{
        str(t):{
          'at_least_before':sum(r['months_profitable']>=t for r in all_rows),
          'at_least_kept':sum(r['months_profitable']>=t for r in keep),
          'at_least_removed':sum(r['months_profitable']>=t for r in drop),
          'exact_kept':sum(r['months_profitable']==t for r in keep),
          'exact_removed':sum(r['months_profitable']==t for r in drop),
          'by_type':{
            key:{'kept':sum(r['category']==key and r['months_profitable']>=t for r in keep),
                 'removed':sum(r['category']==key and r['months_profitable']>=t for r in drop)}
            for key in categories}
        } for t in range(17,23)},
      'kept':len(keep),'removed':len(drop),'oct_profitable':len(profitable),'oct_zero':len(zero),
      'top10_kept':[{k:r[k] for k in ('id','category','months_profitable','symbols','oct_2026_bps',
                                  'profit_2025_bps','profit_2026_bps','total_bps','losing_months','components')} for r in keep[:10]],
      'created_at_utc':datetime.now(timezone.utc).isoformat()
    }
    assert summary['kept']+summary['removed']==3726
    (out/'filter_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('OCT2026_FILTER',json.dumps({k:summary[k] for k in ('baseline_configs','kept','removed','oct_profitable','oct_zero','by_type','thresholds')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('data/v22_exness'))
    p.add_argument('--out',type=Path,default=Path('results/v22_oct2026_filter'))
    a=p.parse_args()
    screen(a.root,a.out)
