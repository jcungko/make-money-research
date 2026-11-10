#!/usr/bin/env python3
"""Locked 2026 H1/H4 / M15 alternative families applied to 2025; no tuning on 2025."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import v81_daily_recurring as v

CONFIGS=[
    ("H1 / H4 momentum 4h","1h_momentum_4","trend",9,19,16,2.0),
    ("H1 momentum 2h","1h_momentum_2","trend",9,19,16,1.5),
    ("M15 RSI 14 trend","m15_rsi50","trend",9,20,16,1.5),
    ("M15 4h range fade","m15_range_pos_16","revert",12,20,12,2.0),
    ("M15 momentum 8h","m15_momentum_32","trend",9,19,16,1.0),
    ("M15 momentum 2h control","m15_momentum_8","trend",9,20,24,2.0),
]

def main():
    data="data/exness/EURUSDm_2025/eurusdm_exness_2025_m15.zip"
    d=v.load_m15(data)
    v.FULL=tuple(f"2025-{j:02d}" for j in range(1,13))
    v.RECENT=("2025-08","2025-09","2025-10")
    days,_=v.signals_on_days(d,{})
    feats=v.build_features(d)
    denom=len(days)
    rows=[]
    for label,key,mode,entry,exit_h,sl,rr in CONFIGS:
        plans,_,miss=v.make_daily_plan(d,days,feats,key,mode,entry,exit_h)
        if len(plans)/denom<.99:raise RuntimeError("Daily coverage shortfall "+label)
        for slip in (.2,.5,1.0):
            z=v.metrics(v.run(d,plans,sl,rr,slip))
            row={
               "label":label,"feature":key,"mode":mode,"entry_utc":entry,
               "exit_utc":exit_h,"SL_pips":sl,"RR":rr,"slippage_pips":slip,
               "days_traded":len(plans),"eligible_days":denom,"netR":z["netR"],
               "winrate":z["winrate"],"profit_factor":z["PF"],
               "maxDD_R":z["maxDD_R"],"profitable_months":z["positive_full_months"],
               "monthly_R":json.dumps(z["monthly_R"]),
               "TP":z["TP"],"SL":z["SL"],"TIME":z["TIME"]
            }
            rows.append(row)
            print("CHECK",json.dumps(row),flush=True)
    out=Path("results/v81_2025_other_families")
    out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/"replication.csv",index=False)
    (out/"method.txt").write_text("2025 application of prespecified 2026 alternatives, based on the same 2025 compact public Exness historical M15 feed; no retuning in 2025. Historical only.",encoding="utf-8")

if __name__=="__main__":main()
