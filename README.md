# MAKE MONEY — Independent Research Engine

**Read-only Binance USDⓈ-M Futures research.** There are no trading API keys, order endpoints, Telegram tokens or Cloudflare bindings. The existing R146 Telegram signal service is not modified.

## Status
- GitHub Actions schedule: `17 1,13 * * *` UTC = **08:17 and 20:17 Vietnam time**, subject to GitHub scheduling delays, account settings and availability.
- GitHub Actions also supports manual `workflow_dispatch`. First run must be checked on the **Actions** tab; writing the workflow does not prove it has executed successfully.
- Every run is capped at 25 minutes; Python's compute budget is 1,050 seconds and 12 model configurations across up to 2 symbols.
- Each run stores a journal and cursor in `results/`. The next run reads that cursor and rotates symbols. Errors and API restrictions are recorded rather than silently interpreted as no-profit.
- This repository was **public when installed**. If the company wants proprietary strategy protection, make it Private in repository settings before adding sensitive research. Never commit trading credentials.

## Scope
The engine uses historical Binance USD-M perpetual futures market data for active USDT contracts, combining high-volume and newly listed coins. It tries six signal families: long breakout, short breakout, EMA pullback, RSI mean reversion, futures-history new-high breakout and funding fade. Timeframes: **15m / 30m / 1h / 4h / 1d**. Random but deterministic configurations vary volatility stops, trading session, R:R, volume filter, hold duration, leverage, and funding threshold.

The simulation uses next-bar entry, conservative stop-first assumptions, fee and slippage estimates, funding charges and simple leverage risk guards. **Not fully modeled:** mark-price liquidations, partial executions, order-book depth, stale/unavailable data, exchange restrictions or delisted symbols. No strategy is approved for real-money trading by this engine. Profitable backtests are labeled **EXPLORATORY** and must undergo untouched walk-forward/paper validation.

## Start and inspect
1. Open **Actions → MAKE MONEY independent research (paper only) → Run workflow**.
2. Confirm **Tests** and **Backtest** steps complete. If Binance blocks the runner, see `results/errors.jsonl`. Do not assume any tests completed.
3. Inspect `results/experiments.jsonl`, `results/candidates.jsonl`, `results/errors.jsonl` and `results/state.json`. Any successful research job commits its progress.
4. Allow the twice-daily schedule to resume automatically, subject to GitHub Actions being enabled.

For local tests: `pip install -r requirements.txt && pytest -q`.

## Budget and reliability
Public repositories may receive free standard GitHub-hosted Actions usage under GitHub's policy; private repository quotas differ by plan and configuration. GitHub can delay or disable scheduled jobs and Binance can restrict IPs. Monthly usage should be monitored. This architecture offloads research from Cloudflare but **cannot guarantee zero cost, uninterrupted runs, or profitable discoveries**.

## Research loop
1. Discover a Binance futures contract.
2. Generate reproducible configurations and backtest under costs.
3. Rank and record outcomes. For a losing or weak configuration, advance the cursor and test another. For promising outcomes, record candidate evidence and continue researching.
4. The process resumes on its next scheduled run. It never alters live signaling or places trades.
