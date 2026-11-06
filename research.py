"""MAKE MONEY independent Binance USD-M research. READ ONLY. Never trades."""
from __future__ import annotations
import hashlib, json, os, random, sys, time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import archive_data

OUT=Path("results"); OUT.mkdir(exist_ok=True)
STATE=OUT/"state.json"
STEP=900000
BUDGET=max(1,int(os.getenv("MODEL_BUDGET","12")))
MAX_COINS=max(1,int(os.getenv("MAX_COINS","2")))
DEADLINE=time.monotonic()+max(120,int(os.getenv("MAX_RUNTIME_SECONDS","1050")))
FEE=.0005; SLIP=.0002; CAPITAL=100; MARGIN=10; RISK_USD=2

@dataclass(frozen=True)
class Config:
    symbol:str
    timeframe:str
    family:str
    lookback:int
    volume_ratio:float
    stop_atr:float
    rr:float
    hold_hours:int
    leverage:int
    session:str
    funding_threshold:float

def persist(name,record):
    with (OUT/name).open("a",encoding="utf-8") as f:
        f.write(json.dumps(record,ensure_ascii=False,default=str,separators=(",",":"))+"\n")

def state_load():
    if STATE.exists(): return json.loads(STATE.read_text())
    return {"version":1,"cursor":0,"coin_cursor":0,"processed":0}

def state_save(state):
    temp=STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state,indent=2),encoding="utf-8")
    temp.replace(STATE)

def resample(df,tf):
    if tf=="15m": return df
    freq={"30m":"30min","1h":"1h","4h":"4h","1d":"1D"}[tf]
    kwargs={"origin":pd.Timestamp("1970-01-01 23:00:00+00:00")} if tf=="1d" else {}
    gr=df.resample(freq,label="left",closed="left",**kwargs)
    out=gr.agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
    counts=gr.close.count()
    return out.loc[counts=={"30m":2,"1h":4,"4h":16,"1d":96}[tf]].dropna()

def next_config(symbol,index):
    seed=int.from_bytes(hashlib.sha256((symbol+"/"+str(index)).encode()).digest()[:8],"big")
    r=random.Random(seed)
    return Config(symbol,r.choice(["15m","30m","1h","4h","1d"]),r.choice(["BREAK_LONG","BREAK_SHORT","EMA_PULLBACK","RSI_REVERSION","ATH_BREAKOUT","FUNDING_FADE"]),r.choice([12,24,48,96]),r.choice([.8,1.,1.3,1.8]),r.choice([1.,1.5,2.,3.]),r.choice([1.5,2.,3.,4.]),r.choice([4,8,16,24,48,72]),r.choice([2,3,5,10,20]),r.choice(["ALL","VN_06_16","VN_16_22"]),r.choice([.0001,.00025,.0005]))

