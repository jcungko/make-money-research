# V22 Exness public CFD stock tick-derived data

Collection date (UTC): 2026-11-12; requested periods:
- 2025-01-01 inclusive to 2026-01-01 exclusive (full 2025)
- 2026-01-01 inclusive to 2026-11-01 exclusive (Jan 1 through Oct 31, 2026)

Symbols: NVDA, NIO, AMD, AVGO, SPCX, XPEV, LI, XOM, GOOGL.
Every successful symbol-year ZIP contains seven UTC CSVs: M5, M15, M30, H1, H4, D1, W1.
Fields: timestamp_utc; bid_open/high/low/close; ask_open/high/low/close; tick_count.
Prices are Exness CFD quotes and tick_count is NOT stock exchange trade volume.

| Symbol | 2025 source months | 2025 M5 rows | 2026 source months | 2026 M5 rows | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| NVDA | 12/12 | 29140 | 10/10 | 24216 | Both years collected |
| AMD | 12/12 | 29113 | 10/10 | 24448 | Both years collected |
| AVGO | 12/12 | 18148 | 10/10 | 15099 | Both years collected |
| GOOGL | 12/12 | 18148 | 10/10 | 15099 | Both years collected |
| XOM | 12/12 | 18148 | 10/10 | 15245 | Both years collected |
| SPCX | Not listed | 0 | 5/5 (June-Oct) | 17099 | First Exness quote at 2026-06-16 18:20 UTC |
| NIO | 0/12 | 0 | 0/10 | 0 | Public archive source returned HTTP 404 |
| XPEV | 0/12 | 0 | 0/10 | 0 | Public archive source returned HTTP 404 |
| LI | 0/12 | 0 | 0/10 | 0 | Public archive source returned HTTP 404 |

**Source:** `https://ticks.ex2archive.com/ticks/{symbol}/{year}/{month:02d}/Exness_{symbol}_{year}_{month:02d}.zip`

Each symbol/year has an independently auditable `*_manifest.json` with all month source URLs, rows, first/last timestamps and errors. ZIP archives exist only for successful symbol-years. 18 manifests and 11 seven-timeframe ZIP archives were saved by [the V22 GitHub Actions run](https://github.com/jcungko/make-money-research/actions/runs/43271110019).

**Backtesting cautions**
- A full set of monthly ZIPs does **not** prove every possible intraday market bar exists. Prices may have nontrading sessions and sparse quotation intervals; audit gaps before simulation.
- These are Bid/Ask quotes, not exchange trade prices, and do not contain true share volume.
- UTC aggregation is a chosen research convention; it does not necessarily reproduce Exness MT5 server timezone or its native D1/W1 open times.
- Weekly buckets at the start/end of a year, and at the initial SPCX listing, can be partial; exclude or reconstruct from adjacent-year data for any strategy based on completed weekly candles.
- NIO, XPEV and LI are MT5-only stock instruments according to Exness Help Center. Do not replace their unavailable Exness quotes with third-party stock exchange prices and label that data 'Exness'.
- No backtest has been performed, and this dataset alone does not establish profitability.
