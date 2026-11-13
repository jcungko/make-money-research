# V22-PREREG-1.0 — registered before V22 signal/ML outcome inspection

UTC registration date: 2026-11-13. Full machine-readable specification SHA256: `f2dd2f22b86ca031f8e9694d3dad0c192d2ca5235de07ff7134bfed49b88eeb5`. Exact JSON is packaged in the V22 reproducibility artifact. **V21 has been sealed, no V21 parameter changes allowed.**

## Historical epistemic boundary
2025-01 through 2026-10 Exness EURUSDm Bid/Ask ticks are previously inspected exploratory research, NOT untouched OOS. No prospective data exists as of registration; not before **2026-11-14T00:00:00Z**. Prospective findings may be declared only after later independent collection and no feedback into frozen rules.

## Anchors/features/labels (fixed ahead of V22 outcomes)
- Every 600s on a UTC 07:00–16:00 grid, first quote at/after anchor within 2000ms, spread <=20 points. Events 600s apart, maximum label 300s: **no overlapping label horizons**.
- Price/quote features use only quotes at/before anchor: midpoint momentum at 5/10/30/60s; prior-60s midpoint range and sum abs moves; quote counts 10/60s and ratio; previous-30-tick up-minus-down rate; current and trailing 60s spread; UTC hour.
- Report conditional mid-price and executable Bid/Ask long/short move at 5/10/30/60/120/300s; target first quote at/after timestamp, at most 2000ms late; censored otherwise. Break down BUY/SELL, session, observed spread.
- PRIMARY model target 60s executable quote-side action net after 100ms entry delay + 1 point adverse slippage each side. Class 0 NO_TRADE, 1 LONG if long net > USD0.04 and best, 2 SHORT if short net > USD0.04 and best.
- Model A statistical baseline: StandardScaler+multinomial LogisticRegression C=1.0/max_iter=1000, seed 22. Model B AI: LightGBM n_estimators=180, learning_rate=.05, num_leaves=7, max_depth=3, min_child_samples=70, colsample_bytree=.8, seed 22, n_jobs=2. **NO tuning/hyperparameter search.**
- From TRAINING ONLY, estimate realized mean LONG/SHORT net payoff conditional on class; choose highest predicted expected net USD from calibrated probabilities only if >=$0.02, exceeds other action by >=$0.01 and current spread <=10 points; else NO_TRADE. Require >=25 training examples/class. Accuracy is diagnostic, not objective.

## Time splits and broker execution
- Expanding training from 2025-01, evaluations Jan-Feb, Mar-Apr, May-Jun, Jul-Aug, Sep-Oct 2026, purge all label windows crossing fold boundary; embargo 300s. All labelled retrospective development, not independent proof.
- $100 equity across all historical eval folds, 0.01 lot (1000 EUR), 1:200 scenario, planned risk <=2% equity, one position, 20-point broker-registered SL / 34-point TP simulated (NOT confirmed accepted by MT5); hold max 60s, forced close intraday, no swap unless rollover (then invalid). Bid/Ask fills and stop sides, slippage adverse 1pt/side, delay 100ms; stress 300ms and 3pt, spread 1.5x/2x with replay. Commission $0/side Standard assumption; no backcom.
- Report monthly net Trading PnL, PF, expectancy, trades, marked-to-market DD, cost decomposition, skipped signals and execution stress. Actual broker fill latency, stop level/freeze level, rejects, commission, margin/stopout require calibration. No 2ms execution claim.

## Prospective approval, fixed before future data
Only evaluate on untouched timestamps >=2026-11-14T00:00Z, require >=200 trades over >=20 distinct trade days, >=2 complete months, net expectancy >0 and day-cluster bootstrap 95% lower >0, PF>=1.2, marked-to-market max DD <=20% initial balance, stressed expectancy >0 and PF>=1.0, positive >=60% complete months and no one month providing >50% positive profit. Broker calibration mandatory. **Select at most one only if all gates pass; otherwise NO_EDGE, no EA, no increase of lot/leverage.**
