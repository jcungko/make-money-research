#!/usr/bin/env python3
"""Research only: Exness EURUSD October 2026 intrabar M1/M5 screen.

Predeclared strategies with train/untouched final-week validation. No trading,
no broker connection, no strategy modification, no hypothetical mid fills.
A trade must enter after a candle starts and exit at a wall-clock timeout
before the candle ends. Prices are Exness Bid/Ask observed up to that timeout.
"""
from __future__ import annotations
import io
import json
import math
import hashlib
import itertools
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

SOURCE = "https://ticks.ex2archive.com/ticks/EURUSD/2026/10/Exness_EURUSD_2026_10.zip"
TARGET = Path("results/eurusd_oct2026_intrabar_30pct")
SOURCE_SHA256 = "43229b754eac1dc42d695cf6b92a12a223a431e101451823c82cefb4b9309ad1"
START = pd.Timestamp("2026-10-01T00:00:00Z")
HOLDOUT = pd.Timestamp("2026-10-26T00:00:00Z")
END = pd.Timestamp("2026-11-01T00:00:00Z")
NS = 1_000_000_000
PIP = 10000.0
# The simulated all-in execution cost is the observed Bid/Ask crossing,
# plus a further 0.05 pip adverse slippage per side (=0.10 pip round trip).
SLIP_RT = 0.10
STRESS_SLIP_RT = 0.30
RAW_ACCOUNT_COMMISSION_PIPS_RT = 0.70
SCHEDULES = {
    "M1": [(10,45), (15,50), (20,55), (30,55)],
    "M5": [(30,210), (60,240), (90,270), (120,270)],
}
SIGNALS = (
    "cur_momentum", "cur_reversal",
    "recent_momentum", "recent_reversal",
    "prev_momentum", "prev_reversal",
    "prev3_momentum", "prev3_reversal",
    "acceleration_momentum", "acceleration_reversal",
)
STRENGTHS = (0.0, 0.2)  # Minimum absolute signal in EURUSD pips
SPREAD_FILTERS = ("all", "p80")  # p80 fitted from training only
SESSIONS = ("all", "liquid_06_20_utc")
MAX_TOP = 20

def load_ticks():
    r=requests.get(SOURCE, timeout=(30,240))
    r.raise_for_status()
    blob=r.content
    sha=hashlib.sha256(blob).hexdigest()
    if sha!=SOURCE_SHA256:
        raise ValueError("Source archive changed; abort to protect reproducibility. "+sha)
    ticks=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=[n for n in z.namelist() if n.lower().endswith(".csv")]
        for name in members:
            with z.open(name) as f:
                for chunk in pd.read_csv(f,usecols=["Timestamp","Bid","Ask"],
                                         dtype={"Bid":"float64","Ask":"float64"},chunksize=250000):
                    ticks.append(chunk)
    frame=pd.concat(ticks,ignore_index=True)
    ts=pd.to_datetime(frame["Timestamp"],utc=True,format="ISO8601",errors="raise")
    if not (ts.is_monotonic_increasing and (ts>=START).all() and (ts<END).all()):
        raise ValueError("Tick timestamps unsorted/out of October")
    b=frame["Bid"].to_numpy(dtype=np.float64)
    a=frame["Ask"].to_numpy(dtype=np.float64)
    if not (np.isfinite(b).all() and np.isfinite(a).all() and (a>=b).all()):
        raise ValueError("Invalid/crossed bids and asks")
    if len(frame)!=1039321:
        raise ValueError(f"Unexpected Exness tick count {len(frame)}")
    return ts.astype("int64").to_numpy(),b,a,sha

