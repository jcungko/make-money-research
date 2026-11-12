#!/usr/bin/env python3
"""V22 deduplicate 1860 November-2026 positive historical stock strategies.

Deterministic direct-to-representative suppression. Never collapse via transitive
chains: every removed member is directly checked against its surviving keeper.
Grouping uses trade instrument, entry UTC window, timeframe, signal style,
direction, hold and monthly profitability similarity; not asset name alone.
"""
import csv, json, math, re
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime, timezone
import numpy as np

INPUT=Path('results/v22_nov2026_filter/surviving_oct_and_nov_to_date.csv')
OUTPUT=Path('results/v22_nov2026_deduplicated')
MONTHS=[f'{y}{m:02}' for y in (2025,2026) for m in range(1,13 if y==2025 else 11)]
TFM={'M5':5,'M15':15,'M30':30,'H1':60,'H4':240}
FIELDS=('symbol','tf','family','orientation','regime','hour','window','hold')

def parse_bot(text):
    tokens=text.strip().split()
    if len(tokens)!=8:raise ValueError('Bad component '+repr(text))
    sym,tf,family,orient,regime,time,window,hold=tokens
    if tf not in TFM:raise ValueError(text)
    if not re.fullmatch(r'entry_\d{2}:00_UTC',time):raise ValueError(text)
    return dict(symbol=sym,tf=tf,family=family,orientation=orient,regime=regime,
        hour=int(time[6:8]),window=int(window.removeprefix('window_').removesuffix('h')),
        hold=int(hold.removeprefix('hold_').removesuffix('min')))

def family_class(family):
    if family.startswith('RSI_') or family.startswith('ZSCORE_'):return 'OSCILLATOR'
    if family.startswith(('SMA_','EMA_','MOMENTUM_','BREAKOUT_')):return 'TREND'
    if family in ('DAILY_PREVIOUS','WEEKLY_PREVIOUS','PREVIOUS_CANDLE'):return 'CANDLE_DIRECTION'
    if family=='CONSTANT_DIRECTION':return 'FIXED'
    return family

def bot_similarity(a,b):
    # Only compare same symbol; caller keyed by symbol already
    entry_diff=abs(a['hour']-b['hour'])
    hours=1.0 if entry_diff==0 else 0.6 if entry_diff==1 else 0.
    if entry_diff>1:return 0.
    tf_ratio=abs(math.log2(TFM[a['tf']]/TFM[b['tf']]))
    timeframe=1. if a['tf']==b['tf'] else .7 if tf_ratio<=1.6 else .3 if tf_ratio<=2.6 else 0.
    orient=1. if a['orientation']==b['orientation'] else 0.
    regime=1. if a['regime']==b['regime'] else .0
    if a['family']==b['family']:family=1.
    elif family_class(a['family'])==family_class(b['family']):family=.68
    else:family=0.
    duration=abs(a['hold']-b['hold'])
    hold=1. if duration==0 else .7 if duration<=60 else .4 if duration<=120 else .0
    return (.27*hours+.15*timeframe+.18*orient+.11*regime+.17*family+.12*hold)

