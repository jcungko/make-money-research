# V21 frozen microstructure retrospective results — 2026-11-13

Status: **NO EDGE / research-only**, no live EA. The original V21-DESIGN-FROZEN-0.1 has not been changed. All 2025-01 through 2026-10 data were previously inspected and are **not clean OOS**.

Frozen design SHA-256: `4a4023cf2e0bc94f63be210bcd098cc827bbd73b8a8d1d884fa4f654c53f45b9`.
Full independent V21-H1 prereg SHA-256: `e982949f0729cadf72a279158f66ab81ef7e1ac2bc29aae52b7ffa292bcf50f8`.
Pre-outcome H1 GitHub registration commit: `b3337e9aa120e4f579213dfb68e8493a897ae2fd`.

Historical Exness EURUSDm Bid/Ask 22 monthly source ZIPs: 26,928,588 quote rows; 26,880,814 retained by V21 after removing 47,774 adjacent identical timestamp+quote duplicates. Same-timestamp different quotes preserved. V20's 26,880,830 retained count differs by 16 rows due parser handling, which should be reconciled before broker-grade certification.

## A — Signal family backtest (100ms entry/stop lag; 1 point adverse slippage each side)
| Family | Trades | Net USD | Profit factor | Expectancy USD/trade | Quote-equity DD USD | Longest losing streak |
|---|---:|---:|---:|---:|---:|---:|
| Tick Momentum | 707 | -87.13 | 0.313 | -0.1232 | 87.64 | 20 |
| Quote Reversal | 87 | -16.16 | 0.343 | -0.1857 | 17.00 | 18 |
| Volatility Compression | 589 | -66.20 | 0.490 | -0.1124 | 66.57 | 23 |

100USD continuously carried across months, 0.01 lot, leverage assumed 1:200, 2% planned risk cap, one open position per family simulation, broker-registered SL/TP simulated, no overnight positions. Commission Standard zero and swap zero for intraday trades are assumptions; broker fills and actual stop acceptance are unverified.

300ms delay + 3 point slippage on each side: -85.00, -17.41, -85.06 USD, respectively. Trade counts differ across scenarios. Repricing original fills to 1.5x/2x spread worsens all expectancies but is fixed-fill stress, **not** a rerun of SL/TP or $100 equity.

## B — Pre-registered 5-second reversal hypothesis
Strong 10s midpoint move >=0.6 pip, last 3s quote rate <=0.5x previous 7s versus control >=0.9x; nonoverlapping event anchors >=20s. Total 369,704 candidate anchors (80,063 slowed / 289,641 control). At +5s, timely future quote available for 64,270 slowed and 236,575 controls. Reversal probability 45.71% vs 46.66%. Difference **-0.94 percentage points**, 95% day-cluster bootstrap **[-1.37, -0.52] percentage points** (472 days): opposite preregistered H1. Missing future quotes mean CIs are conditional on observed timely quotes, not unconditional causal claims.

Hypothetical 5s reversal-side quote roundtrip: 51,554 executable quote pairs among slowdown events, average **-$0.1049/event**, PF 0.026, aggregate -$5,409.89 of independent diagnostics. This is **not $100 continuous-account Trading PnL and is not broker-SL tradable**.

## C — Control conclusions
No candidate selected. 2ms VPS ping is not 2ms broker execution; no 2ms simulations. No historical 2025–2026 results labeled prospective OOS. Future untouched validation may begin no earlier than 2026-11-14 UTC, after later collection and broker execution calibration. No backcom, no live orders.

Evidence package: generated from local verified historical source with 27 original engine tests plus five supplementary causal/sparse-replay tests; saved separately as `V21_TICK_MICROSTRUCTURE_2025_2026_EMPIRICAL_RESULTS.zip`. This commit captures an immutable human-readable retrospective checkpoint; the raw data archive and full event-level outputs are kept in separate downloadable files, not committed here.