def pack_bars(ts, bid, ask, timeframe, entry_s, exit_s):
    step={"M1":60,"M5":300}[timeframe]
    stepns=step*NS
    bar_id=ts//stepns
    first=np.r_[0,1+np.flatnonzero(bar_id[1:]!=bar_id[:-1])]
    last=np.r_[first[1:],len(ts)]
    n=len(first)
    open_ns=bar_id[first]*stepns
    mid=(bid+ask)*0.5
    # As of entry_s: latest *previously known* quote, not entry execution.
    # At entry: first quote strictly after signal cutoff (no lookahead).
    entry_pos=np.searchsorted(ts,open_ns+entry_s*NS,side="right")
    signal_pos=entry_pos-1
    # At clock timeout: last available quote, no future tick information.
    exit_pos=np.searchsorted(ts,open_ns+exit_s*NS,side="right")-1
    prev_recent=np.searchsorted(ts,open_ns+(entry_s-(10 if timeframe=="M1" else 30))*NS,side="right")-1
    prev_recent=np.maximum(prev_recent,first)
    valid=(entry_pos<last)&(signal_pos>=first)&(exit_pos>=entry_pos)&(exit_pos<last)
    # Some candles can lack quotes at entry or after planned timeout.
    s=np.minimum(np.maximum(signal_pos,first),last-1)
    e=np.minimum(np.maximum(entry_pos,first),last-1)
    x=np.minimum(np.maximum(exit_pos,first),last-1)
    q=np.minimum(np.maximum(prev_recent,first),last-1)
    prior=np.maximum(np.arange(n)-1,0)
    prev3=np.maximum(np.arange(n)-3,0)
    # Disallow previous-candle signals across market closures/time gaps.
    contiguous1=np.r_[False,(open_ns[1:]-open_ns[:-1])==stepns]
    contiguous3=np.zeros(n,dtype=bool)
    contiguous3[3:]=(open_ns[3:]-open_ns[:-3])==3*stepns
    prior_change=(mid[last[prior]-1]-mid[first[prior]])*PIP
    prev3_change=(mid[last[prior]-1]-mid[first[prev3]])*PIP
    prior_change=np.where(contiguous1,prior_change,0.0)
    prev3_change=np.where(contiguous3,prev3_change,0.0)
    cur=(mid[s]-mid[first])*PIP
    recent=(mid[s]-mid[q])*PIP
    accel=(mid[s]-2*mid[q]+mid[first])*PIP
    spread=(ask[s]-bid[s])*PIP
    times=pd.DatetimeIndex(pd.to_datetime(open_ns,utc=True))
    hours=times.hour.to_numpy()
    train=np.array(open_ns<HOLDOUT.value)
    test=~train
    return {
        "n":n,"valid":valid,"entry":e,"exit":x,
        "start":open_ns,"time":times,"train":train,"test":test,
        "spread":spread,"hours":hours,
        "dir_inputs":{
            "cur_momentum":cur,"cur_reversal":-cur,
            "recent_momentum":recent,"recent_reversal":-recent,
            "prev_momentum":prior_change,"prev_reversal":-prior_change,
            "prev3_momentum":prev3_change,"prev3_reversal":-prev3_change,
            "acceleration_momentum":accel,"acceleration_reversal":-accel,
        },
        "buy_pips":(bid[x]-ask[e])*PIP,
        "sell_pips":(bid[e]-ask[x])*PIP,
        "entry_quote_count":e-first,
        "exit_quote_count":x-first,
        "actual_entry_at_ns":ts[e],
        "actual_exit_quote_ns":ts[x],
        "bid":bid,"ask":ask
    }

def train_score(pnl):
    if len(pnl)<2:
        return -1e9
    v=float(np.std(pnl,ddof=1))
    return float(np.mean(pnl)/v*math.sqrt(len(pnl))) if v>1e-10 else -1e9

def stats(bars, side, selected, pnl, train_mask=None):
    m=selected if train_mask is None else selected & train_mask
    p=pnl[m]
    n=int(m.sum())
    days=bars["time"][m].strftime("%Y-%m-%d")
    d={}
    for day,val in zip(days,p):
        d[day]=d.get(day,0.0)+float(val)
    wins=sum(x>0 for x in p)
    gross_win=sum(x for x in p if x>0)
    gross_loss=sum(x for x in p if x<0)
    return {
        "trades":n,
        "buy_trades":int((selected&(side==1)&(train_mask if train_mask is not None else True)).sum()),
        "sell_trades":int((selected&(side==-1)&(train_mask if train_mask is not None else True)).sum()),
        "net_pips":round(float(np.sum(p)),3),
        "avg_pips":round(float(np.mean(p)),5) if n else None,
        "win_rate":round(wins/n,5) if n else None,
        "profit_factor":round(gross_win/-gross_loss,4) if gross_loss < 0 else None,
        "positive_days":sum(v>0 for v in d.values()),
        "negative_days":sum(v<0 for v in d.values()),
        "t_score":round(train_score(p),4),
    }

