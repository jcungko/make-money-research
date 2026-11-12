#!/usr/bin/env python3
"""Auditable V21 structural overlap: Jan 2025-Oct 2026 original 44 surviving portfolios.
Only retaining representatives after removing same-asset/same-hour/same-side
duplicate exposures. November forward results were frozen earlier.
"""
import json,sys
from pathlib import Path
from itertools import combinations
from collections import Counter
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/"scripts"))
import v19_strategy_screen as eng
ROOT=BASE/"data"/"v21_crypto"
OUT=BASE/"data"/"v21_crypto_screen"

def legs_trades(ids):
    by_frame={}
    for name in ids:
        s,tf,*_=name.split("|")
        by_frame.setdefault((s,tf),[]).append(name)
    out={}
    for (sym,tf),grp in by_frame.items():
        df=eng.read_frame(ROOT,sym,tf)
        n=len(df)
        time=df.timestamp_utc
        h=time.dt.hour.to_numpy()
        minute=time.dt.minute.to_numpy()
        bid=df.bid_open.to_numpy()
        ask=df.ask_open.to_numpy()
        good=np.isfinite(bid)&np.isfinite(ask)&(bid>0)&(ask>0)
        sig=eng.signals(df)
        ix=np.arange(n)
        for name in grp:
            s,tff,pattern,side,holdstr,slot=name.split("|")
            hold=int(holdstr[1:])
            ends=np.minimum(ix+hold,n-1)
            valid=(ix+hold<n)&good&good[ends]
            mask=sig[pattern] & valid & (h==int(slot[:2])) & (minute==0)
            entries=eng.pick_nonoverlap(np.flatnonzero(mask),hold)
            exits=ends[entries]
            cut=pd.Timestamp("2026-11-01T00:00:00Z")
            select=(time.iloc[exits]<cut).to_numpy()
            entries=entries[select]
            exits=exits[select]
            out[name]=[
                (int(time.iloc[a].value),int(time.iloc[b].value))
                for a,b in zip(entries,exits)]
        print("OVERLAP_FRAMES",sym,tf,len(grp),flush=True)
    return out

def pair_metrics(a,b):
    e1={z[0] for z in a}
    e2={z[0] for z in b}
    equal=len(e1 & e2)
    jacc=equal/max(1,len(e1|e2))
    active=0
    for start,end in a:
        for x,y in b:
            if start < y and x < end:
                active+=1
    return equal,active,jacc

