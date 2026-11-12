#!/usr/bin/env python3
"""V22: auditable trade-overlap / portfolio-similarity de-duplication.

Input: 1860 November-positive configs after October and November Exness filters.
Replays their underlying 97 EA variants on immutable 2025-2026 historical
bid/ask data plus November-to-date archive; detects duplicate trade schedules
and clustered near-identical multi-asset portfolios. This is in-sample research.
"""
import argparse,csv,json,math,zipfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
import v22_nov2026_filter as nov
import v22_17to20_month_screen as model

ROOT=Path('results/v22_nov2026_filter')
INPUT=ROOT/'surviving_oct_and_nov_to_date.csv'
MONTHS=[y*100+m for y in (2025,2026) for m in range(1,13 if y==2025 else 11)]+[202611]
MONTH_TO_INDEX={m:i for i,m in enumerate(MONTHS)}
MIN_EA_MATCH_FRACTION=0.82
MIN_EA_PNL_CORRELATION=0.84
MAX_MATCHED_ENTRY_SEPARATION_MINUTES=60
PORTFOLIO_MONTH_CORRELATION=0.94
PORTFOLIO_VERY_HIGH_MONTH_CORRELATION=0.985

def load_csv(path):
    with path.open('r',newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def november_frame(symbol,tf):
    path=ROOT/'november_candles'/f'{symbol}_202611_through_20261112_1955UTC_5TF.zip'
    with zipfile.ZipFile(path) as z:
        with z.open(f'{symbol}_{tf}_202611_UTC.csv') as f:
            d=pd.read_csv(f,parse_dates=['timestamp_utc'],index_col='timestamp_utc')
    d.index=pd.DatetimeIndex(d.index).tz_convert('UTC')
    return d

def replay_events(c,store):
    sym,tf=c['symbol'],c['tf']
    df, prepared, signal_map=store[sym,tf]
    ordinal,midx,minute,day,week,hold_map=prepared
    raw=signal_map[c['family']]
    if c['orientation']=='FOLLOW':side=raw
    elif c['orientation']=='FADE':side=-raw
    elif c['orientation']=='LONG_ONLY':side=np.where(raw>0,1,0)
    elif c['orientation']=='SHORT_ONLY':side=np.where(raw<0,-1,0)
    else:raise AssertionError('unsupported orientation')
    eligible=side!=0
    if c['regime']=='D1_ALIGN':eligible &= side==day
    elif c['regime']=='W1_ALIGN':eligible &= side==week
    eligible &= (minute>=60*c['hour'])&(minute<min(60*(c['hour']+c['window']),1440))
    valid,longret,shortret=hold_map[c['hold']//model.TFS[tf][0]]
    indices=np.flatnonzero(eligible&valid)
    if len(indices):indices=indices[np.r_[True,ordinal[indices[1:]]!=ordinal[indices[:-1]]]]
    rets=np.where(side[indices]>0,longret[indices],shortret[indices])
    ts=df.index.asi8[indices]
    months=midx[indices]
    pnl=np.bincount(months,weights=rets,minlength=23)
    return {
      'by_day':{int(ordinal[ix]):(int(df.index.asi8[ix]),int(side[ix]),float(ret))
                for ix,ret in zip(indices,rets)},
      'month':pnl,
      'ntrades':len(indices),
      'hour':c['hour'],
      'symbol':sym,
      'spec':c,
      'last_utc':df.index.max().isoformat()
    }

def ea_similarity(a,b):
    if a['symbol']!=b['symbol'] or abs(a['hour']-b['hour'])>1:return None
    days=set(a['by_day']).intersection(b['by_day'])
    min_n=min(a['ntrades'],b['ntrades'])
    if min_n<35 or len(days)/min_n<MIN_EA_MATCH_FRACTION:return None
    matched=[]
    for d in days:
        t1,side1,ret1=a['by_day'][d]
        t2,side2,ret2=b['by_day'][d]
        if side1==side2 and abs(t1-t2)<=MAX_MATCHED_ENTRY_SEPARATION_MINUTES*60*1_000_000_000:
            matched.append((ret1,ret2))
    match_ratio=len(matched)/min_n
    if match_ratio<MIN_EA_MATCH_FRACTION:return None
    r=np.array(matched)
    corr=float(np.corrcoef(r[:,0],r[:,1])[0,1]) if len(r)>5 else 0.0
    if not np.isfinite(corr):corr=0.0
    # Distinct exits are permitted ONLY if their realized same-trade returns
    # still behave similarly. Near-total identical starts/sides are flagged.
    if corr<MIN_EA_PNL_CORRELATION and match_ratio<0.98:return None
    return dict(trade_match=round(match_ratio,4),trade_pnl_corr=round(corr,4),matched_trades=len(matched))

def ea_quality(v):
    arr=v['month']
    return (int(np.count_nonzero(arr[:22]>0)),float(np.min(arr[:22])),
            float(arr[-1]),float(np.sum(arr[:22])))

def months_corr(a,b):
    x=np.asarray(a,dtype=float)[:22]
    y=np.asarray(b,dtype=float)[:22]
    if np.std(x)<1e-8 or np.std(y)<1e-8:return 0.
    return float(np.corrcoef(x,y)[0,1])

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    rows=load_csv(INPUT)
    if len(rows)!=1860:raise AssertionError(f'Unexpected October+November survivors {len(rows)}')
    components={}
    structure={}
    for row in rows:
        specs=[nov.parse_component(s) for s in row['components'].split(' | ')]
        if len(specs)!=int(row['n_strategies']):raise AssertionError('bad component size')
        structure[row['id']]=[nov.component_key(s) for s in specs]
        for s in specs:components[nov.component_key(s)]=s
    if len(components)!=97:raise AssertionError(f'Unexpected unique components: {len(components)}')
    model.MONTHS=MONTHS
    model.MONTH_ID=MONTH_TO_INDEX
    needs={(s['symbol'],s['tf']) for s in components.values()}
    store={}
    for symbol in model.SYMBOLS:
        five=pd.concat([model.load(Path('data/v22_exness'),symbol,'M5'),
                        november_frame(symbol,'M5')]).sort_index()
        if five.index.has_duplicates:raise AssertionError('duplicate M5 '+symbol)
        ds,ws=model.daily_weekly_directions(five)
        for sym,tf in sorted(needs):
            if sym!=symbol:continue
            d=pd.concat([model.load(Path('data/v22_exness'),symbol,tf),
                         november_frame(symbol,tf)]).sort_index()
            if d.index.has_duplicates:raise AssertionError('duplicate frame '+symbol+tf)
            prepared=model.prepare(d,tf,ds,ws)
            signals=dict(model.signal_library(d,prepared[3],prepared[4]))
            store[sym,tf]=(d,prepared,signals)
    events={k:replay_events(spec,store) for k,spec in components.items()}
    print('EA_REPLAY',len(events),'total historic+nov trades',sum(e['ntrades'] for e in events.values()),flush=True)
    # Verify EVERY original monthly observation and November OOS partial observation
    # before performing any de-duplication.
    max_replay_error=0.0
    for row in rows:
        pnl=np.mean(np.stack([events[k]['month'] for k in structure[row['id']]]),axis=0)
        expected=np.array([float(row[f'pnl_{m}_bps']) for m in MONTHS[:22]]+
                          [float(row['nov_2026_bps'])])
        delta=float(np.max(np.abs(pnl-expected)))
        max_replay_error=max(max_replay_error,delta)
        if delta>0.002:raise AssertionError(f"EA replay different from baseline {row['id']} max delta {delta}")
        row['_months']=pnl
    print('VERIFIED_ALL_MONTHS',len(rows),'max_bps_error',max_replay_error,flush=True)
    # Build EA trade-overlap groups using best-vs-representative matching
    ranked=sorted(events,key=lambda k:(ea_quality(events[k]),k),reverse=True)
    groups={}
    map_to_rep={}
    ea_edges=[]
    for key in ranked:
        event=events[key]
        winner=None
        best_match=None
        for rep in groups:
            m=ea_similarity(event,events[rep])
            if m and (best_match is None or (m['trade_match'],m['trade_pnl_corr'])>
                  (best_match['trade_match'],best_match['trade_pnl_corr'])):
                winner=rep; best_match=m
        if winner is None:
            winner=key
            groups[winner]=[]
        else:
            ea_edges.append(dict(component=' | '.join(map(str,key)),
                                 representative=' | '.join(map(str,winner)),**best_match))
        groups[winner].append(key)
        map_to_rep[key]=winner
    rep_id={r:f'EA{n:03d}' for n,r in enumerate(groups,1)}
    print('EA_DEDUP',len(events),'->',len(groups),'removed near-duplicate EAs',len(ea_edges),flush=True)
    aliases={k:rep_id[v] for k,v in map_to_rep.items()}
    # Assign portfolio "signal identity" by actual corresponding grouped EAs.
    # All original 22-month & November profit fields remain unchanged.
    for row in rows:
        names=row['symbols'].split('+')
        representatives=[aliases[k] for k in structure[row['id']]]
        if len(representatives)!=len(names):raise AssertionError('asset/signature mismatch')
        row['_asset_clusters']=dict(zip(names,representatives))
    # Rank stronger risk consistency first, then recent positive months, then P&L.
    def score(row):
        return (int(row['months_profitable']),
                min(float(row[f'pnl_{month}_bps']) for month in MONTHS[:22]),
                float(row['nov_2026_bps']),float(row['total_bps']),
                -int(row['n_strategies']))
    ranked_rows=sorted(rows,key=lambda r:(score(r),r['id']),reverse=True)
    retained=[]
    dropped=[]
    by_assets=defaultdict(list)
    reason_counter=Counter()
    for row in ranked_rows:
        key=tuple(sorted(row['_asset_clusters']))
        clone=None
        test_info=None
        for kept in by_assets[key]:
            matches=sum(row['_asset_clusters'][s]==kept['_asset_clusters'][s] for s in key)
            n=len(key)
            fraction=matches/n
            if n==1:
                isduplicate=(matches==1)
                cor=1. if isduplicate else 0.
                reason='same_trading_signals' if isduplicate else ''
            else:
                cor=months_corr(row['_months'],kept['_months'])
                # One-changed-asset variants are near-duplicates when
                # monthly returns are strongly correlated and most actual
                # signal representatives still match. Retain a stronger one.
                isduplicate=(
                    (matches==n) or
                    (matches>=n-1 and cor>=PORTFOLIO_MONTH_CORRELATION and n>=3) or
                    (matches>=max(1,math.ceil(n*.6)) and cor>=PORTFOLIO_VERY_HIGH_MONTH_CORRELATION)
                )
                reason=('same_trade_clusters' if matches==n
                        else 'same_assets_similar_signals_high_pnl_correlation' if isduplicate else '')
            if isduplicate:
                clone=kept
                test_info=dict(common_asset_eas=matches,total_assets=n,
                               monthly_pnl_correlation=round(cor,5),reason=reason)
                break
        if clone is None:
            retained.append(row)
            by_assets[key].append(row)
        else:
            reason_counter[test_info['reason']]+=1
            dropped.append((row,clone['id'],test_info))
    retained.sort(key=lambda r:(score(r),r['id']),reverse=True)
    if len(retained)+len(dropped)!=len(rows):raise AssertionError('not conserved')
    # Build concise original configurations and full 22+1 monthly returns.
    csv_original=[k for k in rows[0] if not k.startswith('_')]
    csv_fields=csv_original+['signals_after_ea_dedup','unique_ea_cluster_count']
    with (out/'distinct_portfolios.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=csv_fields)
        w.writeheader()
        for r in retained:
            d={k:r[k] for k in csv_original}
            d['signals_after_ea_dedup']=';'.join(r['_asset_clusters'][s] for s in r['symbols'].split('+'))
            d['unique_ea_cluster_count']=len(set(r['_asset_clusters'].values()))
            w.writerow(d)
    with (out/'removed_similar_portfolios.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=csv_fields+['kept_instead','shared_asset_eas',
                                                   'total_assets','monthly_pnl_correlation','reason'])
        w.writeheader()
        for r,rep,metrics in dropped:
            d={k:r[k] for k in csv_original}
            d['signals_after_ea_dedup']=';'.join(r['_asset_clusters'][s] for s in r['symbols'].split('+'))
            d['unique_ea_cluster_count']=len(set(r['_asset_clusters'].values()))
            d.update(dict(kept_instead=rep,shared_asset_eas=metrics['common_asset_eas'],
                          total_assets=metrics['total_assets'],
                          monthly_pnl_correlation=metrics['monthly_pnl_correlation'],
                          reason=metrics['reason']))
            w.writerow(d)
    with (out/'ea_component_clusters.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['cluster_id','symbol','tf','strategy','orientation',
                                      'regime','entry_hour_utc','hold_minutes',
                                      'historic_trades','months_profit','historic_bps',
                                      'november_bps','is_representative'])
        w.writeheader()
        for k in sorted(events):
            e=events[k]; c=e['spec']
            w.writerow(dict(cluster_id=aliases[k],symbol=c['symbol'],tf=c['tf'],strategy=c['family'],
                    orientation=c['orientation'],regime=c['regime'],entry_hour_utc=c['hour'],
                    hold_minutes=c['hold'],historic_trades=e['ntrades'],
                    months_profit=int(np.count_nonzero(e['month'][:22]>0)),
                    historic_bps=round(float(np.sum(e['month'][:22])),4),
                    november_bps=round(float(e['month'][-1]),4),
                    is_representative=(map_to_rep[k]==k)))
    (out/'ea_similarity_evidence.json').write_text(json.dumps(ea_edges,indent=2)+'\n')
    report=dict(
      name='V22 near duplicate EA & portfolio filter',
      data_cutoff_utc=nov.CUTOFF.isoformat(),
      method='reconstruct exact 2025-2026 Nov12 historical trade event dates, time (ns), direction and P&L using Exness Bid/Ask, then compare by same asset same-hour trade overlap; separately greedily deduplicate multi-EA portfolios by matching representative EAs and 22-month P&L correlation.',
      thresholds=dict(ea_match_min_fraction=MIN_EA_MATCH_FRACTION,
          ea_pnl_min_correlation=MIN_EA_PNL_CORRELATION,
          max_entry_time_separation_minutes=MAX_MATCHED_ENTRY_SEPARATION_MINUTES,
          portfolio_month_pnl_corr_min=PORTFOLIO_MONTH_CORRELATION,
          portfolio_very_high_corr=PORTFOLIO_VERY_HIGH_MONTH_CORRELATION),
      historic_months=MONTHS[:22],
      input=1860,
      retained=len(retained),
      removed=len(dropped),
      unique_eas_before=len(events),
      distinct_ea_signal_clusters=len(groups),
      ea_near_duplicates=len(ea_edges),
      reason_counts=dict(reason_counter),
      max_baseline_replay_error_bps=max_replay_error,
      by_portfolio_size={
          str(n):dict(before=sum(int(r['n_strategies'])==n for r in rows),
                      retained=sum(int(r['n_strategies'])==n for r in retained),
                      removed=sum(int(r['n_strategies'])==n for r,_,_ in dropped))
          for n in (1,2,3,4,5)
      },
      by_months_positive={
          str(n):dict(before=sum(int(r['months_profitable'])==n for r in rows),
                      retained=sum(int(r['months_profitable'])==n for r in retained),
                      removed=sum(int(r['months_profitable'])==n for r,_,_ in dropped))
          for n in (17,18,19,20)
      },
      by_symbol_set={
          '+'.join(symbols):len(v) for symbols,v in sorted(by_assets.items())},
      top20=[{k:r[k] for k in ['id','symbols','n_strategies','months_profitable',
                              'nov_2026_bps','nov_trades_all_components',
                              'profit_2025_bps','profit_2026_bps','total_bps','components']}
             for r in retained[:20]],
      removed_examples=[dict(id=r['id'],replaced_by=rep,**m)
                        for r,rep,m in dropped[:25]],
      generated_at_utc=datetime.now(timezone.utc).isoformat()
    )
    (out/'dedup_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('FINAL',json.dumps({k:report[k] for k in
      ('input','retained','removed','unique_eas_before','distinct_ea_signal_clusters',
       'ea_near_duplicates','by_portfolio_size','by_months_positive','reason_counts','max_baseline_replay_error_bps')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('results/v22_deduplicated'))
    args=p.parse_args()
    main(args.out)
