#!/usr/bin/env python3
"""Predeclared exploratory rescue screen, Exness archived M5 bid/ask, USD account, lot 0.01.
Train = Aug-Sep 2026. Holdout = Oct 2026; Nov 1-10 is secondary confirmation.
Frozen single-candle entry, fixed TP and SL, EOC. Research only, no trading calls.
"""
import csv, io, json, zipfile, itertools
from collections import defaultdict
from pathlib import Path

OUT=Path('results/m5_directional_rescue_2026')
SYMBOLS=('GBPUSD','EURUSD','USDJPY')
MONTHS=('2026-08','2026-09','2026-10','2026-11')
TRAIN=('2026-08','2026-09')
SIGNALS=('follow_prev','fade_prev','follow_3','fade_3','breakout_8','ema_trend','ema_pullback')
SESSIONS=('all','utc_06_20')
SPREADS=(None,0.10)  # USD per 0.01 lot, at candle entry
BRACKETS=((0.30,0.30),(0.50,0.50),(0.80,0.80),(1.00,1.00),(1.00,0.50),(0.50,10.00))
CONFIGS=list(itertools.product(SIGNALS,SESSIONS,SPREADS,BRACKETS))
HEDGE_CONFIGS=list(itertools.product(SESSIONS,SPREADS,((0.50,10.00),(0.50,0.50))))
FIELDS=('bid_open','ask_open','bid_high','ask_high','bid_low','ask_low','bid_close','ask_close')
NOISE_COST=0.07 # hypothetical additional roundtrip cost per 0.01 lot; NOT a measured Exness fee
def newstat():
    return dict(trades=0,wins=0,losses=0,tp_exits=0,sl_exits=0,close_exits=0,
                ambiguous=0,gross_profit=0.,gross_loss=0.,pnl=0.,peak=0.,equity=0.,max_dd=0.)
def side_pnl(sym,side,bar,tp,sl):
    bid_o,ask_o,bid_h,ask_h,bid_l,ask_l,bid_c,ask_c=bar
    mid=(bid_o+ask_o)*0.5
    usdperprice=1000.0/mid if sym=='USDJPY' else 1000.0
    if side==1:
        entry=ask_o
        worst=(bid_l-entry)*usdperprice
        best=(bid_h-entry)*usdperprice
        close=(bid_c-entry)*usdperprice
    else:
        entry=bid_o
        worst=(entry-ask_h)*usdperprice
        best=(entry-ask_l)*usdperprice
        close=(entry-ask_c)*usdperprice
    if worst<=-sl:
        return -sl,'SL',best>=tp
    if best>=tp:
        return tp,'TP',False
    return close,'CLOSE',False

def sign(x): return (x>1e-12)-(x< -1e-12)

def update(s,p,reason,amb):
    s['trades']+=1
    s['wins']+=(p>1e-8);s['losses']+=(p< -1e-8)
    s['tp_exits']+=(reason=='TP');s['sl_exits']+=(reason=='SL')
    s['close_exits']+=(reason=='CLOSE');s['ambiguous']+=bool(amb)
    s['gross_profit']+=max(0.,p);s['gross_loss']+=min(0.,p)
    s['pnl']+=p
    s['equity']+=p;s['peak']=max(s['peak'],s['equity'])
    s['max_dd']=max(s['max_dd'],s['peak']-s['equity'])

def row_month(sym,method,session,spread,tp,sl,month,s):
    n=s['trades']
    return dict(symbol=sym,method=method,session=session,max_spread_usd=spread,
                tp_usd=tp,sl_usd=sl,month=month,trades=n,wins=s['wins'],losses=s['losses'],
                win_pct=round(100*s['wins']/n,3) if n else 0.,
                tp_exits=s['tp_exits'],sl_exits=s['sl_exits'],close_exits=s['close_exits'],
                ambiguous=s['ambiguous'],pnl_usd=round(s['pnl'],5),
                stress_pnl_007=round(s['pnl']-NOISE_COST*n,5),
                pf=round(s['gross_profit']/-s['gross_loss'],4) if s['gross_loss'] else None,
                max_drawdown_usd=round(s['max_dd'],4))

