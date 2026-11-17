#!/usr/bin/env python3
"""M5 signal, 15/30/60-min max hold, fixed brackets, nonoverlapping orders.
Research-only preregistered rescue extension: Aug+Sep model selection; October untouched holdout;
November partial secondary. Uses prior completed M5 bars for signals, next bars only for outcomes.
"""
import csv, io, itertools, json, zipfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from m5_directional_rescue_2026 import SYMBOLS, MONTHS, SIGNALS, SESSIONS, SPREADS, get_features, load, side_pnl, sign, NOISE_COST, newstat, update, row_month

OUT=Path('results/m5_longer_hold_2026')
HORIZONS=(3,6,12)  # number of M5 bars = 15,30,60 minutes
BRACKETS=((0.50,0.50),(0.80,0.80),(1.00,1.00),(1.50,1.00),(2.00,2.00))
CONFIGS=list(itertools.product(SIGNALS,SESSIONS,SPREADS,BRACKETS,HORIZONS))
MONTH_TRAIN=('2026-08','2026-09')

def finish_position(sym,bars,start,side,tp,sl,hold):
    enter=bars[start][1]
    entry_price=enter[1] if side==1 else enter[0]
    conversion=1000.0/((enter[0]+enter[1])/2) if sym=='USDJPY' else 1000.0
    exit_idx=start
    for j in range(start,min(start+hold,len(bars))):
        timestamp,quote=bars[j]
        # Refrain from crossing month boundary for clean August+September holdout.
        if timestamp[:7]!=bars[start][0][:7]: break
        if j>start:
            elapsed=(datetime.fromisoformat(timestamp)-datetime.fromisoformat(bars[j-1][0])).total_seconds()
            if elapsed>300:break  # close on the last available bar before a market break
        if side==1:
            worst=(quote[4]-entry_price)*conversion
            best=(quote[2]-entry_price)*conversion
            atclose=(quote[6]-entry_price)*conversion
        else:
            worst=(entry_price-quote[3])*conversion
            best=(entry_price-quote[5])*conversion
            atclose=(entry_price-quote[7])*conversion
        exit_idx=j
        if worst<=-sl:return -sl,'SL',best>=tp,exit_idx
        if best>=tp:return tp,'TP',False,exit_idx
        pnl=atclose
    return pnl,'CLOSE',False,exit_idx

def prepare(sym):
    rows=load(sym)
    vals=[bar for _,bar in rows]
    e20=e60=None
    feats=[]
    for i,(ts,bar) in enumerate(rows):
        midclose=(bar[6]+bar[7])/2
        if e20 is None:e20=e60=midclose
        features=get_features(vals,i,e20,e60)
        if i>0 and (datetime.fromisoformat(ts)-datetime.fromisoformat(rows[i-1][0])).total_seconds()>900:
            features={}
        feats.append(features)
        e20+=(midclose-e20)*(2/21)
        e60+=(midclose-e60)*(2/61)
    return rows,feats

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    month_rows=[]
    coverage={}
    for sym in SYMBOLS:
        bars,features=prepare(sym)
        coverage[sym]=dict(bars=sum(ts[:7] in MONTHS for ts,_ in bars),configs=len(CONFIGS))
        for sig,sess,cap,(tp,sl),hold in CONFIGS:
            # Every candidate starts from identical history, no overlap per candidate.
            i=0
            buckets=defaultdict(newstat)
            while i<len(bars):
                ts,quote=bars[i]
                mo=ts[:7]
                if mo not in MONTHS:
                    i+=1;continue
                side=features[i].get(sig,0)
                if not side:
                    i+=1;continue
                hour=int(ts[11:13])
                if sess=='utc_06_20' and not (6<=hour<20):
                    i+=1;continue
                conversion=1000/((quote[0]+quote[1])/2) if sym=='USDJPY' else 1000
                spread=(quote[1]-quote[0])*conversion
                if cap is not None and spread>cap+1e-12:
                    i+=1;continue
                pnl,why,amb,exit_idx=finish_position(sym,bars,i,side,tp,sl,hold)
                update(buckets[mo],pnl,why,amb)
                i=exit_idx+1
            for mo in MONTHS:
                r=row_month(sym,sig,sess,cap,tp,sl,mo,buckets[mo])
                r['hold_bars']=hold
                month_rows.append(r)
    indexed={(r['symbol'],r['method'],r['session'],r['max_spread_usd'],r['tp_usd'],r['sl_usd'],r['hold_bars'],r['month']):r for r in month_rows}
    selections=[]
    count={}
    for sym in SYMBOLS:
        eligible=[]
        positive_both=0;positive_sum=0;positive_stress=0
        for sig,sess,cap,(tp,sl),hold in CONFIGS:
            key=(sym,sig,sess,cap,tp,sl,hold)
            a=indexed[(*key,'2026-08')]
            b=indexed[(*key,'2026-09')]
            if min(a['trades'],b['trades'])<40: continue
            tr=a['pnl_usd']+b['pnl_usd']
            stressed=a['stress_pnl_007']+b['stress_pnl_007']
            positive_both+=(a['pnl_usd']>0 and b['pnl_usd']>0)
            positive_sum+=(tr>0)
            positive_stress+=(stressed>0)
            eligible.append((stressed,tr,key,a,b))
        eligible.sort(key=lambda x:(-x[0],-x[1],str(x[2])))
        count[sym]=dict(candidates=len(CONFIGS),eligible_count=len(eligible),train_positive_sum=positive_sum,
                        train_positive_both=positive_both,train_positive_after_cost_stress=positive_stress)
        for stressed,tr,key,a,b in eligible[:7]:
            oc=indexed[(*key,'2026-10')]
            nv=indexed[(*key,'2026-11')]
            selections.append(dict(symbol=sym,method=key[1],session=key[2],spread_cap=key[3],
                                   tp=key[4],sl=key[5],max_hold_mins=key[6]*5,
                                   aug_pnl=a['pnl_usd'],sep_pnl=b['pnl_usd'],
                                   train_pnl=round(tr,5),train_stress=round(stressed,5),
                                   oct_pnl=oc['pnl_usd'],oct_trades=oc['trades'],oct_stress=oc['stress_pnl_007'],
                                   nov_partial_pnl=nv['pnl_usd'],nov_partial_trades=nv['trades'],
                                   train_count=a['trades']+b['trades']))
    with (OUT/'all_configs_monthly.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(month_rows[0]))
        writer.writeheader();writer.writerows(month_rows)
    (OUT/'summary.json').write_text(json.dumps(dict(
        design=dict(candle='M5',max_holding_minutes=(15,30,60),lot=0.01,
                    stop_takeprofit='fixed per order USD, execution bid/ask',
                    samebar_ambiguity='SL-first',concurrent_orders='none',
                    training='August September 2026',holdout='October 2026',
                    nov_partial='2026-11-01 through available archive 2026-11-10',
                    spread='Bid Ask embedded',extra_cost_stress_usd=NOISE_COST,
                    USDJPY_conversion='entry mid approximate',
                    source='GitHub data/v17_exness_2026'),
        counts=count,coverage=coverage,top7_training_selections=selections),indent=2),encoding='utf-8')
    print('LONGER_HOLD_RESULTS_START')
    print(json.dumps(dict(counts=count,top7=selections),ensure_ascii=False))
    print('LONGER_HOLD_RESULTS_END')

if __name__=='__main__':
    main()
