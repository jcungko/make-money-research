#!/usr/bin/env python3
"""V14 reproducible exploratory EA screen: Exness Bid/Ask bars, 2026.
No orders, no credentials. Same-sample selection is NOT validation.
"""
import argparse, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

FRAMES = ["M5","M15","M30","H1","H4"]
SYMBOLS = ["EURUSD","GBPUSD","USDJPY"]
STOPS = {"M5":[6,12,20], "M15":[8,16,28], "M30":[10,20,35],
         "H1":[12,25,40], "H4":[25,50,80]}
FREQ_MIN = {"M5":5,"M15":15,"M30":30,"H1":60,"H4":240}
HOURS = [0,4,8,12,16,20]
RRS = [1.0,1.5,2.0,3.0]
HOLDS = [8,16,24]
MODELS = ["prev1","prev3","prev12","ema8_32","ema12_slope","mid24","rsi14","day1"]
SLIPPAGE_PIPS_ROUNDTRIP = 0.4

def index_week(ts):
    d = pd.Timestamp(ts).date()
    return str((pd.Timestamp(d)-pd.Timedelta(days=d.weekday())).date())

def inputs(root,symbol,frame):
    matches=list(root.glob(f"**/{symbol}_{frame}_2026_UTC.csv.gz"))
    if len(matches)!=1:
        raise FileNotFoundError(f"Expected one file {symbol} {frame}; found {len(matches)}: {matches}")
    frame_df=pd.read_csv(matches[0],index_col=0,parse_dates=True).sort_index()
    frame_df.index=pd.to_datetime(frame_df.index,utc=True)
    required=["bid_open","bid_high","bid_low","bid_close","ask_open",
              "ask_high","ask_low","ask_close"]
    if any(x not in frame_df.columns for x in required):
        raise ValueError(f"Missing required columns: {matches[0]}")
    frame_df=frame_df[~frame_df.index.duplicated(keep="first")]
    frame_df=frame_df.loc[(frame_df.index.year==2026)]
    manifest=list(matches[0].parent.glob(f"{symbol}_manifest.json"))
    meta=json.loads(manifest[0].read_text()) if manifest else {}
    return frame_df,meta

