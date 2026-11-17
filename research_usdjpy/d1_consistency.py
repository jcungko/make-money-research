#!/usr/bin/env python3
"""Predeclared D1 hypotheses, executable M5 Bid/Ask stop-first replay; research only."""
import csv, hashlib, io, json, math, zipfile
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'/'usdjpy_d1_consistency_20261117'
PIP=0.01
UNITS=1000.0
TRAIN_END='2026-08-31'
HOLDOUT_START='2026-09-01'
FAMILIES=('body_follow','body_fade','close_follow','close_fade','two_follow','two_fade','three_follow','three_fade')
WIDTHS=(0.25,0.40,0.60)
HOURS=(1,7)


def load(year):
    path=ROOT/'data'/f'v17_exness_{year}'/f'USDJPY_{year}_UTC_7TF.zip'
    b=path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        m=pd.read_csv(io.BytesIO(z.read(f'USDJPY_M5_{year}_UTC.csv')))
        d=pd.read_csv(io.BytesIO(z.read(f'USDJPY_D1_{year}_UTC.csv')))
    cols=['bid_open','bid_high','bid_low','bid_close','ask_open','ask_high','ask_low','ask_close','tick_count']
    for df in (m,d):
        df['timestamp_utc']=pd.to_datetime(df.timestamp_utc,utc=True)
        df.sort_values('timestamp_utc',inplace=True)
        if df.timestamp_utc.duplicated().any() or df[cols].isna().any().any() or (df[cols]<=0).any().any():
            raise ValueError('invalid or duplicate prices')
        if (df.bid_open>df.ask_open).any() or (df.bid_close>df.ask_close).any():
            raise ValueError('crossed quotes')
    return m,d,dict(year=year,sha256=hashlib.sha256(b).hexdigest(),m5=len(m),d1=len(d))


def prepare(m,d):
    m=m.copy();d=d.copy()
    m['day']=m.timestamp_utc.dt.floor('D')
    m['date']=m.timestamp_utc.dt.strftime('%Y-%m-%d')
    m['hour']=m.timestamp_utc.dt.hour
    m['minute']=m.timestamp_utc.dt.minute
    grouped={k:v.reset_index(drop=True) for k,v in m.groupby('date',sort=True)}
    counts=m.groupby('day').size()
    d['day']=d.timestamp_utc.dt.floor('D')
    d['bar_count']=d.day.map(counts).fillna(0).astype(int)
    d=d[(d.timestamp_utc.dt.weekday<5)&(d.bar_count>=150)].copy()
    for p in ('open','high','low','close'):
        d['mid_'+p]=(d['bid_'+p]+d['ask_'+p])/2
    pclose=d.mid_close.shift(1)
    tr=pd.concat([d.mid_high-d.mid_low,(d.mid_high-pclose).abs(),(d.mid_low-pclose).abs()],axis=1).max(axis=1)
    d['atr']=tr.rolling(14,min_periods=14).mean()
    d['body']=(d.mid_close-d.mid_open)/d.atr
    d['close_zone']=(d.mid_close-d.mid_low)/(d.mid_high-d.mid_low).replace(0,np.nan)
    d['ret3']=(d.mid_close-d.mid_close.shift(3))/d.atr
    d['prev_body']=d.body.shift(1)
    d['date']=d.timestamp_utc.dt.strftime('%Y-%m-%d')
    return d.reset_index(drop=True),grouped


def signal(i,fam,d):
    if i<16:return 0
    p=d.iloc[i-1]
    body=float(p.body)
    if not math.isfinite(body):return 0
    if fam.startswith('body_'):
        s=(1 if body>0.10 else -1 if body< -0.10 else 0)
    elif fam.startswith('close_'):
        s=(1 if p.close_zone>0.70 else -1 if p.close_zone<0.30 else 0)
    elif fam.startswith('two_'):
        b=float(d.iloc[i-2].body)
        s=(1 if body>0.08 and b>0.08 else -1 if body< -0.08 and b< -0.08 else 0)
    elif fam.startswith('three_'):
        s=(1 if p.ret3>0.35 else -1 if p.ret3< -0.35 else 0)
    else:raise ValueError(fam)
    return -s if fam.endswith('fade') else s


