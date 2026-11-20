# XAGUSD M15 | Research target: 50+ completed trades per full trading day

**Experimental research project, NOT a real-money EA.** This branch is the project specification. It does not contain live-trading connectivity or validated XAGUSD results.

## Non-negotiable scope

- XAGUSD (Exness unsuffixed Standard/Pro quote series), analysis on **closed M15 candles** only; BUY and SELL.
- **50+ complete round trips per eligible trading day**, not 50 entry attempts, and not a monthly average. A normal 24h day has 96 M15 slots; no artificial order creation to reach a quota.
- Evaluate every eligible day separately: trade count, proportion reaching 50, after-cost profit, max drawdown and worst day. Disclose sparse/incomplete days separately.
- Exness tick-derived **Bid + Ask** historical quotes, with exact source URLs, hash checks, instrument/account type, time zone (UTC), and source gaps.
- Historical split: Aug-Sep 2026 development, Oct 2026 untouched holdout, Nov 2026 prospective/forward holdout (completed UTC days only).
- Do not change V6.9D, R146, existing GitHub workflows, MT5 VPS, Cloudflare, or Telegram.

## Candidate signal families (research only)

At each M15 close, calculate signal from data through that closed candle; execute once at next M15 open if eligible. Compare momentum, reversal, EMA-follow, EMA-fade, two-bar state, with ATR stop/target variants. Both directions. First-stage simulation may close within one bar to examine whether 50/day is even feasible. No tuning on held-out months.

**Countermeasure against fake profits:** BUY opens on Ask and closes on Bid; SELL opens on Bid and closes on Ask. Charge account-specific commission, swap where relevant, and measured slippage; record spreads and market closure gaps. OHLC stop/target collisions use conservative stop-first assumptions, but **M15 OHLC cannot establish tick execution**. A true tick replay with latency and fills is necessary before paper trading.

## Pass / fail

Training candidate passes first screen only when every valid Aug-Sep trading day reaches 50 completed trades AND net profit is positive under declared cost assumptions. Independent Oct and Nov tests must also be assessed. If nothing passes, report *no qualifying model*; do not relax thresholds silently. Favor robust net expectancy and drawdown over maximizing entries.

Live deployment remains DISABLED pending account-specific MT5 cost verification, tick replay, paper trading, a hard daily loss limit, broker-compatible SL/TP, position caps and a circuit breaker. No result is guaranteed.

## Implementation status

A runnable offline prototype including a collector, bar-screening backtester, synthetic tests and manual-only GitHub workflow has been assembled in this conversation as a downloadable ZIP. The code is **not yet committed in this branch**; this repository file records the research protocol for review. Never mistake synthetic unit tests for historical backtests.
