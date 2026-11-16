# XAGUSD Exness M15 — B/C — TP +$10, SL −$5, Aug–Oct 2026

**Research-only.** Uses Exness public tick quotes, not executed trade records, and does not create real orders.

## Scope

- Symbol **XAGUSD, no suffix**; UTC timestamps, first tick of each observed M15 bar.
- Lot 0.01 (primary) and 0.02, 0.05, 0.10 (secondary fixed-lot sensitivity).
- XAGUSD contract 5,000 troy oz/lot, pip 0.01 USD/oz, Exness minimum 0.01 lot.
- Trade entry: LONG Ask, SHORT Bid. Quote P&L: (BidExit−AskEntry)*5,000*lot for LONG; (BidEntry−AskExit)*5,000*lot for SHORT.
- **TP is +10 USD per trade**, price delta +10/(5,000×lot) from entry; limit fill assumed at exactly target.
- **SL is −5 USD per trade**, price delta −5/(5,000×lot) from entry; market stop filled at *first tick quoted past the stop* (may exceed $5 loss).
- Before each entry, method **B**: previous M15 BID Close > max BID High of the 3 bars *before the signal bar* => LONG, else SHORT. **C**: previous M15 BID Close > (highest high + lowest low)/2 of immediately preceding 3 completed M15 bars => LONG, else SHORT.
- Always SHORT used as same-execution comparator.
- If no TP/SL is reached, reference EOC exit is the **historical last recorded tick** in that M15. This choice is hindsight and not guaranteed implementable in live trading; a 10-second-earlier first-tick timed-exit robustness scenario is also calculated, with fallback bars explicitly counted.

## Source verification

- 2026-08: 1,576,827 ticks, 1,940 M15 bars, SHA256 `575ac4b1dc8627794c3044140e1ddc1a55ee56bb378339cdaf018880db78ba1e`; M15 Bid/Ask OHLC and tick-count differences against saved Deepnote V18 all **zero**. Average entry spread 0.02101 USD/oz. 3054 successive identical quotes/timestamps retained; 4054 adjacent repeated timestamps; no backward timestamps and no negative spreads. Source: https://ticks.ex2archive.com/ticks/XAGUSD/2026/08/Exness_XAGUSD_2026_08.zip
- 2026-09: 1,693,112 ticks, 2,014 M15 bars, SHA256 `82360708bbaa7da15c1a9336aab783d2450a510633f284cb1c2fd00f4b9429dd`; M15 Bid/Ask OHLC and tick-count differences against saved Deepnote V18 all **zero**. Average entry spread 0.02105 USD/oz. 288 successive identical quotes/timestamps retained; 827 adjacent repeated timestamps; no backward timestamps and no negative spreads. Source: https://ticks.ex2archive.com/ticks/XAGUSD/2026/09/Exness_XAGUSD_2026_09.zip
- 2026-10: 1,755,276 ticks, 2,016 M15 bars, SHA256 `f1ed1fdf7ca11a774828cbb013f2a013ee93a884aab273cdc52fe4c9e6b15438`; M15 Bid/Ask OHLC and tick-count differences against saved Deepnote V18 all **zero**. Average entry spread 0.01852 USD/oz. 1653 successive identical quotes/timestamps retained; 1995 adjacent repeated timestamps; no backward timestamps and no negative spreads. Source: https://ticks.ex2archive.com/ticks/XAGUSD/2026/10/Exness_XAGUSD_2026_10.zip

Total **5,025,215 ticks** and **5,970 bars**, 100% identical tick-aggregated M15 and stored candles for all 9 checked fields. Timestamp gaps longer than 15 min mainly reflect scheduled market breaks; nothing is interpolated.

## Primary results: 0.01 lot, TP +$10, SL −$5, quote-spread included

| Method | Month | Orders | LONG | SHORT | Wins | Losses | Flat | Win% | PnL (USD) | Profit Factor | Max DD ($) | Avg/order ($) | TP | SL | EOC | Green days | Red days |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B | 2026-08 | 1940 | 311 | 1629 | 682 | 1252 | 6 | 35.15 | -1900.20 | 0.658 | 1906.90 | -0.979 | 229 | 997 | 714 | 2 | 24 |
| C | 2026-08 | 1940 | 978 | 962 | 645 | 1290 | 5 | 33.25 | -2217.80 | 0.610 | 2227.35 | -1.143 | 222 | 1012 | 706 | 2 | 24 |
| SHORT | 2026-08 | 1940 | 0 | 1940 | 659 | 1274 | 7 | 33.97 | -2248.30 | 0.606 | 2258.30 | -1.159 | 206 | 1021 | 713 | 3 | 23 |
| B | 2026-09 | 2014 | 272 | 1742 | 676 | 1330 | 8 | 33.57 | -2347.00 | 0.582 | 2381.50 | -1.165 | 173 | 957 | 884 | 2 | 24 |
| C | 2026-09 | 2014 | 978 | 1036 | 647 | 1357 | 10 | 32.13 | -2693.90 | 0.535 | 2706.95 | -1.338 | 172 | 992 | 850 | 1 | 25 |
| SHORT | 2026-09 | 2014 | 0 | 2014 | 702 | 1303 | 9 | 34.86 | -2042.10 | 0.627 | 2063.70 | -1.014 | 180 | 935 | 899 | 4 | 22 |
| B | 2026-10 | 2016 | 264 | 1752 | 764 | 1249 | 3 | 37.90 | -1775.45 | 0.637 | 1870.45 | -0.881 | 130 | 801 | 1085 | 2 | 24 |
| C | 2026-10 | 2016 | 979 | 1037 | 740 | 1270 | 6 | 36.71 | -1960.20 | 0.608 | 1985.85 | -0.972 | 129 | 809 | 1078 | 0 | 26 |
| SHORT | 2026-10 | 2016 | 0 | 2016 | 792 | 1220 | 4 | 39.29 | -1499.65 | 0.687 | 1653.55 | -0.744 | 139 | 780 | 1097 | 4 | 22 |