def main():
    rows=json.loads((OUT/"V21_nov2026_forward_199.json").read_text())["surviving_portfolios"]
    if len(rows)!=44:
        raise ValueError("Expected 44 candidates from original frozen November forward test")
    clean=[];rejected_same=[]
    for row in rows:
        tags=[("|".join([a[0],a[5],a[3]])) for a in (z.split("|") for z in row["legs"])]
        if len(set(tags))==len(tags):
            clean.append(row)
        else: rejected_same.append(row)
    if len(clean)!=6 or len(rejected_same)!=38: raise AssertionError((len(clean),len(rejected_same)))
    all_legs=sorted({z for row in clean for z in row["legs"]})
    trades=legs_trades(all_legs)
    reports=[]
    for row in clean:
        legs=row["legs"]
        shared_times=0;shared_side=0;overlap_positions=0;pairs=[]
        for a,b in combinations(legs,2):
            if a.split("|")[0]!=b.split("|")[0]:continue
            same,active,jacc=pair_metrics(trades[a],trades[b])
            shared_times+=same
            overlap_positions+=active
            if a.split("|")[3]==b.split("|")[3]:
                shared_side+=same
            pairs.append({"leg_a":a,"leg_b":b,"same_entry_utc":same,
                          "overlapping_position_pairs":active,"jaccard_same_entry":round(jacc,6)})
        reports.append({
            "id":row["id"],
            "nov2026_bp":row["nov_realized_equal_notional_bp"],
            "janoct2026_and_2025_min_month_bp":row["previous_min_22month_bp"],
            "month_2025_bp":row["previous_profit_2025_bp"],
            "month_2026_janoct_bp":row["previous_profit_2026_janoct_bp"],
            "nov_closed_trades":row["nov_closed_trades_component_sum"],
            "legs":legs,
            "same_asset_same_entry_historical_22mo":shared_times,
            "same_asset_same_entry_same_side_historical_22mo":shared_side,
            "overlapping_positions_historical_22mo":overlap_positions,
            "leg_count_by_strategy":{leg:len(trades[leg]) for leg in legs},
            "overlap_details":pairs
        })
    for x in reports:
        print("V21_OVERLAP_CANDIDATE",json.dumps({k:v for k,v in x.items() if k not in ("legs","overlap_details","leg_count_by_strategy")}),flush=True)
    # Uniqueness outranks raw November performance; among all six,
    # prefer fewest direct same-symbol simultaneous entries, then stronger
    # 2025-2026 weakest month, finally November forward PnL.
    reports.sort(key=lambda a:(a["same_asset_same_entry_historical_22mo"],
                               -a["janoct2026_and_2025_min_month_bp"],
                               -a["nov2026_bp"]))
    chosen=reports[0]
    # Every two remaining non-duplicated portfolios contain exactly 3 same bot configurations.
    for a,b in combinations(clean,2):
        shared=len(set(a["legs"]) & set(b["legs"]))
        if shared!=3:
            raise AssertionError(f"Unexpected unique group structure: {a['id']} {b['id']} {shared}")
    result={
        "date_filter":"2026-11-01 to 2026-11-12 20:00 UTC",
        "historical_overlap_sample":"2025-01-01 to 2026-11-01 00:00 UTC (22 months)",
        "original_44":len(rows),
        "excluded_duplicate_same_symbol_hour_side_within_portfolio":len(rejected_same),
        "remaining_structurally_distinct":len(clean),
        "excluded_near_duplicate_portfolios_sharing_3_of_4_bots":len(clean)-1,
        "final_portfolio_count":1,
        "final_selected_id":chosen["id"],
        "selection_priority":"Zero duplicated same asset+UTC entry session+direction within portfolio; minimize actual same asset simultaneous entry in historical data; maximize minimum positive month Jan2025-Oct2026; maximize positive Nov2026",
        "caveats":["At least one strategy (BTCUSD H4 range_top_20 short H3 20utc) is shared by all 44 starting portfolios",
                   "Opposite-side trades on the same asset may overlap in time; collision and position overlap metrics reported",
                   "One retained portfolio is a single selected configuration; not an independent diversified collection",
                   "No hard stop loss in original 199 method model; swap and broker commissions excluded",
                   "November 2026 period incomplete; not live-deployment validation",
                   "These strategies selected on 2025-2026 historical data; in-sample selection bias"],
        "selected_portfolio":chosen,
        "six_structurally_distinct_ranked":reports,
        "rejected_38_ids":[z["id"] for z in rejected_same],
        "rejected_5_redundant_ids":[x["id"] for x in reports if x["id"]!=chosen["id"]],
        "remaining_all_44_legs_overlap_core":'BTCUSD|H4|range_top_20|short|H3|20utc'
    }
    (OUT/"V21_nov2026_no_overlap_audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    lines=["# V21: eliminate duplicated / over-synchronized strategies","",
           "Frozen input: 44 portfolios profitable through 2026-11-12 20:00 UTC.",
           "",
           f"Starting portfolios: {len(rows)}",
           f"Remove internally duplicated symbol+entry hour+trade direction: {len(rejected_same)}",
           f"Structurally distinct candidates: {len(clean)}",
           f"Remove 3/4-identical portfolios: {len(clean)-1}",
           f"**Final selected: {chosen['id']} (1 portfolio)**",
           "",
           "## Six unique-time-direction candidates","",
           "|ID|2025-2026 min month (bp)|Nov 2026 (bp)|Exact same-asset entry collisions Jan2025-Oct2026|Total overlapping position pairs|",
           "|---|---:|---:|---:|---:|"]
    for row in reports:
        lines.append(f"|{row['id']}|{row['janoct2026_and_2025_min_month_bp']:.3f}|{row['nov2026_bp']:.3f}|{row['same_asset_same_entry_historical_22mo']}|{row['overlapping_positions_historical_22mo']}|")
    lines.extend(["","## Selected bot configurations",""])
    for s in chosen["legs"]:lines.append(f"- `{s}`")
    lines.extend(["","## Important limitations","",
                  "Same symbol/time/direction duplication eliminated among bots; however, short and long on the same symbol can still overlap in held positions even when entry times differ. Do not treat the selected portfolio as fully risk-independent.",
                  "Exness Bid/Ask + assumed slippage; swap, commission, hard SL, margin, and execution conditions not included.",
                  "November 2026 has not ended."])
    (OUT/"V21_nov2026_no_overlap_audit.md").write_text("\n".join(lines)+"\n")
    print("V21_DEDUP_FINAL",json.dumps({
        "before":len(rows),"removed_1":len(rejected_same),
        "after_first":len(clean),"removed_2":len(clean)-1,
        "retained":chosen["id"],"nov_bp":chosen["nov2026_bp"],
        "min_month_bp":chosen["janoct2026_and_2025_min_month_bp"],
        "same_entry_collisions":chosen["same_asset_same_entry_historical_22mo"],
        "overlap_positions":chosen["overlapping_positions_historical_22mo"]
    }),flush=True)

if __name__=="__main__":
    main()
