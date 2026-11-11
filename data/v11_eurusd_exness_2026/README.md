# V11 EURUSD — Exness 2026 candles (tick-derived)

Source: [Exness Tick History](https://www.exness.global/tick-history/); public EURUSD (no suffix) quote ZIP archives, UTC timestamps, Bid and Ask. Archives for Jan–Nov 2026 were downloaded. November's monthly ZIP ended Nov 9; the separate Nov 10 and Nov 11 daily ZIPs were merged to extend coverage to 2026-11-11 01:15 UTC = 08:15 Vietnam time. This is a time-limited snapshot; 2026 is not complete.

## Timeframes and counts

| Frame | Candles |
| --- | ---: |
| M5 | 64,177 |
| M15 | 21,420 |
| M30 | 10,711 |
| H1 | 5,356 |
| H4 | 1,385 |

Each `Exness_EURUSD_2026_MM_multiTF.csv.gz` file contains all five frames for one UTC calendar month in a gzip-compressed CSV. Columns:
`timeframe,time_utc,open_bid,high_bid,low_bid,close_bid,open_ask,high_ask,low_ask,close_ask,tick_volume,mean_spread_pips`.

Price fields have 5 decimal places. `time_utc` is candle **start**, e.g. `2026-03-02 12:00`. Add 7 hours for Vietnam local time. H4 is grouped at **UTC 00, 04, 08, 12, 16, 20** hours, which may differ from the Exness MT5 server's H4 boundaries. M5/M15/M30/H1 are also UTC-anchored.

`tick_volume` is the number of source ticks in the candle (not traded volume). `mean_spread_pips` is the arithmetic mean of (Ask - Bid) × 10,000 across source ticks in that candle. The first/last candles of the overall data range may be incomplete.

Exness states tick history is indicative, and trading servers' prices may differ slightly. Use dedicated Exness MT5 server history when exact matching to a specific account is needed. This dataset is intended for research and backtesting, not proof of executable fills.

## Reading in Python

```python
from pathlib import Path
import pandas as pd

files = sorted(Path("data/v11_eurusd_exness_2026").glob("Exness_EURUSD_2026_*_multiTF.csv.gz"))
data = pd.concat([pd.read_csv(p, compression="gzip") for p in files], ignore_index=True)
m5 = data[data["timeframe"] == "M5"].copy()
m5["time_utc"] = pd.to_datetime(m5["time_utc"], utc=True)
m5["time_vn"] = m5["time_utc"].dt.tz_convert("Asia/Ho_Chi_Minh")
```

`manifest.json` lists individual files and row counts.
