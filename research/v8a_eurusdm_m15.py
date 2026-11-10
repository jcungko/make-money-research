#!/usr/bin/env python3
"""V8.0-A: EURUSDm M15 frozen-box breakout; READ-ONLY research.
Rules frozen 2026-11-11 before executing this script. Bid candles generate
signals; Ask for BUY entries and SELL exits, Bid for SELL entries and BUY exits.
No MT5 orders, Telegram messages, API secrets, or leverage assumptions.
"""
import argparse
import io
import json
import math
import pathlib
import re
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd

SL_GRID = [0.0010, 0.0015, 0.0020, 0.0025, 0.0030]
RR_GRID = [2, 3, 4, 5, 6]
SLIP_GRID_PIPS = [0.0, 0.2, 0.5]
BASE_SLIP_PIPS = 0.2
PIP = 0.0001
BOX_BARS = 20
ADX_PERIOD = 14
ER_PERIOD = 20
MAX_BOX_AGE = 24
MAX_HOLD_BARS = 192
BREAK_BUFFER_ATR = 0.15

def _normalized(text):
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())

def _column(df, alternatives):
    lookup = {_normalized(c): c for c in df.columns}
    for s in alternatives:
        if _normalized(s) in lookup:
            return lookup[_normalized(s)]
    raise ValueError("Missing column " + repr(alternatives) + ". Available: " + repr(list(df.columns)))

def _read_one(raw, name):
    d = pd.read_csv(io.BytesIO(raw), sep=None, engine="python")
    aliases = {
        "t": ["time_utc", "timestamp_utc", "timestamp", "open_time_utc", "open_time", "datetime", "time", "date"],
        "bo": ["bid_open", "bidopen", "open_bid", "bid_o", "bidopenprice"],
        "bh": ["bid_high", "bidhigh", "high_bid", "bid_h"],
        "bl": ["bid_low", "bidlow", "low_bid", "bid_l"],
        "bc": ["bid_close", "bidclose", "close_bid", "bid_c"],
        "ao": ["ask_open", "askopen", "open_ask", "ask_o"],
        "ah": ["ask_high", "askhigh", "high_ask", "ask_h"],
        "al": ["ask_low", "asklow", "low_ask", "ask_l"],
        "ac": ["ask_close", "askclose", "close_ask", "ask_c"],
    }
    cols = {k: _column(d, vv) for k,vv in aliases.items()}
    out = d[[cols[k] for k in aliases]].copy()
    out.columns = list(aliases)
    if pd.api.types.is_numeric_dtype(out.t):
        t = pd.to_numeric(out.t, errors="coerce")
        unit = "ms" if t.median() > 10**11 else "s"
        out["t"] = pd.to_datetime(t, unit=unit, utc=True, errors="coerce")
    else:
        out["t"] = pd.to_datetime(out.t, utc=True, errors="coerce")
    for k in list(aliases)[1:]:
        out[k] = pd.to_numeric(out[k], errors="coerce")
    return out.dropna()

def load_m15(path):
    out = []
    with zipfile.ZipFile(path) as z:
        if z.testzip():
            raise ValueError("Corrupted archive")
        names = z.namelist()
        pick = [name for name in names if name.lower().endswith(".csv")
                and re.search(r"(^|[^a-z0-9])(m15|15m)([^a-z0-9]|$)", name.lower())]
        if not pick:
            raise ValueError("No M15 CSV in ZIP: " + repr(names[:40]))
        for name in sorted(pick):
            a = _read_one(z.read(name), name)
            print("LOADED",name,len(a),str(a.t.min()),str(a.t.max()))
            out.append(a)
    d = pd.concat(out, ignore_index=True).sort_values("t")
    dup = d.duplicated(subset=["t"], keep="first")
    if dup.any():
        print("DUPLICATES", int(dup.sum()))
        d = d.loc[~dup]
    d = d.reset_index(drop=True)
    if len(d)<100 or not d.t.is_monotonic_increasing:
        raise ValueError("Not enough monotonic M15 candles")
    for a,b,c in [("bo","bh","bl"),("bc","bh","bl"),("ao","ah","al"),("ac","ah","al")]:
        if not ((d[a] <= d[b]+1e-10)&(d[a]>=d[c]-1e-10)).all():
            raise ValueError("Invalid OHLC in "+a)
    if not (d["ao"].ge(d["bo"]-1e-8) & d["ac"].ge(d["bc"]-1e-8)).all():
        raise ValueError("Invalid negative Bid/Ask spread")
    deltas = d.t.diff().dropna().dt.total_seconds()
    bad_delta = (deltas < 900).sum()
    if bad_delta: raise ValueError("Overlapping M15 bars: "+str(bad_delta))
    print("INPUT",len(d),"candles",str(d.t.iloc[0]),str(d.t.iloc[-1]),"non_15m_gaps",int((deltas!=900).sum()))
    return d

