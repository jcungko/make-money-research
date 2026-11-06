# MAKE MONEY — Independent Research Engine

**Read-only Binance USDⓈ-M Futures research.** There are no trading API keys, order endpoints, Telegram tokens or Cloudflare bindings. The existing R146 Telegram signal service is not modified.

## Status
- GitHub Actions schedule: `2,7,12,17,22,27,32,37,42,47,52,57 * * * *` UTC = **every 5 minutes** (may be delayed or skipped by GitHub).
- GitHub Actions also supports manual `workflow_dispatch`. First run must be checked on the **Actions** tab; writing the workflow does not prove it has executed successfully.
- Every run is capped at 25 minutes; Python's compute budget is 1,050 seconds and 12 model configurations across up to 2 symbols.
- Each run stores a compact run journal, cumulative counters and a deterministic cursor in `results/`. The next run reads that cursor and rotates symbols. Errors and API restrictions are recorded rather than silently interpreted as no-profit.
- This repository was **public when installed**. If the company wants proprietary strategy protection, make it Private in repository settings before adding sensitive research. Never commit trading credentials.

## Scope
The engine uses historical Binance USD-M perpetual futures market data for active USDT contracts, combining high-volume and newly listed coins. It tries six signal families: long breakout, short breakout, EMA pullback, RSI mean reversion, futures-history new-high breakout and funding fade. Timeframes: **15m / 30m / 1h / 4h / 1d**. Random but deterministic configurations vary volatility stops, trading session, R:R, volume filter, hold duration, leverage, and funding threshold.

The simulation uses next-bar entry, conservative stop-first assumptions, fee and slippage estimates, funding charges and simple leverage risk guards. **Not fully modeled:** mark-price liquidations, partial executions, order-book depth, stale/unavailable data, exchange restrictions or delisted symbols. No strategy is approved for real-money trading by this engine. Profitable backtests are labeled **EXPLORATORY** and must undergo untouched walk-forward/paper validation.

## Start and inspect
1. Open **Actions → MAKE MONEY independent research (paper only) → Run workflow**.
2. Confirm **Tests** and **Backtest** steps complete. If Binance blocks the runner, see `results/errors.jsonl`. Do not assume any tests completed.
3. Inspect `results/runs.jsonl`, `results/profitable_experiments.jsonl`, `results/candidates.jsonl`, `results/errors.jsonl` and `results/state.json`. The legacy `results/experiments.jsonl` contains the first 16 raw tests; new unprofitable configurations are reproducible from symbol plus model cursor instead of being appended indefinitely. Successful jobs commit the checkpoints.
4. Allow the 5-minute schedule to resume automatically, subject to GitHub Actions being enabled. Five minutes is GitHub Actions' shortest supported cron interval. Faster repeated polling is deliberately not implemented.

For local tests: `pip install -r requirements.txt && pytest -q`.

## Budget and reliability
Standard GitHub-hosted runner minutes are free in public repositories under GitHub's policy; private repository quotas and cache storage limits differ. GitHub can delay or disable scheduled jobs and Binance can restrict IPs. Monthly usage should be monitored. This architecture offloads research from Cloudflare but **cannot guarantee zero cost, uninterrupted runs, or profitable discoveries**.

## Research loop
1. Discover a Binance futures contract.
2. Generate reproducible configurations and backtest under costs.
3. Rank and record outcomes. For a losing or weak configuration, advance the cursor and test another. For promising outcomes, record candidate evidence and continue researching.
4. The process resumes on its next scheduled run. It never alters live signaling or places trades.

## Data freshness
The backtest downloads **closed monthly Binance Vision archive data** (not the live Binance Futures API, which returned HTTP 451 on GitHub Actions). At the beginning of each month, the engine may use the prior month when the newest ZIP is not yet published. Funding values come from Binance monthly funding archives; funding notional uses the last fully closed 15m candle as an approximation because the funding archive lacks the exact mark-price series. This is research data only, not appropriate for current trading alerts.
