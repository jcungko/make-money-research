#!/usr/bin/env python3
"""V22: exhaustive, deterministic, read-only strategy screening on Exness CFD Bid/Ask.
Output is exploratory in-sample research, never live-trading authorization.
"""
import argparse, json, zipfile, collections, itertools
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

SYMBOLS=('NVDA','AMD','AVGO','XOM','GOOGL')
TFS={'M5':(5,[6,12,24]),'M15':(15,[2,4,8]),'M30':(30,[1,2,4]),'H1':(60,[1,2,3]),'H4':(240,[1])}
MONTHS=[y*100+m for y in (2025,2026) for m in range(1,13 if y==2025 else 11)]
MONTH_ID={m:i for i,m in enumerate(MONTHS)}
SESSIONS=(12,14,15,16,17,18)
SLIPPAGE_ROUND_TRIP_BPS=2.0  # assumed beyond observed bid-ask; no overnight holds
MIN_TRADES_EACH_MONTH=3

def read(root,symbol,year,tf):
    source=root/str(year)/symbol/f'{symbol}_{year}_UTC_7TF.zip'
    with zipfile.ZipFile(source) as z:
        with z.open(f'{symbol}_{tf}_{year}_UTC.csv') as f:
            d=pd.read_csv(f,parse_dates=['timestamp_utc'],index_col='timestamp_utc')
    d.index=pd.DatetimeIndex(d.index).tz_convert('UTC')
    return d

def load(root,symbol,tf):
    d=pd.concat([read(root,symbol,y,tf) for y in (2025,2026)]).sort_index()
    if d.index.has_duplicates:
        raise ValueError(f'{symbol}/{tf}: duplicate timestamps')
    if (d['bid_close']>d['ask_close']).any():
        raise ValueError(f'{symbol}/{tf}: crossed closes')
    return d

