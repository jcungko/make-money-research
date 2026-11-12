#!/usr/bin/env python3
"""V22: AVGO attribution, 2026-11-09..12 exclusion and concurrent AVGO risk.

Use the EXACT 3 SL-qualified portfolios, original strategy entry logic and M5
Bid/Ask simulated stop fills. No future candle close or account-scale USD claims.
Deterministic reconstructs every trade and crosschecks all published PnLs.
"""
import csv, json, itertools
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

import v22_mandatory_sl_retest as base

SRC=Path('results/v22_sl_backtest_2025_2026_nov/surviving_after_mandatory_SL.csv')
OUT=Path('results/v22_avgo_attribution_event_overlap')
IDS=('V22-K0549','V22-K1736','V22-K0722')
EVENT_DAYS={20261109,20261110,20261111,20261112}
NOV_ID=base.MONTHS.index(202611)
EPS=1e-8

def key(c):
    return base.nov.component_key(c)

def compute_trades(c,info,m5):
    """Replay exactly the previously used ATR SL logic and extract trade times."""
    data=base.replay_with_sl(c,info,m5)
    ix,signal,old=base.select_indices(c,info)
    if len(ix)!=len(data['ret']) or not np.allclose(old,data['original'],atol=1e-9):
        raise AssertionError('SL replay/source signal divergence')
    df=info['dataframe']
    tf_min=base.nov.model.TFS[c['tf']][0]
    holdbars=c['hold']//tf_min
    starts=df.index[ix]
    edges=df.index[ix+holdbars-1]+pd.Timedelta(minutes=tf_min)
    bars=np.asarray(m5.index.asi8)
    bid_low=m5.bid_low.to_numpy('float64')
    ask_hi=m5.ask_high.to_numpy('float64')
    ask_entry=df.ask_open.to_numpy('float64')
    bid_entry=df.bid_open.to_numpy('float64')
    mid=(ask_entry+bid_entry)*.5
    records=[]
    for j,k in enumerate(ix):
        side=int(signal[k])
        start=starts[j]
        scheduled_end=edges[j]
        end=scheduled_end
        sl_price=None
        if side>0:
            sl_price=float(ask_entry[k]-data['stop_fraction'][j]*mid[k])
        elif side<0:
            sl_price=float(bid_entry[k]+data['stop_fraction'][j]*mid[k])
        if data['stopped'][j]:
            a=np.searchsorted(bars,start.value,side='left')
            b=np.searchsorted(bars,scheduled_end.value,side='left')
            if side>0:
                hit=np.flatnonzero(bid_low[a:b]<=sl_price)
            else:
                hit=np.flatnonzero(ask_hi[a:b]>=sl_price)
            if len(hit)==0:raise AssertionError('Expected SL hit missing')
            # Intrabar SL time is unknown. Use end of M5 stop-bar (latest
            # plausible hit), a conservative overlap upper bound.
            end=min(scheduled_end,m5.index[a+int(hit[0])]+pd.Timedelta(minutes=5))
        if not (end>start):raise AssertionError('Nonpositive trade interval')
        records.append({
            'symbol':c['symbol'],'tf':c['tf'],'family':c['family'],
            'orientation':c['orientation'],'regime':c['regime'],
            'side':'LONG' if side>0 else 'SHORT',
            'start_utc':start.isoformat(),
            'end_upper_bound_utc':end.isoformat(),
            'exit_is_stop':bool(data['stopped'][j]),
            'sl_price':round(sl_price,6),
            'stop_distance_percent':round(float(data['stop_fraction'][j])*100,4),
            'gap_past_sl':bool(data['gap'][j]),
            'month':int(base.MONTHS[int(data['month'][j])]),
            'day':int(data['days'][j]),
            'pnl_after_sl_bps':float(data['ret'][j]),
            'pnl_without_sl_bps':float(data['original'][j]),
        })
    return records

def metrics(arr,n_bots):
    pnl=float(sum(x['pnl_after_sl_bps'] for x in arr))/n_bots
    n=len(arr)
    w=sum(x['pnl_after_sl_bps']>EPS for x in arr)
    l=sum(x['pnl_after_sl_bps']<-EPS for x in arr)
    z=n-w-l
    return {'portfolio_bps':round(pnl,6),'trades':n,'wins':w,'losses':l,
            'flat':z,'win_rate_percent':round(100*w/n,3) if n else 0,
            'profitable':pnl>EPS,'wins_gt_losses':w>l,'two_or_more_trades':n>=2,
            'passes_nov_filters':pnl>EPS and w>l and n>=2}

