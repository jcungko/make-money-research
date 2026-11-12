#!/usr/bin/env python3
"""V19: exact daily order-opening frequency for all 89 portfolios with 21+/22 profitable months.

Each portfolio comprises four independently traded legs. One new position per
leg on eligible entry signals; overlap between different legs is counted as
separate orders on a hedging account. Historical period 2025-01-01 through
2026-10-31 inclusive UTC. Counts are NOT realized broker fills.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v19_strategy_screen as v19

START = pd.Timestamp("2025-01-01", tz="UTC")
END = pd.Timestamp("2026-10-31", tz="UTC")
DAYS = pd.date_range(START, END, freq="D", tz="UTC")
N_DAYS = len(DAYS)


def candidate_pool(rows, symbol, count=40):
    selected, seen = [], set()
    for r in sorted((x for x in rows if x["symbol"] == symbol),
                    key=v19.best_key, reverse=True):
        key = tuple(np.round(r["monthly_bp"], 2))
        if key in seen:
            continue
        selected.append(r)
        seen.add(key)
        if len(selected) == count:
            break
    assert len(selected) == count, (symbol, len(selected))
    return selected


def discover_qualifiers(pools):
    """Replicate V19's exact enumerated families with candidates >=21 months."""
    s0, s1 = "USOIL", "UKOIL"
    a, b = [np.asarray([r["monthly_bp"] for r in pools[x]], dtype=float)
            for x in (s0, s1)]
    result = []

    def keep(group, leg_symbols, indexes, monthly):
        months_good = (monthly > 0).sum(axis=1)
        both_years = (monthly[:, :12].sum(axis=1) > 0) & (monthly[:, 12:].sum(axis=1) > 0)
        positions = np.flatnonzero(both_years & (months_good >= 21))
        print("V19_DAILY_FAMILY", group, len(positions), flush=True)
        for i in positions:
            ids = [pools[sym][int(idx)]["id"] for sym, idx in zip(leg_symbols, indexes[i])]
            result.append({
                "family": group,
                "legs": ids,
                "profitable_months": int(months_good[i]),
                "profit_2025_bp": float(monthly[i, :12].sum()),
                "profit_2026_bp": float(monthly[i, 12:].sum()),
                "monthly_bp": monthly[i].tolist()
            })

    ia4 = np.asarray(list(itertools.combinations(range(40), 4)), dtype=np.int16)
    keep("4 USOIL", [s0]*4, ia4, a[ia4].mean(axis=1))
    del ia4

    ia2 = np.asarray(list(itertools.combinations(range(40), 2)), dtype=np.int16)
    ib2 = np.asarray(list(itertools.combinations(range(40), 2)), dtype=np.int16)
    idx2 = np.concatenate((np.repeat(ia2, len(ib2), axis=0),
                           np.tile(ib2, (len(ia2), 1))), axis=1)
    vals2 = ((a[ia2].sum(axis=1)[:, None, :] + b[ib2].sum(axis=1)[None, :, :]) / 4).reshape(-1, 22)
    keep("2 USOIL + 2 UKOIL", [s0,s0,s1,s1], idx2, vals2)
    del idx2, vals2

    ia3 = np.asarray(list(itertools.combinations(range(40), 3)), dtype=np.int16)
    idx3 = np.concatenate((np.repeat(ia3, len(b), axis=0),
                           np.tile(np.arange(len(b), dtype=np.int16), (len(ia3), 1)).reshape(-1, 1)), axis=1)
    vals3 = ((a[ia3].sum(axis=1)[:, None, :] + b[None, :, :]) / 4).reshape(-1, 22)
    keep("3 USOIL + 1 UKOIL", [s0,s0,s0,s1], idx3, vals3)
    result.sort(key=lambda p: (-p["profitable_months"], -min(p["monthly_bp"]), -sum(p["monthly_bp"]), p["legs"]))
    if len(result) != 89 or sum(r["profitable_months"] == 22 for r in result) != 3:
        raise RuntimeError(f"Mismatch to published V19 report: {len(result)} total, "
                           f"{sum(r['profitable_months']==22 for r in result)} 22/22")
    return result


def reconstruct_open_days(df, row):
    """Duplicate V19.screen's entry filters exactly, and verify trade total."""
    _, tf, signal, side, hold_str, session = row["id"].split("|")
    hold = int(hold_str[1:])
    n = len(df)
    t = df["timestamp_utc"].dt
    month_index = ((t.year - 2025) * 12 + t.month - 1).to_numpy(dtype=int)
    bid = df.bid_open.to_numpy()
    ask = df.ask_open.to_numpy()
    mid = (bid + ask) / 2
    valid = np.isfinite(mid) & (mid > 0) & np.isfinite(bid) & np.isfinite(ask)
    idx = np.arange(n)
    exits = np.minimum(idx + hold, n-1)
    valid_pair = (idx + hold < n) & valid & valid[exits]
    qualified = v19.signals(df)[signal] & valid_pair
    if session != "all":
        qualified &= (t.hour.to_numpy() == int(session[:2])) & (t.minute.to_numpy() == 0)
    entries = v19.pick_nonoverlap(np.flatnonzero(qualified), hold)
    mm = month_index[exits[entries]]
    entries = entries[(mm >= 0) & (mm < 22)]
    if len(entries) != row["trades"]:
        raise RuntimeError(f"Entry count mismatch {row['id']}: {len(entries)} != {row['trades']}")
    timestamps = df.timestamp_utc.iloc[entries]
    utc_days = timestamps.dt.normalize()
    counts = utc_days.value_counts().reindex(DAYS, fill_value=0).to_numpy(dtype=np.int32)
    if counts.sum() != row["trades"]:
        raise RuntimeError(f"Calendar interval mismatch for {row['id']}")
    return counts


