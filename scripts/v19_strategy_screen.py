#!/usr/bin/env python3
"""V19 read-only energy strategy census: 22 months, 2025 through 2026-10.

All entries use information available before entry: indicators through previous
completed candle; entry at current candle open; exit at a future candle open.
Long: buy Ask, sell Bid. Short: sell Bid, buy Ask. Both sides incur 1bp
slippage per side, on top of the historical observed Bid/Ask spread.
Profit units: summed basis points on a fixed one-notional-per-strategy budget.
No compounding, leverage, stops, or broker commissions are assumed.
"""
import argparse
import itertools
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ("USOIL", "UKOIL", "XNGUSD")
PERIODS = ("M5", "M15", "M30", "H1", "H4", "D1", "W1")
MONTHS = [f"{y}-{m:02d}" for y, limit in ((2025, 12), (2026, 10)) for m in range(1, limit + 1)]
SLIPPAGE = 0.0001


def read_frame(root, symbol, frame):
    tables = []
    for year in (2025, 2026):
        p = root / f"{symbol}_{year}_UTC_7TF.zip"
        with zipfile.ZipFile(p) as z:
            with z.open(f"{symbol}_{frame}_{year}_UTC.csv") as f:
                tables.append(pd.read_csv(f))
    data = pd.concat(tables, ignore_index=True)
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    data = data.drop_duplicates("timestamp_utc").sort_values("timestamp_utc").reset_index(drop=True)
    return data


def signals(df):
    bid = df["bid_close"].astype("float64")
    ask = df["ask_close"].astype("float64")
    close = (bid + ask) / 2
    op = (df["bid_open"] + df["ask_open"]) / 2
    high = (df["bid_high"] + df["ask_high"]) / 2
    low = (df["bid_low"] + df["ask_low"]) / 2
    prev = close.shift(1)
    out = {}

    def add(name, x):
        out[name] = np.asarray(x.fillna(False), dtype=bool)

    add("prev_green", close.shift(1) > op.shift(1))
    add("prev_red", close.shift(1) < op.shift(1))
    add("prev_close_gt_prev2", close.shift(1) > close.shift(2))
    add("prev_close_lt_prev2", close.shift(1) < close.shift(2))

    for n in (2, 3, 5, 10, 20, 40):
        add(f"momentum_up_{n}", prev > close.shift(n + 1))
        add(f"momentum_down_{n}", prev < close.shift(n + 1))
    for n in (5, 10, 20, 50):
        avg = close.rolling(n, min_periods=n).mean().shift(1)
        add(f"above_sma_{n}", prev > avg)
        add(f"below_sma_{n}", prev < avg)

    for fast, slow in ((3, 10), (5, 20), (10, 40)):
        ef = close.ewm(span=fast, adjust=False).mean().shift(1)
        es = close.ewm(span=slow, adjust=False).mean().shift(1)
        add(f"ema_above_{fast}_{slow}", ef > es)
        add(f"ema_below_{fast}_{slow}", ef < es)

    for n in (5, 10, 20):
        high_before = high.shift(2).rolling(n, min_periods=n).max()
        low_before = low.shift(2).rolling(n, min_periods=n).min()
        add(f"break_up_{n}", prev > high_before)
        add(f"break_down_{n}", prev < low_before)
        # Include range-location patterns, not just rare breakouts.
        spread = (high_before - low_before).replace(0, np.nan)
        loc = (prev - low_before) / spread
        add(f"range_top_{n}", loc > 0.75)
        add(f"range_bottom_{n}", loc < 0.25)

    diff = close.diff()
    gains = diff.clip(lower=0)
    losses = -diff.clip(upper=0)
    for n in (7, 14):
        g = gains.ewm(alpha=1/n, adjust=False).mean()
        l = losses.ewm(alpha=1/n, adjust=False).mean()
        rs = g / l.replace(0, np.nan)
        rsi = (100 - 100 / (1 + rs)).shift(1)
        for t in (30, 40, 60, 70):
            add(f"rsi{n}_below_{t}", rsi < t)
            add(f"rsi{n}_above_{t}", rsi > t)

    up = (close > op).astype(int)
    down = (close < op).astype(int)
    for n in (2, 3):
        add(f"green_streak_{n}", up.rolling(n, min_periods=n).sum().shift(1) == n)
        add(f"red_streak_{n}", down.rolling(n, min_periods=n).sum().shift(1) == n)

    volume = df["tick_count"].astype("float64")
    med = volume.rolling(30, min_periods=30).median().shift(1)
    add("tick_active", volume.shift(1) > 1.5 * med)
    add("tick_quiet", volume.shift(1) < 0.7 * med)

    # Rolling indicators enforce their own minimum lookback. Do not suppress
    # January daily/weekly trades with an unrelated 60-bar blanket warm-up.
    return out


