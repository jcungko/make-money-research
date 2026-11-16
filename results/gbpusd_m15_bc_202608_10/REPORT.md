# GBPUSD M15 B/C tick replay — August, September, October 2026

Research only. No live orders or trading automation.

## Source and methodology

- 3,527,094 Exness publicly archived GBPUSD Bid/Ask ticks; 6,240 M15 bars: Aug 2,028, Sep 2,112, Oct 2,100.
- Reconstructed all 6,240 tick OHLC Bid bars and cross-checked against GitHub V17: **all exact matches** (open/high/low/close).
- Backtest timestamps UTC; select signal using completed candles ONLY. B: previous close > max highs of 3 bars BEFORE signal bar => LONG; otherwise SHORT. C: previous close > midpoint(highest high,lowest low of 3 just-completed bars) => LONG; else SHORT. Baseline always SHORT.
- Execute at first tick of entry bar (LONG Ask, SHORT Bid); TP limit price; SL first observed crossed Bid/Ask tick (including any gap); otherwise exit at last available tick within bar.
- **Important:** Last-tick-of-bar EOC exit is a historical approximation and cannot be guaranteed in a live timed close: the trader does not know in advance which tick is last. This test is indicative, not a demonstrated fillable broker execution.
- Spread is included in the bid/ask cashflows. Base case commission = 0 and slippage = 0 (account type not provided), no backcom. Adverse tests deduct extra 0.3, 0.7, 1.0, or 2.0 pips per trade beyond spread. These are post-fill sensitivity tests, not full queue/slippage simulation.
- SL/TP nominal RR >=1; 28 configurations per method, SL/TP in 2,3,4,5,6,8,10 pip; 84 method/config cases with baseline; 252 monthly case rows.
- USD conversion for 0.01 lot GBPUSD: $0.10 per pip assuming 100,000 GBP per 1 lot.

## Primary SL5 TP5 monthly results

| Method | Month | Trades | LONG | SHORT | Wins | Losses | Flat | Win% | Net pips | Net USD 0.01 | PF | Max DD pips | Avg pip/trade | TP | SL | EOC | Profit days | Loss days |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 2026-08 | 2028 | 267 | 1761 | 683 | 1323 | 22 | 33.68 | -2192.5 | -219.25 | 0.440 | 2193.8 | -1.081 | 196 | 470 | 1362 | 0 | 26 |
| C | 2026-08 | 2028 | 998 | 1030 | 670 | 1329 | 29 | 33.04 | -2361.5 | -236.15 | 0.411 | 2364.0 | -1.164 | 187 | 482 | 1359 | 0 | 26 |
| always_SHORT | 2026-08 | 2028 | 0 | 2028 | 712 | 1293 | 23 | 35.11 | -2001.4 | -200.14 | 0.474 | 2001.4 | -0.987 | 207 | 456 | 1365 | 0 | 26 |
| B | 2026-09 | 2112 | 282 | 1830 | 797 | 1295 | 20 | 37.74 | -1847.8 | -184.78 | 0.550 | 1864.6 | -0.875 | 296 | 513 | 1303 | 1 | 25 |
| C | 2026-09 | 2112 | 995 | 1117 | 761 | 1335 | 16 | 36.03 | -2223.7 | -222.37 | 0.485 | 2234.0 | -1.053 | 273 | 540 | 1299 | 0 | 26 |
| always_SHORT | 2026-09 | 2112 | 0 | 2112 | 817 | 1270 | 25 | 38.68 | -1767.7 | -176.77 | 0.561 | 1772.3 | -0.837 | 288 | 513 | 1311 | 1 | 25 |
| B | 2026-10 | 2100 | 315 | 1785 | 785 | 1296 | 19 | 37.38 | -1958.6 | -195.86 | 0.547 | 1986.0 | -0.933 | 329 | 574 | 1197 | 0 | 26 |
| C | 2026-10 | 2100 | 1076 | 1024 | 774 | 1308 | 18 | 36.86 | -2061.8 | -206.18 | 0.529 | 2064.9 | -0.982 | 325 | 582 | 1193 | 0 | 26 |
| always_SHORT | 2026-10 | 2100 | 0 | 2100 | 799 | 1283 | 18 | 38.05 | -1871.7 | -187.17 | 0.562 | 1930.1 | -0.891 | 340 | 568 | 1192 | 0 | 26 |

