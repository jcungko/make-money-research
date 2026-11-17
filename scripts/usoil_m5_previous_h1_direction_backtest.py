#!/usr/bin/env python3
"""USOIL M5: each bar entry in direction of exactly preceding H1 body.
Research only. SL=5 USD; TP=5 or 10 USD. Exit no later than same M5 bar.
Adds a separately identified 3-H1-consensus confirmatory variant.
"""
import io
import json
import zipfile
from pathlib import Path
import pandas as pd

DATA = Path("data/v19_energies")
OUT = Path("results/usoil_m5_previous_h1_direction_2025_2026")
OUT.mkdir(parents=True, exist_ok=True)
LOT = 0.01
CONTRACT = 1000.0  # Confirm symbol specification in the target MT5 account
USD_PER_PRICE = LOT * CONTRACT
SL_USD = 5.0
TAKE_PROFITS = (5.0, 10.0)
MODES = ("PREVIOUS_H1_ONLY", "PREVIOUS_H1_AND_MAJORITY3")
all_trades = []
coverage = []

for year in (2025, 2026):
    with zipfile.ZipFile(DATA / f"USOIL_{year}_UTC_7TF.zip") as z:
        def load(tf):
            df = pd.read_csv(io.BytesIO(z.read(f"USOIL_{tf}_{year}_UTC.csv")))
            df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
            return df.sort_values("timestamp_utc").set_index("timestamp_utc")
        hourly = load("H1")
        five = load("M5")

    # Only data from closed H1 bars is used. Skip opening hour after a market gap
    # when the immediately previous clock-hour H1 bar does not exist.
    h1_direction = {}
    consensus = {}
    for i, (t, bar) in enumerate(hourly.iterrows()):
        direction = (1 if bar.bid_close > bar.bid_open else
                     -1 if bar.bid_close < bar.bid_open else 0)
        h1_direction[t] = direction
        if i >= 2:
            prev3 = hourly.iloc[i-2:i+1]
            bull = int((prev3.bid_close > prev3.bid_open).sum())
            bear = int((prev3.bid_close < prev3.bid_open).sum())
            consensus[t] = (1 if bull >= 2 else -1 if bear >= 2 else 0)
    for t, bar in five.iterrows():
        prior_h1 = t.floor("h") - pd.Timedelta(hours=1)
        direction = h1_direction.get(prior_h1, 0)
        if direction == 0:
            continue  # doji or unavailable prior completed H1
        agrees = consensus.get(prior_h1, 0) == direction
        for mode in MODES:
            if mode == "PREVIOUS_H1_AND_MAJORITY3" and not agrees:
                continue
            entry = float(bar.ask_open if direction > 0 else bar.bid_open)
            close = float(bar.bid_close if direction > 0 else bar.ask_close)
            high = float(bar.bid_high if direction > 0 else bar.ask_high)
            low = float(bar.bid_low if direction > 0 else bar.ask_low)
            for tp_usd in TAKE_PROFITS:
                sl = entry - direction * (SL_USD / USD_PER_PRICE)
                tp = entry + direction * (tp_usd / USD_PER_PRICE)
                sl_hit = low <= sl if direction > 0 else high >= sl
                tp_hit = high >= tp if direction > 0 else low <= tp
                ambiguous = sl_hit and tp_hit
                # Conservative: SL gets priority if both barriers hit same M5
                reason = "SL_AND_TP_SAME_M5" if ambiguous else (
                    "SL" if sl_hit else "TP" if tp_hit else "M5_CLOSE")
                exit_price = sl if sl_hit else tp if tp_hit else close
                pnl = round((exit_price - entry) * direction * USD_PER_PRICE, 4)
                all_trades.append({
                    "time_utc": t.isoformat(),
                    "year": year,
                    "month": t.strftime("%Y-%m"),
                    "side": "LONG" if direction > 0 else "SHORT",
                    "signal_mode": mode,
                    "sl_usd": SL_USD,
                    "tp_usd": tp_usd,
                    "entry": entry,
                    "exit": exit_price,
                    "reason": reason,
                    "pnl_usd": pnl,
                    "ambiguous_m5": ambiguous,
                })
    coverage.append({"year": year, "M5_bars": len(five), "H1_bars": len(hourly)})

