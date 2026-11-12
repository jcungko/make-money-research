# V21-P4-195 with ATR Stop Loss and total BTC/account risk limits

Validation: max original historical entry/exit parity error 0.00000 bp
Status: BACKTEST_MODEL_ONLY
Data cutoff (UTC): 2026-11-12T18:30:00+00:00
Research account starting equity: 10,000.00 USD
Ending marked equity: 11,528.64 USD
Maximum marked drawdown: 1.641%
Completed trades: 1022, stopouts: 156
Historical months positive 2025-01..2026-10: 18/22

## Research risk settings
{
  "sl_formula": "2 x completed H1 ATR14 with floor 3 x live observed spread",
  "per_trade_initial_stop_risk_pct": 0.2,
  "total_btc_initial_stop_risk_pct": 0.6,
  "total_account_initial_stop_risk_pct": 1.0,
  "max_gross_btc_notional_to_equity": 2.0,
  "min_trade_risk_pct": 0.05,
  "daily_equity_loss_pause_new_entries_pct": 2.0,
  "daily_stop_rule": "pause entries until next UTC date; NO forced flattening",
  "default_exit": "original time-based exit if SL not hit",
  "entry_execution": "long Ask / short Bid plus 1bp adverse slippage",
  "exit_execution": "long Bid / short Ask plus 1bp adverse slippage",
  "sl_intrabar": "5-minute Bid low (long) / Ask high (short), stop-first after entry",
  "gap_rule": "if M5 open is through stop, use worse opening price"
}

## Monthly realized PnL (% initial 10k USD)
| Month | Closed trades | USD PnL | Initial capital % |
|---|---:|---:|---:|
| 2025-01 | 47 | -23.62 | -0.23617% |
| 2025-02 | 33 | +25.06 | +0.25057% |
| 2025-03 | 38 | +86.46 | +0.86462% |
| 2025-04 | 49 | -43.74 | -0.43740% |
| 2025-05 | 55 | +85.96 | +0.85963% |
| 2025-06 | 50 | +28.78 | +0.28778% |
| 2025-07 | 51 | +50.95 | +0.50945% |
| 2025-08 | 40 | +84.02 | +0.84016% |
| 2025-09 | 52 | +56.05 | +0.56052% |
| 2025-10 | 47 | +69.94 | +0.69936% |
| 2025-11 | 46 | +66.56 | +0.66564% |
| 2025-12 | 44 | +37.40 | +0.37398% |
| 2026-01 | 43 | -29.29 | -0.29294% |
| 2026-02 | 36 | +97.34 | +0.97344% |
| 2026-03 | 47 | +7.68 | +0.07680% |
| 2026-04 | 54 | +209.24 | +2.09242% |
| 2026-05 | 41 | -32.37 | -0.32369% |
| 2026-06 | 45 | +134.12 | +1.34116% |
| 2026-07 | 50 | +109.71 | +1.09711% |
| 2026-08 | 52 | +110.13 | +1.10126% |
| 2026-09 | 44 | +368.22 | +3.68223% |
| 2026-10 | 41 | +56.86 | +0.56859% |
| 2026-11 | 17 | -26.81 | -0.26813% |

Historical monthly bp are under different equal-notional sizing; do not compare numeric magnitudes directly.
No real-money trading, no guarantee of positive months.