def rsi(c):
    diff=c.diff(); pos=diff.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    neg=(-diff.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    return (100-100/(1+pos/neg.replace(0,np.nan))).fillna(50)

def signals(df,cfg,funds):
    p=df; prev=p.close.shift()
    atr=pd.concat([p.high-p.low,(p.high-prev).abs(),(p.low-prev).abs()],axis=1).max(axis=1).ewm(alpha=1/14,adjust=False).mean().shift()
    hi=p.high.shift().rolling(cfg.lookback).max()
    lo=p.low.shift().rolling(cfg.lookback).min()
    vol=p.volume>=cfg.volume_ratio*p.volume.shift().rolling(cfg.lookback).mean()
    if cfg.family=="BREAK_LONG": sig=np.where((p.close>hi)&vol,1,0)
    elif cfg.family=="BREAK_SHORT": sig=np.where((p.close<lo)&vol,-1,0)
    elif cfg.family=="EMA_PULLBACK":
        e20=p.close.ewm(span=20,adjust=False).mean()
        e60=p.close.ewm(span=60,adjust=False).mean()
        sig=np.where((e20>e60)&(p.low<e20)&(p.close>e20)&vol,1,0)
    elif cfg.family=="RSI_REVERSION":
        z=rsi(p.close)
        sig=np.where((z<28)&(p.close<lo)&vol,1,np.where((z>72)&(p.close>hi)&vol,-1,0))
    elif cfg.family=="ATH_BREAKOUT": sig=np.where((p.close>p.high.shift().cummax())&vol,1,0)
    else:
        t=p.index.view("i8")//1_000_000
        ix=np.searchsorted(funds.time.to_numpy(),t,side="right")-1
        fr=np.zeros(len(t)); good=ix>=0
        fr[good]=funds.rate.to_numpy()[ix[good]]
        sig=np.where((fr>=cfg.funding_threshold)&(p.close<p.open)&vol,-1,np.where((fr<=-cfg.funding_threshold)&(p.close>p.open)&vol,1,0))
    return np.asarray(sig,dtype=np.int8),atr.to_numpy()

def simulate(df,funds,cfg,fee=FEE,slip=SLIP):
    if len(df)<300: return []
    sig,atr=signals(df,cfg,funds)
    o,h,l,c=(df[x].to_numpy(float) for x in ("open","high","low","close"))
    bt=np.asarray(df.index.view("i8")//1_000_000,dtype=np.int64)
    local=df.index.tz_convert("Asia/Ho_Chi_Minh")
    hours=local.hour+local.minute/60
    barhours={"15m":.25,"30m":.5,"1h":1,"4h":4,"1d":24}[cfg.timeframe]
    held=max(1,int(cfg.hold_hours/barhours))
    ft=funds.time.to_numpy(np.int64); fr=funds.rate.to_numpy(float); fm=funds.mark.to_numpy(float)
    result=[]; active=None
    for i in range(max(100,cfg.lookback+2),len(df)):
        if active is None and sig[i-1]!=0 and np.isfinite(atr[i-1]) and atr[i-1]>0:
            if cfg.session=="VN_06_16" and not 6<=hours[i]<16: continue
            if cfg.session=="VN_16_22" and not 16<=hours[i]<22: continue
            side=int(sig[i-1]); entry=float(o[i]); dist=float(atr[i-1])*cfg.stop_atr
            pct=dist/entry
            if pct<=0 or pct>=1/cfg.leverage-.008: continue
            nominal=min(MARGIN*cfg.leverage,RISK_USD/(pct+2*(fee+slip)))
            if nominal<50: continue
            active={"i":i,"entry":entry,"sl":entry-side*dist,"tp":entry+side*dist*cfg.rr,"side":side,"qty":nominal/entry}
        if active is None: continue
        side=active["side"]
        sl=(l[i]<=active["sl"]) if side==1 else (h[i]>=active["sl"])
        tp=(h[i]>=active["tp"]) if side==1 else (l[i]<=active["tp"])
        expired=(i-active["i"]+1>=held)
        if not(sl or tp or expired): continue
        # Same-bar hits assume stop first. Adverse gaps worsen stop executions.
        exitp=(min(active["sl"],o[i]) if side==1 else max(active["sl"],o[i])) if sl else active["tp"] if tp else c[i]
        start=np.searchsorted(ft,bt[active["i"]],side="right")
        finish=np.searchsorted(ft,bt[i],side="right")
        fund=-side*active["qty"]*float(np.dot(fr[start:finish],fm[start:finish]))
        gross=active["qty"]*side*(exitp-active["entry"])
        cost=(fee+slip)*active["qty"]*(active["entry"]+exitp)
        result.append({"entry":pd.Timestamp(bt[active["i"]],unit="ms",tz="UTC").isoformat(),"exit":pd.Timestamp(bt[i],unit="ms",tz="UTC").isoformat(),"gross":gross,"funding":fund,"cost":cost,"pnl":gross+fund-cost,"side":"LONG" if side==1 else "SHORT"})
        active=None
    return result

def score(trades,split,end):
    if not trades: return {"trades":0,"exploratory_candidate":False}
    f=pd.DataFrame(trades); dates=pd.to_datetime(f.entry,utc=True)
    net=f.pnl.to_numpy(float); curve=np.r_[0,net.cumsum()]
    dd=float(np.min(curve-np.maximum.accumulate(curve)))
    train=dates<split; test=~train
    months=f.groupby(dates.dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%Y-%m"))["pnl"].sum()
    last12=[float(months.get(str(end.tz_convert("Asia/Ho_Chi_Minh").to_period("M")-k-1),0)) for k in range(12)]
    years=[]
    for k in range(3):
        a=end-pd.Timedelta(days=(k+1)*365); b=end-pd.Timedelta(days=k*365)
        mask=(dates>=a)&(dates<b)
        years.append({"pnl":round(float(f.loc[mask,"pnl"].sum()),4),"n":int(mask.sum())})
    pos=float(net[net>0].sum()); neg=float(-net[net<0].sum())
    pf=pos/max(.01,neg)
    tr=float(f.loc[train,"pnl"].sum()); te=float(f.loc[test,"pnl"].sum())
    stress=float((f.gross+f.funding-2*f.cost).sum())
    three=(dates.max()-dates.min()).days>=950 and all(y["pnl"]>0 and y["n"]>=8 for y in years)
    twelve=all(x>0 for x in last12)
    candidate=len(f)>=40 and int(test.sum())>=10 and tr>0 and te>0 and float(net.sum())>0 and stress>0 and pf>=1.2 and dd>=-25 and (three or twelve)
    return {"trades":len(f),"win_rate":round(float(np.mean(net>0)),4),"total_usdt":round(float(net.sum()),4),"stress_2x_cost_usdt":round(stress,4),"train_usdt":round(tr,4),"test_usdt":round(te,4),"profit_factor":round(pf,3),"max_drawdown_usdt":round(dd,4),"holdout_n":int(test.sum()),"years":years,"last12_completed_months_usdt":[round(x,4) for x in last12],"three_positive_year_blocks":three,"twelve_positive_months":twelve,"exploratory_candidate":bool(candidate),"live_approved":False,"validation":"EXPLORATORY: repeated holdout selection; independent forward validation required"}

def main():
    st=state_load()
    end=archive_data.closed_end_ms()
    symbols=archive_data.listing()
    if not symbols: raise RuntimeError("No active Binance USDT-M perpetual contracts")
    start_ix=int(st.get("coin_cursor",0))%len(symbols)
    coins=[symbols[(start_ix+j)%len(symbols)] for j in range(min(MAX_COINS,len(symbols)))]
    completed=0
    new_profitable=0
    new_candidates=0
    for coin in coins:
        if completed>=BUDGET or time.monotonic()>DEADLINE-125: break
        symbol=coin
        try:
            since=end-3*365*86400000
            bars,funds=archive_data.load(symbol,since,end)
            datasets={tf:resample(bars,tf) for tf in ["15m","30m","1h","4h","1d"]}
            # Calculated once per dataset rather than per candidate.
            fingerprints={tf:hashlib.sha256(x.to_csv().encode()+funds.to_csv(index=False).encode()).hexdigest() for tf,x in datasets.items()}
            for _ in range(max(1,BUDGET//len(coins))):
                if completed>=BUDGET or time.monotonic()>DEADLINE-90: break
                index=int(st["cursor"]); cfg=next_config(symbol,index)
                st["cursor"]=index+1
                data=datasets[cfg.timeframe]
                if len(data)<300:
                    state_save(st); continue
                try:
                    trades=simulate(data,funds,cfg)
                    boundary=data.index[0]+(data.index[-1]-data.index[0])*.8
                    result=score(trades,boundary,data.index[-1])
                    item={"id":f"MM-{symbol}-{index:09d}","config":asdict(cfg),"from":str(data.index[0]),"to":str(data.index[-1]),"data_sha256":fingerprints[cfg.timeframe],"result":result,"research_only":True,"checked_utc":datetime.now(timezone.utc).isoformat()}
                    # Full failing configurations are reproducible from cursor and source
                    # fingerprints. Do not append thousands of losing records to Git
                    # every day; retain full details for profitable configurations.
                    if result.get("total_usdt",0)>0 and result.get("trades",0)>0:
                        persist("profitable_experiments.jsonl",item)
                        st["profitable"]=st.get("profitable",0)+1
                        new_profitable+=1
                    if result["exploratory_candidate"]:
                        persist("candidates.jsonl",item)
                        st["candidates"]=st.get("candidates",0)+1
                        new_candidates+=1
                    if result.get("trades",0)==0: st["zero_trade"]=st.get("zero_trade",0)+1
                    st["processed"]=st.get("processed",0)+1
                    completed+=1
                except Exception as e:
                    persist("errors.jsonl",{"symbol":symbol,"index":index,"error":str(e)})
                state_save(st)
        except Exception as e:
            persist("errors.jsonl",{"symbol":symbol,"error":str(e),"checked_utc":datetime.now(timezone.utc).isoformat()})
            state_save(st)
    persist("runs.jsonl",{"completed":completed,"new_profitable":new_profitable,"new_candidates":new_candidates,"symbols":coins,"cursor_end":st.get("cursor"),"archive_end_utc":datetime.fromtimestamp(end/1000,timezone.utc).isoformat(),"checked_utc":datetime.now(timezone.utc).isoformat()})
    st["coin_cursor"]=int(st.get("coin_cursor",0))+len(coins)
    st["last_run_utc"]=datetime.now(timezone.utc).isoformat()
    state_save(st)
    print(json.dumps({"completed":completed,"new_profitable":new_profitable,"new_candidates":new_candidates,"total":st.get("processed",0),"coins":coins,"cursor":st["cursor"],"source":"Binance Vision public USD-M monthly OHLCV and funding archives","archive_end_utc":datetime.fromtimestamp(end/1000,timezone.utc).isoformat()}))
    if completed==0: raise RuntimeError("No completed tests: check results/errors.jsonl (archives missing, not-yet-listed, or other data issues)")

if __name__=="__main__":
    try: main()
    except Exception as e:
        persist("errors.jsonl",{"fatal":str(e),"checked_utc":datetime.now(timezone.utc).isoformat()})
        raise