def relationship(a,b):
    names_a=set(a['bots'])
    names_b=set(b['bots'])
    smaller=min(len(names_a),len(names_b))
    bigger=max(len(names_a),len(names_b))
    overlap=names_a&names_b
    if not overlap:return None
    exact=names_a==names_b
    # Different asset portfolios need nearly identical component footprint
    # to be deemed redundant: only 4-vs-5 subsets are eligible.
    subset=(names_a<=names_b or names_b<=names_a) and len(overlap)/bigger>=.8
    if not exact and not subset:return None
    entries=[(a['bots'][s]['hour'],b['bots'][s]['hour']) for s in overlap]
    exact_hours=sum(x==y for x,y in entries)/len(entries)
    within_hour=sum(abs(x-y)<=1 for x,y in entries)/len(entries)
    if exact_hours<.60 or within_hour<.90:return None
    structural=float(np.mean([bot_similarity(a['bots'][s],b['bots'][s]) for s in overlap]))
    if structural<.76:return None
    corr=float(np.dot(a['z'],b['z']))
    agree=float(np.mean(np.sign(a['monthly'])==np.sign(b['monthly'])))
    # Strict but hybrid: structural clones with same loss/profit months,
    # or nearly identical monthly returns, are counted as duplicates.
    if exact:
        qualifies=(structural>=.82 and (corr>=.88 or agree>=.90)) or (structural>=.76 and corr>=.97)
    else:
        qualifies=(structural>=.91 and corr>=.97 and agree>=.95)
    if not qualifies:return None
    return dict(assets='exact' if exact else 'subset',
        common_assets=len(overlap),time_exact_fraction=round(exact_hours,3),
        structural_similarity=round(structural,4),monthly_correlation=round(corr,4),
        monthly_profit_loss_sign_agreement=round(agree,4))

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with INPUT.open(encoding='utf-8-sig',newline='') as f:
        original=list(csv.DictReader(f))
    assert len(original)==1860,(len(original),'expected November filtered baseline')
    parsed=[]
    for item in original:
        bots=[parse_bot(k) for k in item['components'].split(' | ')]
        botby={k['symbol']:k for k in bots}
        if len(botby)!=len(bots) or len(bots)!=int(item['n_strategies']):
            raise AssertionError(item['id'])
        months=np.array([float(item[f'pnl_{m}_bps']) for m in MONTHS],dtype=float)
        if abs(float(item['pnl_202610_bps'])-months[-1])>.01:raise AssertionError(item['id'])
        if (months>1e-8).sum()!=int(item['months_profitable']):raise AssertionError(item['id'])
        centered=months-months.mean()
        norm=np.linalg.norm(centered)
        z=centered/norm if norm else np.zeros_like(centered)
        parsed.append(dict(row=item,bots=botby,assets=tuple(sorted(botby)),
                           monthly=months,z=z,
                           sort=(-int(item['months_profitable']),
                                 -float(item['min_month_bps']),
                                 -min(float(item['profit_2025_bps']),float(item['profit_2026_bps'])),
                                 -float(item['total_bps']),
                                 -float(item['nov_2026_bps']),item['id'])))
    parsed.sort(key=lambda x:x['sort'])
    kept=[]
    removed=[]
    byassets=defaultdict(list)
    # For 4/5 cross-portfolio checks, only compare candidates sharing many assets.
    for current in parsed:
        names=set(current['bots'])
        likely=list(byassets[current['assets']])
        if len(names)==4:
            for group,items in byassets.items():
                if len(group)==5 and names.issubset(group):likely.extend(items)
        elif len(names)==5:
            for group,items in byassets.items():
                if len(group)==4 and set(group).issubset(names):likely.extend(items)
        # Choose the strongest directly similar keeper, never a deleted neighbor.
        best=None
        bestmetric=None
        for representative in likely:
            relation=relationship(current,representative)
            if relation is None:continue
            metric=(int(relation['assets']=='exact'),relation['structural_similarity'],
                    relation['monthly_correlation'],relation['monthly_profit_loss_sign_agreement'])
            if best is None or metric>bestmetric:
                best,bestmetric=(representative,relation),metric
        if best is None:
            kept.append(current)
            byassets[current['assets']].append(current)
        else:
            representative,sim=best
            entry=dict(current['row'])
            entry['representative_id']=representative['row']['id']
            entry['similarity_reason']='same_assets_similar_hours_and_strategy' if sim['assets']=='exact' else 'subset_highly_correlated'
            entry.update(sim)
            removed.append(entry)
    keep_rows=[k['row'] for k in kept]
    assert len(keep_rows)+len(removed)==len(original)
    assert len({r['id'] for r in keep_rows})==len(keep_rows)
    kept.sort(key=lambda x:x['sort'])
    fields=list(original[0])
    with (OUTPUT/'unique_strategies.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows([x['row'] for x in kept])
    with (OUTPUT/'removed_duplicates_with_representatives.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields+['representative_id','similarity_reason',
          'assets','common_assets','time_exact_fraction','structural_similarity','monthly_correlation',
          'monthly_profit_loss_sign_agreement'])
        writer.writeheader();writer.writerows(removed)
    bytype=['single','pair','triple','quad','quint']
    thresholds=(20,19,18,17)
    report={
      'version':'V22-NOV2026-DEDUP',
      'screened_as_of_vietnam':'2026-11-13 02:55 GMT+7 (data through 2026-11-12T19:55:00Z)',
      'november_incomplete':True,
      'source':'results/v22_nov2026_filter/surviving_oct_and_nov_to_date.csv',
      'original':len(original),
      'retained':len(kept),
      'removed':len(removed),
      'unique_asset_combinations_before':len(set(x['assets'] for x in parsed)),
      'unique_asset_combinations_after':len(set(x['assets'] for x in kept)),
      'methods':{
        'ranking':'22-month positive-month count, then worst monthly P&L, worse of 2025/2026 P&L, total P&L, Nov-to-date P&L',
        'comparison':'same symbols with same/within-1-hour UTC entry times and similar timeframe, direction, indicators, regime, duration; monthly P&L similarity. Optional 4/5 overlap only if extremely high correlation',
        'suppress_when_same_assets':'60% exact hours, >=90% within 1h, structural similarity >=0.82 and (monthly corr >=0.88 or profit/loss month sign agree >=90%) OR structural >=0.76 and corr >=0.97',
        'suppress_when_4of5_asset_overlap':'structural >=0.91, monthly corr >=0.97, monthly sign agreement >=95%',
        'direct_only':'Every removed configuration compared directly with final retained representative. No transitive single-linkage overmerging.',
        'disclaimer':'In-sample monthly-return similarity over only 22 months; not trade-by-trade correlation or proven independence.'
      },
      'by_type':{t:{'before':sum(x['row']['category']==t for x in parsed),
                     'kept':sum(x['row']['category']==t for x in kept),
                     'removed':sum(x['category']==t for x in removed)} for t in bytype},
      'by_historical_profitable_months':{str(t):{'before':sum(int(x['row']['months_profitable'])==t for x in parsed),
                                                  'kept':sum(int(x['row']['months_profitable'])==t for x in kept),
                                                  'removed':sum(int(x['months_profitable'])==t for x in removed)} for t in thresholds},
      'monthly_thresholds':{str(t):{'before':sum(int(x['row']['months_profitable'])>=t for x in parsed),
                                   'kept':sum(int(x['row']['months_profitable'])>=t for x in kept)} for t in thresholds},
      'removed_same_assets':sum(x['assets']=='exact' for x in removed),
      'removed_subset_assets':sum(x['assets']=='subset' for x in removed),
      'top30':[{k:x['row'][k] for k in ('id','category','months_profitable','symbols','nov_2026_bps',
                                    'profit_2025_bps','profit_2026_bps','min_month_bps','total_bps','components')}
                for x in kept[:30]],
      'examples_of_removed':[
          {k:x[k] for k in ('id','representative_id','assets','structural_similarity',
                            'monthly_correlation','monthly_profit_loss_sign_agreement')}
          for x in removed[:40]],
      'finished_at_utc':datetime.now(timezone.utc).isoformat()
    }
    (OUTPUT/'dedup_summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('DEDUP_FINAL',json.dumps({k:report[k] for k in ('original','retained','removed','unique_asset_combinations_before',
                'unique_asset_combinations_after','by_type','by_historical_profitable_months','monthly_thresholds',
                'removed_same_assets','removed_subset_assets')}),flush=True)

if __name__=='__main__':main()
