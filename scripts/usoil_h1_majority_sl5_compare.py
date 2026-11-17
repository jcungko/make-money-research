#!/usr/bin/env python3
"""Research-only: USOIL H1 three-candle majority; SL5 TP10 and SL5 TP5.
All fills simulated; never contacts MT5 or executes live trades.
Reuses the exact signal / Bid-Ask / M5 barrier logic of the previous SL10 tests.
"""
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

ARCHIVE = Path("data/v19_energies/USOIL_2026_UTC_7TF.zip")
LOT = 0.01
CONTRACT_SIZE = 1000  # Assumption until confirmed in the trading account
USD_PER_PRICE = LOT * CONTRACT_SIZE
VARIANTS = ((5.0, 10.0), (5.0, 5.0))

with zipfile.ZipFile(ARCHIVE) as z:
    def load(tf):
        d = pd.read_csv(io.BytesIO(z.read(f"USOIL_{tf}_2026_UTC.csv")))
        d["timestamp_utc"] = pd.to_datetime(d["timestamp_utc"], utc=True)
        return d.sort_values("timestamp_utc").set_index("timestamp_utc")
    h = load("H1")
    m = load("M5")

# Precompute signals and precise same-bar entry prices for both variants.
candidates = []
for i in range(3, len(h)):
    start = h.index[i]
    if not ("2026-08-01" <= start.strftime("%Y-%m-%d") < "2026-11-01"):
        continue
    preceding = h.iloc[i-3:i]
    bulls = int((preceding.bid_close > preceding.bid_open).sum())
    bears = int((preceding.bid_close < preceding.bid_open).sum())
    side = 1 if bulls >= 2 else (-1 if bears >= 2 else 0)
    if not side:
        continue
    segment = m[(m.index >= start) & (m.index < start + pd.Timedelta(hours=1))]
    if segment.empty or segment.index[0] != start:
        continue
    candidates.append((start, side, segment))

def summary(g):
    wins = g[g.usd > 0]
    losses = g[g.usd < 0]
    positive = round(float(wins.usd.sum()), 2)
    negative = round(float(losses.usd.sum()), 2)
    return {
        "trades": len(g),
        "wins": len(wins),
        "losses": len(losses),
        "flat": int((g.usd == 0).sum()),
        "win_rate_pct": round(100 * len(wins) / len(g), 2),
        "gross_pnl_usd": round(float(g.usd.sum()), 2),
        "sum_wins_usd": positive,
        "sum_losses_usd": negative,
        "avg_win_usd": round(float(wins.usd.mean()), 4) if len(wins) else None,
        "avg_loss_usd": round(float(losses.usd.mean()), 4) if len(losses) else None,
        "profit_factor": round(positive / -negative, 4) if negative < 0 else None,
        "tp": int((g.reason == "TP").sum()),
        "sl": int(g.reason.isin(["SL", "SL_BOTH_M5"]).sum()),
        "hour_close": int((g.reason == "H1_CLOSE").sum()),
        "hour_close_pnl_usd": round(float(g.loc[g.reason == "H1_CLOSE", "usd"].sum()), 2),
        "ambiguous_m5": int(g.ambiguous_m5.sum())
    }

for SL_USD, TP_USD in VARIANTS:
    out = Path(f"results/usoil_h1_majority_sl5_tp{int(TP_USD)}_2026")
    out.mkdir(parents=True, exist_ok=True)
    stop_step = SL_USD / USD_PER_PRICE
    target_step = TP_USD / USD_PER_PRICE
    records = []
    for start, side, segment in candidates:
        entry = float(segment.ask_open.iloc[0] if side == 1 else segment.bid_open.iloc[0])
        exit_price = float(segment.bid_close.iloc[-1] if side == 1 else segment.ask_close.iloc[-1])
        reason = "H1_CLOSE"
        stop = entry - side * stop_step
        target = entry + side * target_step
        ambiguous = False
        for bar in segment.itertuples():
            high = float(bar.bid_high if side == 1 else bar.ask_high)
            low = float(bar.bid_low if side == 1 else bar.ask_low)
            stop_hit = low <= stop if side == 1 else high >= stop
            target_hit = high >= target if side == 1 else low <= target
            if stop_hit and target_hit:
                exit_price = stop
                reason = "SL_BOTH_M5"
                ambiguous = True
                break
            if stop_hit:
                exit_price = stop
                reason = "SL"
                break
            if target_hit:
                exit_price = target
                reason = "TP"
                break
        gross = (exit_price - entry) * side * USD_PER_PRICE
        records.append({
            "time_utc": start.isoformat(),
            "side": "LONG" if side == 1 else "SHORT",
            "entry": entry,
            "exit": exit_price,
            "reason": reason,
            "usd": round(gross, 4),
            "ambiguous_m5": ambiguous,
            "m5_bars": len(segment),
        })
    trades = pd.DataFrame(records)
    if trades.empty:
        raise RuntimeError("No qualifying trades, check input data")
    trades.to_csv(out / "trades.csv", index=False)
    trades["month"] = trades.time_utc.str[:7]
    report = {
        "method": "USOIL H1 2 of previous 3 bullish long, 2 bearish short; exit at SL/TP or end of H1",
        "source": "Exness V19 Standard USOIL bid/ask H1 and M5 from GitHub",
        "period_utc": "2026-08-01 through 2026-10-31",
        "lot_assumed": LOT,
        "contract_size_assumed": CONTRACT_SIZE,
        "usd_per_one_price_unit": USD_PER_PRICE,
        "sl_usd": SL_USD,
        "tp_usd": TP_USD,
        "sl_price_distance": stop_step,
        "tp_price_distance": target_step,
        "nominal_reward_risk": TP_USD / SL_USD,
        "entry": "first M5 ask open long / bid open short of the H1 hour",
        "exit": "M5 bid highs/lows for long, M5 ask highs/lows for short; last available M5 close otherwise",
        "tie_break": "SL first if both SL and TP occurred within the same M5 candle",
        "limitations": "M5 intrabar sequence unknown; contract size assumed; not including commission, slippage or overnight financing; quote data and fills may differ in live account",
        "monthly": {month: summary(g) for month, g in trades.groupby("month")},
        "sides": {side: summary(g) for side, g in trades.groupby("side")},
        "total": summary(trades),
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"SL": SL_USD, "TP": TP_USD, "monthly": report["monthly"], "total": report["total"]}, ensure_ascii=False), flush=True)
