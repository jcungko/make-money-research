#!/usr/bin/env python3
"""USDJPY Exness-only exploratory research engine. NO MT5 / trading endpoints."""
import hashlib, io, json, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"research_usdjpy"/"results"
PROTOCOL="USDJPY-R1-20261116"
TOTAL=96
PIP=0.01
UNITS=1000.0  # indicative 0.01-lot equivalent; not a live volume

def config(i):
    if not 0<=i<TOTAL: raise ValueError("outside pre-registered search space")
    return dict(id="UJ-R1-%03d"%i,family=("momentum","reversion","breakout","vol_expansion")[i%4],
        lookback=(6,12,24,36)[(i//4)%4],threshold=(0.5,0.8,1.1)[(i//16)%3],
        stop_atr=(1.2,1.5)[(i//48)%2],target_rr=2.25,max_hold_bars=12)

def source(year):
    p=ROOT/"data"/("v17_exness_%d"%year)/("USDJPY_%d_UTC_7TF.zip"%year)
    raw=p.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data=z.read("USDJPY_M5_%d_UTC.csv"%year)
    d=pd.read_csv(io.BytesIO(data))
    need=["bid_open","bid_high","bid_low","bid_close","ask_open","ask_high","ask_low","ask_close","tick_count"]
    if not all(x in d for x in need) or "timestamp_utc" not in d: raise ValueError("missing columns")
    d["timestamp_utc"]=pd.to_datetime(d["timestamp_utc"],utc=True)
    if d.empty or d.timestamp_utc.duplicated().any() or not d.timestamp_utc.is_monotonic_increasing: raise ValueError("timestamp integrity failure")
    if d[need].isna().any().any() or (d[need]<=0).any().any(): raise ValueError("missing/nonpositive prices")
    for side in ("bid","ask"):
        if ((d[side+"_high"]<d[[side+"_open",side+"_close",side+"_low"]].max(axis=1)) |
            (d[side+"_low"]>d[[side+"_open",side+"_close"]].min(axis=1))).any(): raise ValueError("bad OHLC geometry")
    if (d.bid_open>d.ask_open).any() or (d.bid_close>d.ask_close).any(): raise ValueError("crossed quotes")
    meta=dict(year=year,rows=len(d),sha256=hashlib.sha256(raw).hexdigest(),
        first=str(d.timestamp_utc.iloc[0]),last=str(d.timestamp_utc.iloc[-1]))
    return d,meta

def signals(d,c):
    close=(d.bid_close+d.ask_close)/2
    high=(d.bid_high+d.ask_high)/2
    low=(d.bid_low+d.ask_low)/2
    prev=close.shift()
    tr=pd.concat([high-low,(high-prev).abs(),(low-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    n=c["lookback"]; k=c["threshold"]
    avg=close.rolling(n,min_periods=n).mean()
    family=c["family"]
    if family in ("momentum","reversion"):
        delta=(close-avg)/atr.replace(0,np.nan)
        s=np.where(delta>k,1,np.where(delta< -k,-1,0))
        if family=="reversion":s=-s
    elif family=="breakout":
        hi=high.shift().rolling(n,min_periods=n).max()
        lo=low.shift().rolling(n,min_periods=n).min()
        s=np.where(close>hi+k*atr*0.15,1,np.where(close<lo-k*atr*0.15,-1,0))
    else:
        ratio=(high-low)/atr.replace(0,np.nan)
        delta=close-close.shift(n)
        s=np.where((ratio>1+k/3)&(delta>0),1,np.where((ratio>1+k/3)&(delta<0),-1,0))
    return np.asarray(s,dtype=np.int8),atr.to_numpy(float)

def simulate(d,c,slip=0.3,commission=0.0):
    sig,atr=signals(d,c)
    a={k:d[k].to_numpy(float) for k in ("bid_open","bid_high","bid_low","bid_close","ask_open","ask_high","ask_low","ask_close")}
    t=d.timestamp_utc
    trades=[];i=max(50,c["lookback"]+16)
    while i<len(d):
        when=t.iloc[i]
        if not 7<=when.hour<16 or sig[i-1]==0 or not np.isfinite(atr[i-1]):
            i+=1;continue
        side=int(sig[i-1]);width=max(8*PIP,atr[i-1]*c["stop_atr"])
        if not 8*PIP<=width<=65*PIP: i+=1;continue
        entry=(a["ask_open"][i]+slip*PIP) if side==1 else (a["bid_open"][i]-slip*PIP)
        stop=entry-side*width
        target=entry+side*c["target_rr"]*width
        last=min(i+11,len(d)-1);exit_price=None;reason="time";j=i
        for j in range(i,last+1):
            if side==1:
                if a["bid_low"][j]<=stop:
                    exit_price=min(stop,a["bid_open"][j])-slip*PIP;reason="stop";break
                if a["bid_high"][j]>=target:
                    exit_price=target-slip*PIP;reason="target";break
            else:
                if a["ask_high"][j]>=stop:
                    exit_price=max(stop,a["ask_open"][j])+slip*PIP;reason="stop";break
                if a["ask_low"][j]<=target:
                    exit_price=target+slip*PIP;reason="target";break
        if exit_price is None:
            j=last
            exit_price=(a["bid_close"][j]-slip*PIP) if side==1 else (a["ask_close"][j]+slip*PIP)
        pnl=side*(exit_price-entry)*UNITS/exit_price-commission
        trades.append(dict(entry_utc=when.isoformat(),exit_utc=t.iloc[j].isoformat(),
            direction=("BUY" if side==1 else "SELL"),reason=reason,
            entry=round(entry,5),exit=round(exit_price,5),stop=round(stop,5),
            target=round(target,5),pnl_usd=round(float(pnl),7)))
        i=j+1
    return trades

def stats(trades):
    v=np.array([x["pnl_usd"] for x in trades],dtype=float)
    if not len(v): return dict(trades=0,net_usd=0,win_rate=None,realized_rr=None,profit_factor=None,max_drawdown_usd=0,by_month={})
    w=v[v>0];l=-v[v<0];equity=np.r_[0,np.cumsum(v)]
    months={}
    for x in trades: months[x["exit_utc"][:7]]=months.get(x["exit_utc"][:7],0)+x["pnl_usd"]
    return dict(trades=len(v),net_usd=round(float(sum(v)),5),win_rate=round(len(w)/len(v),4),
        realized_rr=(round(float(w.mean()/l.mean()),4) if len(w) and len(l) else None),
        profit_factor=(round(float(w.sum()/l.sum()),4) if len(l) else None),
        max_drawdown_usd=round(float((np.maximum.accumulate(equity)-equity).max()),5),
        by_month={k:round(float(z),5) for k,z in sorted(months.items())})

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    exp=OUT/"experiments";exp.mkdir(exist_ok=True)
    sp=OUT/"state.json"
    state=json.loads(sp.read_text()) if sp.exists() else dict(protocol=PROTOCOL,cursor=0,completed=0,blocked=0)
    if state.get("protocol")!=PROTOCOL: raise ValueError("protocol mismatch")
    now=datetime.now(timezone.utc).isoformat()
    report=dict(protocol=PROTOCOL,utc=now,from_cursor=state["cursor"],status="STARTED",
        experiments=[],live_trading=False,exposed_data=True)
    try:
        frames=[];sources=[]
        for y in (2025,2026):
            d,m=source(y);frames.append(d);sources.append(m)
        d=pd.concat(frames,ignore_index=True)
        if d.timestamp_utc.duplicated().any() or not d.timestamp_utc.is_monotonic_increasing:
            raise ValueError("bad merged times")
        report["sources"]=sources
        for idx in range(state["cursor"],min(TOTAL,state["cursor"]+2)):
            c=config(idx);file=exp/(c["id"]+".json")
            if file.exists():raise ValueError("duplicate ID; state inconsistent")
            trades=simulate(d,c);stress=simulate(d,c,slip=1.2,commission=0.10)
            m=stats(trades);sm=stats(stress)
            status="RESEARCH_CANDIDATE" if m["net_usd"]>0 and sm["net_usd"]>0 and m["trades"]>0 else "REJECTED"
            result=dict(config=c,status=status,metrics=m,stress_metrics=sm,
                trades=trades,source_manifests=sources,forward_verified=False,
                live_approved=False,costs=dict(bid_ask_spread="included once",
                    baseline_slippage_pips_side=0.3,stress_slippage_pips_side=1.2,
                    baseline_commission="UNVERIFIED, modeled zero",stress_commission_usd_roundtrip=0.10,
                    swap="UNVERIFIED, DO NOT CLAIM FULLY COSTED PNL"),
                audit_limits=["2025-2026 historically exposed", "not clean OOS",
                    "intrabar stop-first approximated, raw tick replay missing",
                    "actual MT5 costs and fills unverified",
                    "multiple testing adjustment and forward validation pending"])
            file.write_text(json.dumps(result,separators=(",",":"),ensure_ascii=False)+"\n")
            report["experiments"].append(dict(id=c["id"],status=status,trades=m["trades"],
                net_usd=m["net_usd"],stress_net_usd=sm["net_usd"]))
            state["cursor"]=idx+1;state["completed"]+=1
        report["status"]="EXHAUSTED" if state["cursor"]>=TOTAL else "EXPERIMENTS_COMPLETED"
    except Exception as e:
        report["status"]="BLOCKED";report["error"]=type(e).__name__+": "+str(e)
        state["blocked"]=state.get("blocked",0)+1
    state["last_utc"]=now;state["last_status"]=report["status"]
    stamp=now[:19].replace(":","-")+"_"+hashlib.sha256(now.encode()).hexdigest()[:8]
    (OUT/("run_"+stamp+".json")).write_text(json.dumps(report,indent=2)+"\n")
    sp.write_text(json.dumps(state,indent=2)+"\n")
    print(json.dumps(dict(status=report["status"],completed=len(report["experiments"]),
        cursor=state["cursor"],results=report["experiments"],error=report.get("error"))),flush=True)
    if report["status"]=="BLOCKED":sys.exit(2)

if __name__=="__main__":main()
