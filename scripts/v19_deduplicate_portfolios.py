#!/usr/bin/env python3
"""V19: deduplicate all 22 locked four-leg portfolios by REAL opening-event overlap.

Compare full 2025-2026 Oct actual backtest entry moments (UTC, instrument, side).
Same scheduled hour by itself is not a duplicate. An edge requires at least 3
of 4 identical constituent bot specifications OR at least 85% entry inclusion
of smaller portfolio AND >=70% multiset Jaccard for historical order events.
In both cases portfolio hour sets must overlap >=2 hourly slots.
Prefer realized November 2026 P&L (no retuning), then historical profit, then
historical number of orders. November-loss portfolios remain eligible unless
a better similar portfolio replaces them.

No live trade API. Never delete source files.
"""
import collections
import json
from pathlib import Path

import numpy as np
import pandas as pd

import v19_strategy_screen as v19

HISTORY=Path("data/v19_energies")
SOURCE=Path("data/v19_strategy_screen/V19_22_profit_then_orders_filtered.json")
NOV=Path("results/v19_november_2026/V19_nov2026_22_replay.json")
OUT=Path("results/v19_november_2026")
OVERLAP=0.85
JACCARD=0.70


def one_leg_events(df, leg, expected):
    symbol, tf, signal, side, holdstr, hour = leg.split("|")
    hold = int(holdstr[1:])
    t = df.timestamp_utc.dt
    ts = df.timestamp_utc
    month_index = ((t.year - 2025)*12 + t.month - 1).to_numpy(dtype=int)
    bid=df.bid_open.to_numpy()
    ask=df.ask_open.to_numpy()
    mid=(bid+ask)/2
    valid=np.isfinite(bid) & np.isfinite(ask) & np.isfinite(mid) & (mid>0)
    idx=np.arange(len(df))
    next_idx=np.minimum(idx+hold,len(df)-1)
    valid_pair=(idx+hold<len(df)) & valid & valid[next_idx]
    cond=v19.signals(df)[signal] & valid_pair
    if hour!="all":
        cond &= (t.hour.to_numpy()==int(hour[:2])) & (t.minute.to_numpy()==0)
    entries=v19.pick_nonoverlap(np.flatnonzero(cond), hold)
    months=month_index[next_idx[entries]]
    entries=entries[(months>=0) & (months<22)]
    if len(entries)!=expected:
        raise RuntimeError(f"Mismatch from V19 original strategy census {leg}: {len(entries)} != {expected}")
    return [(symbol,side,ts.iloc[int(i)].isoformat()) for i in entries]


def summary_of(events):
    ct=collections.Counter(events)
    return ct

def compare(p,q,cache,novcache):
    A=cache[p["portfolio"]];B=cache[q["portfolio"]]
    small=min(sum(A.values()),sum(B.values()))
    intersection=sum(min(v,B.get(k,0)) for k,v in A.items())
    union=sum(A.values())+sum(B.values())-intersection
    containment=intersection/small if small else 0
    jaccard=intersection/union if union else 0
    exact_legs=len(set(p["legs"])&set(q["legs"]))
    hoursA={v.split("|")[-1] for v in p["legs"]}
    hoursB={v.split("|")[-1] for v in q["legs"]}
    common_hours=sorted(hoursA&hoursB)
    # Directional event intersection is required, not just same bar timestamp.
    duplicate=len(common_hours)>=2 and (exact_legs>=3 or (containment>=OVERLAP and jaccard>=JACCARD))
    N1=novcache.get(p["portfolio"],collections.Counter())
    N2=novcache.get(q["portfolio"],collections.Counter())
    novintersection=sum(min(v,N2.get(k,0)) for k,v in N1.items())
    novunion=sum(N1.values())+sum(N2.values())-novintersection
    return dict(a=p["portfolio"],b=q["portfolio"],shared_legs=exact_legs,
                overlapping_session_hours_utc=[int(x[:2]) for x in common_hours if x!="all"],
                historical_matching_orders=intersection,
                historical_containment_of_smaller=round(containment,5),
                historical_multiset_jaccard=round(jaccard,5),
                november_matching_orders=novintersection,
                november_multiset_jaccard=round(novintersection/novunion,5) if novunion else 0,
                redundant=duplicate)