def signal_library(df,day_previous,week_previous):
    op=(df.bid_open+df.ask_open)*0.5
    cl=(df.bid_close+df.ask_close)*0.5
    hi=(df.bid_high+df.ask_high)*0.5
    lo=(df.bid_low+df.ask_low)*0.5
    past=cl.shift(1)
    signals=[]
    def add(name,s):
        v=np.asarray(s,dtype='float64')
        v=np.where(np.isfinite(v),np.sign(v),0).astype('int8')
        signals.append((name,v))
    add('PREVIOUS_CANDLE',cl.shift(1)-op.shift(1))
    for n in (2,4,8,16,32):
        add(f'MOMENTUM_{n}',past-cl.shift(n+1))
    for n in (8,16,32,64):
        add(f'SMA_{n}',past-past.rolling(n,min_periods=n).mean())
    for n in (8,21,55):
        add(f'EMA_{n}',past-past.ewm(span=n,adjust=False,min_periods=n).mean())
    for n in (16,32,64):
        avg=past.rolling(n,min_periods=n).mean()
        std=past.rolling(n,min_periods=n).std()
        z=(past-avg)/std.replace(0,np.nan)
        for th in (0.5,1.0):
            add(f'ZSCORE_{n}_{str(th).replace(".","p")}',np.where(abs(z)>=th,z,0))
    dif=cl.diff()
    for n in (7,14,28):
        gain=dif.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        loss=(-dif.clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        rsi=100-100/(1+gain/loss.replace(0,np.nan))
        rsi=rsi.shift(1)
        for th in (30,40):
            raw=np.where(rsi< th,-1,np.where(rsi>100-th,1,0))
            add(f'RSI_{n}_{th}',raw)
    for n in (4,8,16):
        maxprior=hi.shift(2).rolling(n,min_periods=n).max()
        minprior=lo.shift(2).rolling(n,min_periods=n).min()
        raw=np.where(past>maxprior,1,np.where(past<minprior,-1,0))
        add(f'BREAKOUT_{n}',raw)
    add('DAILY_PREVIOUS',day_previous)
    add('WEEKLY_PREVIOUS',week_previous)
    return signals

def daily_weekly_directions(m5):
    days=m5.index.normalize()
    day_bars=m5.groupby(days).agg(bid_open=('bid_open','first'),bid_close=('bid_close','last'))
    day_sign=np.sign(day_bars.bid_close-day_bars.bid_open)
    week_starts=days-pd.to_timedelta(m5.index.dayofweek,unit='D')
    week_bars=m5.groupby(week_starts).agg(bid_open=('bid_open','first'),bid_close=('bid_close','last'))
    week_sign=np.sign(week_bars.bid_close-week_bars.bid_open)
    return day_sign.shift(1),week_sign.shift(1)

def prepare(df,tf,daysig,weeksig):
    idx=df.index
    n=len(df)
    ordinal=(idx.year*10000+idx.month*100+idx.day).to_numpy('int32')
    rawmonths=(idx.year*100+idx.month).to_numpy('int32')
    month_idx=np.asarray([MONTH_ID.get(int(x),-1) for x in rawmonths],dtype='int16')
    minute=(idx.hour*60+idx.minute).to_numpy('int16')
    dayutc=idx.normalize()
    weekutc=dayutc-pd.to_timedelta(idx.dayofweek,unit='D')
    day=np.nan_to_num(daysig.reindex(dayutc).to_numpy(dtype='float64'),nan=0).astype('int8')
    week=np.nan_to_num(weeksig.reindex(weekutc).to_numpy(dtype='float64'),nan=0).astype('int8')
    basevalid=(month_idx>=0)&(idx.dayofweek<5)
    askopen=df.ask_open.to_numpy(dtype='float64')
    bidopen=df.bid_open.to_numpy(dtype='float64')
    bidclose=df.bid_close.to_numpy(dtype='float64')
    askclose=df.ask_close.to_numpy(dtype='float64')
    midopen=(askopen+bidopen)*0.5
    hdict={}
    tfminutes=TFS[tf][0]
    for hold in TFS[tf][1]:
        exitindices=np.minimum(np.arange(n)+hold-1,n-1)
        same=ordinal[exitindices]==ordinal
        timevalid=(idx.asi8[exitindices]-idx.asi8<=tfminutes*hold*60*1e9*2)
        valid=basevalid&same&timevalid&(np.arange(n)+hold-1<n)&(midopen>0)
        longret=((bidclose[exitindices]-askopen)/midopen)*10000-SLIPPAGE_ROUND_TRIP_BPS
        shortret=((bidopen-askclose[exitindices])/midopen)*10000-SLIPPAGE_ROUND_TRIP_BPS
        valid &= np.isfinite(longret)&np.isfinite(shortret)
        hdict[hold]=(valid,longret,shortret)
    return ordinal,month_idx,minute,day,week,hdict

def dedup(candidates,limit=75):
    result=[]
    seen=set()
    # Keeps diverse returns rather than hundreds of near-identical parameter tweaks.
    byrank=sorted(candidates,key=lambda x:(x['months_positive'],x['min_month_bps'],x['total_bps']),reverse=True)
    for x in byrank:
        fingerprint=tuple(np.rint(np.array(x['monthly_bps'])/20).astype('int32'))
        if fingerprint in seen: continue
        seen.add(fingerprint)
        result.append(x)
        if len(result)>=limit:break
    return result

def evaluate_one(symbol,tf,df,daysig,weeksig):
    ordinal,midx,minutes,ds,ws,hdict=prepare(df,tf,daysig,weeksig)
    signals=signal_library(df,ds,ws)
    result=[]
    total=0
    annual_positive=0
    all_months=0
    near=[]
    # All signals use completed previous candles; entry/exit use historical executable bid/ask.
    for signame,base_signal in signals:
        for orientation in (1,-1):
            side=base_signal*orientation
            for regime in ('ANY','D1_ALIGN','W1_ALIGN'):
                eligible=(side!=0)
                if regime=='D1_ALIGN': eligible &= side==ds
                if regime=='W1_ALIGN': eligible &= side==ws
                for hour in SESSIONS:
                    window=(minutes>=hour*60)&(minutes<min(hour*60+120,1440))
                    feasible=eligible&window
                    for hold,(valid,longret,shortret) in hdict.items():
                        total+=1
                        good=np.flatnonzero(feasible&valid)
                        if not len(good):continue
                        first=np.r_[True,ordinal[good[1:]]!=ordinal[good[:-1]]]
                        ix=good[first]
                        pertrade=np.where(side[ix]>0,longret[ix],shortret[ix])
                        month=midx[ix]
                        counts=np.bincount(month,minlength=22)
                        if (counts<MIN_TRADES_EACH_MONTH).any():continue
                        pnl=np.bincount(month,weights=pertrade,minlength=22)
                        posmonths=int((pnl>1e-8).sum())
                        profit2025=float(pnl[:12].sum())
                        profit2026=float(pnl[12:].sum())
                        if profit2025<=0 or profit2026<=0:continue
                        annual_positive+=1
                        record=dict(symbol=symbol,tf=tf,family=signame,orientation=('FOLLOW' if orientation==1 else 'FADE'),
                          regime=regime,entry_start_utc=hour,entry_window_hours=2,
                          hold_bars=hold,hold_minutes=TFS[tf][0]*hold,
                          pnl_2025_bps=round(profit2025,4),pnl_2026_bps=round(profit2026,4),
                          total_bps=round(float(pnl.sum()),4),
                          months_positive=posmonths,min_month_bps=round(float(pnl.min()),4),
                          trades=int(len(ix)),trades_by_month=counts.tolist(),
                          monthly_bps=[round(float(v),5) for v in pnl])
                        if posmonths==22:
                            all_months+=1
                            result.append(record)
                        elif posmonths>=12:
                            near.append(record)
    return dict(total=total,annual_positive=annual_positive,qualifying=all_months,
                records=result,near=dedup(near,limit=90),signals=len(signals))

def combo_record(pool,group):
    pnl=np.mean(np.asarray([c['monthly_bps'] for c in group]),axis=0)
    # Equal notional per symbol, monthly returns averaged: the strategy is an independent multi-EA portfolio.
    npos=int((pnl>1e-8).sum())
    if npos!=22 or pnl[:12].sum()<=0 or pnl[12:].sum()<=0:return None
    return dict(n_symbols=len(group),symbols=[x['symbol'] for x in group],
        components=[{k:v for k,v in x.items() if k not in ('monthly_bps','trades_by_month')} for x in group],
        pnl_2025_bps=round(float(pnl[:12].sum()),4),
        pnl_2026_bps=round(float(pnl[12:].sum()),4),
        monthly_bps=[round(float(x),4) for x in pnl],
        min_month_bps=round(float(pnl.min()),4),
        total_bps=round(float(pnl.sum()),4))

def screen(root,out):
    out.mkdir(parents=True,exist_ok=True)
    allqualified=[]
    pools=collections.defaultdict(list)
    bydataset={}
    for symbol in SYMBOLS:
        # the 5 min source helps produce safely lagged D1/W1 regime signals
        m5=load(root,symbol,'M5')
        daysig,weeksig=daily_weekly_directions(m5)
        for tf in TFS:
            d=load(root,symbol,tf)
            results=evaluate_one(symbol,tf,d,daysig,weeksig)
            key=f'{symbol}/{tf}'
            bydataset[key]={k:results[k] for k in ('total','annual_positive','qualifying','signals')}
            allqualified.extend(results['records'])
            pools[symbol].extend(results['near'])
            pools[symbol].extend(results['records'])
            print('SCAN',key,bydataset[key],flush=True)
    singles=sorted(allqualified,key=lambda x:(x['min_month_bps'],x['total_bps']),reverse=True)
    groups={s:dedup(candidates,limit=75) for s,candidates in pools.items()}
    portfolio_pairs=[]
    portfolio_triples=[]
    pairtrials=0
    tripletrials=0
    for a,b in itertools.combinations(SYMBOLS,2):
        for x,y in itertools.product(groups[a],groups[b]):
            pairtrials+=1
            p=combo_record(None,(x,y))
            if p:portfolio_pairs.append(p)
    for names in itertools.combinations(SYMBOLS,3):
        # Restrict triple research to 22 strongest distinct strategies per asset.
        for tri in itertools.product(*(groups[s][:22] for s in names)):
            tripletrials+=1
            p=combo_record(None,tri)
            if p:portfolio_triples.append(p)
    portfolio_pairs.sort(key=lambda x:(x['min_month_bps'],x['total_bps']),reverse=True)
    portfolio_triples.sort(key=lambda x:(x['min_month_bps'],x['total_bps']),reverse=True)
    report=dict(version='V22',source='Exness public bid/ask tick OHLC',
      period_2025='2025-01-01 to 2025-12-31 inclusive',
      period_2026='2026-01-01 to 2026-10-31 inclusive',
      months=MONTHS,symbols=SYMBOLS,timeframes=list(TFS),
      slippage_roundtrip_bps=SLIPPAGE_ROUND_TRIP_BPS,
      commission_assumption='none (verify Exness account type); bid/ask spread included',
      overnight='not held; exit inside same UTC day',
      minimum_monthly_trades=MIN_TRADES_EACH_MONTH,
      risk_warning='IS sample search and cost assumptions. Not validated on untouched future data. Do not trade live based only on this.',
      datasets=bydataset,
      total_configs_tested=sum(d['total'] for d in bydataset.values()),
      single_annual_positive=sum(d['annual_positive'] for d in bydataset.values()),
      single_all_22_months=len(singles),
      tested_pairs=pairtrials,pairs_all_22_months=len(portfolio_pairs),
      tested_triples=tripletrials,triples_all_22_months=len(portfolio_triples),
      top_single=singles[:60],top_pairs=portfolio_pairs[:30],top_triples=portfolio_triples[:30],
      pool_sizes={s:len(p) for s,p in groups.items()},
      completed_at_utc=datetime.now(timezone.utc).isoformat())
    (out/'screen_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'qualified_singles.json').write_text(json.dumps(singles,ensure_ascii=False)+'\n')
    (out/'qualified_pairs_top1000.json').write_text(json.dumps(portfolio_pairs[:1000],ensure_ascii=False)+'\n')
    (out/'qualified_triples_top1000.json').write_text(json.dumps(portfolio_triples[:1000],ensure_ascii=False)+'\n')
    print('FINAL',json.dumps({k:report[k] for k in ('total_configs_tested','single_annual_positive',
      'single_all_22_months','tested_pairs','pairs_all_22_months','tested_triples',
      'triples_all_22_months','pool_sizes')}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('data/v22_exness'))
    parser.add_argument('--out',type=Path,default=Path('results/v22_strategy_screen'))
    a=parser.parse_args()
    screen(a.root,a.out)
