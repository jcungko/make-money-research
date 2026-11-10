#!/usr/bin/env python3
"""Read-only daily audit export for frozen 2026 V8.1B Python study.
Avoids placing any personal MT5 report/account data in the repository.
"""
import csv
from pathlib import Path
import v81_daily_recurring as v
from v8a_eurusdm_m15 import load_m15

def main():
    d=load_m15("data/exness/EURUSDm_2026/exness_eurusdm_2026_m5_m15_h1.zip")
    features=v.build_features(d)
    days,_=v.signals_on_days(d,features)
    plans,eligible,skipped=v.make_daily_plan(d,days,features,"m15_momentum_8","trend",9,19)
    results=v.run(d,plans,24,1.5,0.2)
    root=Path("results/v81_daily_recurring_2026")
    root.mkdir(exist_ok=True,parents=True)
    rows=[]
    for date,month,side,r,why,entr,exit_ in results:
        rows.append({
            "day_utc":date,"side":"BUY" if side==1 else "SELL",
            "R_net":round(r,8),"exit_reason":why,
            "entry_utc":str(d.t.iloc[entr]),"exit_bar_start_utc":str(d.t.iloc[exit_]),
            "entry_bid_open":float(d.bo.iloc[entr]),
            "entry_ask_open":float(d.ao.iloc[entr]),
            "last_known_bid_close":float(d.bc.iloc[exit_]),
            "last_known_ask_close":float(d.ac.iloc[exit_]),
            "signal_c0845":float(d.bc.iloc[entr-1]),
            "signal_c0645":float(d.bc.iloc[entr-9]),
        })
    assert len(rows)==222,len(rows)
    assert abs(sum(x["R_net"] for x in rows)-26.6375)<.00002
    with (root/"python_v81b_daily_trace_2026.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    print("PYTHON V81B: 222 trades; net R",sum(x["R_net"] for x in rows),flush=True)
    from collections import Counter
    print("REASONS",Counter(x["exit_reason"] for x in rows),flush=True)
    for month in sorted(set(x["day_utc"][:7] for x in rows)):
        z=[x for x in rows if x["day_utc"].startswith(month)]
        print("MONTH",month,"n",len(z),"R",round(sum(x["R_net"] for x in z),8),
              "BUY",sum(x["side"]=="BUY" for x in z),
              "TP",sum(x["exit_reason"]=="TP" for x in z),
              "SL",sum(x["exit_reason"]=="SL" for x in z),
              "TIME",sum(x["exit_reason"]=="TIME" for x in z),flush=True)
if __name__=="__main__":main()
