#!/usr/bin/env python3
"""V17 read-only overlap analysis, original #12 and #13 from the 2025-2026 strategy census."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from v17_strategy_screen import load_data, signal_generator, build_calendar, exit_pips, CUTOFF_MONTHS, NOV_CODE

SYMBOL="USDJPY"
OUT=Path("results/v17_12_vs_13")
CONFIG={12:"return_1", 13:"body_1"}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    f=load_data(Path("data"),SYMBOL)
    m5=f["M5"]
    byhour, mcode, ns = build_calendar(m5)
    valid, longp, shortp, endmonth = exit_pips(m5,byhour,mcode,ns,0.01,(2,))[2]
    daily=f["D1"]
    raw=dict(signal_generator(daily))
    idx=byhour[18]
    eligible = valid[idx] & (endmonth[idx]>=0) & (endmonth[idx]<NOV_CODE)
    ledgers={}
    decisions={}
    for ident, feature in CONFIG.items():
        # Same exact signal timing as the original V17 backtester:
        # signal from prior fully closed D1 candle, reverse, BUY only, at 18:00 UTC.
        signal = raw[feature].shift(1,fill_value=0).reindex(m5.index,method="ffill").fillna(0).to_numpy(dtype=np.int8)
        buy = idx[eligible & (signal[idx]==-1)]
        records={}
        for i in buy:
            if not np.isfinite(longp[i]):
                raise ValueError(f"invalid quote at i={i}")
            records[int(i)]={
                "entry_utc":m5.index[i].isoformat(),
                "exit_utc":m5.index[i+23].isoformat(),
                "pips":round(float(longp[i]),4),
                "exit_month":CUTOFF_MONTHS[int(endmonth[i])]
            }
        ledgers[ident]=records
        decisions[ident]=set(records)
    a,b=decisions[12],decisions[13]
    shared=a & b
    only12=a - b
    only13=b - a
    union=a | b
    allmonths=list(CUTOFF_MONTHS)
    daily_trades=[]
    all_times=sorted(set(idx[eligible]))
    for i in all_times:
        month=CUTOFF_MONTHS[int(endmonth[i])]
        v12=ledgers[12].get(i)
        v13=ledgers[13].get(i)
        daily_trades.append({
            "entry_utc":m5.index[i].isoformat(),
            "exit_month":month,
            "12_trade":int(i in a),"13_trade":int(i in b),
            "12_pips":v12["pips"] if v12 else 0.,
            "13_pips":v13["pips"] if v13 else 0.
        })
    x=pd.DataFrame(daily_trades)
    corr=float(x[["12_pips","13_pips"]].corr().iloc[0,1])
    monthly=[]
    for m in allmonths:
        r12=sum(z["pips"] for z in ledgers[12].values() if z["exit_month"]==m)
        r13=sum(z["pips"] for z in ledgers[13].values() if z["exit_month"]==m)
        monthly.append({
            "month":m, "12_pips":round(r12,2),"13_pips":round(r13,2),
            "12_trades":sum(z["exit_month"]==m for z in ledgers[12].values()),
            "13_trades":sum(z["exit_month"]==m for z in ledgers[13].values()),
            "shared_trades":sum(ledgers[12][i]["exit_month"]==m for i in shared),
            "difference_12_minus_13":round(r12-r13,2)
        })
    monthcorr=float(pd.DataFrame(monthly)[["12_pips","13_pips"]].corr().iloc[0,1])
    overlap_prof=sum(ledgers[12][i]["pips"] for i in shared)
    profit12=sum(z["pips"] for z in ledgers[12].values())
    profit13=sum(z["pips"] for z in ledgers[13].values())
    report={
        "source":"V17 Exness public bid/ask M5 + D1 year 2025, Jan-Oct 2026",
        "settings":"18:00 UTC, D1 prior closed candle, reverse signal, long_only, 2-hour hold",
        "id12_feature":"sign(previous D1 mid close minus earlier D1 mid close) < 0",
        "id13_feature":"sign(previous D1 mid close minus previous D1 mid open) < 0",
        "holding_model":"BUY at ask M5 open, SELL at bid M5 close two hours later; 0.2 pip adverse round-trip slippage",
        "period_complete_months":22,
        "counts":{
            "12_trades":len(a),"13_trades":len(b),
            "both_trade_same_entry":len(shared),
            "only_12":len(only12),"only_13":len(only13),
            "unique_entry_times":len(union),
            "overlap_of_12_percent":round(100*len(shared)/len(a),2),
            "overlap_of_13_percent":round(100*len(shared)/len(b),2),
            "jaccard_percent":round(100*len(shared)/len(union),2),
            "signal_trade_agreement_on_all_eligible_daily_entry_times_percent":round(
                100*sum((i in a)==(i in b) for i in all_times)/len(all_times),2)
        },
        "profit":{
            "12_pips":round(profit12,2),"13_pips":round(profit13,2),
            "shared_trade_pips_each_bot":round(overlap_prof,2),
            "distinct_12_pips":round(sum(ledgers[12][i]["pips"] for i in only12),2),
            "distinct_13_pips":round(sum(ledgers[13][i]["pips"] for i in only13),2),
            "both_bots_sum_pips":round(profit12+profit13,2),
            "both_bots_without_duplicate_entries_pips":round(sum(ledgers[12].get(i,ledgers[13].get(i))["pips"] for i in union),2),
            "daily_pnl_correlation_including_no_trade_days":round(corr,4),
            "monthly_pnl_correlation":round(monthcorr,4),
            "identical_monthly_pnl":sum(abs(m["12_pips"]-m["13_pips"])<0.0001 for m in monthly),
            "both_negative_months":[m["month"] for m in monthly if m["12_pips"]<=0 and m["13_pips"]<=0]
        },
        "monthly":monthly,
        "only_12_trades":[ledgers[12][i] for i in sorted(only12)],
        "only_13_trades":[ledgers[13][i] for i in sorted(only13)]
    }
    # Consistency check with the complete V17 monthly report, not just Nov snapshot.
    expected={12:(213,852.5),13:(205,793.4)}
    for k in CONFIG:
        count,prof=expected[k]
        if len(ledgers[k])!=count or abs(sum(z["pips"] for z in ledgers[k].values())-prof)>0.02:
            raise RuntimeError(f"Mismatch with original V17 expected strategy {k}: {len(ledgers[k])} trades, {sum(z['pips'] for z in ledgers[k].values())} pips")
    (OUT/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pd.DataFrame(monthly).to_csv(OUT/"monthly_overlap.csv",index=False)
    pd.DataFrame(daily_trades).to_csv(OUT/"daily_entries_and_pnl.csv",index=False)
    print("V17_OVERLAP_FINAL",json.dumps({"counts":report["counts"],"profit":report["profit"]},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