def simulate(d,grouped,c,slip=0.20,commission=0.07):
    fam,width,hour=c['family'],c['stop_atr'],c['entry_hour_utc']
    ledger=[]
    for i in range(16,len(d)):
        date=d.iloc[i].date
        previous=d.iloc[i-1]
        if (d.iloc[i].day-previous.day).days>4:continue
        side=signal(i,fam,d)
        if side==0 or not math.isfinite(previous.atr):continue
        arr=grouped.get(date)
        if arr is None:continue
        entries=arr.index[(arr.hour==hour)&(arr.minute==0)]
        if len(entries)!=1:continue
        j0=int(entries[0]);bar=arr.iloc[j0]
        spread=(bar.ask_open-bar.bid_open)/PIP
        if spread>3.0 or spread<0:continue
        stop_w=float(previous.atr)*width
        if stop_w<8*PIP or stop_w>80*PIP:continue
        entry=float(bar.ask_open+slip*PIP if side==1 else bar.bid_open-slip*PIP)
        stop=entry-side*stop_w
        target=entry+side*stop_w
        exit_price=None;reason='time';jj=None
        for j in range(j0,len(arr)):
            b=arr.iloc[j]
            if b.hour>20 or (b.hour==20 and b.minute>55):break
            if side==1:
                if b.bid_low<=stop:
                    exit_price=min(stop,float(b.bid_open))-slip*PIP;reason='SL';jj=j;break
                if b.bid_high>=target:
                    exit_price=target-slip*PIP;reason='TP';jj=j;break
            else:
                if b.ask_high>=stop:
                    exit_price=max(stop,float(b.ask_open))+slip*PIP;reason='SL';jj=j;break
                if b.ask_low<=target:
                    exit_price=target+slip*PIP;reason='TP';jj=j;break
        if exit_price is None:
            eligible=arr.index[(arr.index>=j0)&((arr.hour<21))]
            if len(eligible)==0:continue
            jj=int(eligible[-1]);b=arr.iloc[jj]
            exit_price=float(b.bid_close-slip*PIP if side==1 else b.ask_close+slip*PIP)
        pnl=(side*(exit_price-entry)*UNITS/exit_price)-commission
        ledger.append(dict(day=date,direction='BUY' if side==1 else 'SELL',entry_utc=bar.timestamp_utc.isoformat(),exit_utc=arr.iloc[jj].timestamp_utc.isoformat(),
                           outcome=reason,entry=round(entry,5),sl=round(stop,5),tp=round(target,5),exit=round(exit_price,5),
                           width_pips=round(stop_w/PIP,2),spread_pips=round(float(spread),2),pnl_usd=round(float(pnl),6)))
    return ledger


def wilson(w,n):
    if n==0:return 0
    z=1.96;p=w/n
    return (p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)