def pick_nonoverlap(entries, holding):
    if holding <= 1 or len(entries) < 2:
        return entries
    output = []
    next_valid = -1
    for j in entries:
        if j >= next_valid:
            output.append(j)
            next_valid = j + holding
    return np.array(output, dtype=np.int64)


def screen(root, symbol):
    records = []
    for tf in PERIODS:
        df = read_frame(root, symbol, tf)
        n = len(df)
        t = df["timestamp_utc"].dt
        month_index = ((t.year - 2025) * 12 + t.month - 1).to_numpy(dtype=int)
        hours = t.hour.to_numpy(dtype=int)
        minute = t.minute.to_numpy(dtype=int)
        if tf in ("D1", "W1"):
            sessions = (("all", np.ones(n, dtype=bool)),)
            holds = (1, 2, 3)
        elif tf == "H4":
            sessions = tuple((f"{h:02d}utc", (hours == h) & (minute == 0)) for h in (0, 4, 8, 12, 16, 20))
            holds = (1, 2, 3, 4)
        else:
            sessions = tuple((f"{h:02d}utc", (hours == h) & (minute == 0)) for h in (0, 4, 8, 12, 16, 20))
            holds = (1, 2, 4, 8)

        mid = (df.bid_open.to_numpy() + df.ask_open.to_numpy()) / 2
        bid = df.bid_open.to_numpy()
        ask = df.ask_open.to_numpy()
        valid = np.isfinite(mid) & (mid > 0) & np.isfinite(ask) & np.isfinite(bid)
        choices = signals(df)
        tf_results = 0

        for hold in holds:
            index = np.arange(n)
            possible = index + hold < n
            exits = np.minimum(index + hold, n - 1)
            valid_pair = possible & valid & valid[exits]
            long_bp = (bid[exits] * (1 - SLIPPAGE) - ask * (1 + SLIPPAGE)) / mid * 10000
            short_bp = (bid * (1 - SLIPPAGE) - ask[exits] * (1 + SLIPPAGE)) / mid * 10000
            pnl_sides = (("long", long_bp), ("short", short_bp))

            for signal, mask in choices.items():
                qualified = mask & valid_pair
                if not qualified.any():
                    continue
                for session_name, ses_mask in sessions:
                    entries = np.flatnonzero(qualified & ses_mask)
                    if not len(entries):
                        continue
                    entries = pick_nonoverlap(entries, hold)
                    ends = exits[entries]
                    mm = month_index[ends]
                    keep = (mm >= 0) & (mm < 22)
                    entries = entries[keep]
                    mm = mm[keep]
                    if len(entries) < 22:
                        continue
                    counts = np.bincount(mm, minlength=22)
                    if (counts == 0).any():
                        continue
                    for side, pnl in pnl_sides:
                        p = pnl[entries]
                        if not np.isfinite(p).all():
                            continue
                        monthly = np.bincount(mm, weights=p, minlength=22)
                        wins = int((monthly > 0).sum())
                        year25 = float(monthly[:12].sum())
                        year26 = float(monthly[12:].sum())
                        name = f"{symbol}|{tf}|{signal}|{side}|H{hold}|{session_name}"
                        rec = {
                            "id": name, "symbol": symbol, "timeframe": tf, "signal": signal,
                            "side": side, "hold_bars": hold, "entry_utc": session_name,
                            "trades": int(len(entries)), "months_with_trades": int((counts > 0).sum()),
                            "positive_months": wins, "profit_2025_bp": round(year25, 4),
                            "profit_2026_bp": round(year26, 4),
                            "total_bp": round(float(monthly.sum()), 4),
                            "min_month_bp": round(float(monthly.min()), 4),
                            "passed_both_years": bool(year25 > 0 and year26 > 0),
                            "passed_all_22_months": bool(wins == 22 and year25 > 0 and year26 > 0),
                            "monthly_bp": np.round(monthly, 5).tolist()
                        }
                        records.append(rec)
                        tf_results += 1
        print(f"V19_SCREEN {symbol} {tf}: {n:,} candles; {tf_results:,} fully-active strategies", flush=True)
    return records