def signals(df,frame):
    c=df["bid_close"]
    prev=c.shift(1)
    m={}
    m["prev1"]=c.shift(1)-df["bid_open"].shift(1)
    m["prev3"]=prev-c.shift(4)
    m["prev12"]=prev-c.shift(13)
    e1=c.ewm(span=8,adjust=False).mean()
    e2=c.ewm(span=32,adjust=False).mean()
    m["ema8_32"]=(e1-e2).shift(1)
    e=c.ewm(span=12,adjust=False).mean()
    m["ema12_slope"]=e.shift(1)-e.shift(4)
    h=df["bid_high"].rolling(24,min_periods=24).max().shift(1)
    l=df["bid_low"].rolling(24,min_periods=24).min().shift(1)
    m["mid24"]=prev-(h+l)*0.5
    dc=c.diff()
    u=dc.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    d=(-dc.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    m["rsi14"]=(u-d).shift(1)
    day_bars=max(1,round(1440/FREQ_MIN[frame]))
    m["day1"]=prev-c.shift(day_bars+1)
    return {k:np.sign(v.fillna(0).to_numpy()).astype(np.int8) for k,v in m.items()}

def exit_prices(df,ix,side,slpip,rr,holdbars,pip):
    """One entry at each ix: stop first if both thresholds touched in a bar."""
    bid_o=df["bid_open"].to_numpy()
    ask_o=df["ask_open"].to_numpy()
    if side==1:
        entry=ask_o[ix]
        hi=df["bid_high"].to_numpy()
        lo=df["bid_low"].to_numpy()
        closing=df["bid_close"].to_numpy()
        stop=entry-slpip*pip
        target=entry+slpip*rr*pip
    else:
        entry=bid_o[ix]
        hi=df["ask_high"].to_numpy()
        lo=df["ask_low"].to_numpy()
        closing=df["ask_close"].to_numpy()
        stop=entry+slpip*pip
        target=entry-slpip*rr*pip
    pnl=np.zeros(len(ix),dtype=np.float64)
    close_idx=np.zeros(len(ix),dtype=np.int32)
    for j,i in enumerate(ix):
        last=min(int(i)+holdbars-1,len(df)-1)
        price=closing[last]
        kclose=last
        for k in range(int(i),last+1):
            if side==1:
                if lo[k]<=stop: price=stop; kclose=k; break
                if hi[k]>=target: price=target; kclose=k; break
            else:
                if hi[k]>=stop: price=stop; kclose=k; break
                if lo[k]<=target: price=target; kclose=k; break
        close_idx[j]=kclose
        pnl[j]=(price-entry[j])*side
    return pnl,close_idx

def _max_drawdown(profits):
    eq=np.r_[0.0,np.cumsum(profits)]
    return float(np.max(np.maximum.accumulate(eq)-eq))

def _max_loss_streak(profits):
    longest=run=0
    for p in profits:
        run=(run+1) if p<0 else 0
        longest=max(longest,run)
    return longest

def summarize(pnl,ids,close_ids,days,week_keys,df,meta):
    if len(pnl)<20: return None
    # Entries must appear at least once in EACH rolling k trading days.
    trade_day=set(df.index[ids].date)
    occupied=np.array([d in trade_day for d in days],dtype=np.int8)
    largest_gap=0
    now=0
    for b in occupied:
        now=0 if b else now+1
        largest_gap=max(largest_gap,now)
    cadence=1 if largest_gap==0 else 2 if largest_gap<=1 else 3 if largest_gap<=2 else 99
    if cadence==99: return None
    close_weeks=np.array([index_week(d) for d in df.index[close_ids]])
    week_pnl=np.array([float(pnl[close_weeks==w].sum()) for w in week_keys])
    net=float(np.sum(pnl))
    green=int(np.sum(week_pnl>0))
    red=int(np.sum(week_pnl<0))
    flat=int(np.sum(week_pnl==0))
    return dict(net_usd=round(net,2),net_raw=net,trades=len(pnl),
                win_rate=round(100*float(np.mean(pnl>0)),2),
                green_weeks=green,red_weeks=red,flat_weeks=flat,
                weeks_total=len(week_keys),
                max_drawdown_usd=round(_max_drawdown(pnl),2),
                max_losing_trades=_max_loss_streak(pnl),
                cadence_days=cadence,
                weekly_usd=[round(v,4) for v in week_pnl])

def main(a):
    root=Path(a.input)
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    all_rows=[]
    top_by_symbol=defaultdict(list)
    quality={}
    errors=[]
    for symbol in SYMBOLS:
        for frame in FRAMES:
            try:
                df,manifest=inputs(root,symbol,frame)
                if len(df)<1000: raise ValueError("Too few candles")
                if ((df["ask_open"]-df["bid_open"]) < 0).any(): raise ValueError("Negative spread")
                # Completed weeks only: exclude trailing current partial week.
                end=df.index.max().normalize()
                last_complete_sun=end-pd.Timedelta(days=end.weekday()+1)
                df=df.loc[df.index.normalize()<=last_complete_sun]
                if len(df)<1000:raise ValueError("No completed weeks")
                days=sorted(set(x.date() for x in df.index if x.weekday()<5))
                week_keys=sorted(set(index_week(d) for d in days))
                if len(week_keys)<30:raise ValueError("Insufficient weeks")
                prices = df[["bid_open","ask_open","bid_high","ask_high","bid_low","ask_low","bid_close","ask_close"]]
                if prices.isna().any().any():raise ValueError("NaNs in quotes")
                ixall=np.arange(len(df))
                idx_hour={h:ixall[(df.index.hour==h)&(df.index.minute==0)&(df.index.weekday<5)] for h in HOURS}
                sig=signals(df,frame)
                pip=0.01 if symbol=="USDJPY" else 0.0001
                q=dict(candles=len(df),from_utc=str(df.index.min()),
                       to_utc=str(df.index.max()),first_week=week_keys[0],
                       last_week=week_keys[-1],weeks=len(week_keys),
                       trading_days=len(days),
                       complete_monthly_download=manifest.get("complete_monthly_download"),
                       source_errors=manifest.get("errors",[]),
                       months_downloaded=len(manifest.get("months",[])))
                quality[f"{symbol}_{frame}"]=q
                count=0
                for h,ix in idx_hour.items():
                    if len(ix)<30:continue
                    # This is a stop-first, OHLC-based bar execution simulator.
                    for stop in STOPS[frame]:
                        for rr in RRS:
                            for hold in HOLDS:
                                bars=max(1,math.ceil(hold*60/FREQ_MIN[frame]))
                                lret,lclose=exit_prices(df,ix,1,stop,rr,bars,pip)
                                sret,sclose=exit_prices(df,ix,-1,stop,rr,bars,pip)
                                # Exact Bid/Ask spread already included in entry/exit.
                                # Add explicit adverse 0.4 pip total round-trip price impact.
                                lc=(lret-SLIPPAGE_PIPS_ROUNDTRIP*pip)
                                sc=(sret-SLIPPAGE_PIPS_ROUNDTRIP*pip)
                                for model,sarr in sig.items():
                                    for reverse in (False,True):
                                        direction=sarr[ix]*(-1 if reverse else 1)
                                        keep=(direction!=0)
                                        if int(keep.sum())<20: continue
                                        side=direction[keep]
                                        ii=ix[keep]
                                        cc=np.where(side==1,lclose[keep],sclose[keep])
                                        delta=np.where(side==1,lc[keep],sc[keep])
                                        # 0.01 lots = 1,000 base units.
                                        # JPY quote profits converted into USD at execution exit.
                                        if symbol=="USDJPY":
                                            mid=(df["bid_close"].to_numpy()[cc]+df["ask_close"].to_numpy()[cc])/2
                                            usd=delta*1000/mid
                                        else:usd=delta*1000
                                        stats=summarize(usd,ii,cc,days,week_keys,df,manifest)
                                        if stats is None: continue
                                        row={"symbol":symbol,"frame":frame,"hour_utc":h,
                                             "model":model,"reverse":reverse,
                                             "stop_pips":stop,"rr":rr,"max_hold_hours":hold,
                                             **stats}
                                        all_rows.append(row)
                                        count+=1
                q["candidates_pass_cadence"]=count
                print("SCANNED",symbol,frame,"candles",len(df),"weeks",len(week_keys),"candidates",count,flush=True)
            except Exception as ex:
                errors.append(f"{symbol} {frame}: {type(ex).__name__}: {ex}")
                print("ERROR",errors[-1],flush=True)

    # Strict priority: 100% of completed weeks positive, then highest realized net.
    # If none, label near-misses accurately and rank by green weeks then net.
    all_rows.sort(key=lambda r:(r["green_weeks"]==r["weeks_total"],
                                 r["green_weeks"],r["net_usd"]),reverse=True)
    strict=[x for x in all_rows if x["green_weeks"]==x["weeks_total"] and x["net_usd"]>0]
    profitable=[x for x in all_rows if x["net_usd"]>0]
    by_profit=sorted(profitable,key=lambda r:r["net_usd"],reverse=True)
    by_green=sorted(profitable,key=lambda r:(r["green_weeks"],r["net_usd"]),reverse=True)

    def clean(r):
        return {k:v for k,v in r.items() if k not in ("net_raw","weekly_usd")}
    # Shortlist of possible independent EAs, without assuming portfolio independence.
    report={
        "status":"research_only_not_live_validated",
        "source_workflow_run":42964857297,
        "source":"Exness 2026 artifact OHLC Bid/Ask on GitHub Actions",
        "units":"USD at fixed 0.01 standard lot per trade",
        "slippage_assumption_roundtrip_pips":SLIPPAGE_PIPS_ROUNDTRIP,
        "cost_method":"Ask/Bid entry-exit + stop-first OHLC + slippage; no commissions",
        "week_method":"ISO weeks with data, through last fully completed Sunday; realized exit-week PnL",
        "cadence_method":"for observed forex trading days, every rolling 1/2/3 days has >=1 entry",
        "sample_warning":"Searched thousands of rules on 2026; in-sample rankings are overfit and require untouched OOS & MT5 tick validation",
        "count_evaluated":len(all_rows),"count_profitable":len(profitable),
        "count_strict_weekly":len(strict),
        "source_quality":quality,"errors":errors,
        "strict_top_20":[clean(x) for x in sorted(strict,key=lambda r:r["net_usd"],reverse=True)[:20]],
        "near_miss_green_top_20":[clean(x) for x in by_green[:20]],
        "net_profit_top_20":[clean(x) for x in by_profit[:20]]
    }
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    # Keep weekly PnL for auditable performance of the leading candidates.
    selected=[]
    keys=set()
    for r in sorted(strict,key=lambda x:x["net_usd"],reverse=True)[:30]+by_green[:30]+by_profit[:30]:
        k=tuple(r[x] for x in ("symbol","frame","hour_utc","model","reverse","stop_pips","rr","max_hold_hours"))
        if k not in keys:
            selected.append(r);keys.add(k)
    pd.DataFrame([{**clean(x),**{f"week_{i+1}":v for i,v in enumerate(x["weekly_usd"])}} for x in selected]).to_csv(out/"top_candidates_weekly.csv",index=False)
    (out/"README.md").write_text(
        "# V14 — Exness 2026 EA research\n\n"+
        f"Scanned {len(all_rows)} candidate configurations, {len(profitable)} profitable, "+
        f"{len(strict)} strict weekly-positive. See report.json for source quality and top candidates.\n\n"+
        "All signals use fully closed previous candles. Entries use next eligible scheduled bar open. "+
        "OHLC stop-first rule, includes measured Bid/Ask spread and 0.4 pip adverse impact, fixed 0.01 lot. "+
        "All entry schedules UTC. Weekly profit recognized by exit week; trailing incomplete week omitted. "+
        "Backtest selection is in-sample; not proof of future return or ready for live use.\n")
    print("FINAL",{k:report[k] for k in ("count_evaluated","count_profitable","count_strict_weekly","errors")},flush=True)
    if len(quality)!=15: raise RuntimeError(f"Only {len(quality)}/15 source files analyzed")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="v14_inputs")
    p.add_argument("--out",default="results/v14_ea_2026")
    main(p.parse_args())
