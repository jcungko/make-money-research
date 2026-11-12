#!/usr/bin/env python3
"""Compute daily net PnL and realized winner/loser R:R for four frozen V19 EAs with SL 1%.

Same frozen Nov 1-12 2026 Exness M5 Bid/Ask and identical SL engine as verified
V19_four_portfolios_with_SL_report.json. No actual broker trades.
R:R reported is REALIZED average win / absolute average loss per closed EA leg,
not contractual R:R, because EA uses time exit and NO fixed take-profit.
"""
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

import v19_four_portfolios_sl_replay as engine
import v19_nov2026_22_replay as replay

BASE = Path("data/v19_energies")
REPORT_DIR = Path("results/v19_sl_research")
SELECTION = Path("data/v19_strategy_screen/V19_22_profit_then_orders_filtered.json")
LEDGER = Path("results/v19_november_2026/V19_nov2026_leg_ledger.json")
PREVIOUS = REPORT_DIR / "V19_four_portfolios_with_SL_report.json"
STOP_BP = 100


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    picked = json.loads(SELECTION.read_text())
    selected = {x["portfolio"]: x for x in picked["retained"] if x["portfolio"] in engine.WINNERS}
    assert set(selected) == set(engine.WINNERS) and len(selected)==4
    ledger = json.loads(LEDGER.read_text())
    old = json.loads(PREVIOUS.read_text())
    reference = {r["portfolio"]: r for r in old["fixed_1pct_default"]}
    assert set(reference)==set(engine.WINNERS)

    unique_legs=sorted({leg for x in selected.values() for leg in x["legs"]})
    symbols=sorted({leg.split("|")[0] for leg in unique_legs})
    frames={}
    m5_arrays={}
    for sym in symbols:
        nov_m5=engine.load_nov_m5(sym)
        # Only November M5 stop checks necessary: all entries are Nov 2 onward.
        m5_arrays[sym]=engine.to_m5_arrays(nov_m5.reset_index())
        tf_frames=replay.rebuild_frames(BASE,sym,nov_m5)
        for leg in unique_legs:
            s,tf,*_=leg.split("|")
            if s==sym:
                frames[(sym,tf)]=tf_frames[tf]
        print("V19_SL_DAILY_SRC",sym,len(nov_m5),flush=True)

    results={}
    originals={}
    for leg in unique_legs:
        sym,tf,*_=leg.split("|")
        trades=engine.november_legs(frames[(sym,tf)],leg,ledger)
        originals[leg]=trades
        results[leg]=engine.apply_stop(trades,m5_arrays[sym],STOP_BP)
        print("V19_SL_DAILY_LEG",leg,"orders",len(trades),"stop",int(results[leg]["stops"].sum()),flush=True)

    rows=[]
    detail={}
    for pid in engine.WINNERS:
        port=selected[pid]
        prior=reference[pid]["november"]
        trades=[(leg,calcs) for leg in port["legs"] for calcs in [results[leg]]]
        win_sum=loss_sum=0.0
        wins=losses=evens=0
        daily=defaultdict(float)
        daily_orders=defaultdict(int)
        baseline=sum(sum(e["baseline_bp"] for e in originals[leg]) for leg in port["legs"])/4
        for leg,calc in trades:
            for value,exit_date in zip(calc["pnl"],calc["exits"]):
                value=float(value)
                allocation=value/4.
                day=exit_date.strftime("%Y-%m-%d")
                assert "2026-11-01" <= day <= "2026-11-12", (pid,day)
                daily[day]+=allocation
                daily_orders[day]+=1
                if value>1e-9: wins+=1;win_sum+=value
                elif value< -1e-9:losses+=1;loss_sum+=value
                else:evens+=1
        total=sum(daily.values())
        avg_win=win_sum/wins if wins else None
        avg_loss=loss_sum/losses if losses else None
        realized_rr=(avg_win/abs(avg_loss)) if wins and losses else None
        profitable_days=sum(v>1e-9 for v in daily.values())
        losing_days=sum(v< -1e-9 for v in daily.values())
        neutral_days=len(daily)-profitable_days-losing_days
        ntrades=wins+losses+evens
        stop_count=sum(int(results[leg]["stops"].sum()) for leg in port["legs"])
        assert abs(total-prior["total_profit_bp"])<0.0002,(pid,total,prior["total_profit_bp"])
        assert ntrades==prior["trades"] and wins==prior["winning_orders"] and losses==prior["losing_orders"]
        assert stop_count==prior["stop_count"]
        assert abs(baseline-old["baseline"][pid]["november_bp"])<0.0002
        assert profitable_days+losing_days+neutral_days==len(daily)
        row={
            "portfolio":pid,
            "sl_pct":1.0,
            "november_realized_profit_bp":round(total,5),
            "november_no_sl_profit_bp":round(baseline,5),
            "november_orders":ntrades,
            "november_stop_orders":stop_count,
            "profitable_days":profitable_days,
            "losing_days":losing_days,
            "breakeven_days":neutral_days,
            "days_with_closed_orders":len(daily),
            "days_without_closed_orders_of_12":12-len(daily),
            "avg_net_profit_bp_per_day_with_closed_orders":round(total/len(daily),5) if daily else 0.0,
            "avg_net_profit_bp_per_12_calendar_days":round(total/12,5),
            "winning_orders":wins,
            "losing_orders":losses,
            "break_even_orders":evens,
            "avg_winning_order_bp_unweighted":round(avg_win,5) if avg_win is not None else None,
            "avg_losing_order_bp_unweighted":round(avg_loss,5) if avg_loss is not None else None,
            "realized_rr_reward_to_risk":round(realized_rr,5) if realized_rr is not None else None,
            "realized_rr_formatted":f"1:{realized_rr:.2f}" if realized_rr is not None else "N/A",
        }
        rows.append(row)
        detail[pid]=[
            {"date_utc":d,"net_profit_bp":round(pnl,6),"closed_orders":daily_orders[d]}
            for d,pnl in sorted(daily.items())
        ]
        print("V19_SL_DAILY_RESULT",json.dumps(row),flush=True)
    assert len(rows)==4
    result={
        "project":"V19","source":"Exness USOIL and UKOIL M5 historical and Nov 2026 frozen snapshots",
        "date_start_inclusive_utc":"2026-11-01T00:00:00+00:00",
        "date_cutoff_exclusive_utc":"2026-11-12T18:00:00+00:00",
        "sl_pct":1.0,
        "sl_definition":old["sl_definition"],
        "pnl_units":"basis points (bp) of equal 1/4 fixed portfolio notional, not USD",
        "day_definition":"UTC DATE OF EXIT of closed trades including stop exits; win day means net sum of four independently traded legs > 0",
        "avg_daily_definition":"Net total November profit / number of UTC days with >=1 closed trade, including losing days",
        "rr_definition":"Ex post realized (average profitable EA leg PnL) / absolute(average losing EA leg PnL); reported as risk:reward 1:X, not preset RR because bots have no fixed TP.",
        "execution_limitations":old["remaining_limitations"],
        "cross_validation":"All 4 SL replay November PnL, win/loss trade counts, stop counts and pre-SL baselines verified against committed previous SL report.",
        "rows":rows,"daily_exit_utc":detail
    }
    (REPORT_DIR/"V19_four_SL1pct_Nov2026_daily_winloss_RR.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame(rows).to_csv(REPORT_DIR/"V19_four_SL1pct_Nov2026_daily_winloss_RR.csv",index=False)
    print("V19_SL_DAILY_COMPLETE",len(rows),flush=True)


if __name__=="__main__":
    main()
