#!/usr/bin/env python3
"""Convert frozen Nov 2026 V19-065 with 4% SL to USD at exactly 0.01 Exness lot per bot.

Both USOIL and UKOIL Exness instruments have 1000 barrels / 1 lot,
so each 0.01 lot trade is 10 barrels (not 1/4 portfolio notional).
No extra leverage applied to PnL. Historical spread and assumed 1bp slippage
on both sides are already embedded in pnl_bp_leg. No commissions/swaps.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

import v19_strategy_screen as v19
from v19_nov2026_22_replay import rebuild_frames
from v19_four_portfolios_sl_replay import (
    BASE, HIST, NOV, LEDGER, load_nov_m5, to_m5_arrays,
    november_legs, apply_stop, END_NOV
)

NAME="V19-065"
SL_PCT=4
SL_BP=400
LOT=0.01
BARRELS_PER_LOT=1000
QTY=LOT*BARRELS_PER_LOT
OUT=Path("results/v19_sl_research")
TZ="Asia/Ho_Chi_Minh"


def main():
    slfile=json.loads((OUT/"V19_four_portfolios_with_SL_report.json").read_text())
    slreplay=next(x for x in slfile["all_scenarios"] if x["portfolio"]==NAME and x["stop_basis_points"]==SL_BP)
    basefile=json.loads(HIST.read_text())
    selected=next(x for x in basefile["retained"] if x["portfolio"]==NAME)
    ledger=json.loads(LEDGER.read_text())
    all_frames={}
    m5_data={}
    for symbol in ("USOIL","UKOIL"):
        x=load_nov_m5(symbol)
        m5_data[symbol]=to_m5_arrays(v19.read_frame(BASE,symbol,"M5"),x)
        all_frames.update({(symbol,tf):fr for tf,fr in rebuild_frames(BASE,symbol,x).items()})
    orders=[]
    for n,leg in enumerate(selected["legs"],start=1):
        symbol,tf,*_=leg.split("|")
        trade_list=november_legs(all_frames[(symbol,tf)],leg,ledger)
        a=apply_stop(trade_list,m5_data[symbol],SL_BP)
        for j,t in enumerate(trade_list):
            mid=(t["entry_ask"]+t["entry_bid"])/2
            pnl_bp_leg=float(a["pnl"][j])
            # 1 bp = 0.0001 of entry notional = 10 barrels * entry mid price.
            usd=pnl_bp_leg/10000*mid*QTY
            got_sl=bool(a["stops"][j])
            row={
                "bot":f"B{n}","symbol":symbol,"direction":t["side"].upper(),"lot":LOT,
                "entry_ict":t["entry"].tz_convert(TZ).isoformat(),
                "exit_ict":a["exits"][j].tz_convert(TZ).isoformat(),
                "entry_day_ict":t["entry"].tz_convert(TZ).date().isoformat(),
                "exit_day_ict":a["exits"][j].tz_convert(TZ).date().isoformat(),
                "entry_mid_usd_per_barrel":round(float(mid),6),
                "entry_bid":round(float(t["entry_bid"]),6),
                "entry_ask":round(float(t["entry_ask"]),6),
                "entry_notional_usd":round(float(mid*QTY),4),
                "illustrative_margin_at_1_200_usd":round(float(mid*QTY/200),4),
                "exit_reason":"SL" if got_sl else "TIME",
                "pnl_bp_one_leg":round(pnl_bp_leg,6),
                "pnl_usd":round(usd,6),
            }
            orders.append(row)
    orders.sort(key=lambda x:(x["entry_ict"],x["bot"]))
    assert len(orders)==17
    assert sum(x["exit_reason"]=="SL" for x in orders)==2
    portfolio_bp=sum(x["pnl_bp_one_leg"]/4 for x in orders)
    expected=slreplay["november"]["total_profit_bp"]
    if abs(portfolio_bp-expected)>0.00005:
        raise ValueError(f"Mismatch V19-065 SL4 bp baseline {portfolio_bp} vs {expected}")

    daily={}
    start=pd.Timestamp("2026-11-01",tz=TZ)
    for date in pd.date_range(start,pd.Timestamp(END_NOV).tz_convert(TZ).normalize()):
        name=date.date().isoformat()
        ent=[x for x in orders if x["entry_day_ict"]==name]
        ext=[x for x in orders if x["exit_day_ict"]==name]
        daily[name]={
            "date_ict":name,
            "opened":len(ent),
            "closed":len(ext),
            "stopped":sum(x["exit_reason"]=="SL" for x in ext),
            "profit_usd":round(sum(x["pnl_usd"] for x in ext),4),
            "profit_per_bot_usd":{f"B{i}":round(sum(x["pnl_usd"] for x in ext if x["bot"]==f"B{i}"),4) for i in range(1,5)}
        }
    cum=0
    for row in daily.values():
        cum+=row["profit_usd"]
        row["cumulative_usd"]=round(cum,4)
    total_usd=sum(x["pnl_usd"] for x in orders)
    by_bot={f"B{i}":{
        "trades":sum(x["bot"]==f"B{i}" for x in orders),
        "stop_count":sum(x["bot"]==f"B{i}" and x["exit_reason"]=="SL" for x in orders),
        "net_profit_usd":round(sum(x["pnl_usd"] for x in orders if x["bot"]==f"B{i}"),4)
    } for i in range(1,5)}
    report={
        "project":NAME,
        "period_end_exclusive_utc":END_NOV.isoformat(),
        "lot_each_leg":LOT,
        "contract_size_barrels_per_lot":BARRELS_PER_LOT,
        "quantity_barrels_per_trade":QTY,
        "sl_percent_of_entry_price":SL_PCT,
        "leverage_set_by_user":200,
        "important_leverage_note":"Not applied as profit multiplier; Exness oil instruments can have instrument-specific fixed margin.",
        "source_ohlc":"Frozen November 2026 Exness M5 bid/ask tick archive with October and earlier indicator warmup",
        "costs":"Historical bid/ask, 1bp additional slippage on each side included, broker commissions/swaps not included",
        "total_profit_usd":round(total_usd,4),
        "total_profit_bp_equal_weight_simulation":round(portfolio_bp,5),
        "total_trades":len(orders),
        "stop_count":sum(x["exit_reason"]=="SL" for x in orders),
        "by_bot":by_bot,
        "daily":list(daily.values()),
        "orders":orders
    }
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/"V19_065_SL4_Nov2026_001lot_USD.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame(orders).to_csv(OUT/"V19_065_SL4_Nov2026_001lot_USD_orders.csv",index=False)
    print("V19_065_USD_FINAL",json.dumps({
        "total_usd":report["total_profit_usd"],
        "bp_crosscheck":report["total_profit_bp_equal_weight_simulation"],
        "trades":len(orders),"stops":report["stop_count"],
        "by_bot":by_bot,
        "daily":report["daily"]
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