def screen_frame(ts,bid,ask,tf):
    all_candidates=[]
    n_bars=None
    for entry_s,exit_s in SCHEDULES[tf]:
        bars=pack_bars(ts,bid,ask,tf,entry_s,exit_s)
        n=bars["n"]
        if n_bars is None:
            n_bars=n
        elif n_bars!=n:
            raise AssertionError("Bar count changed across schedules")
        expected=31284 if tf=="M1" else 6285
        if n!=expected:
            raise AssertionError(f"{tf}: expected {expected} unique candles, found {n}")
        base=bars["valid"]
        spread80=float(np.quantile(bars["spread"][base&bars["train"]],0.80))
        # Net executable P&L crosses the contemporaneous bid/ask on both sides.
        # No mid-price profits. Constant extra slip is adverse round-trip.
        buy_net=bars["buy_pips"]-SLIP_RT
        sell_net=bars["sell_pips"]-SLIP_RT
        for signal,strength,spread_filter,session in itertools.product(SIGNALS,STRENGTHS,SPREAD_FILTERS,SESSIONS):
            val=bars["dir_inputs"][signal]
            side=np.where(val>strength,1,np.where(val<-strength,-1,0))
            # A reversal signal uses sign-flipped values, so strength gating stays causal.
            sel=base&(side!=0)
            if spread_filter=="p80":
                sel=sel&(bars["spread"]<=spread80)
            if session=="liquid_06_20_utc":
                sel=sel&(bars["hours"]>=6)&(bars["hours"]<20)
            cnt=int(sel.sum())
            # Strictly > 30% of all available October bars, without rounding errors.
            if cnt*10<=n*3:
                continue
            train_cnt=int((sel&bars["train"]).sum())
            test_cnt=int((sel&bars["test"]).sum())
            train_bars=int(bars["train"].sum())
            test_bars=int(bars["test"].sum())
            # Require same frequency floor in untouched holdout AND training.
            if train_cnt*10<=train_bars*3 or test_cnt*10<=test_bars*3:
                continue
            pnl=np.where(side==1,buy_net,sell_net)
            train_stats=stats(bars,side,sel,pnl,bars["train"])
            test_stats=stats(bars,side,sel,pnl,bars["test"])
            full_stats=stats(bars,side,sel,pnl)
            # Rank using training only, never final-week performance.
            all_candidates.append({
                "id":f"{tf}_e{entry_s}_x{exit_s}_{signal}_{strength:.1f}_{spread_filter}_{session}",
                "tf":tf,"signal":signal,"threshold_pips":strength,
                "spread_filter":spread_filter,"spread80_pips_training":round(spread80,5),
                "session":session,"entry_second":entry_s,"exit_second":exit_s,
                "exit_mechanism":"clock-close using latest observed quote at deadline; no take-profit/stop-loss",
                "monthly_trade_fraction":round(cnt/n,5),
                "train_trade_fraction":round(train_cnt/train_bars,5),
                "holdout_trade_fraction":round(test_cnt/test_bars,5),
                "train":train_stats,"holdout":test_stats,"month":full_stats,
                "month_net_pips_no_extra_slippage":round(full_stats["net_pips"]+cnt*SLIP_RT,3),
                "month_net_pips_slip_0p3":round(full_stats["net_pips"]-cnt*(STRESS_SLIP_RT-SLIP_RT),3),
                "month_net_pips_slip_0p1_plus_raw_commission_0p7":round(full_stats["net_pips"]-cnt*RAW_ACCOUNT_COMMISSION_PIPS_RT,3),
                "test_pass_profit":test_stats["net_pips"]>0,
                "monthly_pass_profit":full_stats["net_pips"]>0,
            })
    # All research results are retained; best candidates are selected only by in-sample PnL/stability.
    all_candidates.sort(key=lambda x:(
        x["train"]["net_pips"]>0,
        x["train"]["t_score"],
        x["train"]["net_pips"]
    ),reverse=True)
    passing=[c for c in all_candidates if c["train"]["net_pips"]>0 and c["holdout"]["net_pips"]>0 and c["month"]["net_pips"]>0]
    return {
        "candles":n_bars,
        "required_trades_strictly_gt_30pct":(3*n_bars)//10+1,
        "predefined_combinations":len(SCHEDULES[tf])*len(SIGNALS)*len(STRENGTHS)*len(SPREAD_FILTERS)*len(SESSIONS),
        "frequency_qualified_combinations":len(all_candidates),
        "frequency_and_positive_training":sum(x["train"]["net_pips"]>0 for x in all_candidates),
        "frequency_and_positive_month":sum(x["month"]["net_pips"]>0 for x in all_candidates),
        "frequency_and_positive_holdout":sum(x["holdout"]["net_pips"]>0 for x in all_candidates),
        "positive_train_holdout_and_month":len(passing),
        "top_train_only":all_candidates[:MAX_TOP],
        "passing_sorted_by_train_only":passing[:MAX_TOP],
    },all_candidates

