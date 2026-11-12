#!/usr/bin/env python3
"""V22: de-duplicate the fixed 47 portfolio candidates by actual order history.

A lower-ranked portfolio is a duplicate ONLY when, compared to an accepted
better portfolio, all are true:
 * >=75% same asset + UTC 2h entry window components (relative to larger list)
 * >=75% common historical trade events (2025 through Oct 2026), relative to larger list
 * >=75% common November 2026 trade events, relative to larger list

Trade event = asset + UTC entry bar timestamp + direction, counted as multiset,
so short/long opposites do not count as duplicates.
Greedy processing in descending simulated November 2026 profit retains the
highest Nov-profit configuration from each duplicate cluster, using secondary
criteria for ties. Does not combine or delete physically trading positions.
"""
import argparse,csv,json,collections
from pathlib import Path
import numpy as np
import pandas as pd
import v22_strategy_screen as bs

HISTORY_MIN=0.75
NOV_MIN=0.75
SLOT_MIN=0.75
EPS=1e-9
TF_MINUTES={key:val[0] for key,val in bs.TFS.items()}
def key_from_text(part):
    p=part.split()
    if len(p)!=8:raise ValueError('unknown component '+part)
    sym,tf,fam,ori,reg,entry,win,hold=p
    h=int(entry[len('entry_'):len('entry_')+2])
    w=int(win.removeprefix('window_').removesuffix('h'))
    minutes=int(hold.removeprefix('hold_').removesuffix('min'))
    if minutes%TF_MINUTES[tf]:raise ValueError('unsupported holding')
    return (sym,tf,fam,ori,reg,h,w,minutes//TF_MINUTES[tf])
def key_from_nov(item):
    return '|'.join(map(str,item))
def make_rows(csvpath):
    with csvpath.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=47:raise ValueError('expected fixed 47 portfolios')
    for r in rows:
        r['legs']=[key_from_text(p) for p in r['components'].split(' | ')]
        if len(r['legs']) not in (4,5):raise ValueError('unexpected number of legs')
        r['slots']=collections.Counter((s[0],s[5],s[6]) for s in r['legs'])
        r['nov_pnl']=float(r['november_net_bps'])
        r['historical_months']=int(r['historical_months_profitable'])
        r['historical_pnl']=float(r['historical_total_bps'])
        r['nov_orders']=int(r['november_orders'])
    return rows

def audit_november(path,all_keys):
    with path.open() as f:records=json.load(f)
    missing={key_from_nov(k) for k in all_keys}-records.keys()
    if missing: raise ValueError('Missing November components: '+str(missing))
    nov={}
    for k in all_keys:
        v=records[key_from_nov(k)]
        trades=collections.Counter((k[0],item['entry_utc'],item['direction']) for item in v['items'])
        if sum(trades.values())!=v['trades']:raise ValueError('November count mismatch')
        nov[k]=trades
    return nov

def historical_orders(root,keys):
    byasset=collections.defaultdict(list)
    for k in keys:byasset[k[0]].append(k)
    output={}
    for sym in byasset:
        m5=bs.load(root,sym,'M5')
        lagday,lagweek=bs.daily_weekly_directions(m5)
        bytf=collections.defaultdict(list)
        for key in byasset[sym]:bytf[key[1]].append(key)
        for tf,params in bytf.items():
            df=bs.load(root,sym,tf)
            ords,monthid,minutes,day,week,hdict=bs.prepare(df,tf,lagday,lagweek)
            signallib=dict(bs.signal_library(df,day,week))
            ts=df.index
            for key in params:
                _,_,fam,orientation,regime,hour,window,holdbars=key
                base=signallib[fam]
                if orientation=='FOLLOW':side=base
                elif orientation=='FADE':side=-base
                elif orientation=='LONG_ONLY':side=np.where(base>0,1,0)
                elif orientation=='SHORT_ONLY':side=np.where(base<0,-1,0)
                else:raise ValueError('unknown orientation')
                valid=hdict[holdbars][0]
                allow=(side!=0)
                if regime=='D1_ALIGN':allow=allow&(side==day)
                elif regime=='W1_ALIGN':allow=allow&(side==week)
                elif regime!='ANY':raise ValueError('unknown regime')
                chosen=np.flatnonzero(allow&valid&(minutes>=hour*60)&
                                       (minutes<min((hour+window)*60,1440)))
                if len(chosen):
                    first=np.r_[True,ords[chosen[1:]]!=ords[chosen[:-1]]]
                    chosen=chosen[first]
                output[key]=collections.Counter((sym,ts[i].isoformat(),'long' if side[i]>0 else 'short')
                    for i in chosen)
            print('HIST',sym,tf,'nlegs',len(params),flush=True)
    if len(output)!=len(keys):raise AssertionError('missing unique historical EA')
    return output

def merged_orders(legs,order_lookup):
    counter=collections.Counter()
    for k in legs:counter.update(order_lookup[k])
    return counter

def common_fraction(a,b):
    # Symmetric containment: fraction of the larger full configuration matched
    largest=max(sum(a.values()),sum(b.values()))
    if largest==0:return 0.,0,0
    shared=sum((a&b).values())
    return shared/largest,shared,largest

def rank(r):
    return (-r['nov_pnl'],-r['historical_months'],-r['historical_pnl'],-r['nov_orders'],r['postfilter_id'])

def brief(r):
    return {k:r[k] for k in ('postfilter_id','final_id','symbols','category','historical_months_profitable',
                              'november_net_bps','november_orders','historical_total_bps','historical_total_orders',
                              'components')}

def run(root,src,novpath,out):
    out.mkdir(parents=True,exist_ok=True)
    rows=make_rows(src)
    keys=set(k for r in rows for k in r['legs'])
    november=audit_november(novpath,keys)
    history=historical_orders(root,keys)
    for r in rows:
        r['nov_events']=merged_orders(r['legs'],november)
        r['hist_events']=merged_orders(r['legs'],history)
        if sum(r['nov_events'].values())!=r['nov_orders']:
            raise ValueError(f"Nov trade count mismatch {r['postfilter_id']}")
        historical_leg_count=sum(sum(history[k].values()) for k in r['legs'])
        if historical_leg_count!=int(r['historical_total_orders']):
            raise ValueError(f"Hist trade count mismatch {r['postfilter_id']}, recorded={r['historical_total_orders']}, actual={historical_leg_count}")
    rows.sort(key=rank)
    accepted=[]
    dropped=[]
    stats={'pairs_compared':0,'duplicates_rejected':0,'max_history_overlap':0.,'max_nov_overlap':0.}
    overlap_pairs=[]
    for candidate in rows:
        matches=[]
        for better in accepted:
            stats['pairs_compared']+=1
            slot_fraction,shared_slots,maxslots=common_fraction(candidate['slots'],better['slots'])
            if slot_fraction+EPS <SLOT_MIN:continue
            hist_fraction,shared_hist,maxhist=common_fraction(candidate['hist_events'],better['hist_events'])
            stats['max_history_overlap']=max(stats['max_history_overlap'],hist_fraction)
            if hist_fraction+EPS < HISTORY_MIN:continue
            nov_fraction,shared_nov,maxnov=common_fraction(candidate['nov_events'],better['nov_events'])
            stats['max_nov_overlap']=max(stats['max_nov_overlap'],nov_fraction)
            if nov_fraction+EPS < NOV_MIN:continue
            matches.append((better,slot_fraction,hist_fraction,nov_fraction,
                            shared_slots,maxslots,shared_hist,maxhist,shared_nov,maxnov))
        if matches:
            # A removed candidate is attached to the best-performing similar survivor.
            best=min(matches,key=lambda x:rank(x[0]))
            better,slot,hist,nov,sn,sm,hn,hm,nn,nm=best
            record=dict(**brief(candidate),removed_as_duplicate_of=better['postfilter_id'],
              similar_survivor_november_bps=better['nov_pnl'],
              same_symbol_entry_window_ratio=round(slot,5),
              shared_symbol_entry_windows=f'{sn}/{sm}',
              same_historical_order_ratio=round(hist,5),
              matching_historical_orders=f'{hn}/{hm}',
              same_november_order_ratio=round(nov,5),
              matching_november_orders=f'{nn}/{nm}')
            dropped.append(record)
            stats['duplicates_rejected']+=1
        else:
            accepted.append(candidate)

    saved=[]
    for i,r in enumerate(accepted,1):
        q=dict(**brief(r))
        q['deduplicated_id']=f'V22-U{i:03d}'
        q['historical_orders_audit']=sum(r['hist_events'].values())
        q['november_orders_audit']=sum(r['nov_events'].values())
        saved.append(q)
    fields=['deduplicated_id','postfilter_id','final_id','symbols','category',
        'historical_months_profitable','november_net_bps','november_orders',
        'historical_total_bps','historical_total_orders','historical_orders_audit',
        'november_orders_audit','components']
    with (out/'v22_unique_strategies.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(saved)
    with (out/'v22_removed_similar_strategies.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dropped[0]) if dropped else fields)
        w.writeheader();w.writerows(dropped)
    if len(saved)+len(dropped)!=47:raise AssertionError('did not account for all 47')
    threshold_report=dict(version='V22-STRUCTURE-SCHEDULE-DEDUPE',
        interpretation='Two stock EA portfolios treated as near-duplicates ONLY if >=75% of asset+UTC entry windows match and >=75% executed trade events match both over 2025-Oct2026 and November 2026. Events are symbol+timestamp+direction with multiplicity.',
        ranking='Keep higher November 2026 (partial) modeled net bps; then historical profitable-month count, historical bps, November order count, fixed ID. Pairwise greedy against already accepted strategy.',
        history='2025-01-01 through 2026-10-31 UTC',
        partial_november='2026-11-01 through 2026-11-11T20:40:00Z (last observed common quote)',
        thresholds=dict(same_symbol_utc_window=SLOT_MIN,history_trades=HISTORY_MIN,
                        november_trades=NOV_MIN),
        original=47,remaining=len(saved),removed=len(dropped),
        source_unique_eas=len(keys),verified_historical_legs=len(history),
        original_categories=dict(quad=sum(r['category']=='quad' for r in rows),quint=sum(r['category']=='quint' for r in rows)),
        remaining_categories=dict(quad=sum(r['category']=='quad' for r in saved),quint=sum(r['category']=='quint' for r in saved)),
        original_months=dict((str(x),sum(r['historical_months']==x for r in rows)) for x in (17,18,19)),
        remaining_months=dict((str(x),sum(int(r['historical_months_profitable'])==x for r in saved)) for x in (17,18,19)),
        counts=stats,
        kept=saved,
        removed_groups=dropped,
        note='Behavioral similarity threshold is a documented research choice, not proof of statistical independence. Same sessions or assets alone do not trigger removal. Month November is incomplete; rankings may change.',
        report_created_at_utc=pd.Timestamp.now(tz='UTC').isoformat())
    (out/'v22_dedup_summary.json').write_text(json.dumps(threshold_report,ensure_ascii=False,indent=2)+'\n')
    print('DEDUPE_RESULT',json.dumps({k:threshold_report[k] for k in
          ('original','remaining','removed','source_unique_eas','remaining_categories','remaining_months','counts')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('data/v22_exness'))
    p.add_argument('--selection',type=Path,default=Path('results/v22_november_2026/v22_nov_after_profit_trade_filter_47.csv'))
    p.add_argument('--nov-trades',type=Path,default=Path('results/v22_november_2026/v22_nov2026_component_trades.json'))
    p.add_argument('--out',type=Path,default=Path('results/v22_november_2026/deduplicated'))
    a=p.parse_args()
    run(a.data,a.selection,a.nov_trades,a.out)
