# V10.0 — shortlist selected by user + five additional strategies

**Date reviewed:** 2026-11-11. **Symbol:** USDJPY (Exness-labelled tick archive derived M15/H1/H4). **Repository branch:** data/v10-usdjpy-2026.

## Confirmed shortlist
User's first three: **#3, #5, #2**.
Five additional recommended: **#8, #4, #6, #12, #17**.

## Method
- "petpip" interpreted as **NetPip per trade**. NetPip = cumulative price P/L in pips from Bid/Ask fills plus an assumed extra 0.5 pip cost per position; not USD profit.
- Three latest calendar months = **September, October, November 2026**. November includes only data through **November 9, 2026** (partial month).
- Each strategy places exactly one trade per eligible Monday–Friday trading day (at least 10 H1 bars per day): 22 September, 22 October, 6 November = **50 trades per method**.
- Each of these 8 strategies also met positive net pips in every month **May–November 9**, although November is not complete. These returns were identified from a broad retrospective parameter search and are in-sample, not independent validation.

## NetPip and average pip per trade (Sept–Nov 9, 2026)

| # | Indicator | Sep | Oct | Nov (partial) | Three-month net pip | Pip/trade | SL/TP pips |
|---:|---|---:|---:|---:|---:|---:|---|
| 3 | M15 close vs SMA8 (momentum) | 777.7 | 112.6 | 16.5 | 906.8 | 18.14 | time exit only |
| 2 | M15 momentum 2 bars | 431.7 | 132.2 | 53.5 | 617.4 | 12.35 | 45/60 |
| 5 | H1 close vs current-day range midpoint | 360.3 | 164.7 | 44.9 | 569.9 | 11.40 | 45/60 |
| 8 | H1 SMA12 slope | 397.9 | 80.0 | 28.1 | 506.0 | 10.12 | 45/60 |
| 4 | H1 close vs SMA12 (reverse) | 249.7 | 206.5 | 23.0 | 479.2 | 9.58 | 35/70 |
| 6 | H1 12-hour momentum acceleration | 313.1 | 2.2 | 75.0 | 390.3 | 7.81 | time exit only |
| 12 | M15 SMA4 vs SMA16 (reverse) | 181.7 | 79.2 | 86.0 | 346.9 | 6.94 | 30/30 |
| 17 | H1 12-hour acceleration (reverse) | 181.2 | 117.8 | 34.8 | 333.8 | 6.68 | 30/30 |

## Full 3-month cross-check (August–October 2026, complete months)

| # | NetPip Aug–Oct |
|---:|---:|
| 3 | 1229.5 |
| 2 | 576.7 |
| 5 | 600.9 |
| 8 | 514.2 |
| 4 | 481.7 |
| 6 | 317.7 |
| 12 | 264.4 |
| 17 | 301.7 |

## Entry and exit rules (UTC time; VN +7)

| # | Entry UTC | Max holding hours | Stop loss | Take profit |
|---:|---:|---:|---:|---:|
| 3 | 06:00 | 8 | none | none |
| 5 | 06:00 | 8 | 45 | 60 |
| 2 | 06:00 | 8 | 45 | 60 |
| 8 | 06:00 | 8 | 45 | 60 |
| 4 | 14:00 | 8 | 35 | 70 |
| 6 | 00:00 | 6 | none | none |
| 12 | 14:00 | 8 | 30 | 30 |
| 17 | 18:00 | 8 | 30 | 30 |

## Avoiding excessive overlap

The previously analyzed #3 and #7 had 86.86% matching directions and Pearson 0.9516 daily net-pip correlation for May–Nov 9, so #7 was intentionally excluded in spite of its very high three-month net (+817.2 pip). Among September–November signals, #4 and #9 were **96%** same-direction and had Pearson **0.928** daily-pip correlation; #9 (+391.8 pip / 7.84 pip per trade) was excluded to avoid another near-duplicate. #8 and #5 were **76%** same-direction and had Pearson **0.703** daily-pip correlation, so they are not fully independent and joint exposure must be capped.

## Risk limitations

These are **in-sample optimized** backtests and may overfit. No guarantee they will continue making money. #3 and #6 lack a broker-side SL in the original configuration; before live deployment, add a tested emergency SL and re-run the backtest. #6 made just +2.2 pip in October (22 entries), a fragile month. All 8 trade the **same USDJPY** underlying; pip totals are not additive into an independent diversified portfolio. Bid/Ask and extra 0.5 pip friction are included, but execution slippage, swap and commissions are not fully accounted for. Real-world MT5 Exness prices can differ from the source mirror.

**Further work:** validate all eight methods together for correlated signals, simultaneous risk, intra-trade drawdown, execution timing, appropriate stops and out-of-sample performance before any Auto Trade deployment.