def indicators(d):
    h=d.bh.to_numpy(dtype=float); l=d.bl.to_numpy(dtype=float); c=d.bc.to_numpy(dtype=float)
    n=len(d)
    tr=np.zeros(n); plus=np.zeros(n); minus=np.zeros(n)
    tr[0]=h[0]-l[0]
    for i in range(1,n):
        tr[i]=max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        up=h[i]-h[i-1]; down=l[i-1]-l[i]
        plus[i]=up if up>down and up>0 else 0.0
        minus[i]=down if down>up and down>0 else 0.0
    atr=np.full(n,np.nan); adx=np.full(n,np.nan); dx=np.full(n,np.nan)
    tsm=tr[1:15].sum(); psm=plus[1:15].sum(); msm=minus[1:15].sum()
    atr[14]=tsm/14
    for i in range(14,n):
        if i>14:
            tsm=tsm - tsm/14 + tr[i]
            psm=psm - psm/14 + plus[i]
            msm=msm - msm/14 + minus[i]
            atr[i]=tsm/14
        pdi=100*psm/tsm if tsm>0 else 0
        mdi=100*msm/tsm if tsm>0 else 0
        dx[i]=100*abs(pdi-mdi)/(pdi+mdi) if pdi+mdi>0 else 0
    adx[27]=np.mean(dx[14:28])
    for i in range(28,n):
        adx[i]=(13*adx[i-1]+dx[i])/14
    er=np.full(n,np.nan)
    movement=np.abs(np.diff(c))
    for i in range(ER_PERIOD,n):
        path=movement[i-ER_PERIOD:i].sum()
        er[i]=abs(c[i]-c[i-ER_PERIOD])/path if path>0 else 0.0
    return {"atr":atr,"adx":adx,"er":er}

def exit_fill(side, stop, target, slip, bo,bh,bl,bc,ao,ah,al,ac, timeout):
    """Worst-case stop-first on any ambiguous bar, adverse open gap, adverse slip."""
    if side=="BUY":
        if bl<=stop: return min(bo,stop)-slip,"SL"
        if bh>=target: return target-slip,"TP"
        if timeout: return bc-slip,"TIMEOUT"
    else:
        if ah>=stop: return max(ao,stop)+slip,"SL"
        if al<=target: return target+slip,"TP"
        if timeout: return ac+slip,"TIMEOUT"
    return None,None