def stats_of(values):
    return {
        "min": round(float(np.min(values)), 4),
        "max": round(float(np.max(values)), 4),
        "mean": round(float(np.mean(values)), 4),
        "median": round(float(np.median(values)), 4)
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data/v19_energies"))
    ap.add_argument("--out", type=Path, default=Path("data/v19_strategy_screen"))
    args = ap.parse_args()

    stored = json.loads((args.out / "V19_screening_report.json").read_text())
    assert stored["total_pass_all_22"] == 3 and stored["total_pass_exactly_21"] == 86
    rows = [r for symbol in v19.SYMBOLS for r in v19.screen(args.root, symbol)]
    pool = {sym: candidate_pool(rows, sym) for sym in v19.SYMBOLS}
    selected = discover_qualifiers(pool)
    by_id = {r["id"]: r for r in rows}
    unique_legs = sorted({leg for item in selected for leg in item["legs"]})
    print("V19_DAILY_UNIQUE_LEGS", len(unique_legs), flush=True)

    timestamps_cache = {}
    frame_cache = {}
    for leg in unique_legs:
        row = by_id[leg]
        key = (row["symbol"], row["timeframe"])
        if key not in frame_cache:
            frame_cache[key] = v19.read_frame(args.root, *key)
        timestamps_cache[leg] = reconstruct_open_days(frame_cache[key], row)
    del frame_cache

    # Trading days: market has an M5 tick candle in at least one instrument
    # represented by the portfolio, INCLUDING occasional Sunday sessions.
    opens_by_symbol = {}
    for sym in ("USOIL", "UKOIL"):
        df = v19.read_frame(args.root, sym, "M5")
        opens_by_symbol[sym] = set(df.timestamp_utc.dt.normalize())
    assert N_DAYS == 669

    csv_rows, daily_records = [], []
    for i, item in enumerate(selected, 1):
        total_daily = np.sum([timestamps_cache[x] for x in item["legs"]], axis=0)
        total = int(total_daily.sum())
        expected = int(sum(by_id[x]["trades"] for x in item["legs"]))
        assert total == expected and total_daily.max() <= 4
        asset_names = {leg.split("|")[0] for leg in item["legs"]}
        market_mask = np.array([any(day in opens_by_symbol[s] for s in asset_names) for day in DAYS], dtype=bool)
        market_days = int(market_mask.sum())
        traded_days = int((total_daily > 0).sum())
        inactive_trading_days = int(np.count_nonzero((total_daily == 0) & market_mask))
        first_yr = DAYS.year == 2025
        second_yr = DAYS.year == 2026
        totals_2025 = int(total_daily[first_yr].sum())
        totals_2026 = int(total_daily[second_yr].sum())
        r = {
            "portfolio": f"V19-{i:03d}",
            "family": item["family"],
            "positive_months": item["profitable_months"],
            "october_2026_bp": round(float(item["monthly_bp"][21]), 5),
            "monthly_bp": [round(float(x), 5) for x in item["monthly_bp"]],
            "profit_2025_bp": round(float(item["profit_2025_bp"]), 5),
            "profit_2026_bp": round(float(item["profit_2026_bp"]), 5),
            "legs": item["legs"],
            "total_entries": total,
            "entries_2025": totals_2025,
            "entries_2026_Jan_Oct": totals_2026,
            "mean_per_calendar_day": round(total / N_DAYS, 5),
            "market_open_days": market_days,
            "mean_per_market_open_day": round(total / market_days, 5),
            "days_with_entries": traded_days,
            "mean_per_day_with_entry": round(total / traded_days, 5),
            "market_open_days_without_entry": inactive_trading_days,
            "share_market_days_with_no_entry_pct": round(inactive_trading_days * 100 / market_days, 3),
            "max_daily_entries": int(total_daily.max()),
            "daily_0_entries": int(np.count_nonzero(total_daily == 0)),
            "daily_1_entries": int(np.count_nonzero(total_daily == 1)),
            "daily_2_entries": int(np.count_nonzero(total_daily == 2)),
            "daily_3_entries": int(np.count_nonzero(total_daily == 3)),
            "daily_4_entries": int(np.count_nonzero(total_daily == 4)),
        }
        daily_records.append(r)
        csv_rows.append({k:v for k,v in r.items() if k not in ("legs", "monthly_bp")})
    out = args.out
    out.mkdir(exist_ok=True, parents=True)
    pd.DataFrame(csv_rows).to_csv(out / "V19_89_portfolios_trade_frequency.csv", index=False)
    retained = [r for r in daily_records if r["october_2026_bp"] >= 0]
    excluded = [r for r in daily_records if r["october_2026_bp"] < 0]
    zero_month = [r for r in retained if r["october_2026_bp"] == 0]
    filtered_report = {
        "criteria": "Keep V19 21+/22 positive-month strategies profitable in both 2025 and 2026 Jan-Oct, excluding those with strictly negative PnL in October 2026",
        "october_index": 21,
        "base_candidates": len(daily_records),
        "removed_negative_october": len(excluded),
        "retained_nonnegative_october": len(retained),
        "retained_positive_october": len(retained) - len(zero_month),
        "retained_zero_october": len(zero_month),
        "removed": [{"id":r["portfolio"],"october_2026_bp":r["october_2026_bp"]} for r in excluded],
        "retained": retained,
    }
    (out / "V19_89_filtered_oct2026.json").write_text(json.dumps(filtered_report,ensure_ascii=False,indent=2))
    pd.DataFrame([{k:v for k,v in r.items() if k not in ("legs", "monthly_bp")} for r in retained]).to_csv(out / "V19_filtered_no_loss_oct2026.csv", index=False)
    print("V19_FILTER_OCT2026", json.dumps({
        "original":len(daily_records),"removed":len(excluded),"retained":len(retained),
        "zero":len(zero_month),"positive":len(retained)-len(zero_month),
        "retained_21_months":sum(r["positive_months"]==21 for r in retained),
        "retained_22_months":sum(r["positive_months"]==22 for r in retained)
    }), flush=True)

    all_daily_mean = np.asarray([r["mean_per_calendar_day"] for r in daily_records])
    market_mean = np.asarray([r["mean_per_market_open_day"] for r in daily_records])
    daily_with_trade = np.asarray([r["mean_per_day_with_entry"] for r in daily_records])
    all_totals = np.asarray([r["total_entries"] for r in daily_records])
    min_max = {
        "total_entries_per_portfolio": stats_of(all_totals),
        "mean_entries_per_calendar_day": stats_of(all_daily_mean),
        "mean_entries_per_market_open_day": stats_of(market_mean),
        "mean_entries_per_day_with_entry": stats_of(daily_with_trade),
        "days_with_entries_per_portfolio": stats_of([r["days_with_entries"] for r in daily_records]),
        "market_days_without_entry_per_portfolio": stats_of([r["market_open_days_without_entry"] for r in daily_records]),
        "max_entries_in_one_day_by_portfolio": stats_of([r["max_daily_entries"] for r in daily_records])
    }
    report = {
        "source": "V19 Exness 2025 & 2026 (through Oct 31), exact 89 qualifying 21+/22 month strategies",
        "timezone": "UTC",
        "start": "2025-01-01",
        "end": "2026-10-31",
        "calendar_days": N_DAYS,
        "qualified": len(daily_records),
        "exact_21": sum(x["positive_months"] == 21 for x in daily_records),
        "exact_22": sum(x["positive_months"] == 22 for x in daily_records),
        "four_legs_per_portfolio": True,
        "entry_count_definition": "Each independent bot signal entering a position counts as one new order; simultaneous bot orders are counted separately (hedging). No pending orders or rejected trades are simulated.",
        "trading_day_definition": "UTC dates with at least one M5 Exness bid/ask tick for any instrument represented in the portfolio, including Sunday sessions.",
        "aggregate_summary": min_max,
        "family_summary": {
            group: {
                "portfolios": len(items),
                "avg_orders_per_calendar_day": round(float(np.mean([q["mean_per_calendar_day"] for q in items])),5),
                "avg_orders_per_market_day": round(float(np.mean([q["mean_per_market_open_day"] for q in items])),5),
                "avg_orders_per_portfolio_over_period": round(float(np.mean([q["total_entries"] for q in items])),3),
                "min_orders_per_calendar_day": round(float(min(q["mean_per_calendar_day"] for q in items)),5),
                "max_orders_per_calendar_day": round(float(max(q["mean_per_calendar_day"] for q in items)),5)
            }
            for group in sorted({x["family"] for x in daily_records})
            for items in [[x for x in daily_records if x["family"] == group]]
        },
        "highest_frequency": sorted(daily_records,key=lambda q:q["total_entries"],reverse=True)[:5],
        "lowest_frequency": sorted(daily_records,key=lambda q:q["total_entries"])[:5],
        "all_portfolios": daily_records
    }
    (out / "V19_89_portfolios_daily_trade_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("V19_DAILY_FINAL", json.dumps({
        "portfolio_count":len(daily_records),
        "calendar_days":N_DAYS,
        "totals":min_max,
        "families":report["family_summary"],
        "highest":report["highest_frequency"][0]["total_entries"],
        "lowest":report["lowest_frequency"][0]["total_entries"]
    }), flush=True)


if __name__ == "__main__":
    main()
