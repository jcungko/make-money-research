# Chinese open-source Forex EA screen — August–October 2026

**Status:** RESEARCH / OHLC diagnostic only, NOT MT4 MetaEditor compilation or MT4 Strategy Tester verification. **No deployment.**

Research performed 2026-11-17. EURUSD and USDJPY, M15 and H1, 0.01 lot per trade, **$1,000 reference capital per independent configuration**, Exness historical Bid/Ask M5 quotes, 2026-08-01 through 2026-10-31 UTC, commission sensitivity **$7 per lot round-trip** ($0.07 per 0.01-lot closed trade), no swap/slippage/margin model.

## Source provenance

- Yumerain/EA-MQL4, 151 stars and 81 forks at review, SHA `d6338c4cee7c38cf15b4781fddfb5c78a5b790f0`: Experts/OKMA.mq4, Experts/MATrend.mq4, Experts/TrendMacd.mq4
- gemgin/ExpertAdvisors, 26 stars and 14 forks at review, SHA `85f3dd7400eaa6416c2ba79ed3fdba91bc873184`: 样例/J_EA_Test9_sh.mq4

Repo stars/forks are NOT independent evidence of individual-strategy profitability. Source MQL4 tested via independent Python port, not native compiled, with M5-based first-quote and intrabar stop approximations. Results can differ materially from real ticks.

## Results: closed-trade PnL USD *after hypothetical commission*

| EA | Pair | TF | Closed trades | Aug | Sep | Oct | Total after fee | Open at 31 Oct |
|---|---|---|---:|---:|---:|---:|---:|---:|
| OKMA | EURUSD | M15 | 91 | +3.76 | +8.98 | -3.66 | +9.08 | 0 |
| OKMA | EURUSD | H1 | 29 | +0.04 | +12.87 | -12.38 | +0.53 | 0 |
| OKMA | USDJPY | M15 | 112 | -10.55 | +16.63 | -25.11 | -19.04 | 0 |
| OKMA | USDJPY | H1 | 24 | -24.91 | +14.51 | -9.55 | -19.95 | 1 |
| MATrend | EURUSD | M15 | 195 | -9.94 | +3.56 | -8.38 | -14.76 | 1 |
| MATrend | EURUSD | H1 | 51 | +14.35 | +18.52 | -9.15 | +23.72 | 1 |
| MATrend | USDJPY | M15 | 210 | -4.91 | +29.29 | -24.22 | +0.15 | 0 |
| MATrend | USDJPY | H1 | 58 | +3.87 | +6.97 | -20.04 | -9.20 | 1 |
| TrendMacd | EURUSD | M15 | 104 | -8.52 | -4.81 | -4.16 | -17.49 | 0 |
| TrendMacd | EURUSD | H1 | 16 | -2.82 | +1.75 | -10.41 | -11.48 | 0 |
| TrendMacd | USDJPY | M15 | 100 | -6.40 | +21.40 | -10.74 | +4.26 | 1 |
| TrendMacd | USDJPY | H1 | 24 | -0.51 | +3.88 | -2.54 | +0.84 | 0 |
| J_EA_Test9_sh | EURUSD | M15 | 736 | -41.68 | -56.07 | -36.79 | -134.54 | 1 |
| J_EA_Test9_sh | EURUSD | H1 | 179 | -9.34 | -13.75 | -13.84 | -36.93 | 0 |
| J_EA_Test9_sh | USDJPY | M15 | 726 | -27.05 | -12.55 | -44.38 | -83.98 | 1 |
| J_EA_Test9_sh | USDJPY | H1 | 180 | -7.54 | +23.27 | -22.77 | -7.03 | 0 |

**Total closed trades across 16 independent scenarios: 2,835.**

## Audit and action

1. All three Yumerain EAs lack broker-side hard SL/TP in their actual OrderSend paths. **Do not deploy without native risk validation.**
2. gemgin strategy's `MIN_EQ=300` blocks a $100 account by default; to comply with fixed 0.01 lots, independent simulator overrides dynamic sizing only (`RISK=0, Lots=0.01`). Its close/close Stochastic uses a sum-of-ranges slowed %K and close when reversal.
3. Most configurations are negative. A positive result over three tested months is **not** forward/live proof. Remaining positions are not force-closed and are excluded from closed PnL.
4. No MQL4 compiler or native Strategy Tester was available. OHLC M5 time sampling, broker symbol rules, order fills, M1 tick sequence, commission/fees and margin can change results. DD is marked-to-market via M5 and not equivalent to MT4 equity DD.
5. This research does NOT change held candidate `research_candidates/EMA_MTF_EURUSD_M15_HOLD.md`.

The full detailed CSV trade ledgers and reproducible Python simulation were delivered as a ZIP within ChatGPT. SHA256 of Python engine: `c6c605b8bc1ccee8dbad0a907733529ab84904bc84bb1d00b2ef460cb5eae34a`.

**Decision:** watchlist only: OKMA/EURUSD M15 and MATrend/EURUSD H1; **not approved to trade** without native validation and risk safeguards.