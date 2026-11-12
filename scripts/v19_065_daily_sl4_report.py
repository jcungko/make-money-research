#!/usr/bin/env python3
"""V19-065 daily November 2026 read-only trading report with 4% price stop loss.

Groups trade openings and realised trade exits by local Asia/Ho_Chi_Minh day.
Uses exact published November frozen ledger, the same original 4% M5 SL model.
No trading, no live orders, no change of parameters.
"""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

import v19_strategy_screen as v19
from v19_four_portfolios_sl_replay import (
    load_nov_m5, to_m5_arrays, november_legs, apply_stop, BASE, HIST, NOV, LEDGER,
    START_NOV, END_NOV
)
from v19_nov2026_22_replay import rebuild_frames

OUT=Path("results/v19_sl_research")
NAME="V19-065"
SL=400
TZ="Asia/Ho_Chi_Minh"


def as_ict(ts):
    return pd.Timestamp(ts).tz_convert(TZ)


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    source=json.loads(HIST.read_text())
    selected=next(x for x in source["retained"] if x["portfolio"]==NAME)
    assert len(selected["legs"])==4
    november=json.loads(NOV.read_text())
    original=next(x for x in november["rows"] if x["id"]==NAME)
    ledger=json.loads(LEDGER.read_text())
    published=json.loads((OUT/"V19_four_portfolios_with_SL_report.json").read_text())
    published_row=next(x for x in published["all_scenarios"] if x["portfolio"]==NAME and x["stop_basis_points"]==SL)
    frames={}
    m5={}
    for symbol in sorted({leg.split("|")[0] for leg in selected["legs"]}):
        history_m5=v19.read_frame(BASE,symbol,"M5")
        new_m5=load_nov_m5(symbol)
        m5[symbol]=to_m5_arrays(history_m5,new_m5)
        frames.update({(symbol,tf):frame for tf,frame in rebuild_frames(BASE,symbol,new_m5).items()})
        print("V19_DAILY_SOURCE",symbol,len(new_m5),flush=True)

    orders=[]
    for no,leg in enumerate(selected["legs"],1):
        symbol,tf,signal,side,hold,session=leg.split("|")
        trade_list=november_legs(frames[(symbol,tf)],leg,ledger)
        outcome=apply_stop(trade_list,m5[symbol],SL)
        for i,t in enumerate(trade_list):
            entry=as_ict(t["entry"])
            exit_time=as_ict(outcome["exits"][i])
            pnl=float(outcome["pnl"][i])
            orders.append({
                "id":f"V19-065-B{no}-{i+1:02d}",
                "bot":f"B{no}",
                "symbol":symbol,
                "timeframe":tf,
                "signal":signal,
                "direction":side.upper(),
                "entry_time_ict":entry.isoformat(),
                "entry_day_ict":entry.date().isoformat(),
                "exit_time_ict":exit_time.isoformat(),
                "exit_day_ict":exit_time.date().isoformat(),
                "original_time_exit_ict":as_ict(t["time_exit"]).isoformat(),
                "exit_reason":"SL" if bool(outcome["stops"][i]) else "TIME",
                "sl_pct":SL/100,
                "pnl_bp_leg":round(pnl,6),
                "pnl_bp_portfolio":round(pnl/4,6)
            })
    orders.sort(key=lambda x:(x["entry_time_ict"],x["bot"],x["id"]))
    assert len(orders)==original["november_closed_orders"]==17
    assert sum(x["exit_reason"]=="SL" for x in orders)==published_row["november"]["stop_count"]==2
    portfolio_pnl=sum(x["pnl_bp_portfolio"] for x in orders)
    target=published_row["november"]["total_profit_bp"]
    if abs(portfolio_pnl-target)>0.0002:
        raise ValueError(f"SL4 baseline mismatch {portfolio_pnl} != {target}")
    if any(x["entry_time_ict"]>x["exit_time_ict"] for x in orders):
        raise ValueError("trade exits before entries")

    start=pd.Timestamp("2026-11-01",tz=TZ)
    end=pd.Timestamp(END_NOV).tz_convert(TZ).normalize()
    days=pd.date_range(start,end,freq="D")
    running=0.
    daily=[]
    for day in days:
        key=day.date().isoformat()
        entries=[x for x in orders if x["entry_day_ict"]==key]
        exits=[x for x in orders if x["exit_day_ict"]==key]
        day_pl=sum(x["pnl_bp_portfolio"] for x in exits)
        running+=day_pl
        daily.append({
            "date_ict":key,
            "orders_opened":len(entries),
            "orders_closed":len(exits),
            "winning_closed":sum(x["pnl_bp_leg"]>0 for x in exits),
            "losing_closed":sum(x["pnl_bp_leg"]<0 for x in exits),
            "stop_loss_exits":sum(x["exit_reason"]=="SL" for x in exits),
            "profit_bp_portfolio":round(day_pl,5),
            "cumulative_bp_portfolio":round(running,5),
            "by_bot":{
                f"B{i}":round(sum(x["pnl_bp_portfolio"] for x in exits if x["bot"]==f"B{i}"),5)
                for i in range(1,5)
            }
        })
    assert sum(x["orders_opened"] for x in daily)==17
    assert sum(x["orders_closed"] for x in daily)==17
    assert sum(x["stop_loss_exits"] for x in daily)==2
    assert abs(running-target)<0.0002

    report={
        "project":"V19","portfolio":"V19-065",
        "study":"Daily frozen November 2026 realised trade PnL with 4% broker-price SL simulated against M5 quotes",
        "stop_loss_pct":4.0,
        "stop_type":"Hard stop; model fills at stop level or worse M5 opening quote, plus 1bp slippage",
        "time_zone":"Asia/Ho_Chi_Minh UTC+07:00",
        "period_utc":"2026-11-01T00:00:00Z to 2026-11-12T18:00:00Z (exclusive)",
        "pnl_measure":"Basis points of equal quarter-leg fixed notional portfolio, not USD",
        "profit_reporting":"Exit-day realised PnL. Opened and exited counts are grouped by local ICT dates.",
        "costs":"Bid/Ask source spread and assumed 1bp slippage on both sides; swaps, commissions and broker fill risk excluded",
        "counts":{
            "bot_legs":4,
            "closed_orders":len(orders),
            "stop_exits":sum(x["exit_reason"]=="SL" for x in orders),
            "positive_closed_trades":sum(x["pnl_bp_leg"]>0 for x in orders),
            "negative_closed_trades":sum(x["pnl_bp_leg"]<0 for x in orders),
            "total_portfolio_bp":round(running,5),
            "days_with_any_open":sum(x["orders_opened"]>0 for x in daily),
            "days_with_any_close":sum(x["orders_closed"]>0 for x in daily),
            "profitable_closed_days":sum(x["profit_bp_portfolio"]>0 for x in daily),
            "losing_closed_days":sum(x["profit_bp_portfolio"]<0 for x in daily),
        },
        "four_legs":selected["legs"],
        "daily":daily,
        "orders":orders
    }
    name="V19_065_SL4_nov2026_daily_report"
    (OUT/(name+".json")).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame([{k:v for k,v in x.items() if k!="by_bot"}|x["by_bot"] for x in daily]).to_csv(OUT/(name+".csv"),index=False)
    pd.DataFrame(orders).to_csv(OUT/"V19_065_SL4_nov2026_trade_ledger.csv",index=False)
    print("V19_DAILY_FINAL",json.dumps({"counts":report["counts"],"daily":daily},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
