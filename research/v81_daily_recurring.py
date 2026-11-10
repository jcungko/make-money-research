#!/usr/bin/env python3
"""V8.1 EURUSDm 2026, repeatable DAILY session strategies: RESEARCH ONLY.
No trading credentials, no MT5 orders, no cloud alerts. No future information.
Only closed candles are used for signals, fills use Exness Bid/Ask with adverse
slippage and stop-first intrabar ordering. No financing/swap (intraday only).
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from v8a_eurusdm_m15 import load_m15

PIP=0.0001
BASE_SLIP=0.2
ENTRY_HOURS=(7,8,9,12,13,15)
EXIT_HOURS=(19,20)
STOPS=(8,12,16,24)
RRS=(0.75,1.0,1.5,2.0,3.0)
RECENT=("2026-08","2026-09","2026-10")
FULL=tuple(f"2026-{j:02d}" for j in range(1,11))

def build_features(d):
    c=d.bc.astype(float)
    out={}
    for n in (4,8,16,32,64):
        out[f"m15_momentum_{n}"]=c-c.shift(n)
    for n in (16,32,64):
        hi=d.bh.shift(0).rolling(n).max()
        lo=d.bl.shift(0).rolling(n).min()
        out[f"m15_range_pos_{n}"]=c-(hi+lo)/2.0
    for fast,slow in ((8,21),(12,36),(20,50)):
        out[f"m15_ema_{fast}_{slow}"]=c.ewm(span=fast,adjust=False).mean()-c.ewm(span=slow,adjust=False).mean()
    delta=c.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    out["m15_rsi50"]=100-100/(1+gain/(loss+1e-12))-50

    # hourly and 4-hour bars are available for signals ONLY AFTER the end time.
    x=d.set_index("t")
    for freq,lookbacks,pairs in [
        ("1h",(1,2,4,8,16),((5,15),(8,21))),
        ("4h",(1,2,3,6),((4,12),(6,18)))
    ]:
        gr=x.resample(freq,origin="start_day",label="left",closed="left")
        close=gr.bc.last()
        count=gr.bc.count()
        expected=4 if freq=="1h" else 16
        close=close.where(count==expected)
        # Do not forward-fill missing OHLC bars as data; compare only valid bars.
        for n in lookbacks:
            val=close-close.shift(n)
            out[f"{freq}_momentum_{n}"]=asof_previous_complete(d.t,val,freq)
        for f,s in pairs:
            fa=close.ewm(span=f,adjust=False,min_periods=s).mean()
            sl=close.ewm(span=s,adjust=False,min_periods=s).mean()
            val=(fa-sl).where(close.notna())
            out[f"{freq}_ema_{f}_{s}"]=asof_previous_complete(d.t,val,freq)

    # Yesterday's UTC trading session directional move, available at next day.
    days=x.groupby(x.index.date)
    prev=days.bc.agg(["first","last"])
    prev["dir"]=prev["last"]-prev["first"]
    previous=prev["dir"].shift(1)
    out["prior_utc_day_direction"]=pd.Series([previous.get(k,np.nan) for k in d.t.dt.date],index=d.index)
    # At time-of-day t: bid close of last closed candle vs first bid open
    # of the same UTC day, available before the entry.
    dayopen=d.groupby(d.t.dt.date).bo.transform("first")
    out["intraday_open_move"]=c-dayopen
    return {k:np.asarray(v,dtype=float) for k,v in out.items()}

def asof_previous_complete(t,series,freq):
    # Interval start S, completion time S+1h or S+4h. Only visible at t >= completion.
    ends=series.index+pd.Timedelta(freq)
    end_ns=np.asarray(ends.astype("int64"))
    t_ns=np.asarray(t.astype("int64"))
    k=np.searchsorted(end_ns,t_ns,side="right")-1
    values=series.to_numpy(dtype=float)
    dst=np.full(len(t),np.nan)
    ok=k>=0
    dst[ok]=values[k[ok]]
    return dst

def signals_on_days(d,features):
    dates=np.asarray(d.t.dt.strftime("%Y-%m-%d"))
    month=np.asarray(d.t.dt.strftime("%Y-%m"))
    days={}
    # UTC trading weekdays with >=48 M15 candles and standard hourly
    # 19:45 close. Excludes Sunday and partial holidays by definition.
    for day,g in d.groupby(d.t.dt.strftime("%Y-%m-%d"),sort=True):
        if len(g)<48 or pd.Timestamp(day).weekday()>=5:continue
        index=g.index.to_numpy()
        hh={int(d.t.iloc[k].hour):k for k in index if d.t.iloc[k].minute==0}
        end={h:next((int(k) for k in index if d.t.iloc[k].hour==h-1 and d.t.iloc[k].minute==45),None)
             for h in EXIT_HOURS}
        days[day]={"idx":index, "first":int(index[0]),"hour":hh,"exit":end,"month":day[:7]}
    feature_keys=list(features)
    names=[]
    for f in feature_keys:
        if f=="intraday_open_move":
            names.extend([(f,"trend"),(f,"revert")])
        elif "range_pos" in f:
            names.extend([(f,"trend"),(f,"revert")])
        else:
            names.extend([(f,"trend"),(f,"revert")])
    return days,names

def make_daily_plan(d,days,feats,key,flavor,hour,exit_hour):
    series=feats[key]
    plans=[]
    denom=0
    skip={}
    for day,v in days.items():
        if v["month"] not in FULL and v["month"]!="2026-11":continue
        first=v["first"]
        entry=v["hour"].get(hour)
        stop=v["exit"].get(exit_hour)
        # eligible market day: both entry and planned exit exist with full data
        if entry is None or stop is None or entry>=stop:
            skip[day]="missing_clock"
            continue
        # Required complete history since first, series is shifted by one M15 bar.
        if entry <=0 or not np.isfinite(series[entry-1]):
            skip[day]="insufficient_lookback"
            continue
        denom+=1
        value=series[entry-1]
        side=1 if value>=0 else -1
        if flavor=="revert":side=-side
        plans.append((day,v["month"],entry,stop,side))
    return plans,denom,skip

def run(d,plans,slpips,rr,slippage=0.2):
    # Most recent closed candle signal -> next M15 open, bid/ask priced.
    bo=d.bo.to_numpy();bh=d.bh.to_numpy();bl=d.bl.to_numpy();bc=d.bc.to_numpy()
    ao=d.ao.to_numpy();ah=d.ah.to_numpy();al=d.al.to_numpy();ac=d.ac.to_numpy()
    t=d.t.to_numpy()
    trades=[]
    risk=slpips*PIP
    slip=slippage*PIP
    for day,month,start,end,side in plans:
        entry=(ao[start]+slip) if side==1 else (bo[start]-slip)
        stop=entry-side*risk
        target=entry+side*risk*rr
        fill=None; why=None; jexit=None
        for j in range(start,end+1):
            if side==1:
                if bl[j]<=stop:
                    fill=min(bo[j],stop)-slip;why="SL"
                elif bh[j]>=target:
                    fill=target-slip;why="TP"
                elif j==end:
                    fill=bc[j]-slip;why="TIME"
            else:
                if ah[j]>=stop:
                    fill=max(ao[j],stop)+slip;why="SL"
                elif al[j]<=target:
                    fill=target+slip;why="TP"
                elif j==end:
                    fill=ac[j]+slip;why="TIME"
            if why:
                jexit=j
                break
        if fill is None:raise AssertionError("Did not exit")
        r=(fill-entry)*side/risk
        trades.append((day,month,int(side),float(r),why,int(start),int(jexit)))
    return trades

def metrics(trades):
    n=len(trades)
    r=np.array([t[3] for t in trades],dtype=float)
    monthly={m:0.0 for m in FULL}
    counts={m:0 for m in FULL}
    for row in trades:
        if row[1] in monthly:
            monthly[row[1]]+=row[3]
            counts[row[1]]+=1
    equity=np.r_[0.0,np.cumsum(r)]
    dd=float(np.min(equity-np.maximum.accumulate(equity))) if n else 0
    wins=r[r>0];loss=r[r<0]
    pf=float(wins.sum()/-loss.sum()) if len(loss) else math.inf
    return {
        "trades":n,"netR":float(r.sum()),"expectancyR":float(r.mean()) if n else 0.0,
        "winrate":float(np.mean(r>0)) if n else 0.0,
        "PF":pf,"maxDD_R":dd,
        "positive_full_months":sum(v>0 for v in monthly.values()),
        "recent_3_positive":all(monthly[m]>0 for m in RECENT),
        "recent_minR":min(monthly[m] for m in RECENT),
        "recent_sumR":sum(monthly[m] for m in RECENT),
        "dev_sumR":sum(monthly[m] for m in FULL[:7]),
        "all10_positive":all(monthly[m]>0 for m in FULL),
        "monthly_R":monthly,"monthly_n":counts,
        "TP":sum(t[4]=="TP" for t in trades),"SL":sum(t[4]=="SL" for t in trades),
        "TIME":sum(t[4]=="TIME" for t in trades)
    }

def analyze(path,out):
    d=load_m15(path)
    feats=build_features(d)
    days,names=signals_on_days(d,feats)
    print("FEATURES",len(names),"MARKET DAYS",len(days))
    rows=[]
    plan_cache={}
    benchmark_days=set(day for day,v in days.items() if v["month"] in FULL)
    for hour in ENTRY_HOURS:
      for key,flavor in names:
        for close_h in EXIT_HOURS:
            if hour>=close_h:continue
            plans,denom,skip=make_daily_plan(d,days,feats,key,flavor,hour,close_h)
            daily_coverage=len(set(t[0] for t in plans if t[1] in FULL))/len(benchmark_days)
            # Strict daily signal coverage (no missing eligible day due to feature)
            if daily_coverage < 0.99: continue
            plan_cache[(key,flavor,hour,close_h)]=plans
            for sl in STOPS:
              for rr in RRS:
                trades=run(d,plans,sl,rr)
                stats=metrics(trades)
                rows.append({
                    "feature":key,"direction":flavor,"entry_utc":hour,"exit_utc":close_h,
                    "SL_pips":sl,"RR":rr,"coverage":daily_coverage,
                    **{k:v for k,v in stats.items() if k not in ("monthly_R","monthly_n")},
                    **{f"R_{m}":stats["monthly_R"][m] for m in FULL},
                    **{f"N_{m}":stats["monthly_n"][m] for m in FULL}
                })
    report=pd.DataFrame(rows)
    if report.empty:
        raise RuntimeError("No candidates with >99% daily coverage")
    report=report.sort_values(["recent_3_positive","positive_full_months","recent_minR","netR"],ascending=False)
    root=Path(out);root.mkdir(exist_ok=True,parents=True)
    report.to_csv(root/"all_daily_candidates.csv",index=False,float_format="%.6f")
    qualified=report[(report.recent_3_positive==True)]
    qualified.to_csv(root/"qualified_recent3.csv",index=False,float_format="%.6f")
    strong=report[(report.recent_3_positive==True)&(report.dev_sumR>0)]
    strong.to_csv(root/"qualified_recent3_and_devpositive.csv",index=False,float_format="%.6f")
    report.head(30).to_csv(root/"top30.csv",index=False,float_format="%.6f")
    # Stress all qualifying configurations for 0.5 / 1.0 pip per side.
    stressrows=[]
    for cfg in qualified.head(200).itertuples():
        plans=plan_cache[(cfg.feature,cfg.direction,int(cfg.entry_utc),int(cfg.exit_utc))]
        for slip in (0.2,0.5,1.0):
            stats=metrics(run(d,plans,int(cfg.SL_pips),float(cfg.RR),slip))
            stressrows.append({
               "feature":cfg.feature,"direction":cfg.direction,
               "entry_utc":cfg.entry_utc,"exit_utc":cfg.exit_utc,
               "SL_pips":cfg.SL_pips,"RR":cfg.RR,"slip_pips_side":slip,
               "netR":stats["netR"],"recent_sumR":stats["recent_sumR"],
               "recent_minR":stats["recent_minR"],"recent3positive":stats["recent_3_positive"],
               "dev_sumR":stats["dev_sumR"],"positive_full_months":stats["positive_full_months"],
               "maxDD_R":stats["maxDD_R"],"monthly_R":json.dumps(stats["monthly_R"])
            })
    pd.DataFrame(stressrows).to_csv(root/"stress_top200.csv",index=False,float_format="%.6f")
    meta={
        "data":path,"n_candles":len(d),"first":str(d.t.iloc[0]),"last":str(d.t.iloc[-1]),
        "eligible_full_days":len(benchmark_days),"weekday_days_by_month":
           {m:sum(day.startswith(m) for day in benchmark_days) for m in FULL},
        "entry_utc_hours":ENTRY_HOURS,"exit_utc_hours":EXIT_HOURS,
        "SL_pips":STOPS,"RR":RRS,"signal_features":names,
        "candidates_tested":len(report),"qualifying_recent3":len(qualified),
        "qualifying_recent3_dev_positive":len(strong),
        "qualifying_all10":int(report.all10_positive.sum()),
        "pnl":"R per trade; fixed SL in pips; bid/ask mark; adverse 0.2 pip per side; no fees or swap",
        "limits":["Retrospective exhaustive parameter search; recent 3 months ARE NOT an untouched holdout",
          "Eligible days = weekdays with >=48 M15 bars, scheduled exit candle present; coverage 99% minimum",
          "One scheduled intraday entry each eligible trading day, no weekend overnight carry",
          "MT5 mark-price/spread/commissions/swap/specific execution conditions not independently verified",
          "0.5 and 1.0 pips stress applied to top200 recent3 candidates only"]
        }
    (root/"metadata.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    print("META",json.dumps(meta,default=str))
    print("TOP30",report.head(30).to_string(index=False))
    print("TOP RECENT3+DEV",strong.head(12).to_string(index=False))
    print("STRESS",pd.DataFrame(stressrows).head(20).to_string(index=False))

def selftest():
    # Verify causal H1/H4 availability at period boundary.
    t=pd.date_range("2026-01-05T00:00:00Z",periods=40,freq="15min")
    s=pd.Series(np.arange(10.0),index=pd.date_range("2026-01-05",periods=10,freq="h",tz="UTC"))
    out=asof_previous_complete(pd.Series(t),s,"1h")
    assert np.isnan(out[0]) and np.isnan(out[3]) and out[4]==0 and out[8]==1
    assert (len(FULL)==10 and len(RECENT)==3)
    print("SELFTEST PASS")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="data/exness/EURUSDm_2026/exness_eurusdm_2026_m5_m15_h1.zip")
    ap.add_argument("--out",default="results/v81_daily_recurring_2026")
    ap.add_argument("--selftest",action="store_true")
    args=ap.parse_args()
    if args.selftest: selftest();return
    analyze(args.data,args.out)
if __name__=="__main__": main()
