# V10.0 — USDJPY Exness 2026 candle archive

**Status:** collected and validated from a public mirror of Exness tick-history ZIP files as of 2026-11-11. This is **USDJPY**, not a directly tradable Exness symbol called JPYUSD. USDJPY quotes Japanese yen per 1 US dollar. Do not silently invert trade directions or P&L conventions.

## Coverage and output

- First tick (UTC): `2026-01-01 22:11:01.493Z`
- Last tick (UTC): `2026-11-09 23:59:57.348Z`
- Total raw bid/ask ticks: **14,941,657**
- **M15:** 21,317 candles — `USDJPY_Exness_2026_M15.csv`
- **H1:** 5,330 candles — `USDJPY_Exness_2026_H1.csv`
- **H4:** 1,378 candles — `USDJPY_Exness_2026_H4.csv`
- **Provenance and per-month SHA-256:** `manifest_2026.json`

These files cover 2026 **to the last available archive tick**, not the complete calendar year. The November archive currently ends November 9, 2026; updates beyond that are not included.

## CSV fields

`time_utc,bid_open,bid_high,bid_low,bid_close,ask_open,ask_high,ask_low,ask_close,tick_volume,mean_spread_pips`

- Each `time_utc` is the candle's **opening time** on UTC/GMT+0, with M15 on :00/:15/:30/:45, H1 on the hour, and H4 at 00:00/04:00/08:00/12:00/16:00/20:00 UTC.
- OHLC values are separate for Bid and Ask, in JPY per 1 USD.
- `tick_volume` counts price-update ticks in each candle, **not** centrally reported traded volume.
- `mean_spread_pips` is the tick-weighted average (Ask−Bid)/0.01 JPY. It is **not** swap, commission or slippage.
- Bars with zero archived ticks are absent, including normal market closures; **do not fill weekends with flat synthetic candles** for trade backtests.

## Provenance and cautions

Public archive download pattern: `https://ticks.ex2archive.com/ticks/USDJPY/2026/MM/Exness_USDJPY_2026_MM.zip`, months 01–11, as used in a third-party archive guide. This is **a mirror of Exness-labeled tick history**, not a direct verified MT5 export from the user's specific Exness server/account. Each source ZIP has an SHA-256 value recorded in the manifest. The official Exness tick history archive: https://www.exness.com/tick-history/ . The official server-time reference: https://get.exness.help/hc/en-us/articles/360014390760-What-is-the-default-timezone-set-for-MetaTrader . The Exness help center warns historical chart candles may differ from MT5/server-specific charts: https://get.exness.help/hc/en-us/articles/30553857642780-Why-can-chart-candles-differ-in-Exness-Trade .

Validation: all three timeframes conserve the same 14,941,657 tick count; no synthetic price observations were added. H1 and H4 were rolled up from chronological M15 Bid/Ask OHLC and tick-weighted spread. Future execution-oriented backtesting should account for spread, slippage, commission, swaps and account-specific symbol settings, and verify representative bars against actual Exness MT5 data.