## Three-month SL5 TP5 totals

| Method | Trades | LONG | SHORT | Win% | Net pips | Net USD 0.01 | PF | Max DD pips | Avg pip/trade | Profit days | Loss days | TP | SL | EOC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 6240 | 864 | 5376 | 36.30 | -5998.9 | -599.89 | 0.514 | 6025.7 | -0.961 | 1 | 77 | 821 | 1557 | 3862 |
| C | 6240 | 3069 | 3171 | 35.34 | -6647.0 | -664.70 | 0.477 | 6647.9 | -1.065 | 0 | 78 | 785 | 1604 | 3851 |
| always_SHORT | 6240 | 0 | 6240 | 37.31 | -5640.8 | -564.08 | 0.534 | 5683.0 | -0.904 | 1 | 77 | 835 | 1537 | 3868 |

## Aug-Sep training selection and October OOS assessment

Selection rule fixed in advance: maximize sum of net pip PnL on **August+September ONLY**, among 28 eligible SL/TP pairs for each method (tie-break smaller TP then smaller SL). Evaluate October only AFTER selection. All train winners are in fact losses. October already featured in earlier project conversations for other strategies, so it is temporally OOS for this grid but not a completely unseen market period in the wider research project.

| Method | Locked SL | Locked TP | Aug pips | Sep pips | Aug+Sep pips | Oct OOS pips | Oct +0.3 pip/trade | Oct +0.7 pip/trade | 3-month pips |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 10 | 10 | -1978.1 | -1802.8 | -3780.9 | -2112.7 | -2742.7 | -3582.7 | -5893.6 |
| C | 2 | 2 | -2054.6 | -2151.8 | -4206.4 | -1930.0 | -2560.0 | -3400.0 | -6136.4 |
| always_SHORT | 10 | 10 | -1815.2 | -1685.8 | -3501.0 | -2050.3 | -2680.3 | -3520.3 | -5551.3 |

**No positive three-month configurations:** 0. All 84 method/config cases are negative in October, so no profitable October OOS result. Profit factor and profitability are after observed quoted spreads but before unverified commission/slippage. Small TP 2–3 pip configurations are included in the exhaustive grid and did not produce profits; TP1 pip / SL1 pip was not in the requested grid.

## Execution and audit caveats

- OHLC tick aggregation audit: 6240 matched / 6240 tick bars, 0 mismatched Bid OHLC fields.
- No trade exit after the next trade entry timestamp in B, C, or always_SHORT; maximum quote-to-quote holding duration was 899.964 seconds, but end-of-candle fills rely on retrospectively selected last quote.
- For SL5, first-quote spread was at least 5 pip on 36 August bars, 37 September bars and 33 October bars (106 bar entries). A broker might reject such stop placement or require a different stop distance; simulations mechanically count triggers and do not demonstrate every order could be placed.
- Closing quote can be older than 60 seconds before bar boundary on 8, 10, and 14 bars respectively. This underscores the end-of-candle execution approximation.
- No martingale or variable lot, no actual broker orders. Results do not validate any forward-trade-ready positive strategy.

## Saved records

- `results/gbpusd_m15_bc_202608_10/summary.json`: every base monthly and total statistic, selected train configurations, archive provenance.
- `results/gbpusd_m15_bc_202608_10/all_configs_monthly.csv`: 252 monthly scenario records, all 84 strategies/config combinations.
- `results/gbpusd_m15_bc_202608_10/config_grid_train_oos.csv`: all 84 train/OOS comparisons.
- `results/gbpusd_m15_bc_202608_10/audit.json`: tick/OHLC and chronology reconciliation.
- `research/gbpusd_m15_bc_202608_10/backtest_gbpusd_B_C.py` and `audit_gbpusd_m15.py`: reproducible source.
- Full trade-level ledger (18,720 records at SL5 TP5) also saved in associated Deepnote research project.

### Decision

**Reject B and C as currently defined for forward test.** Neither exhibits positive returns after observed spread, and both underperform always_SHORT on the same basis. Additional real-world transaction costs worsen results.
