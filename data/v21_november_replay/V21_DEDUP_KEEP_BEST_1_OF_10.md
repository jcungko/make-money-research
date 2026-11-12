# V21 dedup: November 2026 10 positive portfolios

Filtering rule: two *portfolios* conflict if they contain at least one identical bot leg (symbol, timeframe, signal, trade side, hold bars and entry UTC hour). From a conflict group choose highest November modeled PnL. Historical 22-month PnL and November trade count are tie-breakers. No new backtest or portfolio recombination.

- Input: data/v21_november_replay/V21_NOV_SURVIVORS.json, 10 positive portfolios.
- Shared exact leg in ALL ten: `BTCUSD|H4|range_top_20|short|H3|20utc` (20:00 UTC = 03:00 ICT next day).
- Selected: **V21-P4-195**, +32.03916 bp in November through cutoff 2026-11-12 18:00 UTC, 16 closed leg trades; historical 2025 to 2026-10: +3050.6204 bp.
- Rejected: **V21-P4-041, V21-P4-047, V21-P4-052, V21-P4-194, V21-P4-085, V21-P4-064, V21-P4-095, V21-P4-098, V21-P4-089**.
- Remaining: **1 of 10**. All other nine portfolios contained at least the same H4 BTC short strategy; this does *not* mean the four components of each portfolio were all identical.
- Approximate simulated basis points only; observed spread and 1bp assumed slippage per side, **swap, separate commission, live fills, margin not modeled**.
- Original 50-screen and November results had parameter selection bias; this is not a live-performance guarantee.
