# Exness XAGUSD M15 V6.9-REVERSAL — SL −$6 / TP 75% and SL −$10 / TP 100%

Research only, August–October 2026 (UTC). This is an independently executed tick backtest with 0.01 fixed lot, **no time exit**.

## Rules and execution

- Prior completed M15 candle MID (Bid+Ask)/2 range at least 0.35%: `(MID_HIGH - MID_LOW)/MID_OPEN*100 >=0.35`.
- Current M15: MID first moves >=0.05% below/above its opening MID; then recovers/reverses >=0.05% from the updated extreme. First completed tick-based reversal wins.
- Maximum 1 entry per M15, and never open a new trade while the prior trade remains active.
- LONG fills at Ask and closes at Bid; SHORT fills at Bid and closes at Ask.
- Paired configurations: **SL −$6 USD, TP 75% of previous candle percentage range**; **SL −$10 USD, TP 100% of previous candle percentage range**. TP distance is calculated from the true executed entry price: `entry * prev_vol_pct/100 * tp_fraction`. At 0.01 lot XAGUSD contract 5000 oz/lot, stop price offsets are $0.12/oz and $0.20/oz respectively.
- TP limit simulated at precisely target price on first tick whose opposite-side quote reaches target; stop executes at the first observed crossed Bid/Ask quote, including overshoot. **No closing at candle end or after 60min**.
- Spread is included naturally in Bid/Ask cashflows. No Backcom. Additional commission and unobserved slippage set to zero in base. $0.07 round-trip (Raw Spread **hypothetical**, quotes may differ) and $0.50/$1 per trade adverse cost scenarios also computed. Overnight swap/margin/order rejections are NOT modeled.

## Source and audit

Archived public tick Exness XAGUSD 2026 08, 09, 10 reused through same verified Exness public archive URLs. Total 5,025,215 ticks; 5,970 M15 candles. Bid/Ask Open/High/Low/Close and tick counts reconstructed match all historical Deepnote M15 bars 100%. Data ZIP SHA256 recorded in summary.json; no negative spreads or reversed timestamps. First active candle after price gap >15m is skipped because it lacks an immediately prior M15 candle.

## Monthly results (P&L grouped by opening month)

| SL USD | TP prior candle fraction | Month | Trades | LONG/SHORT | Wins/Losses | Win% | PnL USD | PF | Max DD USD | Profit/Loss days |
|---|---:|---|---:|---|---|---:|---:|---:|---:|---|
| −$6 | 75% | 2026-08 | 655 | 341/314 | 185/470 | 28.24 | -555.24 | 0.808 | 638.11 | 7/18 |
| −$6 | 75% | 2026-09 | 566 | 289/277 | 166/400 | 29.33 | -449.65 | 0.818 | 614.97 | 6/17 |
| −$6 | 75% | 2026-10 | 511 | 265/246 | 153/358 | 29.94 | -558.38 | 0.745 | 625.38 | 7/18 |
| −$10 | 100% | 2026-08 | 446 | 225/221 | 135/311 | 30.27 | -818.92 | 0.742 | 888.83 | 10/15 |
| −$10 | 100% | 2026-09 | 354 | 180/174 | 124/230 | 35.03 | -61.88 | 0.974 | 375.09 | 10/13 |
| −$10 | 100% | 2026-10 | 327 | 163/164 | 112/215 | 34.25 | -432.85 | 0.802 | 477.95 | 7/18 |

## Three-month totals

| Metric | SL $6 / TP 75% | SL $10 / TP 100% |
|---|---:|---:|
| Trades | 1,732 | 1,127 |
| Wins | 504 | 371 |
| Losses | 1,228 | 756 |
| Win rate % | 29.10 | 32.92 |
| Profit Factor | 0.793 | 0.829 |
| Net Trading PnL USD | -1,563.27 | -1,313.65 |
| Max drawdown USD | 1,606.24 | 1,371.26 |
| Avg USD per trade | -0.903 | -1.166 |
| Average winning trade USD | 11.87 | 17.20 |
| Average losing trade USD | -6.15 | -10.18 |
| Realized average reward/risk | 1.932 | 1.690 |
| TP hit count | 504 | 371 |
| SL hit count | 1,228 | 756 |
| Profit days | 20 | 27 |
| Loss days | 53 | 46 |
| Max holding minutes | 401.68 | 3,512.77 |
| Mean holding minutes | 20.96 | 77.03 |
| Skipped signals while holding | 341 | 946 |
| SL overshoots below nominal | 945 | 578 |
| Quoted entry spread avg USD | 1.013 | 1.014 |
| Hypothetical Raw commission scenario USD | -1,684.51 | -1,392.54 |
| Additional $0.50/trade scenario USD | -2,429.27 | -1,877.15 |

**Historical comparison:** Original SL −$5/TP 50% = −$1,877.03 and SL −$10/TP 50% = −$1,573.61 from earlier research. SL −$6/TP 75% reduces loss by approximately $313.75 vs original $5/50%; SL −$10/TP 100% reduces loss by approximately $259.96 vs original $10/50%. These are retrospective comparisons using the same August–October history, not clean OOS validation.

## Execution risk

Maximum holding time SL −$10/TP 100% **58.55 hours**. This may cross market closures and incur unmodeled swap or financing. SL nominal stop is not guaranteed filled at the target due to tick gaps: among the 1228 loss exits in SL6, 945 have worse-than-$6 execution; among 756 loss exits in SL10, 578 exceed −$10. Account-specific spread/commission and execution order rejection are not validated. Results do not represent tradeable broker fills to the dollar.

## Audit

- SL 6/TP 75%: 1732 recorded trades, 0 overlapping positions, 0 negative duration, 0 duplicate candle entries, 0 timed exits, 0 open at end, 0 price/PnL discrepancies over 1 cent.
- SL 10/TP 100%: 1127 recorded trades, 0 overlapping positions, 0 negative duration, 0 duplicate candle entries, 0 timed exits, 0 open at end, 0 price/PnL discrepancies over 1 cent.

## Saved artifacts

- `research/xagusd_v69_reversal_sl6tp75_sl10tp100_20260810/backtest.py` (reproducible tick backtest)
- `results/xagusd_v69_reversal_sl6tp75_sl10tp100_20260810/summary.json` (source, data audit, totals, price assumptions)
- `monthly_by_entry_month.csv`, `monthly_by_exit_month.csv`, `totals.csv`, `AUDIT.csv`
- `weekly_parts_manifest.csv` (index to **26 weekly trade journals**, with 2,859 trade rows in `trades/`)

**Decision: neither configuration has demonstrated a profitable edge. All three months negative. SL−$10/TP100% is the lower-loss of these two backtested variants, but not forward-test-ready. No live trading or EA changes.**
