# V23 cycle 007 — unresolved exposure and censoring implementation gate

Status: **DESIGN REVIEW ONLY — NOT A CHANGE TO FROZEN V23-PREREG-1.0, NOT A BACKTEST, NOT A NEW PERFORMANCE CLAIM.**

## Frozen rule reconciliation

V23-PREREG-1.0 requires broker-registered stops, next quote after modeled 100ms trigger-to-fill delay, max 2s lateness, 300s maximum holding, risk and margin checks, and **no unresolved position, unregistered broker stop, or unaccounted open equity**. Historical quote availability alone does not establish a broker fill.

The partial synthetic `v23_barrier_core.py` currently returns `CENSORED` and null PnL when a triggered stop/target cannot be filled within the quote tolerance, and also when a 300s timeout lacks a valid exit quote. This is a useful diagnostic but is **not** a valid flat-position transition.

## Implementation requirements for full V23 pipeline (proposed, not executed)

1. Track separate `position_state` (FLAT, OPEN, EXIT_REQUESTED, UNRESOLVED) and `observation_state` (VALID, STALE, MISSING), never equating a censored label with zero realized PnL.
2. Preserve entry timestamp, executable entry price, side, size, stop/target registration status, trigger timestamp and reason, last valid quote, requested exit time, and all attempted fill timestamps. If no executable fill within the registered 2s window, mark UNRESOLVED and **fail strategy eligibility** until resolution can be independently demonstrated; do not drop these cases from DD, trade-count denominator or success statistics.
3. On gaps, evaluate quote-side stop triggers chronologically using original same-timestamp ordering; do not fill at stop price when next executable quote gaps beyond it. Distinguish simulated exit quote from actual broker execution evidence.
4. An unresolved exposure blocks new entries under one-position rule. For research-only reporting, publish count, duration, latest mark-to-market equity and conservative gap-risk sensitivity separately; do not assign arbitrary closed PnL or assert broker stop completion.
5. Both BUY and SELL counterfactuals are correlated outcomes of one anchor. A missing or unresolved action payoff must not be silently imputed as a losing/winning/flat training class. Define an explicit censored-row funnel and check consistency with frozen class rule before training.
6. Add synthetic QA for unresolved stop, unresolved timeout, no next quote, spread widening, gap loss beyond 2% planned stop risk, same-ms ordering, and margin/stopsLevel rejection. These tests must run against the exact GitHub-committed SHA, with output log and source hashes recorded.
7. Do not modify the frozen prereg or tune thresholds using prospective data. If any substantive interpretation changes the frozen strategy, register a new protocol ID and new future cutoff **before** outcome inspection.

## Other static audit observations

- Partial core's `commission_usd` is an aggregated cash amount, not independently verified per-side broker commission. Actual commission, swap, stop/freeze levels and order rejection remain uncalibrated.
- `swap_usd` may be negative (a credit); this is allowed by the prototype but must not be assumed for Exness without account evidence.
- Current risk gate uses planned stop cash loss; gap losses can exceed that amount. Mark-to-market DD cannot be inferred from closed trade PnL alone.
- GitHub Actions QA execution and artifact listing are not established; the local 19/19 synthetic test evidence from cycle 006 does not certify a full strategy.

**Decision:** V23 remains DESIGN_FROZEN_NOT_TRAINED_NOT_VALIDATED. Next code work should implement explicit unresolved position accounting and tests without trading or main-branch changes.
