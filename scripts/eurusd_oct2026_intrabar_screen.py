#!/usr/bin/env python3
"""Exness EURUSD October 2026 M1/M5 same-candle, bid/ask-aware tick replay.
Entry decisions use only quotes strictly before a fixed signal time. Results exploratory.
"""
import io
import json
import math
import zipfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from numba import njit

SOURCE = "https://ticks.ex2archive.com/ticks/EURUSD/2026/10/Exness_EURUSD_2026_10.zip"
OUT = Path("results/eurusd_oct2026_intrabar")
PIP = 0.0001
BASE_EXTRA_PIPS = 0.20  # round-trip slippage beyond archived Bid/Ask
STRESS_EXTRA_PIPS = 0.50  # total extra execution cost, round trip
TRAIN_END_NS = pd.Timestamp("2026-10-15T00:00:00Z").value
SESSION_HOURS = {"all": None, "asia_00_07": (0, 7), "overlap_12_17": (12, 17), "london_07_12": (7, 12)}

@njit(cache=True)
def fill_trades(eidx, didx, direction, bid, ask, stop_pips, tp_pips):
    n = len(eidx)
    gross = np.empty(n, dtype=np.float64)
    closes = np.empty(n, dtype=np.int64)
    why = np.empty(n, dtype=np.int8)  # 0 timed, 1 stop, 2 tp
    for i in range(n):
        e = eidx[i]
        end = didx[i]
        side = direction[i]
        entry = ask[e] if side == 1 else bid[e]
        exitidx = end
        reason = 0
        for k in range(e + 1, end + 1):
            mark = bid[k] if side == 1 else ask[k]
            movement = (mark - entry) / PIP * side
            if movement <= -stop_pips:
                exitidx = k
                reason = 1
                break
            if movement >= tp_pips:
                exitidx = k
                reason = 2
                break
        exitprice = bid[exitidx] if side == 1 else ask[exitidx]
        gross[i] = (exitprice - entry) * side / PIP
        closes[i] = exitidx
        why[i] = reason
    return gross, closes, why

def get_ticks():
    response = requests.get(SOURCE, timeout=(30, 240))
    response.raise_for_status()
    raw = response.content
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise RuntimeError("Invalid Exness ZIP")
    pieces = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zz:
        for name in zz.namelist():
            if name.lower().endswith(".csv"):
                pieces.append(pd.read_csv(zz.open(name), usecols=["Timestamp", "Bid", "Ask"]))
    if not pieces:
        raise RuntimeError("No source CSV")
    d = pd.concat(pieces, ignore_index=True)
    ts = pd.to_datetime(d["Timestamp"], utc=True, format="ISO8601", errors="coerce")
    ok = ts.notna() & d["Bid"].notna() & d["Ask"].notna()
    if not bool(ok.all()):
        raise RuntimeError("Unexpected missing tick values")
    times = ts.astype("int64").to_numpy()
    bid = d["Bid"].to_numpy(dtype=np.float64)
    ask = d["Ask"].to_numpy(dtype=np.float64)
    if np.any(np.diff(times) < 0) or np.any(bid > ask):
        raise RuntimeError("Unordered or crossed quotes in source")
    return times, bid, ask, hashlib.sha256(raw).hexdigest()

