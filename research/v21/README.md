# V21 Tick Microstructure Scalping — research-only simulator QA

Created 2026-11-13 on an isolated branch. No EA, trading, backcom or live order endpoint.

**Frozen V21 preliminary design hash:** `4a4023cf2e0bc94f63be210bcd098cc827bbd73b8a8d1d884fa4f654c53f45b9` (`V21-DESIGN-FROZEN-0.1`), frozen before any V21 historical PnL replay.

3 predeclared families: TICK_MOMENTUM (quote-change clustering), QUOTE_REVERSAL (short excursion/fade), VOL_COMPRESSION (price-range breakout). Maximum planned loss 2% of $100 baseline equity, broker-registerable SL/TP at entry, one position at a time, spread and slippage with correct Bid/Ask side, commission explicitly accounted, no unverified overnight swap charge. Broker StopsLevel and true execution remain unknown and require MT5 account-side checks.

A separate downloadable source bundle generated in the current research conversation contains `v21/simulator.py`, the frozen JSON, 27 passing synthetic unit tests, a 50,000 real-tick input QC report and a full V20 raw/source/results archive. This GitHub branch is **an audit index and research checkpoint**, not a claim that local file assets are already durably pushed to GitHub.

The 50,000 quote input QC sample showed spread median 0.9 pip, positive interarrival median 587ms, and 1.32% of positive interarrivals <=2ms. These are quote-arrival statistics only; **2ms broker fills are NOT established**. Sub-10ms fill simulation blocked outside explicitly labeled artificial unit tests. Research replay scenarios 100ms/300ms are hypotheses only, not execution calibration.

2025 through 2026-10 historical data was inspected by V20 and cannot be described as untouched OOS for V21. Prospective evidence not before 2026-11-14 UTC, excluding already previewed dates. No V21 performance backtest was run; **NO V21 Trading PnL, PF, expectancy or drawdown is yet supported**.