def run_one(d, feat, stop_frac, rr, slip_pips):
    t=d.t.to_numpy(); bo=d.bo.to_numpy(); bh=d.bh.to_numpy(); bl=d.bl.to_numpy()
    bc=d.bc.to_numpy(); ao=d.ao.to_numpy(); ah=d.ah.to_numpy(); al=d.al.to_numpy(); ac=d.ac.to_numpy()
    atr=feat["atr"]; adx=feat["adx"]; er=feat["er"]; n=len(d)
    box=None; pending=None; position=None; trades=[]; boxes=0; signals=0
    slip=slip_pips*PIP
    for i in range(28,n):
        if pending is not None and position is None:
            side=pending["side"]
            entry=ao[i]+slip if side=="BUY" else bo[i]-slip
            distance=entry*stop_frac
            position={
                "side":side,"entry_i":i,"entry_t":pd.Timestamp(t[i]).isoformat(),
                "entry":entry,"stop":entry-distance if side=="BUY" else entry+distance,
                "target":entry+rr*distance if side=="BUY" else entry-rr*distance,
                "risk_dist":distance,"signal_t":pending["signal_t"],
                "box_upper":pending["upper"],"box_lower":pending["lower"],
                "box_lock_t":pending["lock_t"],
            }
            pending=None
        if position is not None:
            timeout=(i-position["entry_i"]>=MAX_HOLD_BARS-1) or (i==n-1)
            fill,reason=exit_fill(position["side"],position["stop"],position["target"],slip,
                                  bo[i],bh[i],bl[i],bc[i],ao[i],ah[i],al[i],ac[i],timeout)
            if reason:
                side=position["side"]
                gross=fill-position["entry"] if side=="BUY" else position["entry"]-fill
                trades.append({
                    "SL_pct":round(stop_frac*100,4),"RR":rr,"slippage_pips_side":slip_pips,
                    "side":side,"entry_time_utc":position["entry_t"],
                    "exit_time_utc":pd.Timestamp(t[i]).isoformat(),
                    "entry":position["entry"],"exit":fill,
                    "stop":position["stop"],"target":position["target"],
                    "signal_time_utc":position["signal_t"],"box_lock_utc":position["box_lock_t"],
                    "box_top":position["box_upper"],"box_bottom":position["box_lower"],
                    "hold_bars":i-position["entry_i"]+1,
                    "exit_reason":reason,"R_net":gross/position["risk_dist"],
                })
                position=None
        if position is not None or pending is not None:
            continue
        if box is not None:
            age=i-box["lock_i"]
            if age>MAX_BOX_AGE:
                box=None
            elif age>=1:
                candle_range=bh[i]-bl[i]
                body=abs(bc[i]-bo[i])
                if candle_range>0 and body/candle_range>=0.5:
                    side=None
                    if bc[i]>box["upper"]+BREAK_BUFFER_ATR*box["atr"] and bc[i]>bo[i]:
                        side="BUY"
                    elif bc[i]<box["lower"]-BREAK_BUFFER_ATR*box["atr"] and bc[i]<bo[i]:
                        side="SELL"
                    if side:
                        pending={"side":side,"signal_t":pd.Timestamp(t[i]).isoformat(),
                                 "upper":box["upper"],"lower":box["lower"],"lock_t":box["lock_t"]}
                        signals+=1
                        box=None
        if box is None and pending is None and i>=BOX_BARS and np.isfinite(adx[i]):
            upper=float(bh[i-BOX_BARS+1:i+1].max())
            lower=float(bl[i-BOX_BARS+1:i+1].min())
            width=(upper-lower)/atr[i] if atr[i]>0 else math.inf
            if adx[i]<20 and er[i]<0.35 and 1.5<=width<=3.5:
                box={"upper":upper,"lower":lower,"atr":atr[i],
                     "lock_i":i,"lock_t":pd.Timestamp(t[i]).isoformat()}
                boxes+=1
    return pd.DataFrame(trades),{"boxes":boxes,"breakout_signals":signals}

def summarize(trades, info, sl_pct, rr, slip_pips, months):
    if trades.empty:
        a=np.zeros(0)
    else:
        trades=trades.sort_values(["exit_time_utc","entry_time_utc"])
        a=trades.R_net.to_numpy()
    eq=np.r_[0.0,np.cumsum(a)]
    dd=(eq-np.maximum.accumulate(eq)).min()
    wins=a[a>0]; losses=a[a<0]
    pf=(wins.sum()/(-losses.sum())) if len(losses) else (float("inf") if len(wins) else 0)
    mon={}
    for m in months:
        subset=trades.loc[trades.entry_time_utc.str.slice(0,7)==m] if not trades.empty else pd.DataFrame()
        mon[m]=(len(subset),float(subset.R_net.sum()) if len(subset) else 0.0)
    return {
        "SL_pct":sl_pct,"RR":rr,"slippage_pips_side":slip_pips,"trades":len(a),
        "winrate_pct":round(100*len(wins)/len(a),3) if len(a) else 0.0,
        "net_R":round(a.sum(),5),"expectancy_R":round(a.mean(),5) if len(a) else 0.0,
        "profit_factor":round(pf,4),"max_drawdown_R":round(float(dd),5),
        "tp_trades":int((trades.exit_reason=="TP").sum()) if not trades.empty else 0,
        "sl_trades":int((trades.exit_reason=="SL").sum()) if not trades.empty else 0,
        "timeout_trades":int((trades.exit_reason=="TIMEOUT").sum()) if not trades.empty else 0,
        "positive_months":sum(1 for n,r in mon.values() if r>0),
        "negative_months":sum(1 for n,r in mon.values() if r<0),
        "no_trade_months":sum(1 for n,r in mon.values() if n==0),
        "boxes_detected":info["boxes"],"breakout_signals":info["breakout_signals"],
    }, [
        {"SL_pct":sl_pct,"RR":rr,"slippage_pips_side":slip_pips,
         "month_utc":m,"trades":x[0],"net_R":round(x[1],5)}
        for m,x in mon.items()
    ]