## Combined 3 months, primary 0.01 lot

| Method | Total trades | Net PnL | Win Rate | Profit Factor | Max DD | Avg/trade | TP/SL/EOC | Green/Red days | Raw commission **scenario** | Zero commission **scenario** |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|
| B | 5970 | -6022.65 | 35.54% | 0.625 | $6119.40 | -1.009 | 532/2755/2683 | 6/72 | -6440.55 | -11992.65 |
| C | 5970 | -6871.90 | 34.04% | 0.583 | $6884.10 | -1.151 | 523/2813/2634 | 3/75 | -7289.80 | -12841.90 |
| SHORT | 5970 | -5790.05 | 36.06% | 0.637 | $5938.95 | -0.970 | 525/2736/2709 | 11/67 | -6207.95 | -11760.05 |

## Other fixed lot simulations; **not all mechanically executable**

| Method | 0.01 lot | 0.02 lot | 0.05 lot | 0.10 lot |
|---|---:|---:|---:|---:|
| B | -6022.65 | -11842.90 | -29491.75 | -60234.00 |
| C | -6871.90 | -12518.20 | -29533.00 | -60234.00 |
| SHORT | -5790.05 | -11619.50 | -29211.75 | -60234.00 |

IMPORTANT: at 0.05 lot, the entry spread already exceeds the entire $5 SL allowance on **4,275/5,970 bars**; at 0.10 lot, it does so on **5,970/5,970 bars**. Those mechanical scenarios demonstrate incompatibility, **not executable broker trades**. Exness does not allow SL within spread. Stop-level, freeze-level, volume step and rejections must be verified on the actual account/MT5 symbol.

## Time-exit robustness

Alternative exit at first tick after M15 start+14m50s, if such tick exists (otherwise previous historical last tick fallback; **127 bars** without a quote in the final 10s across 3 months). Results at 0.01 lot:

| Method | August | September | October | Total |
|---|---:|---:|---:|---:|
| B | -1906.45 | -2375.25 | -1796.00 | -6077.70 |
| C | -2224.40 | -2718.30 | -1953.15 | -6895.85 |
| SHORT | -2240.80 | -2063.05 | -1531.85 | -5835.70 |

This time-exit check is more mechanically specified but still does not prove fills when no quote exists, nor incorporate execution latency or order rejection.

## Slippage, commissions, and risks

- Base case **only** uses the observed Bid/Ask quoted spread (already included). Commission=0 and extra execution slippage=0, since account type and actual fills were not supplied. No Backcom or swap.
- Official Exness commission reference for XAGUSD: Raw Spread $3.50 per lot **per side**, Zero $50 per lot **per side** (as of official commodity specification). The table's Raw/Zero scenarios apply those charges hypothetically to the **same no-suffix XAGUSD quotes**; these are NOT authentic Raw/Zero execution results, since those accounts can have different quotes.
- A $0.50 extra adverse cost **per trade** cuts another $2,985 off total three-month PnL per method at 5,970 orders. Results remain losses, even before those costs.
- Near M15 closing boundary, historical last tick sometimes occurs far before the boundary; 65 bars have the last tick >60 seconds before bar end. Historical last quote is not a guaranteed tradeable quote at scheduled close.
- Modeling assumes sufficient margin and capital to place every trade even after sustained losses, no margin stop-out, no order rejection. Thus large negative hypothetical PnL does not represent an actual feasible account equity path.
- Quote timestamp granularity is milliseconds, but some distinct quote updates share millisecond timestamps; source CSV order is retained.
- SL fills at observed first tick after the threshold; broker execution queues may add slippage beyond this. TP fill assumes target limit filled once quoted crossed.

## Ledger audit

- B: 5970 rows, 0 overlaps, 0 exits in wrong candle, 0 negative durations, max simulated quote holding time 899.954s, 0 PnL/filled-price inconsistencies >$0.01.
- C: 5970 rows, 0 overlaps, 0 exits in wrong candle, 0 negative durations, max simulated quote holding time 899.954s, 0 PnL/filled-price inconsistencies >$0.01.
- SHORT: 5970 rows, 0 overlaps, 0 exits in wrong candle, 0 negative durations, max simulated quote holding time 899.954s, 0 PnL/filled-price inconsistencies >$0.01.

## Reproducible outputs

- `research/xagusd_m15_bc_usd_202608_10/backtest_xagusd_B_C_usd.py`
- `results/xagusd_m15_bc_usd_202608_10/summary.json`
- `results/xagusd_m15_bc_usd_202608_10/all_lots_monthly.csv`
- `results/xagusd_m15_bc_usd_202608_10/timed_exit_10sec_robustness.csv`
- `results/xagusd_m15_bc_usd_202608_10/ledger_audit.json`
- The full 17,910 trade journal for 0.01 lot is stored in the linked Deepnote project at `xag_bc_usd_outputs/trades_lot001_all_methods.csv`.

## Conclusion

**Reject B/C with the requested +$10/−$5 brackets for forward-trading candidacy.** Both lost money every month, and neither beat always SHORT over the full sample. Higher lot size worsens SL-vs-spread incompatibility. The evidence supports further research into signals, not live EA deployment.