def prepare_frame(ts, bid, ask, period_sec, signal_sec, deadline_sec, max_entry_lag_sec):
    period_ns = period_sec * 1_000_000_000
    barid, starts, counts = np.unique(ts // period_ns, return_index=True, return_counts=True)
    ends = starts + counts
    barstarts = barid * period_ns
    signal_time = barstarts + signal_sec * 1_000_000_000
    entry = np.searchsorted(ts, signal_time, side="left")
    valid = (entry < ends) & (entry > starts)
    good = entry[valid]
    valid_idx = np.flatnonzero(valid)
    entry = entry[valid]
    starts = starts[valid]
    ends = ends[valid]
    barstarts = barstarts[valid]
    enough_quote = (ts[entry] < signal_time[valid] + max_entry_lag_sec * 1_000_000_000)
    min_updates = 3 if period_sec == 60 else 5
    enough_quote &= (entry - starts >= min_updates)
    entry = entry[enough_quote]
    starts = starts[enough_quote]
    ends = ends[enough_quote]
    barstarts = barstarts[enough_quote]
    prev = entry - 1  # signal strictly before intended entry
    cutoff = np.searchsorted(ts, barstarts + deadline_sec * 1_000_000_000, side="right") - 1
    ok = (cutoff >= entry) & (cutoff < ends)
    entry, starts, prev, cutoff, barstarts = entry[ok], starts[ok], prev[ok], cutoff[ok], barstarts[ok]
    deltamid = ((bid[prev] + ask[prev]) - (bid[starts] + ask[starts])) / (2.0 * PIP)
    prior_spread = (ask[prev] - bid[prev]) / PIP
    hour = ((barstarts // 1_000_000_000) % 86400) // 3600
    return {
        "entry": entry, "deadline": cutoff, "start": barstarts,
        "delta": deltamid, "spread_prior": prior_spread, "hour": hour,
        "period_sec": period_sec, "signal_sec": signal_sec,
        "deadline_sec": deadline_sec
    }

def metrics(p):
    p = np.asarray(p)
    n = len(p)
    if not n:
        return {"n": 0, "sum_pips": 0.0, "avg_pips": None, "win_pct": None, "profit_factor": None, "max_dd_pips": None, "t_value": None}
    pos = float(p[p > 0].sum())
    neg = float(-p[p < 0].sum())
    dd = np.maximum.accumulate(np.r_[0.0, np.cumsum(p)])[1:] - np.cumsum(p)
    return {"n": n, "sum_pips": round(float(p.sum()), 4),
            "avg_pips": round(float(p.mean()), 5),
            "win_pct": round(100.0 * float(np.mean(p > 0)), 2),
            "profit_factor": round(pos / neg, 4) if neg else None,
            "max_dd_pips": round(float(np.max(dd)), 3),
            "t_value": round(float(p.mean() / (p.std(ddof=1) / math.sqrt(n))), 3) if n > 1 and p.std(ddof=1) > 0 else None}

def main():
    ts, bid, ask, sha = get_ticks()
    OUT.mkdir(parents=True, exist_ok=True)
    allrows = []
    strategies = []
    cached = {}
    candidate_count = 0
    for frame, sec, offsets, thresholds, plans in (
        ("M1", 60, [15, 30], [0.5, 1.0, 1.8], [(2.0, 3.0), (3.0, 5.0)]),
        ("M5", 300, [60, 120], [1.0, 2.0, 3.5], [(3.0, 4.0), (5.0, 8.0)]),
    ):
        cutoff = 55 if sec == 60 else 285
        for offset in offsets:
            base = prepare_frame(ts, bid, ask, sec, offset, cutoff, 10 if sec == 60 else 30)
            cached[(frame, offset)] = base
            for style in ("momentum", "fade"):
                for threshold in thresholds:
                    for spread_cap in (0.8, 1.5):
                        for session, bounds in SESSION_HOURS.items():
                            selection = ((np.abs(base["delta"]) >= threshold) &
                                         (base["spread_prior"] <= spread_cap) &
                                         (base["spread_prior"] >= 0.0))
                            if bounds is not None:
                                selection &= (base["hour"] >= bounds[0]) & (base["hour"] < bounds[1])
                            if not selection.any():
                                continue
                            e = base["entry"][selection]
                            stop_idx = base["deadline"][selection]
                            times = base["start"][selection]
                            dirs = np.sign(base["delta"][selection]).astype(np.int8)
                            if style == "fade":
                                dirs *= -1
                            for sl,tp in plans:
                                candidate_count += 1
                                pnl_gross, close_idx, why = fill_trades(e, stop_idx, dirs, bid, ask, sl, tp)
                                pnl = pnl_gross - BASE_EXTRA_PIPS
                                training = times < TRAIN_END_NS
                                test = ~training
                                tr = metrics(pnl[training])
                                te = metrics(pnl[test])
                                full = metrics(pnl)
                                score = tr["t_value"] if tr["t_value"] is not None else -999
                                row = {"id": f"OI{candidate_count:04d}", "frame": frame, "style": style,
                                       "entry_sec": offset, "exit_sec": cutoff,
                                       "signal_move_min_pips": threshold, "spread_max_pips": spread_cap,
                                       "session_utc": session, "sl_pips": sl, "tp_pips": tp,
                                       "n_train": tr["n"], "train_pips": tr["sum_pips"],
                                       "train_pf": tr["profit_factor"], "train_t": tr["t_value"],
                                       "n_test": te["n"], "test_pips": te["sum_pips"],
                                       "test_pf": te["profit_factor"],
                                       "n_oct": full["n"], "oct_net_pips": full["sum_pips"],
                                       "oct_win_pct": full["win_pct"], "oct_pf": full["profit_factor"],
                                       "oct_max_dd_pips": full["max_dd_pips"],
                                       "oct_net_stress_05_pips": round(float(pnl.sum()) - (STRESS_EXTRA_PIPS - BASE_EXTRA_PIPS) * len(pnl), 4),
                                       "train_selection_score": score}
                                allrows.append(row)
    result = pd.DataFrame(allrows)
    if result.empty:
        raise RuntimeError("No strategy evaluations generated")
    result.to_csv(OUT / "all_predefined_configs.csv", index=False)
    # Choose candidates using ONLY the first portion of October, before checking the second.
    rankable = result.loc[
        (result["n_train"] >= 30) &
        (result["train_pips"] > 0) &
        (result["train_pf"] >= 1.05) &
        (result["train_t"] >= 0.6)
    ].copy()
    rankable = rankable.sort_values(
        ["train_selection_score","train_pips","n_train"],
        ascending=[False,False,False], kind="mergesort")
    candidates = []
    for (frame, style), group in rankable.groupby(["frame","style"],sort=True):
        candidates.extend(group.head(3)["id"].tolist())
    # This pre-validation shortlist is explicitly separated from strategies discovered after seeing the full month.
    selected = result[result["id"].isin(candidates)].copy()
    selected["train_only_selected"] = True
    selected["test_positive"] = selected["test_pips"] > 0
    selected["oct_positive"] = selected["oct_net_pips"] > 0
    selected["oct_stress_positive"] = selected["oct_net_stress_05_pips"] > 0
    selected.to_csv(OUT / "train_selected_holdout_results.csv", index=False)
    # Independent audit: all rules that appear profitable on the whole month,
    # not claimed to be out-of-sample or deployable.
    positive = result[(result["n_oct"] >= 20) & (result["oct_net_pips"] > 0)]
    positive = positive.sort_values(["oct_net_stress_05_pips","oct_net_pips"], ascending=False)
    positive.head(100).to_csv(OUT / "exploratory_oct_positive_top100.csv", index=False)
    # Intrabar order log for all strategies selected without peeking at holdout results.
    logs = []
    for row in selected.to_dict("records"):
        base = cached[(row["frame"], int(row["entry_sec"]))]
        flag = (np.abs(base["delta"]) >= row["signal_move_min_pips"]) & (base["spread_prior"] <= row["spread_max_pips"]) & (base["spread_prior"] >= 0)
        bounds = SESSION_HOURS[row["session_utc"]]
        if bounds is not None:
            flag &= (base["hour"] >= bounds[0]) & (base["hour"] < bounds[1])
        e, end, start = base["entry"][flag], base["deadline"][flag], base["start"][flag]
        side = np.sign(base["delta"][flag]).astype(np.int8)
        if row["style"] == "fade":
            side *= -1
        gp, exit_index, why = fill_trades(e, end, side, bid, ask, row["sl_pips"], row["tp_pips"])
        for k in range(len(e)):
            logs.append({"id": row["id"],"frame":row["frame"],
                         "bar_open_utc":pd.Timestamp(int(start[k]),tz="UTC").isoformat(),
                         "entry_utc":pd.Timestamp(int(ts[e[k]]),tz="UTC").isoformat(),
                         "exit_quote_utc":pd.Timestamp(int(ts[exit_index[k]]),tz="UTC").isoformat(),
                         "side":"BUY" if side[k] == 1 else "SELL",
                         "entry_bid":float(bid[e[k]]),"entry_ask":float(ask[e[k]]),
                         "exit_bid":float(bid[exit_index[k]]),"exit_ask":float(ask[exit_index[k]]),
                         "exit_reason":("time" if why[k] == 0 else ("SL" if why[k] == 1 else "TP")),
                         "net_pips":round(float(gp[k]-BASE_EXTRA_PIPS),5),
                         "stress_net_pips":round(float(gp[k]-STRESS_EXTRA_PIPS),5),
                         "half":"train" if start[k] < TRAIN_END_NS else "holdout"})
    trades = pd.DataFrame(logs)
    trades.to_csv(OUT / "train_selected_trades.csv", index=False)
    data_manifest = {
        "symbol":"EURUSD", "source_url":SOURCE, "source_zip_sha256":sha,
        "source_ticks":int(len(ts)), "timezone":"UTC", "test_month":"2026-10",
        "train_period":"2026-10-01..2026-10-14 UTC",
        "untouched_holdout_period":"2026-10-15..2026-10-30 UTC",
        "training_rule":"filter >=30 trades, positive train pips, PF>=1.05, t>=0.6; rank by train-only t-stat and keep top 3 per frame and style",
        "candidate_count":candidate_count,
        "month_positive_exploratory_count":int(len(positive)),
        "holdout_selected_count":int(len(selected)),
        "holdout_selected_oct_positive_count":int(selected["oct_positive"].sum()) if len(selected) else 0,
        "holdout_selected_oct_and_holdout_positive_count":int((selected["oct_positive"] & selected["test_positive"]).sum()) if len(selected) else 0,
        "holdout_selected_oct_and_holdout_stress_positive_count":int((selected["oct_positive"] & selected["test_positive"] & selected["oct_stress_positive"]).sum()) if len(selected) else 0,
        "tick_time_first":pd.Timestamp(int(ts[0]),tz="UTC").isoformat(),
        "tick_time_last":pd.Timestamp(int(ts[-1]),tz="UTC").isoformat(),
        "costs":{
            "archived_spread":"included through buy at Ask, exit Bid; sell at Bid, exit Ask",
            "base_extra_pips_roundtrip":BASE_EXTRA_PIPS,
            "stress_extra_pips_roundtrip":STRESS_EXTRA_PIPS,
            "commission":"NOT INCLUDED; add according to specific Exness account",
            "slippage_limits":"hypothetical fixed per trade; does not model liquidity, delay, reject/requote or adverse gaps"
        },
        "signals":"at scheduled second, use the last available tick strictly before second; execute at next tick; no future candle values consulted",
        "exit":"first tick after entry touching TP/SL, or close at deadline using latest bid/ask quote at or before that deadline; all times inside same bar",
        "rule_count_warning":"Multiple predefined rules tested on a single month; even holdout outcomes are exploratory, not independent multi-month validation.",
        "generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    (OUT / "summary.json").write_text(json.dumps(data_manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines = [
        "# EURUSD October 2026 intrabar tick replay (M1, M5)",
        "",
        f"- Exness raw tick rows: **{len(ts):,}**; predeclared configurations: **{candidate_count}**.",
        "- Entry: after 15s/30s in M1; after 60s/120s in M5.",
        "- Exit: TP/SL first or at 55s (M1) / 285s (M5), always within original bar.",
        "- Trading signal uses first tick and last tick **before entry decision**, preventing future leakage.",
        "- Bid/Ask spread included, +0.2 pip per round trip extra execution friction; +0.5 pip stressed.",
        f"- Whole-month profit on >=20 trades (exploratory, in-sample selection): **{len(positive)}** configs.",
        f"- Selected only on first half of month: **{len(selected)}** configs.",
        f"- Selected with positive October: **{data_manifest['holdout_selected_oct_positive_count']}**.",
        f"- Selected with positive October AND positive second-half holdout: **{data_manifest['holdout_selected_oct_and_holdout_positive_count']}**.",
        f"- Plus positive full-month stress +0.5 pip: **{data_manifest['holdout_selected_oct_and_holdout_stress_positive_count']}**.",
        "",
        "## Train-selected candidates (second half was not used to rank)",
        "",
        "ID | Frame | Side signal | Entry s | Threshold pip | Spread cap | Session UTC | SL/TP pip | Train pips | Holdout pips | October pips | Stress Oct pips | N",
        "---|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:"
    ]
    for r in selected.sort_values("train_selection_score",ascending=False).to_dict("records"):
        lines.append(f"{r['id']} | {r['frame']} | {r['style']} | {r['entry_sec']} | {r['signal_move_min_pips']} | {r['spread_max_pips']} | {r['session_utc']} | {r['sl_pips']}/{r['tp_pips']} | {r['train_pips']} | {r['test_pips']} | {r['oct_net_pips']} | {r['oct_net_stress_05_pips']} | {r['n_oct']}")
    lines.extend(["","Only a single month was replayed. Do not deploy with real funds based on this screen alone.",
                  "The archived quotes are not an MT5 execution record. Extra commission, latency and partial fills can reverse tiny profits.",
                  ""])
    (OUT / "REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(data_manifest,ensure_ascii=False),flush=True)
    print(selected[["id","frame","style","n_train","train_pips","n_test","test_pips","n_oct","oct_net_pips","oct_net_stress_05_pips"]].to_string(index=False),flush=True)

if __name__ == "__main__":
    main()