def self_test():
    assert exit_fill("BUY",1.09,1.12,0.0,1.10,1.13,1.08,1.11,1.1001,1.1301,1.0801,1.1101,False)==(1.09,"SL")
    assert exit_fill("SELL",1.12,1.08,0.0,1.10,1.13,1.07,1.11,1.1001,1.1301,1.0701,1.1101,False)==(1.12,"SL")
    assert exit_fill("BUY",1.09,1.12,0.0,1.08,1.13,1.07,1.11,1.0801,1.1301,1.0701,1.1101,False)==(1.08,"SL")
    assert exit_fill("BUY",1.09,1.12,0.0,1.10,1.13,1.10,1.11,1.1001,1.1301,1.1001,1.1101,False)==(1.12,"TP")
    assert len(SL_GRID)*len(RR_GRID)==25
    print("SELF-TEST OK stop-first, adverse gaps, distinct grids")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="data/exness/EURUSDm_2026/exness_eurusdm_2026_m5_m15_h1.zip")
    ap.add_argument("--out",default="results/v8a_box_breakout_2026")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test: self_test(); return
    d=load_m15(args.data); feat=indicators(d)
    out=pathlib.Path(args.out); out.mkdir(parents=True,exist_ok=True)
    months=pd.period_range(d.t.min().tz_localize(None).to_period("M"),d.t.max().tz_localize(None).to_period("M"),freq="M").astype(str).tolist()
    summaries=[]; monthly=[]; alltrades=[]
    for slip in SLIP_GRID_PIPS:
        for sl in SL_GRID:
            for rr in RR_GRID:
                trades,info=run_one(d,feat,sl,rr,slip)
                summary, mon=summarize(trades,info,round(100*sl,4),rr,slip,months)
                summaries.append(summary); monthly.extend(mon)
                if not trades.empty:
                    alltrades.append(trades)
                print("RESULT",sl,rr,slip,summary["trades"],summary["net_R"],summary["max_drawdown_R"])
    summ=pd.DataFrame(summaries); months_df=pd.DataFrame(monthly)
    trades_df=pd.concat(alltrades,ignore_index=True) if alltrades else pd.DataFrame()
    summ.to_csv(out/"summary_all_slippage.csv",index=False)
    summ.loc[summ.slippage_pips_side==BASE_SLIP_PIPS].to_csv(out/"summary_25.csv",index=False)
    months_df.to_csv(out/"monthly_all.csv",index=False)
    trades_df.to_csv(out/"trades_all.csv",index=False)
    meta={
       "study":"V8.0-A EURUSDm M15 breakout, in-sample retrospective, research only",
       "rules":"20 completed Bid candles, ADX14<20, ER20<0.35, boxwidth/ATR14=[1.5,3.5]. Freeze box 24 bars. M15 closes beyond edge by 0.15*ATR14(lock), bullish/bearish real body >=50% of Bid range. Entry at next M15 open Ask for BUY / Bid for SELL. Fixed SL as entry percentage, TP multiple. Single trade, single signal per frozen box. 192 M15 bars max. Same-bar STOP-FIRST. Bid marks long exits, Ask marks short exits. Adverse slippage each side. Commission 0 (Standard assumption); swap/overnight financing excluded.",
       "source":"Public Exness-derived tick archive transformed and committed to project Github; NOT broker MT5 execution logs",
       "input_archive":args.data,
       "time_first_utc":str(d.t.min()),"time_last_utc":str(d.t.max()),"n_candles":len(d),
       "sl_percent":[round(x*100,3) for x in SL_GRID],
       "RR":RR_GRID,"slippage_pips_per_side":SLIP_GRID_PIPS,"baseline_slippage_pips":BASE_SLIP_PIPS,
       "limitations":["in-sample exploration, not prospectively unseen","missing true MT5 liquidity/fill and swap",
                      "M15 candles cannot determine intrabar event chronology; stop-first is pessimistic",
                      "raw tick archive vs monthly tick archive discrepancies unresolved",
                      "stop loss/TP use percentage price distances, not percent of account balance",
                      "number of trades can vary across SL and TP due to one position at a time"]
    }
    (out/"metadata.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
    top=summ[(summ.slippage_pips_side==BASE_SLIP_PIPS)].sort_values("net_R",ascending=False).head(10)
    print("BASELINE TOP10\n",top.to_string(index=False))
    print("FILES",list(map(str,out.iterdir())))
if __name__=="__main__": main()
