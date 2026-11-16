# XAGUSD M15 — B/C USD Stop-Loss / Take-Profit Grid — August to October 2026

**Research only. No EA deployed.** Exness public Bid/Ask tick replay of XAGUSD (unsuffixed), M15, fixed 0.01 lot.

## Experimental design

- SL dollar amounts: **5, 6, 7, 8, 9, 10, 15, 20 USD**.
- TP dollar amounts: **2, 3, 4, 5, 6, 7, 8, 9, 10 USD**.
- **72** dollar SL/TP pairs per method, including TP below SL; methods B, C, and an always-SHORT control; 216 total configurations and **648 monthly records**.
- 0.01 lot × 5,000 oz/lot = 50 oz exposure, so price changes of $0.02/oz equal $1 gross before spread.
- B: previous closed M15 BID close above maximum BID high from the 3 candles **preceding the signal candle** => LONG; otherwise SHORT.
- C: previous closed M15 BID close above midpoint of highest BID high and lowest BID low in immediately previous 3 closed candles => LONG; otherwise SHORT.
- One trade at first tick per observed M15: LONG enters Ask, exits Bid; SHORT enters Bid, exits Ask. TP limit at exact price corresponding to its USD amount. SL closes on first actionable opposite quote crossing stop, possibly worse than the dollar threshold. If neither hit, close at last available tick in M15 as historical EOC proxy.
- Transaction costs: actual archive Bid/Ask spread included; unverified additional commission and slippage set 0 for base. Sensitivities subtract an additional $0.50 or $1.00 **per trade**, not observed fees. No Backcom.
- **Selection protocol:** choose SL/TP with highest August + September net USD separately for B, C and SHORT. Only then inspect October. October is chronological OOS for this grid but NOT a pristine holdout across the entire project's previous research.

## Source provenance and data audit

| Month UTC | Ticks | M15 bars | Mean spread at entry, per 0.01 lot | M15 mismatch against saved Deepnote |
|---|---:|---:|---:|---:|
| 2026-08 | 1,576,827 | 1940 | $1.050 | 0 |
| 2026-09 | 1,693,112 | 2014 | $1.052 | 0 |
| 2026-10 | 1,755,276 | 2016 | $0.926 | 0 |

All 5970 reconstructed M15 bid/ask OHLC and tick-count records matched existing data. All sources are native 2026 Exness public tick archives. Source zip SHA256 strings are preserved in summary.json. Market breaks are not filled with synthetic candles. A small number of identical consecutive tick records are retained for fidelity; no reverse-ordered timestamps. First and last tick timestamps are recorded per source.

## Selected by August and September only

| Method | SL USD | TP USD | August USD | September USD | Training USD | October OOS USD | All 3 months USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| B | 9 | 6 | -1729.20 | -1973.55 | -3702.75 | -1579.50 | -5282.25 |
| C | 9 | 6 | -2072.50 | -2288.70 | -4361.20 | -1867.90 | -6229.10 |
| SHORT | 9 | 9 | -1936.80 | -1790.25 | -3727.05 | -1390.15 | -5117.20 |

**Zero** of all 216 configurations produced positive PnL in any individual month. In particular, there is no positive October OOS result. The least-negative pair selected for B and C was SL $9 / TP $6, which has nominal RR **0.67:1**, not a profitable configuration.

## Selected configurations: three-month trade-level metrics

| Method | SL / TP | Trades | Win% | Profit factor | Max DD USD | Avg USD/trade | TP / SL / Time | Profit / loss days | PnL USD |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| B | 9/6 | 5970 | 45.13 | 0.681 | 5397.45 | -0.885 | 1491 / 1088 / 3391 | 12 / 66 | -5282.25 |
| C | 9/6 | 5970 | 43.47 | 0.637 | 6260.50 | -1.043 | 1464 / 1096 / 3410 | 2 / 76 | -6229.10 |
| SHORT | 9/9 | 5970 | 43.03 | 0.699 | 5242.65 | -0.857 | 778 / 1131 / 4061 | 15 / 63 | -5117.20 |

Stops may fill beyond their dollar target: B SL9/TP6 had 809 SL overshoots and C had 813; the replay does not misstate these as fixed -$9.

## Selected B/C detailed per-month statistics

