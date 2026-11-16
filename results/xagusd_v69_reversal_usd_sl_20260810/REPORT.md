# XAGUSD M15 — V6.9-REVERSAL corrected SL −$5 / −$10, TP 50% previous M15 volatility

Research-only Exness public Bid/Ask tick replay, August 1 – October 31, 2026. **This is the corrected experiment, replacing the previous SL/TP both-volatility and 15min/60min timed-close interpretations.**

## Exact trading rules

- XAGUSD **no suffix**; 0.01 lot, contract 5,000 ounces per lot => 50 oz position, $1 price change per oz corresponds to $50 account USD PnL.
- **Previous FULL M15 candle**: volatility = (MID high - MID low) / MID open × 100, using only its actual completed ticks; required ≥0.35%.
- **Current candle**: MID must first move ≥0.05% away from the current candle MID open, then reverse ≥0.05% from the most recent extreme. First completed LONG/SHORT signal by tick sequence is chosen. One entry maximum per M15; never open another trade while one is already active.
- LONG Ask entry and Bid exit; SHORT Bid entry and Ask exit.
- **SL targets** two separate fixed-USD scenarios: loss −$5 and loss −$10 *per trade*. At 0.01 lot, $5 / 50oz = $0.100/oz price stop distance; $10 / 50oz = $0.200/oz.
- **TP** both cases: price distance = Entry_price × ((previous M15 MID volatility percent / 100) × 0.50); TP in USD is therefore dynamic and varies with silver price and candle volatility. Example previous 0.35% and $60 entry => TP price distance 0.105 USD/oz; TP profit $5.25 at 0.01 lot.
- **No time-based exit** of any kind. Stop-market exit at first tick Bid/Ask past stop threshold (can lose more than $5/$10). TP limit fill model at exact target price once actionable quote reaches target.
- At dataset end, any still-open position must be marked censored, not force-closed. Observed 0 censored for both settings.
- Skip the first candle after an exchange quote gap longer than 15 minutes (no immediately preceding completed M15 candle). No synthetic market data inserted.
- Backcom excluded. Bid/Ask spread reflected in realized PnL. Actual commissions, financing swap, network latency/order rejections and extra slippage not known; base model assumes 0 and has adverse cost scenarios.

## Data

| Period (UTC) | Tick updates | M15 candles | Bid/Ask OHLC mismatch |
|---|---:|---:|---:|
| Aug 2026 | 1,576,827 | 1,940 | 0 |
| Sep 2026 | 1,693,112 | 2,014 | 0 |
| Oct 2026 | 1,755,276 | 2,016 | 0 |
| **Total** | **5,025,215** | **5,970** | **0** |

Native Exness archived public XAGUSD tick CSV sources used; tick timestamps verified monotonic, no negative Bid/Ask spreads. Source ZIP SHA-256 and duplicates counts recorded in `summary.json`. All 9 fields of Bid/Ask M15 OHLC plus tick_count matched existing Deepnote 2026 dataset.

## Signal availability

| Month | Prior candle qualifying (≥0.35%) | LONG completed | SHORT completed | Both completed in same candle | Candle with ≥1 signal |
|---|---:|---:|---:|---:|---:|
| Aug | 773 | 639 | 649 | 516 | 772 |
| Sep | 676 | 564 | 563 | 451 | 676 |
| Oct | 627 | 532 | 507 | 414 | 625 |

These are independent completed-event counts within candles, including later signals that were not acted upon because another side triggered first or a trade was still open. No same-tick LONG/SHORT tie observed. The actual trade count is lower, especially with SL −$10 because orders stay open longer.

## Monthly realized PnL by entry month

| SL | Month | Trades | LONG | SHORT | Wins | Losses | Win% | TP | SL | Profit days | Loss days | Net USD | PF | Max DD USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| −$5 | 2026-08 | 751 | 386 | 365 | 247 | 504 | 32.89 | 247 | 504 | 4 | 21 | -553.80 | 0.787 | 602.27 |
| −$5 | 2026-09 | 650 | 338 | 312 | 201 | 449 | 30.92 | 201 | 449 | 3 | 20 | -708.56 | 0.694 | 834.38 |
| −$5 | 2026-10 | 588 | 310 | 278 | 193 | 395 | 32.82 | 193 | 395 | 6 | 19 | -614.67 | 0.696 | 633.25 |
| −$10 | 2026-08 | 650 | 335 | 315 | 310 | 340 | 47.69 | 310 | 340 | 7 | 18 | -764.31 | 0.779 | 842.55 |
| −$10 | 2026-09 | 542 | 278 | 264 | 285 | 257 | 52.58 | 285 | 257 | 7 | 16 | -204.26 | 0.922 | 453.44 |
| −$10 | 2026-10 | 487 | 256 | 231 | 245 | 242 | 50.31 | 245 | 242 | 10 | 15 | -605.04 | 0.753 | 631.24 |

