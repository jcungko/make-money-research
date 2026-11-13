# V22 — independent read-only audit and sealed correction (2026-11-13 UTC)

**Status:** NO_VERIFIED_EDGE; V22-PREREG-1.0, original models, decisions, thresholds and all historical outcomes are unchanged. No V22 refit and no backcom.

## Immutable identity
- Frozen prereg JSON SHA-256: `f2dd2f22b86ca031f8e9694d3dad0c192d2ca5235de07ff7134bfed49b88eeb5`.
- **Verified final delivered evidence ZIP SHA-256: `61d3578eaaf45ee812528ae781a8ba2be0996147c2b733d8bf73bc4feb595a5f`.**
- All 25 interior files match the supplied ZIP-embedded SHA-256 manifest.
- Historical source: Exness EURUSDm third-party indicative Bid/Ask archive, 2025-01 through 2026-10, already observed in V20–V22, **not clean OOS**.
- Prior `V22_RETROSPECTIVE_NO_EDGE_CHECKPOINT_20261113.md` cites an earlier packaging SHA-256 (`297eda52...`) that does **not** match the final delivered ZIP. This audit is a new additive correction; do not overwrite or reinterpret the old checkpoint.

## Sampling funnel — hard-coded, not opportunity discovery
26,880,814 filtered real tick rows; 36,126 ten-minute clock-grid slots (UTC 07:00–16:00 all calendar days).
- No quote within +2s: 14,229
- Spread >20 points: 72
- Past-only features unavailable/stale: 14,138
- No entry quote within 2s of +100ms: 613
- Eligible anchor rows: **7,074**
- Missing at least one 60-second future executable quote within 2 seconds: **1,126**
- Labelled anchors: **5,948**
- 2025 training pool: 3,868; 2026 five retrospective test folds together: **2,080** per model.

Strong selection/censoring bias: valid-60 labels by UTC session 07–10: 1,612; 10–13: 1,337; 13–16: 2,999 (50.4%). Only 15/5,948 valid labels were at spread 16–20 points; the other 5,933 are <=10 points, with no 11–15 point labels. Missing labels/session are not missing at random by construction; results cannot be generalized to quiet/wide-spread periods without new evidence.

## Why only 1 and 5 trades?
No-trade abstention is mostly **predicted cost-adjusted EV**, not post-signal margin rejection.
For EACH model: 2,080 historical eval predictions, 2,077 passed spread<=10; only Logistic **1** and LightGBM **5** had best-side predicted net EV >= USD +0.02. Each passed the directional margin and all six were simulated as positions.
- Logistic max predicted side EV +$0.05677; p95 -$0.09362; median -$0.10361.
- LightGBM max +$0.03882; p95 -$0.05145; median -$0.09413.
- Flat-class mean probability ~0.608 Logistic / ~0.605 LightGBM; class accuracy is NOT the optimization goal and the majority flat baseline explains much of it.
- Median entry spread 9 points and mean 8.534 points; baseline adverse slippage adds 2 points/roundtrip. Cost ~10.534 points ~= $0.10534 per 0.01-lot EURUSD trade, before any nonzero broker commission. To reach +$0.02 EV requires expected favorable midpoint move >12.534 points; +$0.04 class threshold requires >14.534 points.

## Consistency / caveats
- Original 19/19 V22 source tests passed on reconstructed dependency layout; 14 additional static audit assertions passed.
- Frozen prereg source hash matches; no signature of future features; chronological fold labels purged with 300-second embargo; event anchors 600 seconds apart vs labels <=300 seconds.
- 2,565 V21 source trade rows reconstruct PnL with 0 USD absolute difference; original V22 1 Logistic positive trade +$0.33 but insufficient sample, 5 LightGBM trades -$1.10; no prospective validation.
- **Methodological limitation, not a retroactively edited parameter**: training class label assumes a fixed 60-second quote-side exit; executed simulator enforces early broker-like SL20/TP34. Cost-class EV does not directly forecast final barrier-exit payoff. V23 must align target with executable barrier outcomes.
- MT5 stop order acceptance, broker server time/rollover, commission and slippage, missing quote when a stop fills, stop-out/margin and VPS 2ms execution remain unverified. Zero historical transaction costs beyond quoted spread and fixed assumed slip are not a live-broker certification.
- Cannot certify the historical scan as clean OOS, cannot choose winning model from six trades.

## Prospective capture (separate operational path)
- Installed NEW `.github/workflows/v22-prospective-exness-isolated.yml` and NEW `scripts/v22_prospective_scheduler.py` in `main` alongside an unchanged copy of frozen `scripts/v22_prospective_collect.py`. No other preexisting workflow files edited or disabled.
- UTC schedule `43 2 * * *`, GitHub read-only `contents: read`, no credentials, bot hooks, Telegram or Cloudflare integrations.
- At 2026-11-14T02:43Z preflight/date gate skips downloading 2026-11-13. Earliest valid date 2026-11-14 UTC can be fetched **no earlier than 2026-11-15T02:43Z**, after closure. Day 2026-11-14 is Saturday; 404 should be logged as unavailable, NOT as confirmed closure; rolling 7-day backfill retries.
- Each valid original ZIP is stored as an action artifact (90-day retention) with SHA256, first/last UTC milliseconds, row count, spread QC, duplicates and gaps; missing dates have explicit manifests. Cron timing and availability are not guaranteed; **first live scheduled run has not happened at audit time**.
- User should arrange separate long-term backup before artifact expiry. Collector does not generate labels or retrain models.

**Gate:** Preserve V22 NO_EDGE. New V23 must preregister before scoring outcomes; >=2026-11-14 UTC future observations untouched until protocol locked; no live EA.