| Method | Month | Trades | TP | SL | Time-close | Win | Loss | Flat | Positive days | Negative days | PnL USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 2026-08 | 1940 | 555 | 422 | 963 | 909 | 1026 | 5 | 6 | 20 | -1729.20 |
| B | 2026-09 | 2014 | 516 | 384 | 1114 | 883 | 1124 | 7 | 2 | 24 | -1973.55 |
| B | 2026-10 | 2016 | 420 | 282 | 1314 | 902 | 1109 | 5 | 4 | 22 | -1579.50 |
| C | 2026-08 | 1940 | 547 | 414 | 979 | 868 | 1067 | 5 | 1 | 25 | -2072.50 |
| C | 2026-09 | 2014 | 511 | 392 | 1111 | 853 | 1151 | 10 | 0 | 26 | -2288.70 |
| C | 2026-10 | 2016 | 406 | 290 | 1320 | 874 | 1136 | 6 | 1 | 25 | -1867.90 |

## Improvement against the original SL $5 / TP $10

| Method | Original three-month USD | Best Aug+Sep SL9/TP6 three-month USD | Reduction in simulated loss |
|---|---:|---:|---:|
| B | -6022.65 | -5282.25 | +$740.40 |
| C | -6871.90 | -6229.10 | +$642.80 |

**Cost stress, held-out October:** B selected -$1,579.50 before unverified extra costs, -$2,587.50 with extra $0.50 per trade; C selected -$1,867.90, versus -$2,875.90 under the same stress. Over three months, B selected becomes -$8,267.25 and C -$9,214.10 with extra $0.50 per trade.

## End-of-M15 order execution limitation

Base EOC uses last historical tick within each 15-minute interval: this is not necessarily a quote that could be selected in advance. An additional run uses the **first tick on/after 14 minutes 50 seconds of the bar** where available, falling back to the last observed tick on **127 bars without a quote in the final ten seconds**. This yields selected B -5332.35 USD and selected C -6238.60 USD, still negative. The fallback is not an executable price guarantee and no actual broker order-rejection, margin stop-out, execution latency, or slippage distribution was measured. These backtests cannot be presented as fill-accurate live-account profit/loss.

## Top 5 training configurations per method (training only)

| Method | SL | TP | Aug+Sep USD | October USD | Whole period USD |
|---|---:|---:|---:|---:|---:|
| B | 9 | 6 | -3702.75 | -1579.50 | -5282.25 |
| B | 9 | 9 | -3729.65 | -1692.35 | -5422.00 |
| B | 9 | 7 | -3730.10 | -1569.00 | -5299.10 |
| B | 9 | 8 | -3742.30 | -1673.70 | -5416.00 |
| B | 9 | 5 | -3761.55 | -1566.45 | -5328.00 |
| C | 9 | 6 | -4361.20 | -1867.90 | -6229.10 |
| C | 9 | 7 | -4433.50 | -1923.30 | -6356.80 |
| C | 7 | 6 | -4450.00 | -1784.70 | -6234.70 |
| C | 8 | 6 | -4458.45 | -1809.30 | -6267.75 |
| C | 9 | 5 | -4468.15 | -1839.00 | -6307.15 |

## Artifacts

- `research/xagusd_m15_bc_sl_tp_grid_202608_10/grid_replay.py`: rerunnable full tick grid code.
- `research/xagusd_m15_bc_sl_tp_grid_202608_10/audit_selected.py`: independent selected pair tick replay including alternate EOC.
- `results/xagusd_m15_bc_sl_tp_grid_202608_10/summary.json`: source hash provenance, grid and the locked picks.
- `results/xagusd_m15_bc_sl_tp_grid_202608_10/all_config_train_oos_216_rows.csv`: all 216 per-method/SL/TP Aug+Sep selection vs Oct OOS.
- `results/xagusd_m15_bc_sl_tp_grid_202608_10/all_monthly_2026-08.csv`, `all_monthly_2026-09.csv`, `all_monthly_2026-10.csv`: all 648 monthly records, split by source month (each 216).
- `results/xagusd_m15_bc_sl_tp_grid_202608_10/selected_locked_audit.json`: selected SL/TP detailed chronological audit.
- `results/xagusd_m15_bc_sl_tp_grid_202608_10/selected_locked_totals.csv`: compact three-month results.

**Research conclusion:** No evidence of profitable trading in B or C on this grid. All strategies/configs lose money in all months before additional fees. Reject as currently defined; don't deploy as real EA solely based on the least-loss combination.