Monthly PnL above groups orders by **entry month**, even if they close after entry month's end. An additional `monthly_by_exit_month.csv` gives cash realized by actual exit month. All entries closed by end of archived October and none were force-closed at month boundaries.


## Whole sample

| Metric | SL −$5 | SL −$10 |
|---|---:|---:|
| Total trades | 1989 | 1679 |
| Wins | 641 | 840 |
| Losses | 1348 | 839 |
| LONG | 1034 | 869 |
| SHORT | 955 | 810 |
| Win Rate % | 32.23 | 50.03 |
| Profit Factor | 0.729 | 0.815 |
| Net USD | -1877.03 | -1573.61 |
| Mean USD/trade | -0.944 | -0.937 |
| Average win USD | 7.883 | 8.271 |
| Average loss USD | -5.141 | -10.156 |
| Realized avg win:loss | 1.533 | 0.814 |
| Max drawdown USD | 1896.97 | 1592.39 |
| TP hit | 641 | 840 |
| SL hit | 1348 | 839 |
| Profit days | 13 | 24 |
| Loss days | 60 | 49 |
| Average holding minutes | 11.01 | 33.76 |
| Maximum holding minutes | 179.40 | 3077.04 |
| SL fills worse than nominal | 1025 | 635 |
| New signals skipped while holding | 84 | 394 |

**Averages show realized, not nominal RR.** At SL −$5, average win/loss ratio ~1.53 vs win rate 32.23%. At SL −$10, realized average win/loss ~0.81 and win rate 50.03%; neither produces a positive expectancy after quoted spread.

## Costs and major risk caveats

| Fixed SL | Quote-spread-included base | Hypothetical +$0.07 fee/trade | Additional $0.50 negative cost/trade | Additional $1 cost/trade |
|---|---:|---:|---:|---:|
| −$5 | -1877.03 | -2016.26 | -2871.53 | -3866.03 |
| −$10 | -1573.61 | -1691.14 | -2413.11 | -3252.61 |

Mean entry spread about $1.01 per 0.01-lot trade. Quote-based spread is already part of PnL — **do not deduct it again**. Commission scenarios are illustrative because the account type and applicable feed-specific fees are not provided. Stop-market executions are approximated using the first recorded crossed quote, not real broker fill latency. No swap/financing is included: in the SL −$10 sample a trade was held over **51 hours**, so ignoring swap and market-closure exposure is important. Trading all signals presumes enough balance/margin throughout sustained drawdown; actual margin stop-out not modeled.

## Trade-by-trade audit

- SL −$5: 1989 trades, 0 overlapping positions, 0 timed exits, 0 open/censored trades; max price-vs-PnL discrepancy 5.178e-13 USD; max TP-conversion discrepancy 3.553e-13 USD; no invalid stop-side prices.
- SL −$10: 1679 trades, 0 overlapping positions, 0 timed exits, 0 open/censored trades; max price-vs-PnL discrepancy 5.178e-13 USD; max TP-conversion discrepancy 3.553e-13 USD; no invalid stop-side prices.

## Reproducibility and storage

- `research/xagusd_v69_reversal_usd_sl_20260810/backtest.py` — standalone tick-based replay source.
- `results/xagusd_v69_reversal_usd_sl_20260810/summary.json` — full results, data hashes, assumptions and provenance.
- `results/xagusd_v69_reversal_usd_sl_20260810/monthly_by_entry_month.csv` and `monthly_by_exit_month.csv` — monthly cashflow/cohort views.
- `results/xagusd_v69_reversal_usd_sl_20260810/totals.csv`, `AUDIT.json` — summary and validation.
- `results/xagusd_v69_reversal_usd_sl_20260810/weekly_trade_parts_manifest.csv` — complete index covering 3,668 individual trade log rows stored in 26 weekly `trades/*.csv` files. Every record has signal timestamp, side, true entry quote, TP/SL price, exit quote/timestamp, realized PnL, spread and holding time.

## Decision

Both SL −$5 and SL −$10 lose money in August, September AND October. SL −$10 loses less overall but substantially increases duration and exposure to overnight/weekend financing/gaps. There is no demonstrated after-all-cost trading advantage with these exact rules; **do not forward deploy live based solely on this test.** No live orders created.
