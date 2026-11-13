# V23 QA committed-source static review — cycle 005 (2026-11-13 UTC)

**Status: STATIC_REVIEW_ONLY; no execution of committed source, no Exness backtest, no model training, no prospective outcome.**

Source reviewed directly via GitHub connector, on branch `research/autopilot-control-20261113`:
- `research/v23/qa/v23_barrier_core.py` blob `7c87d05ec07f83f3ba06a15047771e1d65d34ee4`
- `research/v23/qa/test_v23_barrier_core.py` blob `0a4f072fa89512cebcd3727d71d08177522ac8ae`
- `research/v23/qa/README.md` blob `ed92610838f1f922fce5913371df9b2d612828b4`

## Findings requiring new tests or explicit scope limits

1. **Source execution not established:** local sandbox attempted to fetch the exact committed Python files from `raw.githubusercontent.com`, but DNS resolution failed. This is a connectivity blocker, not a test failure. Prior 13/13 local tests were a separate analogous prototype; do not claim exact committed-source pass.
2. **Censoring of missing stop fills:** after a stop trigger, `fill_after` returns `CENSORED` if no quote within 2 seconds of modeled fill due time. This leaves a potentially severe open loss unresolved. Must not discard such positions as zero PnL in expectancy or risk statistics; maintain open exposure, conservative tail-risk bound or invalidate affected backtest.
3. **Timeout with a later stop:** the loop stops processing when quote timestamp exceeds deadline and then seeks the first quote at/after deadline; a price gap between the last quote and timeout may create a large loss. Add explicit synthetic test to ensure the loss is charged rather than marked zero or skipped.
4. **Risk limit is a simplified planned bound:** `(stop_points + 2*slip_points)*0.01 + commission` does not account for spread changes, broker stop rejection, gap risk, stopout, margin, swap or dynamically computed V23 stop. This cannot certify the <=2% broker-feasible planned risk gate.
5. **Stop/target definitions are a partial model:** prototype computes SL/TP from simulated filled entry, triggers on quote-side Bid/Ask and fills on next quote with adverse slip. MT5 StopsLevel/FreezeLevel, order acceptance, take-profit limit semantics, realized latency, fill policy and server rollover remain unverified. The QA README correctly disclaims these omissions.
6. **Temporal and model gates absent:** no V23 event-driven sampling, volatility prequalification, labels, training-only conditional payoff, embargo, walk-forward, Holm-adjusted prospective inference, DD, or complete costs. Do not call this a complete prereg implementation.

## Next safe actions

- Execute exact SHA-pinned committed Python files in an environment with GitHub checkout, capture command, Python version, stdout/stderr, test count, and SHA-256 log; no new paid services.
- Add deterministic synthetic tests for missing triggered-stop fill, gap at timeout, spread widening, same-timestamp quote ordering, invalid inputs and worst-case unresolved exposure.
- Only after complete prereg-compatible code is reviewable and tested, freeze code and model weights **before** inspecting prospective outcome labels. No edits to frozen V22 or V23 prereg, no live trades.

No trading or Telegram/Cloudflare workflows were changed. No GitHub Actions workflow was created or dispatched.
