# V20 — EURUSDm tick recovery (research only)

This branch is deliberately isolated from existing research/Telegram/Cloudflare/MT5 workflows. It places **no orders** and does not read trading credentials.

## Verified pre-existing precedent
- `.github/workflows/v12-exness-2025.yml`: 2025 EURUSD/GBPUSD/USDJPY 12 months fetched successfully, but only OHLC exported.
- `.github/workflows/v12-exness-2026.yml`: 2026 EURUSD etc. fetched successfully, but only OHLC exported.
- `.github/workflows/v7-exness-2025-archive.yml`: original annual EURUSDm tick ZIP published as an Actions artifact; original full 2025 source archive available while artifact lives.
- `.github/workflows/v7-eurusdm-exness-2026.yml`: 2026 original EURUSDm ZIP also published as artifact.
- No V16-named workflow found in workflows listing at audit time.

**Symbol requirement:** Standard account EURUSDm is intentionally different from unsuffixed EURUSD used by V12. Source quotes are indicative, not actual deal fills.

## Workflow procedure
1. A push adding `.github/workflows/v20-exness-tick-recovery.yml` to branch `v20-tick-recovery-20261113` triggers sample 2025-01. It runs both test suites and downloads a genuine EURUSDm ZIP. Raw data and `audit_2025_01.json` are uploaded as `v20-raw-2025-01`.
2. **Only if the sample succeeds**, `backfill` downloads all remaining 21 completed months, at most two concurrent network jobs. Every month has a separate source ZIP and audit manifest in an Actions artifact (`v20-raw-YYYY-MM`, 30-day retention).
3. **Only if all 22 succeed**, `replay` restores the exact raw ZIPs (not OHLC), checks frozen SHA-256, runs all 24 configurations of `research/v20/v20_backtest.py`, and uploads `v20-walkforward-replay`, with `summary.json`, `oos_monthly.csv`, `fold_selections.csv`, original trade log, and validation manifest.
4. Optional `november_preview` attempts the latest complete day 2026-11-12; it is **excluded** from selection and accepted-OOS totals. Failure does not cause the 22-month validation to pass or fail.

Actions: https://github.com/jcungko/make-money-research/actions

### Reproduce

```
python -m pip install pytest
python -m pytest -q tests/test_v20_tick_collect.py research/v20/test_v20.py
python scripts/v20_tick_collect.py --month 2025-01 --out v20_exness_data
python research/v20/v20_backtest.py --data-dir research/v20/data --out v20_replay_results
```

The replay command requires **all** 22 original monthly EURUSDm ZIPs. Any missing, corrupt, or non-millisecond source causes an explicit failure and **no invented PnL**.

### Known limits
- The first date and last timestamp of every ZIP, tick count, bid/ask validity, spread distribution, subsecond proportion, relative tick gaps and SHA-256 are audited.
- A timestamp ending in `.123Z` is not evidence of a new quote every 1ms. Observability is measured by the number of successive quotes <=2/100/300ms. The matching model is a quote-latency counterfactual, **not** VPS ping or historical Exness fill latency.
- Margin model uses US$100 and 0.01 lot with leverage 200. Actual broker-specific execution and historical swap/stop restrictions need real account deal records. No Backcom credited.
- GitHub Actions artifact retention is finite; obtain copies if long-term audit is needed. The download branch and pull request are the reproducible code source; data artifacts are not pushed into public git history.
- Historical full-scale replay is potentially slow due to Python tick-by-tick execution; timeout and OOM must be treated as incomplete, not losing strategies. Changing **implementation performance** is allowed after proving output equivalence; changing the 24 frozen strategy rules is not.