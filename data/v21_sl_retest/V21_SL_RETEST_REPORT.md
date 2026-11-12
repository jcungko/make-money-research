# V21: SL backtest on the 10 frozen portfolios
SL is an absolute stop-loss from quoted entry on each of four legs.
Fill tested on 5-minute observed Bid/Ask high/low; adverse gap and 1bp slippage.
Stop 1% is the default defined **before** reviewing November results.
Validation: PASS_VALIDATED_SL_BACKTEST.

|SL|Profitable both years|22/22 profitable months|Nov profitable|22/22 and Nov|
|---|---:|---:|---:|---:|
|0.50%|10|0|7|0|
|1.00%|10|0|3|0|
|1.50%|10|0|3|0|
|2.00%|10|0|9|0|

See V21_SL_RETEST_FULL.json for each portfolio monthly P&L and each of its four bots.
No real orders. Does not include swap or commissions.
Data only through 2026-11-12 18:00 UTC, not the full November month.