def stats(ledger):
    n=len(ledger)
    if not n:return dict(n=0,win_rate=0,win_lower95=0,net_usd=0,profit_factor=None,max_dd_usd=0,tp_count=0,sl_count=0,time_count=0,monthly={})
    v=np.array([x['pnl_usd'] for x in ledger]);w=int((v>0).sum());loss=-v[v<0].sum();win=v[v>0].sum();eq=np.r_[0,v.cumsum()]
    monthly=defaultdict(lambda:dict(n=0,net_usd=0,wins=0))
    for t in ledger:
        k=t['day'][:7];z=monthly[k];z['n']+=1;z['net_usd']+=t['pnl_usd'];z['wins']+=int(t['pnl_usd']>0)
    for z in monthly.values():z['net_usd']=round(z['net_usd'],5);z['win_rate']=round(z['wins']/z['n'],4)
    return dict(n=n,win_rate=round(w/n,4),win_lower95=round(wilson(w,n),4),net_usd=round(v.sum(),5),
                profit_factor=round(float(win/loss),3) if loss else None,max_dd_usd=round(float(np.maximum.accumulate(eq).__sub__(eq).max()),5),
                tp_count=sum(t['outcome']=='TP' for t in ledger),sl_count=sum(t['outcome']=='SL' for t in ledger),time_count=sum(t['outcome']=='time' for t in ledger),monthly=dict(sorted(monthly.items())))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    m26,d26,meta26=load(2026)
    d,g=prepare(m26,d26)
    if len(d)<170:raise RuntimeError('insufficient complete weekday daily bars')
    # Evidence that dataset is as described. Keep the validation window untouched for selection.
    assert d.date.min().startswith('2026-01') and d.date.max()<='2026-11-10'
    specs=[dict(id=f'D1-{i:02d}',family=f,stop_atr=w,entry_hour_utc=h,rr=1.0) for i,(f,w,h) in enumerate((f,w,h) for f in FAMILIES for w in WIDTHS for h in HOURS)]
    results=[]
    for c in specs:
        base=simulate(d,g,c,slip=0.20,commission=0.07)
        stressed=simulate(d,g,c,slip=0.70,commission=0.10)
        train=[t for t in base if t['day']<=TRAIN_END]
        hold=[t for t in base if t['day']>=HOLDOUT_START]
        st_train=[t for t in stressed if t['day']<=TRAIN_END]
        st_hold=[t for t in stressed if t['day']>=HOLDOUT_START]
        a,b,cs,hs=stats(train),stats(hold),stats(st_train),stats(st_hold)
        half1=stats([t for t in train if t['day']<='2026-04-30'])
        half2=stats([t for t in train if t['day']>='2026-05-01'])
        # This training qualification contains NO holdout references.
        qualifies=a['n']>=55 and a['win_rate']>=0.53 and a['net_usd']>0 and cs['net_usd']>0 and half1['net_usd']>0 and half2['net_usd']>0
        results.append(dict(config=c,train=a,holdout=b,train_stress=cs,holdout_stress=hs,
                            train_early=half1,train_late=half2,train_qualified=qualifies,
                            selection_score=round(a['win_lower95']+0.0005*a['n'],5)))
    eligible=sorted((r for r in results if r['train_qualified']),key=lambda x:(x['selection_score'],x['train']['n']),reverse=True)
    # If fewer than three qualify, do not promote failing strategies to finalists.
    selected=eligible[:3]
    all_ranked=sorted(results,key=lambda x:(x['selection_score'],x['train']['n']),reverse=True)
    ledger=[]
    for r in selected:
        c=r['config'];base=simulate(d,g,c,slip=0.20,commission=0.07)
        ledger.extend([dict(strategy=c['id'],period=('train' if t['day']<=TRAIN_END else 'holdout'),**t) for t in base])
        r['holdout_pass']=(r['holdout']['n']>=15 and r['holdout']['win_rate']>0.50 and r['holdout_stress']['net_usd']>0)
    # Back-check in 2025 ONLY after fixed selection, never used for optimization.
    if selected:
        m25,d25,meta25=load(2025)
        d25,g25=prepare(m25,d25)
        for r in selected:
            y25=simulate(d25,g25,r['config'],slip=0.20,commission=0.07)
            stress25=simulate(d25,g25,r['config'],slip=0.70,commission=0.10)
            r['retro_2025']=stats(y25)
            r['retro_2025_stress']=stats(stress25)
    else:meta25=None
    report=dict(protocol='USDJPY-D1-consistency-v1',date_range=['2026-01-01','2026-11-10'],train_end=TRAIN_END,
                holdout_start=HOLDOUT_START,source_2026=meta26,source_2025=meta25,
                input_bars=dict(m5=len(m26),d1=len(d26),full_weekday_d1=len(d)),
                configs_tested=len(specs),train_qualified=len(eligible),
                selected=selected,leaderboard=all_ranked,
                costs=dict(bid_ask='executable open and exit quotes',baseline_slippage_pips_per_side=0.20,
                           baseline_commission_usd_per_roundtrip=0.07,stress_slippage_pips_per_side=0.70,
                           stress_commission_usd_per_roundtrip=0.10,swap='not modeled; intraday only'),
                limitations=['Exness archived Bid/Ask M5 bars, not raw ticks','SL first when both levels touch within same M5 bar',
                             '2025 and 2026 historical data previously exposed, not independent forward testing',
                             'holidays may have insufficient intraday data','no account-specific commissions or server fill rules',
                             '2026 sample ends November 10, not fully current','48 related hypotheses imply selection bias'])
    (OUT/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,default=lambda x: x.item() if hasattr(x, 'item') else str(x))+'\n')
    with open(OUT/'leaderboard.csv','w',newline='') as file:
        w=csv.writer(file);w.writerow(['id','family','stop_atr','entry_hour_utc','train_n','train_winrate','train_lower95','train_net_usd','train_stress_net_usd','holdout_n','holdout_winrate','holdout_net_usd','holdout_stress_net_usd','train_qualified'])
        for r in all_ranked:
            c=r['config'];a=r['train'];b=r['holdout'];w.writerow([c['id'],c['family'],c['stop_atr'],c['entry_hour_utc'],a['n'],a['win_rate'],a['win_lower95'],a['net_usd'],r['train_stress']['net_usd'],b['n'],b['win_rate'],b['net_usd'],r['holdout_stress']['net_usd'],r['train_qualified']])
    with open(OUT/'selected_trades.csv','w',newline='') as file:
        if ledger:
            w=csv.DictWriter(file,fieldnames=list(ledger[0]));w.writeheader();w.writerows(ledger)
    print(json.dumps(dict(configs_tested=len(specs),train_qualified=len(eligible),selected=[dict(id=r['config']['id'],train=r['train'],holdout=r['holdout'],holdout_stress=r['holdout_stress'],holdout_pass=r['holdout_pass']) for r in selected]),ensure_ascii=False,default=lambda x: x.item() if hasattr(x, 'item') else str(x)))

if __name__=='__main__':main()
