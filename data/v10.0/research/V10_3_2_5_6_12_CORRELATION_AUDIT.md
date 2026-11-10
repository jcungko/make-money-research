# V10.0 — Correlation audit of chosen USDJPY strategies #3 #2 #5 #6 #12

**Backtest data:** Exness-labelled tick mirror candles, Bid/Ask M15/H1. Signals derived from *previously closed* candles only. Timezone of quotes UTC. Simulation subtracts an additional 0.5 pip per trade beyond Bid/Ask spread. Stops simulated on M15 high/low with stops taking precedence if both stop and target hit inside a candle. No independent out-of-sample validation. November 2026 is partial to 2026-11-09.

**Sample:** 137 eligible weekday trading sessions, May 1–Nov 9 2026. Extended cross-check: 221 common sessions Jan 5–Nov 9 2026. Daily results saved in `V10_3_2_5_6_12_daily_correlations.csv`.

## Entries and exits
- #3 (M15 SMA8): entry 06:00 UTC (13:00 VN), hold 8h, time-only stop.
- #2 (M15 momentum 2): entry 06:00 UTC, SL45/TP60 pips, max 8h.
- #5 (intraday H1 range): entry 06:00 UTC, SL45/TP60 pips, max 8h.
- #6 (H1 acceleration 12h): entry 00:00 UTC (07:00 VN), hold 6h, time-only stop.
- #12 (M15 SMA4/SMA16 inverse): entry 14:00 UTC (21:00 VN), SL30/TP30 pips, max 8h. Tie rule: if fast and slow MAs exactly equal, inverse side is SHORT, consistent with original backtest's inverse signal.

## Pairwise similarity, May–Nov 9 2026

| Pair | Same Long/Short direction | Daily NetPip Pearson | Days both losing /137 |
|---|---:|---:|---:|
| #3 / #2 | 78.83% | +0.4640 | 40 |
| #3 / #5 | 76.64% | +0.4210 | 38 |
| #3 / #6 | 52.55% | +0.2455 | 27 |
| #3 / #12 | 37.23% | +0.0831 | 19 |
| #2 / #5 | 62.77% | +0.3554 | 34 |
| #2 / #6 | 47.45% | -0.0177 | 33 |
| #2 / #12 | 37.96% | +0.1211 | 27 |
| #5 / #6 | 51.09% | -0.0868 | 27 |
| #5 / #12 | 41.61% | +0.0386 | 24 |
| #6 / #12 | 49.64% | +0.0472 | 34 |

## Full available-year cross-check (221 common trading days)

| Pair | Same direction | NetPip Pearson |
|---|---:|---:|
| #3/#2 | 80.54% | +0.5411 |
| #3/#5 | 77.38% | +0.4330 |
| #3/#6 | 51.13% | +0.1441 |
| #3/#12 | 44.34% | +0.0791 |
| #2/#5 | 66.06% | +0.4048 |
| #2/#6 | 48.87% | +0.0054 |
| #2/#12 | 43.89% | +0.1212 |
| #5/#6 | 48.42% | -0.0553 |
| #5/#12 | 44.34% | +0.0428 |
| #6/#12 | 51.58% | +0.0359 |

## Joint-loss and concentration check

- #3/#2/#5 all go in the same direction on **81 of 137 days (59.1%)** and all three lose together on **31 of 137 days**.
- All five select the same direction on **12 of 137 days (8.8%)**, although the entries occur at different times, so matching direction is not synonymous with simultaneous exposure.
- All five lose on **9 of 137 days**. At least 4 lose on **26** days; at least 3 lose on **53** days.
- 2026-07-30: individual net pips: #3 **-380.7**, #2 **-45.5**, #5 **-45.5**, #6 **-24.7**, #12 **-30.5**. Arithmetic sum **-526.9 pips** at equal-lot illustration. #3 and #6 lack broker-side stops.
- The arithmetic sum of five daily pip streams is not a proper capital-weighted portfolio risk/return estimate, and does not model leverage, overlapping positions, equity margin, swaps and slippage.
- #12 has narrow positive May–Aug months (e.g. July +4.3, Aug +3.5 pips). #6 has Aug +2.4 and Oct +2.2 pips. Such months could easily turn negative after modest additional trading costs.

## Conclusion
The five strategy **rules** are different, and #6/#12 have low daily-P&L correlation versus the original #3/#2/#5. But the latter three share a common 06:00 UTC entry and often the same direction; they should be managed as a correlated group, not three independent bets. The whole portfolio is USDJPY risk and remains vulnerable to market shocks. The high in-sample gains come from extensive retrospective optimization, not validated predictive performance. Before live trading, independently stress-test slippage and fees, commission and swap, broker-specific MT5 candles, fixed hard stops for #3/#6, portfolio exposure limits and untouched future-period performance.
