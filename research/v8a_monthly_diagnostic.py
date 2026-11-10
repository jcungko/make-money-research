#!/usr/bin/env python3
"""Post-backtest diagnostic for V8-A 0.30% SL, 5R TP; read-only.
Builds small audit files from already committed V8-A trades and M15 candles.
"""
import json
import pathlib
import numpy as np
import pandas as pd
from v8a_eurusdm_m15 import load_m15

ROOT=pathlib.Path("results/v8a_box_breakout_2026")
SL=0.30
RR=5
SLIP=0.2
def nice(x):
    return None if pd.isna(x) else round(float(x),4)

def main():
    d=load_m15("data/exness/EURUSDm_2026/exness_eurusdm_2026_m5_m15_h1.zip")
    logs=pd.read_csv(ROOT/"trades_all.csv")
    ts=logs[(np.isclose(logs.SL_pct,SL))&(logs.RR==RR)&(np.isclose(logs.slippage_pips_side,SLIP))].copy()
    if len(ts)!=107:
        raise ValueError(f"Expected 107 baseline trades, found {len(ts)}")
    ts["entry_dt"]=pd.to_datetime(ts.entry_time_utc,utc=True)
    ts["exit_dt"]=pd.to_datetime(ts.exit_time_utc,utc=True)
    ts=ts.sort_values("entry_dt").reset_index(drop=True)
    ts["month"]=ts.entry_dt.dt.strftime("%Y-%m")
    ts["is_win"]=ts.R_net>0
    ts["is_loss"]=ts.R_net<0
    ts["duration_hours"]=(ts.exit_dt-ts.entry_dt).dt.total_seconds()/3600
    d["timeindex"]=pd.to_datetime(d.t,utc=True)
    idx={x:i for i,x in enumerate(d["timeindex"])}
    back_in_box=[]; mfe=[]; mae=[]; close4=[]
    for row in ts.itertuples(index=False):
        s=idx[row.entry_dt]; e=idx[row.exit_dt]
        direction=1 if row.side=="BUY" else -1
        in_box_4=False
        for k in range(s,min(e+1,s+4)):
            close=d.iloc[k].bc
            if row.box_bottom<=close<=row.box_top:
                in_box_4=True
        # Bar-level prices are descriptive excursions only, NOT ordered fills.
        if direction==1:
            best=float(d.iloc[s:e+1].bh.max())
            worst=float(d.iloc[s:e+1].bl.min())
            price4=float(d.iloc[min(e,s+3)].bc)
            fav=(best-row.entry)/abs(row.entry-row.stop)
            adv=(worst-row.entry)/abs(row.entry-row.stop)
            c4=(price4-row.entry)/abs(row.entry-row.stop)
        else:
            best=float(d.iloc[s:e+1].al.min())
            worst=float(d.iloc[s:e+1].ah.max())
            price4=float(d.iloc[min(e,s+3)].ac)
            fav=(row.entry-best)/abs(row.entry-row.stop)
            adv=(row.entry-worst)/abs(row.entry-row.stop)
            c4=(row.entry-price4)/abs(row.entry-row.stop)
        back_in_box.append(in_box_4)
        mfe.append(max(0.0,fav))
        mae.append(min(0.0,adv))
        close4.append(c4)
    ts["back_in_box_first4"]=back_in_box
    ts["MFE_R_bar_approx"]=mfe
    ts["MAE_R_bar_approx"]=mae
    ts["close_after_4bars_R"]=close4
    records=[]
    for month, g in ts.groupby("month",sort=True):
        stop=g[g.exit_reason=="SL"]
        tp=g[g.exit_reason=="TP"]
        timeout=g[g.exit_reason=="TIMEOUT"]
        buy=g[g.side=="BUY"]
        sell=g[g.side=="SELL"]
        records.append({
            "month":month,"trades":len(g),"net_R":round(g.R_net.sum(),5),
            "avg_R":round(g.R_net.mean(),5),
            "winners":int(g.is_win.sum()),"losers":int(g.is_loss.sum()),
            "win_rate_pct":round(100*g.is_win.mean(),3),
            "SL_count":len(stop),"SL_netR":round(stop.R_net.sum(),5),
            "TP_count":len(tp),"TP_netR":round(tp.R_net.sum(),5),
            "TIMEOUT_count":len(timeout),"TIMEOUT_netR":round(timeout.R_net.sum(),5),
            "TIMEOUT_win":int((timeout.R_net>0).sum()),"TIMEOUT_loss":int((timeout.R_net<0).sum()),
            "BUY_count":len(buy),"BUY_netR":round(buy.R_net.sum(),5),
            "SELL_count":len(sell),"SELL_netR":round(sell.R_net.sum(),5),
            "box_return_first4_count":int(g.back_in_box_first4.sum()),
            "box_return_first4_pct":round(100*g.back_in_box_first4.mean(),3),
            "median_MFE_R_bar_approx":round(g.MFE_R_bar_approx.median(),4),
            "median_hold_hours":round(g.duration_hours.median(),2),
            "median_timeout_R":round(timeout.R_net.median(),4) if len(timeout) else None,
        })
    monthly=pd.DataFrame(records)
    monthly.to_csv(ROOT/"monthly_diagnostic_sl030_rr5.csv",index=False)
    ts.drop(columns=["entry_dt","exit_dt"]).to_csv(ROOT/"trades_sl030_rr5_diagnostic.csv",index=False)
    by_reason=ts.groupby("exit_reason").agg(
       trades=("R_net","size"),net_R=("R_net","sum"),
       avg_R=("R_net","mean"),median_R=("R_net","median"),
       mean_MFE_R=("MFE_R_bar_approx","mean"),median_MFE_R=("MFE_R_bar_approx","median"),
       win=("is_win","sum"),box_return_first4=("back_in_box_first4","sum"),
    ).reset_index()
    by_reason.to_csv(ROOT/"exit_reason_sl030_rr5.csv",index=False)
    by_side=ts.groupby("side").agg(trades=("R_net","size"),net_R=("R_net","sum"),
                                wins=("is_win","sum"),sl=("exit_reason",lambda v:int((v=="SL").sum())),
                                tp=("exit_reason",lambda v:int((v=="TP").sum())),
                                timeout=("exit_reason",lambda v:int((v=="TIMEOUT").sum())),
                                fake4=("back_in_box_first4","sum")).reset_index()
    by_side.to_csv(ROOT/"direction_sl030_rr5.csv",index=False)
    print("MONTHLY DETAIL\n",monthly.to_string(index=False))
    print("BY EXIT REASON\n",by_reason.to_string(index=False))
    print("BY SIDE\n",by_side.to_string(index=False))
    meta={
        "model":"V8-A 2026 EURUSDm SL0.30% RR1:5 slippage0.2pips each side",
        "all_trades":len(ts),"total_R":nice(ts.R_net.sum()),"positive_months":int((monthly.net_R>0).sum()),
        "back_in_box_first4_count":int(ts.back_in_box_first4.sum()),
        "back_in_box_first4_note":"Counted only among the bars actually held, before or including exit bar; 4 M15 bars maximum",
        "MFE_note":"Bar-high/low descriptive max move until exit (inclusive). Ambiguous same-bar stop-first means MFE is not necessarily tradable or time ordered.",
        "commission_and_swap":"No additional commission (Standard assumption) or swap/financing modeled",
        "caution":"In-sample diagnostic, after selecting top combination. Observational patterns may be consequences rather than causal evidence."
    }
    (ROOT/"diagnostic_metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    if not np.isclose(ts.R_net.sum(),2.39335,atol=1e-4):
        raise ValueError(f"R total discrepancy: {ts.R_net.sum()}")
    print("DIAGNOSTIC VERIFIED",json.dumps(meta))
if __name__=="__main__":
    main()
