#!/usr/bin/env python3
"""V19 November 2026 daily realized PnL and win/loss-day statistics for 27 survivors.

Replay locked 27 strategies using proven 2026-11 M5 Exness quotes and same prior
history, signals, open prices, 1bp each-side slippage as 89 portfolio screen.
Date bucket uses UTC exit date. Counting window is 2026-11-02..12 weekdays,
9 observed trading dates. Days with zero realized PnL are separately classified.
"""
import json
from pathlib import Path
import pandas as pd
import v19_nov2026_22_replay as replay

HISTORY=Path("data/v19_energies")
OUT=Path("results/v19_november_2026")
ORIGINAL=OUT/"V19_89_nov2026_profit_and_orders_filter.json"
CUTOFF=pd.Timestamp("2026-11-12T18:00:00Z")
DAYS=pd.date_range("2026-11-02", "2026-11-12", freq="B", tz="UTC")
assert len(DAYS)==9
BASE=replay.START


def main():
    stored=json.loads(ORIGINAL.read_text())
    candidates=stored["retained"]
    assert len(candidates)==27 and stored["counts"]["original"]==89
    frames={}
    for sym in replay.NAMES:
        p=OUT/f"{sym}_2026-11_M5_UTC.csv.gz"
        m5=pd.read_csv(p,parse_dates=["timestamp_utc"],index_col="timestamp_utc")
        m5.index=pd.to_datetime(m5.index,utc=True)
        assert m5.index.min()>=BASE and m5.index.max()<CUTOFF
        frames[sym]=replay.rebuild_frames(HISTORY,sym,m5)
        print("V19_DAILY_SOURCE",sym,len(m5),str(m5.index.max()),flush=True)
    unique_legs=sorted({leg for p in candidates for leg in p["legs"]})
    ledger={}
    for leg in unique_legs:
        symbol,tf,*_=leg.split("|")
        ledger[leg]=replay.replay_one_leg(frames[symbol][tf],leg,CUTOFF)
    print("V19_DAILY_LEGS",len(unique_legs),flush=True)

    rows=[]
    day_records=[]
    base_set=set(DAYS.strftime("%Y-%m-%d"))
    for item in candidates:
        by_date={day:{"pnl_bp":0.0,"orders_closed":0,"winning_orders":0,"losing_orders":0}
                 for day in DAYS.strftime("%Y-%m-%d")}
        all_closed=[]
        for leg in item["legs"]:
            for t in ledger[leg]:
                if t["status"]=="closed":
                    exit_day=t["exit_utc"][:10]
                    if exit_day not in base_set:
                        raise AssertionError(f"Closed trade outside nine trading weekdays: {leg}, {t}")
                    bp=float(t["pnl_bp"])/4
                    by_date[exit_day]["pnl_bp"]+=bp
                    by_date[exit_day]["orders_closed"]+=1
                    by_date[exit_day]["winning_orders"]+=int(bp>0)
                    by_date[exit_day]["losing_orders"]+=int(bp<0)
                    all_closed.append(t)
        total_bp=round(sum(float(e["pnl_bp"]) for e in all_closed)/4,5)
        if total_bp!=item["november_realized_profit_bp"]:
            raise AssertionError(f"Profit mismatch {item['portfolio']}: {total_bp} vs {item['november_realized_profit_bp']}")
        if len(all_closed)!=item["november_closed_orders"]:
            raise AssertionError(f"Order mismatch {item['portfolio']}")
        pnls=[by_date[d]["pnl_bp"] for d in by_date]
        winning=sum(v>1e-10 for v in pnls)
        losing=sum(v< -1e-10 for v in pnls)
        zero=len(DAYS)-winning-losing
        no_close=sum(by_date[d]["orders_closed"]==0 for d in by_date)
        row={
           "portfolio":item["portfolio"],
           "winning_days":winning,
           "losing_days":losing,
           "zero_pnl_days":zero,
           "days_without_closed_orders":no_close,
           "days_with_closed_orders":len(DAYS)-no_close,
           "calendar_trading_weekdays":len(DAYS),
           "total_realized_profit_bp":total_bp,
           "mean_realized_profit_bp_per_trading_weekday":round(total_bp/len(DAYS),5),
           "mean_realized_profit_bp_per_day_with_closed_orders":round(total_bp/(len(DAYS)-no_close),5) if no_close<len(DAYS) else None,
           "mean_positive_day_profit_bp":round(sum(x for x in pnls if x>0)/winning,5) if winning else None,
           "mean_negative_day_loss_bp":round(sum(x for x in pnls if x<0)/losing,5) if losing else None,
           "closed_orders":len(all_closed),
           "positive_day_rate_pct":round(winning/len(DAYS)*100,2),
        }
        rows.append(row)
        for d,info in by_date.items():
            day_records.append({
                "portfolio":item["portfolio"],"exit_day_utc":d,
                "realized_profit_bp":round(info["pnl_bp"],6),
                "closed_orders":info["orders_closed"],
                "day_result":"profit" if info["pnl_bp"]>1e-10 else ("loss" if info["pnl_bp"]< -1e-10 else "zero")
            })
        assert winning+losing+zero==len(DAYS)
        assert sum(x["realized_profit_bp"] for x in day_records if x["portfolio"]==item["portfolio"])-total_bp<0.00005

    rows.sort(key=lambda x: (-x["mean_realized_profit_bp_per_trading_weekday"],x["portfolio"]))
    by_id={x["portfolio"]:x for x in rows}
    assert len(by_id)==len(rows)==27
    assert all(x["total_realized_profit_bp"]>0 and x["closed_orders"]>=3 for x in rows)
    report={
        "project":"V19", "period":"November 2026 (partial)",
        "as_of_cutoff_exclusive_utc":CUTOFF.isoformat(),
        "daily_timezone":"UTC",
        "counted_weekdays_utc":list(DAYS.strftime("%Y-%m-%d")),
        "date_definition":"Trading weekdays Monday-Friday between Nov 02 and Nov 12 UTC; 9 dates, last date partially observed through 18:00 UTC. Nov 01 and Nov 08 excluded from averages as Sundays (market hours are partial).",
        "day_pnl_definition":"Sum of realized PnL of orders closed on that UTC day. Zero includes days without closed orders or exact net break-even. Open orders excluded from PnL.",
        "daily_mean_definition":"Total realized profit in bp / 9 observed trading weekdays, including zero-PnL days; not USD and not profit per winning day.",
        "modeling":"Same historical Exness bid/ask plus 1bp slippage each side; 4 legs equal notional, no stop-loss / swaps / broker fees or fill simulation.",
        "base_report":str(ORIGINAL),
        "number_of_portfolios":len(rows),
        "number_of_unique_legs":len(unique_legs),
        "rows":rows,
        "daily":day_records,
    }
    p=OUT/"V19_27_nov2026_daily_win_loss_profit.json"
    p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame(rows).to_csv(OUT/"V19_27_nov2026_daily_win_loss_profit.csv",index=False)
    pd.DataFrame(day_records).to_csv(OUT/"V19_27_nov2026_daily_pnl_by_exit_utc.csv",index=False)
    print("V19_27_DAILY_FINAL",json.dumps({"rows":len(rows),"legs":len(unique_legs),"days":len(DAYS),"top5":rows[:5],"bottom5":rows[-5:]}),flush=True)


if __name__=="__main__":
    main()