def best_key(r):
    return (r["positive_months"], int(r["passed_both_years"]), r["min_month_bp"], r["total_bp"])


def assemble_portfolios(all_records):
    """All top-40-per-asset two/three-leg equal-notional combos; exact, not sampled.
    Portfolios are screened on the same 22 months; NOT an out-of-sample estimate.
    """
    pools = {}
    for sym in SYMBOLS:
        rows = [r for r in all_records if r["symbol"] == sym]
        rows.sort(key=best_key, reverse=True)
        selected = []
        seen = set()
        for row in rows:
            # Prevent exact duplicates created by distinct sessions but same trades.
            key = tuple(np.round(row["monthly_bp"], 2))
            if key in seen:
                continue
            selected.append(row)
            seen.add(key)
            if len(selected) == 40:
                break
        pools[sym] = selected
        print("V19_POOL", sym, len(selected), "best positive months:", selected[0]["positive_months"] if selected else 0, flush=True)

    passes = []
    counters = {}
    best_portfolios = []
    for degree in (2, 3):
        tested = 0
        both_years = 0
        all_months = 0
        for symbols in itertools.combinations(SYMBOLS, degree):
            chosen = [pools[s] for s in symbols]
            if not all(chosen):
                continue
            for legs in itertools.product(*chosen):
                # One notional unit per leg / equal-weight budget.
                monthly = np.mean([r["monthly_bp"] for r in legs], axis=0)
                tested += 1
                if monthly[:12].sum() > 0 and monthly[12:].sum() > 0:
                    both_years += 1
                    if np.all(monthly > 0):
                        all_months += 1
                        r = {
                            "legs": [leg["id"] for leg in legs],
                            "positive_months": 22,
                            "monthly_bp": np.round(monthly, 4).tolist(),
                            "profit_2025_bp": round(float(monthly[:12].sum()), 4),
                            "profit_2026_bp": round(float(monthly[12:].sum()), 4),
                            "total_bp": round(float(monthly.sum()), 4),
                            "min_month_bp": round(float(monthly.min()), 4),
                        }
                        passes.append(r)
                if len(best_portfolios) < 8 or int((monthly > 0).sum()) >= best_portfolios[-1][0][0]:
                    score = (int((monthly > 0).sum()), float(monthly.min()), float(monthly.sum()))
                    candidate = (score, [r["id"] for r in legs], monthly.tolist())
                    best_portfolios.append(candidate)
                    best_portfolios.sort(key=lambda x: x[0], reverse=True)
                    best_portfolios = best_portfolios[:8]
        counters[str(degree)] = {
            "tested": tested, "profitable_in_both_years": both_years,
            "profitable_in_all_22_months": all_months
        }
        print("V19_PORTFOLIO", degree, json.dumps(counters[str(degree)]), flush=True)
    passes.sort(key=lambda r: (r["min_month_bp"], r["total_bp"]), reverse=True)
    return counters, passes, [
        {"positive_months": item[0][0], "min_month_bp": round(item[0][1], 3),
         "total_bp": round(item[0][2], 3), "legs": item[1],
         "monthly_bp": np.round(item[2], 4).tolist()} for item in best_portfolios
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data/v19_energies"))
    ap.add_argument("--out", type=Path, default=Path("data/v19_strategy_screen"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    recs = []
    counts = {}
    for symbol in SYMBOLS:
        rows = screen(args.root, symbol)
        recs.extend(rows)
        counts[symbol] = {
            "tested": len(rows),
            "profitable_in_both_years": sum(x["passed_both_years"] for x in rows),
            "profitable_in_all_22_months": sum(x["passed_all_22_months"] for x in rows),
            "best_positive_months": max((r["positive_months"] for r in rows), default=0)
        }
        print("V19_SINGLE", symbol, json.dumps(counts[symbol]), flush=True)

    summary = [
        {k: v for k, v in r.items() if k != "monthly_bp"}
        for r in recs
    ]
    pd.DataFrame(summary).to_csv(args.out / "all_single_strategy_metrics.csv", index=False)
    pass_single = [r for r in recs if r["passed_all_22_months"]]
    pass_single.sort(key=lambda r: (r["min_month_bp"], r["total_bp"]), reverse=True)
    with (args.out / "passing_single_strategies.json").open("w") as f:
        json.dump(pass_single, f, indent=2)

    c, passing_portfolios, top_portfolios = assemble_portfolios(recs)
    with (args.out / "passing_portfolio_strategies.json").open("w") as f:
        json.dump(passing_portfolios, f, indent=2)
    best_single = sorted(recs, key=best_key, reverse=True)[:25]
    report = {
        "study": "V19 USOIL UKOIL XNGUSD strategy screen",
        "months": MONTHS,
        "reference_years": "2025 full; 2026 January 01 - October 31 UTC",
        "screening_universe": "M5 M15 M30 H1 H4 D1 W1; momentum, candle, SMA, EMA, Donchian, RSI, streak, tick intensity, UTC session, long/short, 1-8 bar holds. Portfolios combine top 40 nonidentical single strategies per symbol across distinct symbols.",
        "execution": "indicator from previous completed candle; next bar open on bid/ask; exit at future bar open; entry at 00/04/08/12/16/20UTC for intraday, each new bar for D1/W1; one position per strategy; no commissions",
        "cost_model": "Historical bid/ask spread included; extra 1 basis point adverse slippage per side (2bp per roundtrip). Does not include broker commissions, financing, swap, funding or real futures rollover costs.",
        "pnl_units": "uncompounded basis points on equal fixed notional per strategy, 1 notional unit per leg for portfolios",
        "monthly_rule": "Profit realized in exit month, all 22 calendar months must have at least one closed trade for a standalone strategy; strictly positive PnL (>0bp) in each month",
        "cautions": ["Same 22 months used for both model discovery and evaluation; in-sample selection bias and multiple testing", "No tick-level intrabar SL/TP", "CFD instrument contract specs, financing and order execution may differ", "Weekly boundary weeks partially excluded by historical file design"],
        "single_counts_by_symbol": counts,
        "single_totals": {
            "tested": len(recs),
            "profitable_in_both_years": sum(r["passed_both_years"] for r in recs),
            "profitable_in_all_22_months": len(pass_single),
        },
        "portfolio_counts_by_leg_count": c,
        "total_pass_all_22": len(pass_single) + len(passing_portfolios),
        "best_single_candidates": best_single,
        "best_portfolio_candidates": top_portfolios,
        "passing_single_strategies_file": "passing_single_strategies.json",
        "passing_portfolio_strategies_file": "passing_portfolio_strategies.json",
    }
    (args.out / "V19_screening_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("V19_FINAL", json.dumps({
        "single": report["single_totals"],
        "portfolio": c,
        "all_22_total": report["total_pass_all_22"]
    }), flush=True)


if __name__ == "__main__":
    main()