def main():
    ts,bid,ask,sha=load_ticks()
    TARGET.mkdir(parents=True,exist_ok=True)
    results={}
    full_candidates=[]
    for tf in ("M1","M5"):
        report,cands=screen_frame(ts,bid,ask,tf)
        results[tf]=report
        full_candidates.extend(cands)
        print(tf,"bars",report["candles"],"frequency qualified",len(cands),
              "positive train+holdout+month",report["positive_train_holdout_and_month"],
              flush=True)
    # Save all eligible candidates to prevent hiding failed configurations.
    allpath=TARGET/"all_frequency_qualified.csv"
    pd.json_normalize(full_candidates).drop(columns=[
        "top_train_only","passing_sorted_by_train_only"],errors="ignore").to_csv(allpath,index=False)
    summary={
        "research_version":"EURUSD-OCT2026-INTRABAR-30PCT-1",
        "symbol":"EURUSD", "source":SOURCE,"source_sha256":sha,
        "source_tick_rows":len(ts),"timezone":"UTC","open_close_same_candle":True,
        "non_overlap_trades":True,
        "train_period":"2026-10-01 00:00 UTC to 2026-10-25 23:59 UTC",
        "untouched_holdout_period":"2026-10-26 00:00 UTC to 2026-10-30 market close",
        "price_model":"entry at first observed quote strictly after signal offset; exit at deadline with latest available quote (may be stale); buys pay Ask and sell at Bid; sells enter at Bid and exit at Ask",
        "extra_adverse_slippage_pips_round_trip":SLIP_RT,
        "stress_extra_adverse_slippage_pips_round_trip":STRESS_SLIP_RT,
        "additional_commission_if_raw_spread_pips_round_trip":RAW_ACCOUNT_COMMISSION_PIPS_RT,
        "no_guaranteed_broker_fill":True,
        "warning":"No intrabar protective SL and no guaranteed execution. Large backtests of frequent trades risk severe overfitting. Test-week evaluated after screening.",
        "selection_rule":"Top candidates ranked only by train t-score, then train net. Train, holdout, full month all must be positive to report validation-qualified; all candidates and failures logged.",
        "frames":results,
        "created_utc":datetime.now(timezone.utc).isoformat(),
    }
    (TARGET/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    lines=["# EURUSD October 2026 same-candle trades (>30% frequency)",
           "Source: Exness public Bid/Ask archive; UTC; extra 0.10 pip round-trip simulated slippage, plus actual Bid/Ask crossing.",
           "Training dates: Oct 1–25; untouched holdout Oct 26–30. No current trading deployment.",
           ""]
    for tf,rep in results.items():
        lines += [f"## {tf}",
                  f"Bars {rep['candles']}, required trades {rep['required_trades_strictly_gt_30pct']}; "
                  f"screened {rep['predefined_combinations']}, frequency qualified {rep['frequency_qualified_combinations']}; "
                  f"month positive {rep['frequency_and_positive_month']}, validation-qualified {rep['positive_train_holdout_and_month']}.",
                  ""]
        for item in rep["passing_sorted_by_train_only"][:5]:
            lines.append(f"- {item['id']}: {item['month']['trades']} trades; month {item['month']['net_pips']} pips; "
                         f"train {item['train']['net_pips']} pips; holdout {item['holdout']['net_pips']} pips.")
        if not rep["passing_sorted_by_train_only"]:
            lines.append("- No verified positive candidates meeting all frequency and holdout requirements.")
        lines.append("")
    (TARGET/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({tf:{k:v for k,v in x.items() if k not in ("top_train_only","passing_sorted_by_train_only")}
                      for tf,x in results.items()},ensure_ascii=False),flush=True)
if __name__=="__main__":
    main()
