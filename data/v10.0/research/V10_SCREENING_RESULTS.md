# V10.0 — USDJPY Exness 2026 strategy screen

**Status:** research/backtest only; no live recommendation or proof of an edge.
**Data source:** \`data/v10.0/USDJPY_Exness_2026_M15.csv\`, H1, H4 in this branch. Source data: public Exness-labelled tick mirror, not account-specific MT5 export. **Symbol USDJPY**, not JPYUSD.

## Scope and search
- Dataset: tick-derived Bid and Ask M15/H1/H4 bars from 2026-01-01 to 2026-11-09 23:59:57 UTC.
- Eligible full trading dates: 222 Monday–Friday UTC dates with >=10 recorded H1 bars. Excludes short Sunday sessions and the partial Jan 1 session.
- Strategy search: 11 UTC entry-hours (00,02,...,20) x 5 holding-period limits (1,2,4,6,8 hours) x 7 exits (time only, SL/TP 15/30, 20/40, 25/50, 35/70, 30/30, 45/60 pips) x sign/reverse and indicators derived only from previously closed M15/H1/H4 candles. **Important: H4 candles are counted only when their four hours have fully elapsed; no current/unclosed H4 used.** 25 indicator families.
- 50,750 configurations passed the every-1-or-2-trading-days frequency test across the whole period, including indicator warmup where necessary.
- Each selected strategy sends one market entry at its fixed UTC hour on each eligible trading date, LONG or SHORT determined by its signal; no discretion/filtering. Selected strategies have **137 trades on 137 eligible dates** from May 2026 to Nov 9, 2026.
- LONG entered at Ask and exited at Bid. SHORT entered at Bid and exited at Ask. Stop-loss and take-profit are simulated on within-interval M15 Bid/Ask highs/lows, **stops take priority if both SL and TP could hit in the same M15 candle**. Time expiry closes at the scheduled hour or last available bar before a market closure. Slippage/commission are NOT separately modelled; an **extra 0.5 pip per completed trade** is subtracted beyond the observed Bid/Ask spread. Swaps, other commissions, financing, market execution/latency and variable pip-to-USD value are not modelled.
- Monthly pnl assigned to **entry month**. Conditions: positive net pips in *each* month of a contiguous most-recent window and at least one trade in every 2 consecutive eligible trading dates. Selected 20 distinct realized daily P&L paths across 16 indicator families, avoiding exact duplicate P&L sequences. Ranking used \`(total_pips + 2 * min_month_pips)/(1 + max_closed_trade_drawdown_pips/150)\` with family diversification.
- **November is partial** (6 active days through Nov 9, not a completed calendar month). May–Oct are complete months.
- No strategy met all months Jan–Nov. 1 passed Mar–Nov (9 months), 7 passed Apr–Nov (8 months), and **33** passed May–Nov (7 months), including 30 different daily P&L sequences. Among those, 27 used a fixed SL/TP. Selecting from 50,750 candidates on the same data creates a very large multiple-testing / overfitting risk. These results should not be interpreted as expected future returns.

## 20 selected configurations

\`reverse=N\`: LONG on positive signal / SHORT on negative signal; \`reverse=Y\`: SHORT on positive / LONG on negative. \`Long\`: always LONG.
\`entry\` is UTC (Vietnam time = UTC+7). \`pnl\` and \`DD\` are **pips**, not dollars, and drawdown is on **closed-trade equity**, not worst intra-position drawdown.

| No | Indicator / parameter | Reverse | Entry UTC | Time exit max (h) | SL/TP (pips) | Trades | Net pips May-Nov9 | Win % | Closed DD pips | Worst monthly pips | Positive Jan-Apr months |
|---:|---|:---:|---:|---:|:---:|---:|---:|---:|---:|---:|---:|
| 1 | Always LONG | – | 14 | 6 | time only | 137 | 953.6 | 70.07 | 134.9 | 4.1 | 2/4 |
| 2 | M15 2-bar momentum | N | 06 | 8 | 45/60 | 137 | 933.4 | 58.39 | 154.4 | 12.8 | 1/4 |
| 3 | M15 close vs SMA8 | N | 06 | 8 | time only | 137 | 1446.8 | 64.23 | 380.7 | 16.5 | 0/4 |
| 4 | H1 close vs SMA12 | Y | 14 | 8 | 35/70 | 137 | 681.5 | 59.85 | 119.9 | 15.9 | 0/4 |
| 5 | H1 intraday close vs high-low midpoint | N | 06 | 8 | 45/60 | 137 | 924.9 | 57.66 | 230.0 | 25.8 | 2/4 |
| 6 | H1 12h return minus preceding 12h return | N | 00 | 6 | time only | 137 | 670.3 | 50.36 | 136.7 | 2.2 | 2/4 |
| 7 | H1 2-bar momentum | N | 06 | 8 | time only | 137 | 1254.4 | 60.58 | 418.7 | 16.5 | 0/4 |
| 8 | H1 rising/falling SMA12 | N | 06 | 8 | 45/60 | 137 | 683.6 | 52.55 | 180.6 | 25.9 | 0/4 |
| 9 | H1 weighted momentum 12 | Y | 14 | 8 | 35/70 | 137 | 506.9 | 56.93 | 119.9 | 15.9 | 0/4 |
| 10 | M15 previous candle close vs high-low midpoint | Y | 16 | 4 | 45/60 | 137 | 439.7 | 57.66 | 126.5 | 13.0 | 2/4 |
| 11 | H1 SMA2 vs SMA6 | Y | 14 | 8 | 35/70 | 137 | 392.2 | 51.09 | 120.6 | 6.7 | 1/4 |
| 12 | M15 SMA4 vs SMA16 | Y | 14 | 8 | 30/30 | 137 | 392.9 | 54.74 | 133.9 | 3.5 | 2/4 |
| 13 | Previous trading day close vs day high-low midpoint | Y | 20 | 8 | 30/30 | 137 | 296.6 | 49.64 | 121.7 | 6.2 | 1/4 |
| 14 | H1 RSI(14) relative to 50 | N | 00 | 4 | 35/70 | 137 | 258.9 | 48.18 | 106.5 | 1.4 | 2/4 |
| 15 | H4 SMA3 vs SMA8 (only completed H4 candles) | Y | 00 | 8 | 15/30 | 137 | 283.2 | 43.07 | 149.1 | 5.0 | 2/4 |
| 16 | Previous trading day close vs open | Y | 12 | 2 | 25/50 | 137 | 243.9 | 54.01 | 146.1 | 12.9 | 1/4 |
| 17 | H1 12h momentum acceleration | Y | 18 | 8 | 30/30 | 137 | 520.5 | 60.58 | 123.5 | 2.7 | 0/4 |
| 18 | M15 previous candle close vs high-low midpoint | N | 06 | 8 | 30/30 | 137 | 403.9 | 56.93 | 211.4 | 5.0 | 0/4 |
| 19 | H1 4-bar momentum | Y | 18 | 8 | 45/60 | 137 | 185.8 | 54.01 | 188.8 | 1.2 | 2/4 |
| 20 | H1 6h return minus prior 6h return | N | 06 | 2 | time only | 137 | 420.0 | 54.01 | 96.1 | 1.2 | 1/4 |

## Monthly net pips for selected examples (May 2026–November 9, 2026)

| # | May | Jun | Jul | Aug | Sep | Oct | Nov* |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 191.2 | 127.4 | 4.4 | 327.9 | 267.6 | 31.0 | 4.1 |
| 2 | 68.5 | 48.2 | 186.5 | 12.8 | 431.7 | 132.2 | 53.5 |
| 3 | 65.6 | 39.7 | 95.5 | 339.2 | 777.7 | 112.6 | 16.5 |
| 4 | 130.7 | 30.2 | 15.9 | 25.5 | 249.7 | 206.5 | 23.0 |
| 5 | 151.2 | 25.8 | 102.1 | 75.9 | 360.3 | 164.7 | 44.9 |
| 8 | 43.9 | 71.5 | 25.9 | 36.3 | 397.9 | 80.0 | 28.1 |

*November is incomplete. All numbers are net pips after Bid/Ask spread plus the assumed 0.5 pip extra trading friction, not US dollar P&L.*

**Cautions:** Only 2 of the listed SL/TP strategies (#5, #8) survive *an additional 1 pip per trade* for all 7 selected months, based on their month-level P&L margins (this is a sensitivity check, not an execution model). Stopless strategies #1, #3, #6, #7 and #20 can suffer much larger intra-trade risk than reported closed-trade drawdown. Future forward/out-of-sample evaluation is essential before using real money or leverage.

## Source files
- [M15](../USDJPY_Exness_2026_M15.csv)
- [H1](../USDJPY_Exness_2026_H1.csv)
- [H4](../USDJPY_Exness_2026_H4.csv)
- [Data manifest](../manifest_2026.json)