def inside(a,b):
    return (a['start_utc']<b['end_upper_bound_utc'] and
            b['start_utc']<a['end_upper_bound_utc'])

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with SRC.open(encoding='utf-8-sig',newline='') as f:
        raw={r['id']:r for r in csv.DictReader(f)}
    if set(raw)!=set(IDS):raise AssertionError('SL pass list changed '+str(set(raw)))
    components={id:[base.nov.parse_component(p) for p in raw[id]['components'].split(' | ')] for id in IDS}
    store,m5=base.build_source()
    cache={}
    for name in IDS:
        for c in components[name]:
            k=key(c)
            if k not in cache:
                cache[k]=compute_trades(c,store[c['symbol'],c['tf']],m5[c['symbol']])
    print('COMPONENTS',len(cache),flush=True)
    per_component=[]
    trade_rows=[]
    portfolio_report={}
    for name in IDS:
        cs=components[name]
        n_bots=len(cs)
        alltrades=[]
        component_detail=[]
        for c in cs:
            component=cache[key(c)]
            # The same physical EA across multiple portfolios may be duplicated
            # in the trade audit, with portfolio ID; count only once for exposure
            # analysis per distinct AVGO component config.
            for trade in component:
                trade_rows.append({'portfolio_id':name,'component_index':len(component_detail)+1,
                                   'portfolio_weight':1/n_bots,**trade})
            nov=[r for r in component if r['month']==202611]
            historical=[r for r in component if r['month']<=202610]
            y2025=[r for r in component if r['month']//100==2025]
            y2026=[r for r in component if 202601<=r['month']<=202610]
            event=[r for r in nov if r['day'] in EVENT_DAYS]
            normal=[r for r in nov if r['day'] not in EVENT_DAYS]
            summary={
                'component_index':len(component_detail)+1,
                'symbol':c['symbol'],'tf':c['tf'],
                'family':c['family'],'orientation':c['orientation'],
                'regime':c['regime'],
                'entry_window_start_utc':c['hour'],
                'hold_minutes':c['hold'],
                'component_weight':1/n_bots,
                'gross_2025_component_bps':round(sum(x['pnl_after_sl_bps'] for x in y2025),6),
                'gross_2026_JanOct_component_bps':round(sum(x['pnl_after_sl_bps'] for x in y2026),6),
                'gross_Nov_component_bps':round(sum(x['pnl_after_sl_bps'] for x in nov),6),
                'portfolio_contribution_2025_bps':round(sum(x['pnl_after_sl_bps'] for x in y2025)/n_bots,6),
                'portfolio_contribution_2026_JanOct_bps':round(sum(x['pnl_after_sl_bps'] for x in y2026)/n_bots,6),
                'portfolio_contribution_Nov_bps':round(sum(x['pnl_after_sl_bps'] for x in nov)/n_bots,6),
                'nov_trades':len(nov),
                'nov_wins':sum(x['pnl_after_sl_bps']>EPS for x in nov),
                'nov_losses':sum(x['pnl_after_sl_bps']<-EPS for x in nov),
                'nov_stops':sum(x['exit_is_stop'] for x in nov),
                'nov_event_09to12_trades':len(event),
                'nov_event_09to12_contribution_bps':round(sum(x['pnl_after_sl_bps'] for x in event)/n_bots,6),
                'nov_non_event_contribution_bps':round(sum(x['pnl_after_sl_bps'] for x in normal)/n_bots,6),
            }
            component_detail.append(summary)
            per_component.append(dict(portfolio_id=name,**summary))
            alltrades.extend(component)
        full=[r for r in alltrades if r['month']==202611]
        exclude_all=[r for r in full if r['day'] not in EVENT_DAYS]
        exclude_avgo=[r for r in full if not (r['symbol']=='AVGO' and r['day'] in EVENT_DAYS)]
        full_stats=metrics(full,n_bots)
        excl_stats=metrics(exclude_all,n_bots)
        noavgo_stats=metrics(exclude_avgo,n_bots)
        avgo=[r for r in full if r['symbol']=='AVGO']
        other=[r for r in full if r['symbol']!='AVGO']
        byday={str(day):metrics([r for r in full if r['day']==day],n_bots)
               for day in sorted(set(x['day'] for x in full))}
        avgo_byday={str(day):metrics([r for r in avgo if r['day']==day],n_bots)
                   for day in sorted(set(x['day'] for x in avgo))}
        any_event=sum(r['day'] in EVENT_DAYS for r in full)
        # Consistency with the exact SL backtest before attributing contributions.
        r=raw[name]
        for val,field in [(sum(x['portfolio_contribution_2025_bps'] for x in component_detail),'sl_2025_bps'),
                          (sum(x['portfolio_contribution_2026_JanOct_bps'] for x in component_detail),'sl_2026_JanOct_bps'),
                          (full_stats['portfolio_bps'],'sl_nov2026_to_date_bps')]:
            if abs(val-float(r[field]))>.001:
                raise AssertionError(f'Baseline does not match {name}/{field}: {val} vs {r[field]}')
        if (full_stats['trades'],full_stats['wins'],full_stats['losses']) != (
            int(r['sl_nov_trades']),int(r['sl_nov_wins']),int(r['sl_nov_losses'])):
            raise AssertionError('November trade counts mismatch: '+name)
        # Per-period ex-AVGO hypothetical: remaining EAs are renormalized
        # equally. It differs from simply subtracting AVGO contribution.
        left=[c for c in component_detail if c['symbol']!='AVGO']
        hypothetical={
           period:round(sum(c[rawname] for c in left)/len(left),6) if left else None
           for period,rawname in (
               ('2025_bps','gross_2025_component_bps'),
               ('2026_JanOct_bps','gross_2026_JanOct_component_bps'),
               ('nov_to_date_bps','gross_Nov_component_bps'))}
        if left:
            hypothetical['nov_remaining_wins']=sum(c['nov_wins'] for c in left)
            hypothetical['nov_remaining_losses']=sum(c['nov_losses'] for c in left)
            hypothetical['nov_remaining_trades']=sum(c['nov_trades'] for c in left)
        component_report={
            'portfolio_id':name,'original_number_of_bots':n_bots,
            'baseline':full_stats,
            'exclusion_09to12_all_assets':excl_stats,
            'exclusion_09to12_only_avgo_trades':noavgo_stats,
            'event_trades_all_assets':any_event,
            'event_profit_contribution_bps':round(full_stats['portfolio_bps']-excl_stats['portfolio_bps'],6),
            'event_profit_fraction_of_baseline_percent':round(
                100*(full_stats['portfolio_bps']-excl_stats['portfolio_bps'])/full_stats['portfolio_bps'],3)
                if abs(full_stats['portfolio_bps'])>EPS else None,
            'nov_component_avgo_contribution_bps':round(sum(r['portfolio_contribution_Nov_bps'] for r in component_detail if r['symbol']=='AVGO'),6),
            'nov_component_rest_contribution_bps':round(sum(r['portfolio_contribution_Nov_bps'] for r in component_detail if r['symbol']!='AVGO'),6),
            'nov_avgo_trades':len(avgo),
            'nov_non_avgo_trades':len(other),
            'hypothetical_remove_avgo_and_reweight_other_bots':hypothetical,
            'components':component_detail,
            'nov_daily_portfolio_bps':byday,
            'nov_daily_AVGO_bps':avgo_byday,
        }
        portfolio_report[name]=component_report
        print('PORTFOLIO',name,full_stats,'EX_EVENT',excl_stats,flush=True)
    # All unique AVGO bots for the 3 actual portfolios, unlike repeated
    # count across portfolios. Map entry and time-in-position overlaps.
    avgo_configs={name:next(c for c in components[name] if c['symbol']=='AVGO') for name in IDS}
    avgo_trades={name:cache[key(c)] for name,c in avgo_configs.items()}
    pairs={}
    collisions=[]
    for p,q in itertools.combinations(IDS,2):
        pair=[]
        for a in avgo_trades[p]:
            for b in avgo_trades[q]:
                if a['day']!=b['day']:continue
                if inside(a,b):
                    pair.append({
                        'pair':p+'|'+q,
                        'day':a['day'],
                        'both_sides':a['side']+'/'+b['side'],
                        'same_direction':a['side']==b['side'],
                        'entry_time_A':a['start_utc'],
                        'entry_time_B':b['start_utc'],
                        'exit_upper_bound_A':a['end_upper_bound_utc'],
                        'exit_upper_bound_B':b['end_upper_bound_utc'],
                        'pnl_A_bps':round(a['pnl_after_sl_bps'],6),
                        'pnl_B_bps':round(b['pnl_after_sl_bps'],6),
                        'Nov2026':a['month']==202611
                    })
        collisions.extend(pair)
        novpairs=[r for r in pair if r['Nov2026']]
        pairs[p+' | '+q]={
            'overlapping_intervals_all_dates':len(pair),
            'overlap_same_direction_all_dates':sum(r['same_direction'] for r in pair),
            'overlap_opposite_direction_all_dates':sum(not r['same_direction'] for r in pair),
            'overlapping_intervals_nov_to_date':len(novpairs),
            'overlap_same_direction_nov_to_date':sum(r['same_direction'] for r in novpairs),
            'overlap_opposite_direction_nov_to_date':sum(not r['same_direction'] for r in novpairs),
            'overlap_dates_nov_to_date':sorted(set(r['day'] for r in novpairs)),
            'sample_nov_to_date':novpairs[:20],
            'sample_recent_all':pair[-10:],
        }
    tri=[]
    for a in avgo_trades[IDS[0]]:
        matches1=[b for b in avgo_trades[IDS[1]] if a['day']==b['day'] and inside(a,b)]
        matches2=[c for c in avgo_trades[IDS[2]] if a['day']==c['day'] and inside(a,c)]
        for b in matches1:
            for c in matches2:
                # every interval must share one simultaneous M5 time span,
                # pairwise overlap on the same day is not sufficient by itself.
                st=max(a['start_utc'],b['start_utc'],c['start_utc'])
                en=min(a['end_upper_bound_utc'],b['end_upper_bound_utc'],c['end_upper_bound_utc'])
                if st<en:
                    tri.append({'day':a['day'],
                                'simultaneous_upper_bound_start_utc':st,
                                'simultaneous_upper_bound_end_utc':en,
                                'sides':[a['side'],b['side'],c['side']],
                                'all_same_side':a['side']==b['side']==c['side'],
                                'Nov2026':a['month']==202611})
    triples_nov=[x for x in tri if x['Nov2026']]
    novdays={name:sum(r['month']==202611 for r in avgo_trades[name]) for name in IDS}
    report={
      'version':'V22-AVGO-RISK-ATTRIBUTION-NEWS-EXCLUSION',
      'date_of_analysis':datetime.now(timezone.utc).isoformat(),
      'original_backtest_period':'2025-01-01 through 2026-10-31 plus 2026-11-01 to 2026-11-12 19:55 UTC',
      'november_partial':True,
      'source':'Original V22 strategy signals + mandatory ATR SL + Exness Bid/Ask M5 exit simulations',
      'basis_points_explainer':'Component raw bps sums are not dollars or account ROI; portfolio bps is arithmetic mean per EA component with equal notionals',
      'news_exclusion_definition':'Skip new entries on UTC calendar dates 2026-11-09,10,11,12 for all symbols; keep historical candle signals unchanged; no trade opened on excluded day. Only November 2-6 remains in observed sample.',
      'avgo_only_exclusion_definition':'Only skip AVGO EA new entries on excluded dates; non-AVGO entries on dates continue.',
      'overlap_definition':'Both AVGO EA positions simultaneously open based on signal timestamps and M5 bar exit timing. Since exact stop hit is unknown within M5, exit time upper-bound is end of first M5 stop bar, and some borderline overlaps may be false positives.',
      'no_live_trading_authorization':'No proven fills, commission not included; event filter is hindsight and not a forward-tradable news classifier.',
      'portfolios':portfolio_report,
      'avgo_concurrent_risk':{
          'unique_avgo_components_in_three_portfolios':len(set(key(c) for c in avgo_configs.values())),
          'avgo_component_specs':{name:avgo_configs[name] for name in IDS},
          'avgo_total_trades_nov_to_date':novdays,
          'pairwise':pairs,
          'triple_concurrent_all_dates':len(tri),
          'triple_same_direction_all_dates':sum(r['all_same_side'] for r in tri),
          'triple_mixed_direction_all_dates':sum(not r['all_same_side'] for r in tri),
          'triple_concurrent_nov_to_date':len(triples_nov),
          'triple_same_direction_nov_to_date':sum(r['all_same_side'] for r in triples_nov),
          'triple_mixed_direction_nov_to_date':sum(not r['all_same_side'] for r in triples_nov),
          'triple_overlap_samples_nov':triples_nov[:30],
          'triple_overlap_recent_history':tri[-15:]
      }
    }
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def tocsv(filename,rows):
        if not rows:return
        fields=list(rows[0])
        with (OUT/filename).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
            writer.writeheader();writer.writerows(rows)
    tocsv('per_component_pnl.csv',per_component)
    tocsv('all_trades_with_SL_entry_exit.csv',trade_rows)
    tocsv('AVGO_concurrent_positions.csv',collisions)
    tocsv('AVGO_triple_concurrent_positions.csv',tri)
    print('FINAL',json.dumps({
        'event':{name:{'full':report['portfolios'][name]['baseline'],
                       'exclude_all':report['portfolios'][name]['exclusion_09to12_all_assets'],
                       'avgo_share':report['portfolios'][name]['nov_component_avgo_contribution_bps']}
                 for name in IDS},
        'overlap_pairs':{k:{j:v[j] for j in ('overlapping_intervals_all_dates',
             'overlap_same_direction_all_dates','overlap_opposite_direction_all_dates',
             'overlapping_intervals_nov_to_date')}
            for k,v in pairs.items()},
        'overlap_triple':len(tri),'overlap_triple_nov':len(triples_nov),
    },ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