trades = pd.DataFrame(all_trades)
if trades.empty:
    raise RuntimeError("No M5 trades; check archive columns or previous H1 lookup")
trades.to_csv(OUT / "trades.csv", index=False)

def summarize(g):
    wins = g[g.pnl_usd > 0]
    losses = g[g.pnl_usd < 0]
    pos = float(wins.pnl_usd.sum())
    neg = float(losses.pnl_usd.sum())
    return {
        "orders": int(len(g)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "flat": int((g.pnl_usd == 0).sum()),
        "win_rate_pct": round(100 * len(wins) / len(g), 2) if len(g) else None,
        "pnl_usd": round(float(g.pnl_usd.sum()), 2),
        "avg_win_usd": round(float(wins.pnl_usd.mean()), 3) if len(wins) else None,
        "avg_loss_usd": round(float(losses.pnl_usd.mean()), 3) if len(losses) else None,
        "profit_factor": round(pos / (-neg), 4) if neg < 0 else None,
        "tp": int((g.reason == "TP").sum()),
        "sl": int(g.reason.isin(["SL", "SL_AND_TP_SAME_M5"]).sum()),
        "close_m5": int((g.reason == "M5_CLOSE").sum()),
        "close_m5_pnl_usd": round(float(g[g.reason == "M5_CLOSE"].pnl_usd.sum()), 2),
        "ambiguous_m5": int(g.ambiguous_m5.sum()),
    }

report = {
    "name": "USOIL prior completed H1 candle controls direction of every following M5",
    "source": "Exness archived bid/ask data; GitHub data/v19_energies USOIL 2025 and 2026 UTC 7TF",
    "data_coverage": coverage,
    "signal": "if exactly prior completed H1 bid_close>bid_open then LONG on each next-hour M5; if < then SHORT; doji skip",
    "signals_tested": {
        "PREVIOUS_H1_ONLY": "user's requested rule with no 2/3 filter",
        "PREVIOUS_H1_AND_MAJORITY3": "supplemental strict filter: direction must also agree with majority of prior three H1 candles",
    },
    "entry": "at first quote of EACH available M5 candle; buy at ask_open, sell at bid_open",
    "exit": "check SL and TP using bid_high/low for LONG and ask_high/low for SHORT; if neither hits, exit at corresponding M5 close",
    "intrabar_tie": "if SL and TP are both touched within a M5 candle, count SL first",
    "lot_assumed": LOT,
    "contract_size_assumed": CONTRACT,
    "sl_usd": SL_USD,
    "tps_usd": list(TAKE_PROFITS),
    "caveats": "M5 OHLC cannot determine true first touch intrabar; slippage/commission not included; quote close is last M5 tick; contract size must match broker; not live-execution evidence",
    "variants": {}
}
for mode in MODES:
    for tp in TAKE_PROFITS:
        k = f"{mode}_SL5_TP{int(tp)}"
        d = trades[(trades.signal_mode == mode) & (trades.tp_usd == tp)]
        report["variants"][k] = {
            "aug_oct_2026": summarize(d[(d.month >= "2026-08") & (d.month <= "2026-10")]),
            "year_2025": summarize(d[d.year == 2025]),
            "year_2026_through_oct": summarize(d[d.year == 2026]),
            "monthly_2026_aug_oct": {
                x: summarize(g) for x,g in d[(d.month >= "2026-08") & (d.month <= "2026-10")].groupby("month")
            },
            "monthly_2025": {x: summarize(g) for x,g in d[d.year == 2025].groupby("month")},
            "monthly_2026_all": {x: summarize(g) for x,g in d[d.year == 2026].groupby("month")},
            "sides_aug_oct_2026": {
                x: summarize(g) for x,g in d[(d.month >= "2026-08") & (d.month <= "2026-10")].groupby("side")
            }
        }
        print(k, json.dumps(report["variants"][k]["monthly_2026_aug_oct"]), flush=True)
(OUT/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("AUDIT_COMPLETE", len(trades), flush=True)
