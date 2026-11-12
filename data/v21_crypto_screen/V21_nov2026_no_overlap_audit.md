# V21: eliminate duplicated / over-synchronized strategies

Frozen input: 44 portfolios profitable through 2026-11-12 20:00 UTC.

Starting portfolios: 44
Remove internally duplicated symbol+entry hour+trade direction: 38
Structurally distinct candidates: 6
Remove 3/4-identical portfolios: 5
**Final selected: V21-P4-098 (1 portfolio)**

## Six unique-time-direction candidates

|ID|2025-2026 min month (bp)|Nov 2026 (bp)|Exact same-asset entry collisions Jan2025-Oct2026|Total overlapping position pairs|
|---|---:|---:|---:|---:|
|V21-P4-098|9.495|9.376|2|173|
|V21-P4-088|11.103|0.872|4|175|
|V21-P4-119|5.988|7.958|7|178|
|V21-P4-194|0.234|17.123|25|196|
|V21-P4-195|0.234|32.039|31|202|
|V21-P4-053|16.036|27.084|83|254|

## Selected bot configurations

- `BTCUSD|H1|range_top_20|long|H2|08utc`
- `BTCUSD|H1|rsi7_below_40|long|H4|20utc`
- `BTCUSD|H1|above_sma_50|short|H8|00utc`
- `BTCUSD|H4|range_top_20|short|H3|20utc`

## Important limitations

Same symbol/time/direction duplication eliminated among bots; however, short and long on the same symbol can still overlap in held positions even when entry times differ. Do not treat the selected portfolio as fully risk-independent.
Exness Bid/Ask + assumed slippage; swap, commission, hard SL, margin, and execution conditions not included.
November 2026 has not ended.
