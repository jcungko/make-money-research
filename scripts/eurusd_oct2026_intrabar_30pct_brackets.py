#!/usr/bin/env python3
"""Independent preregistered intra-candle TP/SL extension of October EURUSD screen.

Entry signals learned by train only, stop/take triggered at executable side of
Exness quotes in chronological order, remaining positions close before bar end.
No broker order execution or guarantees.
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

from eurusd_oct2026_intrabar_30pct import load_ticks,pack_bars,stats,SLIP_RT,STRESS_SLIP_RT,RAW_ACCOUNT_COMMISSION_PIPS_RT

OUT=Path("results/eurusd_oct2026_intrabar_30pct_brackets")
SCHEDULES={"M1":[(10,55),(20,55)],"M5":[(30,270),(90,270)]}
SIGNALS=("cur_momentum","cur_reversal","recent_momentum","recent_reversal","prev_momentum","prev_reversal")
STRENGTHS=(0.0,0.2)
BRACKETS=((0.5,0.5),(0.7,1.2),(1.2,1.2),(1.5,2.0),(2.0,1.0),(2.0,3.0))
SPREAD_FILTERS=("all","p80")
SESSIONS=("all","liquid_06_20_utc")

def bracket_pnl(bars,bid,ask,stop_pips,take_pips):
    n=bars["n"]
    entry=bars["entry"]
    scheduled=bars["exit"]
    valid=bars["valid"]&(scheduled>entry)
    buy=np.zeros(n,dtype=np.float64)
    sell=np.zeros(n,dtype=np.float64)
    eventbuy={"tp":0,"sl":0,"clock":0}
    eventsell={"tp":0,"sl":0,"clock":0}
    stop=stop_pips/10000.0
    take=take_pips/10000.0
    for i in np.flatnonzero(valid):
        e=int(entry[i]); x=int(scheduled[i])
        # All possible automatic exits are evaluated in chronological
        # order from strictly after entry to the scheduled same-bar deadline.
        path_buy=bid[e+1:x+1]
        ask_entry=ask[e]
        hit_tp=np.flatnonzero(path_buy>=ask_entry+take)
        hit_sl=np.flatnonzero(path_buy<=ask_entry-stop)
        tp_at=int(hit_tp[0]) if len(hit_tp) else len(path_buy)+1
        sl_at=int(hit_sl[0]) if len(hit_sl) else len(path_buy)+1
        if tp_at<sl_at and tp_at<len(path_buy):
            bx=e+1+tp_at
            eventbuy["tp"]+=1
        elif sl_at<=tp_at and sl_at<len(path_buy):
            bx=e+1+sl_at
            eventbuy["sl"]+=1
        else:
            bx=x
            eventbuy["clock"]+=1
        buy[i]=(bid[bx]-ask[e])*10000-SLIP_RT

        path_sell=ask[e+1:x+1]
        bid_entry=bid[e]
        tp_short=np.flatnonzero(path_sell<=bid_entry-take)
        sl_short=np.flatnonzero(path_sell>=bid_entry+stop)
        t_at=int(tp_short[0]) if len(tp_short) else len(path_sell)+1
        s_at=int(sl_short[0]) if len(sl_short) else len(path_sell)+1
        if t_at<s_at and t_at<len(path_sell):
            sx=e+1+t_at
            eventsell["tp"]+=1
        elif s_at<=t_at and s_at<len(path_sell):
            sx=e+1+s_at
            eventsell["sl"]+=1
        else:
            sx=x
            eventsell["clock"]+=1
        sell[i]=(bid[e]-ask[sx])*10000-SLIP_RT
    return valid,buy,sell

def do_frame(ts,bid,ask,tf):
    records=[]
    count_bar=None
    tested=0
    preprocessed={}
    for e_s,x_s in SCHEDULES[tf]:
        bars=pack_bars(ts,bid,ask,tf,e_s,x_s)
        count_bar=bars["n"]
        spread80=float(np.quantile(bars["spread"][bars["valid"]&bars["train"]],0.80))
        for stop,take in BRACKETS:
            executable,buy,sell=bracket_pnl(bars,bid,ask,stop,take)
            for signal,strength,sp_filter,session in itertools.product(SIGNALS,STRENGTHS,SPREAD_FILTERS,SESSIONS):
                tested+=1
                value=bars["dir_inputs"][signal]
                side=np.where(value>strength,1,np.where(value<-strength,-1,0))
                sel=executable & (side!=0)
                if sp_filter=="p80":
                    sel&=(bars["spread"]<=spread80)
                if session=="liquid_06_20_utc":
                    sel&=(bars["hours"]>=6)&(bars["hours"]<20)
                ntr=int(sel.sum())
                n=count_bar
                if ntr*10<=n*3:
                    continue
                ntrain=int((sel & bars["train"]).sum())
                ntest=int((sel & bars["test"]).sum())
                if ntrain*10<=int(bars["train"].sum())*3 or ntest*10<=int(bars["test"].sum())*3:
                    continue
                pnl=np.where(side==1,buy,sell)
                train=stats(bars,side,sel,pnl,bars["train"])
                test=stats(bars,side,sel,pnl,bars["test"])
                month=stats(bars,side,sel,pnl)
                records.append({
                    "id":f"{tf}_e{e_s}_x{x_s}_{signal}_{strength:.1f}_{sp_filter}_{session}_SL{stop}_TP{take}",
                    "tf":tf,"signal":signal,"minimum_signal_pips":strength,
                    "spread_filter":sp_filter,"spread80_training_pips":round(spread80,4),
                    "session":session,"entry_second":e_s,"last_exit_second":x_s,
                    "stop_pips":stop,"take_pips":take,
                    "frequency":round(ntr/n,5),
                    "train":train,"holdout":test,"month":month,
                    "month_no_extra_slippage_pips":round(month["net_pips"]+ntr*SLIP_RT,3),
                    "month_0p3_slippage_pips":round(month["net_pips"]-ntr*(STRESS_SLIP_RT-SLIP_RT),3),
                    "month_0p1_slippage_plus_0p7_raw_commission_pips":round(month["net_pips"]-ntr*RAW_ACCOUNT_COMMISSION_PIPS_RT,3),
                })
    # Candidate ranking is strictly based on the train split.
    records.sort(key=lambda x:(x["train"]["net_pips"]>0,x["train"]["t_score"],x["train"]["net_pips"]),reverse=True)
    passing=[x for x in records if x["train"]["net_pips"]>0 and x["holdout"]["net_pips"]>0 and x["month"]["net_pips"]>0]
    return {
        "candles":count_bar,
        "required_min_trades":(count_bar*3)//10+1,
        "grid_size":tested,
        "frequency_qualified":len(records),
        "train_profitable":sum(x["train"]["net_pips"]>0 for x in records),
        "month_profitable":sum(x["month"]["net_pips"]>0 for x in records),
        "holdout_profitable":sum(x["holdout"]["net_pips"]>0 for x in records),
        "train_holdout_month_positive":len(passing),
        "best_train_10":records[:10],
        "validated_10":passing[:10],
    },records

def main():
    ts,bid,ask,sha=load_ticks()
    OUT.mkdir(parents=True,exist_ok=True)
    reports={}
    rows=[]
    for tf in ("M1","M5"):
        rep,rec=do_frame(ts,bid,ask,tf)
        reports[tf]=rep
        rows.extend(rec)
        print(tf,{k:v for k,v in rep.items() if k not in ("best_train_10","validated_10")},flush=True)
    pd.json_normalize(rows).to_csv(OUT/"all_frequency_qualified.csv",index=False)
    result={
        "source":"Exness public tick archive","source_sha256":sha,
        "symbol":"EURUSD","timezone":"UTC",
        "train_period":"2026-10-01 to 2026-10-25 UTC",
        "holdout_period":"2026-10-26 to 2026-10-30 UTC",
        "rule":"one trade max per bar; entry on next tick strictly after signal; TP/SL hit only on executable Bid for BUY or Ask for SELL; otherwise clock exit before bar end",
        "costs":"market Bid/Ask observed, plus adverse 0.10 pip roundtrip slippage, no commission in baseline",
        "caveats":["Exness history is indicative, no guaranteed live fills.","Clock close uses last quote before deadline, live fill may differ.","Fixed bracket exits use first observed quote that crosses TP/SL; gap losses may exceed stated stop.","Screen is exploratory; train/holdout positives do not guarantee profitability."],
        "reports":reports,"created_utc":datetime.now(timezone.utc).isoformat(),
    }
    (OUT/"summary.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("Saved",OUT,flush=True)
if __name__=="__main__":
    main()