def get_features(bs,i,e20,e60):
    if i<10: return {}
    prev=bs[i-1];older=bs[i-4]
    pco=(prev[0]+prev[1])*0.5
    pcl=(prev[6]+prev[7])*0.5
    oldclose=(older[6]+older[7])*0.5
    dir1=sign(pcl-pco)
    dir3=sign(pcl-oldclose)
    history=bs[i-9:i-1]
    breakout=1 if pcl>max((b[2]+b[3])*0.5 for b in history) else (-1 if pcl<min((b[4]+b[5])*0.5 for b in history) else 0)
    trend=1 if pcl>e20 and e20>e60 else (-1 if pcl<e20 and e20<e60 else 0)
    pullback=(1 if e20>e60 and dir1==-1 and pcl>e60 else
              -1 if e20<e60 and dir1==1 and pcl<e60 else 0)
    return dict(follow_prev=dir1,fade_prev=-dir1,follow_3=dir3,fade_3=-dir3,
                breakout_8=breakout,ema_trend=trend,ema_pullback=pullback)

def load(sym):
    zpath=Path(f'data/v17_exness_2026/{sym}_2026_UTC_7TF.zip')
    with zipfile.ZipFile(zpath) as z:
        with z.open(f'{sym}_M5_2026_UTC.csv') as stream:
            rdr=csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8'))
            return [(r['timestamp_utc'],tuple(float(r[c]) for c in FIELDS))
                    for r in rdr if r['timestamp_utc']>='2026-07-15']

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    directional=defaultdict(newstat)
    hedged=defaultdict(newstat)
    coverage={}
    for sym in SYMBOLS:
        bars=load(sym); vals=[b for _,b in bars]
        e20=e60=None
        scanned=0;highspread=0
        for i,(ts,bar) in enumerate(bars):
            midclose=(bar[6]+bar[7])*0.5
            if e20 is None: e20=e60=midclose
            month=ts[:7]
            if month in MONTHS and i>=10:
                scanned+=1
                hour=int(ts[11:13])
                price_conversion=1000./((bar[0]+bar[1])/2) if sym=='USDJPY' else 1000.
                spread=(bar[1]-bar[0])*price_conversion
                highspread+=(spread>0.1)
                features=get_features(vals,i,e20,e60)
                # Do not rely on stale candle momentum after an extended market gap.
                from datetime import datetime
                latest=datetime.fromisoformat(ts.replace('Z','+00:00'))
                last=datetime.fromisoformat(bars[i-1][0].replace('Z','+00:00'))
                if (latest-last).total_seconds()>900:
                    features={}
                # Cache current-bar execution outcomes; only entry signals use prior candles.
                execution={}
                for session,cap in itertools.product(SESSIONS,SPREADS):
                    if session=='utc_06_20' and not (6<=hour<20):continue
                    if cap is not None and spread>cap+1e-12:continue
                    for bracket in BRACKETS:
                        for sig in SIGNALS:
                            side=features.get(sig,0)
                            if not side: continue
                            key=(sym,sig,session,cap,bracket,month)
                            exkey=(side,bracket)
                            if exkey not in execution:
                                execution[exkey]=side_pnl(sym,side,bar,*bracket)
                            p,reason,amb=execution[exkey]
                            update(directional[key],p,reason,amb)
                    # Control: continuing two-sided hedge, selectively entered.
                    for bracket in ((0.50,10.00),(0.50,0.50)):
                        for side in (1,-1):
                            exkey=(side,bracket)
                            if exkey not in execution:
                                execution[exkey]=side_pnl(sym,side,bar,*bracket)
                            p,reason,amb=execution[exkey]
                            update(hedged[(sym,'both_legs',session,cap,bracket,month)],p,reason,amb)
            e20+=(midclose-e20)*(2/21)
            e60+=(midclose-e60)*(2/61)
        coverage[sym]=dict(scanned=scanned,spread_above_010_share=round(highspread/scanned,3) if scanned else None)
    rows=[]
    for (sym,method,sess,cap,bracket,month),s in directional.items():
        rows.append(row_month(sym,method,sess,cap,*bracket,month,s))
    rows.sort(key=lambda r:(r['symbol'],r['method'],r['session'],str(r['max_spread_usd']),r['tp_usd'],r['sl_usd'],r['month']))
    hedge_rows=[]
    for (sym,method,sess,cap,bracket,month),s in hedged.items():
        hedge_rows.append(row_month(sym,method,sess,cap,*bracket,month,s))
    def write_csv(name,recs):
        with (OUT/name).open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(recs[0]))
            writer.writeheader();writer.writerows(recs)
    write_csv('all_directional_monthly.csv',rows)
    write_csv('hedge_controls_monthly.csv',hedge_rows)
    # Train selection uses ONLY August and September.
    indexed={(r['symbol'],r['method'],r['session'],r['max_spread_usd'],r['tp_usd'],r['sl_usd'],r['month']):r for r in rows}
    picks=[]
    candidates=[]
    counts={}
    for sym in SYMBOLS:
        pool=[]
        n_train_positive=0
        n_both_positive=0
        for sig,sess,cap,(tp,sl) in CONFIGS:
            key=(sym,sig,sess,cap,tp,sl)
            aug=indexed.get((*key,'2026-08'))
            sep=indexed.get((*key,'2026-09'))
            if not aug or not sep or aug['trades']<80 or sep['trades']<80:continue
            n_both_positive+=(aug['pnl_usd']>0 and sep['pnl_usd']>0)
            if aug['pnl_usd']+sep['pnl_usd']>0:n_train_positive+=1
            pool.append((aug['stress_pnl_007']+sep['stress_pnl_007'],
                         aug['pnl_usd']+sep['pnl_usd'],key,aug,sep))
        # Explicitly fixed selection: maximum cost-stressed training PnL; check holdout afterward.
        pool.sort(key=lambda t:(-t[0],-t[1],str(t[2])))
        counts[sym]=dict(qualified_by_frequency=len(pool),train_positive_count=n_train_positive,
                          train_both_months_positive=n_both_positive)
        for score,pnl,key,aug,sep in pool[:5]:
            octr=indexed.get((*key,'2026-10'))
            novr=indexed.get((*key,'2026-11'))
            cand=dict(symbol=sym,method=key[1],session=key[2],spread_cap_usd=key[3],
                      tp_usd=key[4],sl_usd=key[5],
                      aug=aug,sep=sep,oct=octr,nov_partial=novr,
                      train_pnl=round(pnl,4),train_cost_stress=round(score,4),
                      holdout_oct_pnl=octr['pnl_usd'] if octr else None,
                      holdout_oct_cost_stress=octr['stress_pnl_007'] if octr else None,
                      nov_partial_pnl=novr['pnl_usd'] if novr else None)
            candidates.append(cand)
        picks.extend(candidates[-min(5,len(pool)):])
    hedge_summary=[]
    for sym in SYMBOLS:
        for sess,cap,bracket in HEDGE_CONFIGS:
            matching=[r for r in hedge_rows if r['symbol']==sym and r['session']==sess
                     and r['max_spread_usd']==cap and (r['tp_usd'],r['sl_usd'])==bracket]
            hedge_summary.append(dict(symbol=sym,session=sess,spread_cap=cap,tp_usd=bracket[0],sl_usd=bracket[1],
                  monthly={m: next((r['pnl_usd'] for r in matching if r['month']==m),0) for m in MONTHS}))
    payload=dict(assumptions=dict(source='Exness archived Bid/Ask M5; 0.01 lot and USD account',
         sample='Aug + Sep training; October untouched holdout; Nov through Nov 10 partial',
         no_lookahead='All signals from preceding completed candles; EOC within current 5m candle',
         fills='BUY ask open to bid exit, SELL bid open to ask exit, SL priority if ambiguous',
         same_candle='TP or SL intrabar, else EOC; 5m high/low cannot determine intra-candle event order',
         USDJPY='USD conversion approximated by entry midprice',
         cost_stress='Additional hypothetical $0.07 USD per 0.01 lot roundtrip in addition to embedded Bid/Ask spread',
         excluded='Other slippage, financing, broker-specific commissions, partial fills'),coverage=coverage,
         candidate_counts=counts,selected_top5_per_symbol=picks,hedge_controls=hedge_summary)
    (OUT/'summary.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print('RESCUE_REPORT_START')
    print(json.dumps(dict(candidate_counts=counts,coverage=coverage,
        selected=[dict(symbol=p['symbol'],method=p['method'],session=p['session'],spread_cap=p['spread_cap_usd'],
                       tp=p['tp_usd'],sl=p['sl_usd'],train=p['train_pnl'],train_stress=p['train_cost_stress'],
                       oct=p['holdout_oct_pnl'],oct_stress=p['holdout_oct_cost_stress'],
                       nov=p['nov_partial_pnl'],
                       oct_trades=p['oct']['trades'] if p['oct'] else None) for p in picks],
        hedge_controls=[h for h in hedge_summary if h['session']=='all' and h['spread_cap'] is None])))
    print('RESCUE_REPORT_END')

if __name__=='__main__':
    main()