def main():
    out=OUT
    out.mkdir(parents=True,exist_ok=True)
    source=json.loads(SOURCE.read_text())
    selected=source["retained"]
    assert len(selected)==22 and len(set(x["portfolio"] for x in selected))==22
    nov=json.loads(NOV.read_text())
    month_perf={r["id"]:r for r in nov["rows"]}
    ledger=json.loads((OUT/"V19_nov2026_leg_ledger.json").read_text())
    # Original census has a fully explicit single-bot trade count for validation
    original=pd.read_csv("data/v19_strategy_screen/all_single_strategy_metrics.csv")
    counts=dict(zip(original.id,original.trades))
    legs=sorted({leg for p in selected for leg in p["legs"]})
    print("V19_DEDUP_LEGS",len(legs),flush=True)
    by_frame={}
    by_leg={}
    for leg in legs:
        symbol,tf,*_=leg.split("|")
        key=(symbol,tf)
        if key not in by_frame:
            by_frame[key]=v19.read_frame(HISTORY,*key)
        by_leg[leg]=one_leg_events(by_frame[key],leg,int(counts[leg]))
        print("V19_DEDUP_LEG",leg,"orders",len(by_leg[leg]),flush=True)

    history={}
    nov_events={}
    for p in selected:
        pid=p["portfolio"]
        history[pid]=summary_of(ev for leg in p["legs"] for ev in by_leg[leg])
        nov_events[pid]=summary_of((ev["symbol"],ev["side"],ev["entry_utc"])
                                   for leg in p["legs"] for ev in ledger[leg])
        assert sum(nov_events[pid].values())==month_perf[pid]["november_total_order_signals"]

    pairs=[]
    for i,p in enumerate(selected):
        for q in selected[i+1:]:
            pairs.append(compare(p,q,history,nov_events))

    index={(p["a"],p["b"]):p for p in pairs}
    def pair(a,b):
        return index.get((a,b)) or index.get((b,a))
    ordered=sorted(selected,key=lambda x:(
        -month_perf[x["portfolio"]]["november_realized_profit_bp"],
        -x["total_profit_bp"],-x["total_entries"],x["portfolio"]))
    keep=[]
    removed=[]
    for cand in ordered:
        conflicts=[(u,pair(cand["portfolio"],u["portfolio"])) for u in keep
                   if pair(cand["portfolio"],u["portfolio"])["redundant"]]
        if conflicts:
            conflicts.sort(key=lambda t:(
                -t[1]["historical_multiset_jaccard"],
                -t[1]["historical_containment_of_smaller"],
                -t[1]["shared_legs"]))
            winner,comparison=conflicts[0]
            removed.append(dict(portfolio=cand["portfolio"],replaced_by=winner["portfolio"],
                 november_bp=month_perf[cand["portfolio"]]["november_realized_profit_bp"],
                 kept_november_bp=month_perf[winner["portfolio"]]["november_realized_profit_bp"],
                 reason=comparison))
        else:
            keep.append(cand)
    kept=[{
        "portfolio":p["portfolio"],
        "family":p["family"],
        "november_realized_profit_bp":month_perf[p["portfolio"]]["november_realized_profit_bp"],
        "november_closed_orders":month_perf[p["portfolio"]]["november_closed_orders"],
        "historical_profit_bp":p["total_profit_bp"],
        "historical_total_orders":p["total_entries"],
        "historical_months_profitable":p["positive_months"],
        "entry_utc_hours":sorted({int(leg.split("|")[-1][:2]) for leg in p["legs"]}),
        "legs":p["legs"]
    } for p in keep]
    report={
        "study":"V19 remove redundant 4-bot portfolio variants based on actual historical entry timestamps and same hours",
        "scope":"22 original selected V19 portfolios; November replay through 2026-11-12 18:00 UTC",
        "comparison_period":"2025-01-01 to 2026-10-31 UTC",
        "entry_event_key":"(symbol, side, exact UTC entry timestamp), counted with multiplicity",
        "redundancy_rule":"At least 2 scheduled entry-hour slots in common AND (3+ of 4 identical bot specifications OR historical event containment >=85% and multiset Jaccard >=70%).",
        "ranking_rule":"Highest November 2026 realized PnL in bp first; tie highest historical total bp, then most historical orders.",
        "costs":"Exness actual bid/ask spread + assumed 1bp extra slippage each side, swap/commissions excluded",
        "do_not_interpret_as":"No guarantee of independent trading. Even retained portfolios may share clock hours, correlated oil exposure and/or entry events. This filter does not force nonoverlapping position hours.",
        "counts":{
            "initial":len(selected),
            "removed_redundant":len(removed),
            "retained":len(kept),
            "retained_profitable_november":sum(x["november_realized_profit_bp"]>0 for x in kept),
            "retained_losing_november":sum(x["november_realized_profit_bp"]<0 for x in kept),
            "historical_pairs_compared":len(pairs),
            "redundant_pairs":sum(x["redundant"] for x in pairs)
        },
        "retained":kept,
        "removed":removed,
        "pairwise":pairs,
    }
    (out/"V19_22_deduplicated_by_time_and_strategy.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    pd.DataFrame([{k:v for k,v in row.items() if k not in ("legs","entry_utc_hours")} for row in kept]).to_csv(
      out/"V19_22_deduplicated_by_time_and_strategy.csv",index=False)
    print("V19_DEDUP_FINAL",json.dumps({"counts":report["counts"],"kept":[(x["portfolio"],x["november_realized_profit_bp"]) for x in kept],
     "removed":[(x["portfolio"],x["replaced_by"]) for x in removed]}),flush=True)


if __name__=="__main__":
    main()
