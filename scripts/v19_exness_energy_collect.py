#!/usr/bin/env python3
"""V19: Exness public tick archives -> bid/ask OHLC for USOIL, UKOIL, XNGUSD.
Research-only. Never accesses brokerage accounts or places orders.
"""
import argparse
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v12_exness_collect as reader
import v17_exness_prepare as validator

SYMBOLS = ("USOIL", "UKOIL", "XNGUSD")
PERIODS = ("M5", "M15", "M30", "H1", "H4", "D1", "W1")


def aggregate(m5, freq):
    result = m5.resample(freq, closed="left", label="left").agg(reader.FIELDS)
    return result.loc[result["tick_count"] > 0]


def collect(symbol, year, outdir):
    if symbol not in SYMBOLS or year not in (2025, 2026):
        raise ValueError("Unsupported V19 symbol/year")
    start = pd.Timestamp(f"{year}-01-01T00:00:00Z")
    exclusive_end = pd.Timestamp("2026-11-01T00:00:00Z") if year == 2026 else pd.Timestamp("2026-01-01T00:00:00Z")
    last_month = 10 if year == 2026 else 12
    months = []
    fragments = []

    with requests.Session() as session:
        session.headers.update({"User-Agent": "V19-Exness-public-tick-research/1.0"})
        for month in range(1, last_month + 1):
            url, raw = reader.archive_bytes(session, symbol, year, month)
            if not zipfile.is_zipfile(io.BytesIO(raw)):
                raise ValueError(f"Not a ZIP: {url}")
            bars = reader.ticks_to_5m(raw, exclusive_end, start)
            if bars.empty:
                raise ValueError(f"Empty tick month: {url}")
            fragments.append(bars)
            months.append({
                "month": f"{year}-{month:02d}",
                "url": url,
                "archive_bytes": len(raw),
                "archive_sha256": hashlib.sha256(raw).hexdigest(),
                "m5_candles": len(bars),
                "first_tick_bucket_utc": bars.index.min().isoformat(),
                "last_tick_bucket_utc": bars.index.max().isoformat()
            })
            print(f"{symbol} {year}-{month:02d}: {len(bars):,} M5 / {len(raw):,} ZIP bytes", flush=True)

    if len(months) != last_month:
        raise RuntimeError("Incomplete monthly download")
    m5 = reader.merge_parts(fragments)
    m5 = m5[(m5.index >= start) & (m5.index < exclusive_end)]
    if m5.empty or m5.index.has_duplicates:
        raise ValueError("Empty or duplicate 5-minute source bars")
    frames = reader.build_frames(m5)
    daily = aggregate(m5, "1D")
    frames["D1"] = daily.loc[daily.index + pd.Timedelta(days=1) <= exclusive_end]
    weekly = aggregate(m5, "W-MON")
    # Keep only whole Monday-Sunday calendar weeks within the requested interval.
    frames["W1"] = weekly.loc[
        (weekly.index >= start) &
        (weekly.index + pd.Timedelta(days=7) <= exclusive_end)
    ]
    for tf in PERIODS:
        validator.check_bars(frames[tf], symbol, tf)

    meta = {
        "dataset": "V19 Exness energies",
        "source": "Exness publicly accessible archived Bid/Ask tick files",
        "source_variant": "unsuffixed / Standard",
        "symbol": symbol, "year": year,
        "start_inclusive_utc": start.isoformat(),
        "end_exclusive_utc": exclusive_end.isoformat(),
        "timezone": "UTC",
        "price_fields": [
            "bid_open", "bid_high", "bid_low", "bid_close",
            "ask_open", "ask_high", "ask_low", "ask_close", "tick_count"
        ],
        "weekly_rule": "W1 opens Monday 00:00 UTC; incomplete boundary weeks are excluded",
        "daily_rule": "D1 opens 00:00 UTC; only elapsed calendar days with ticks are retained",
        "note": "Market-closed periods have no candles. Tick count is quote count, not exchange trade volume. CFD rollover and trading schedule can affect prices.",
        "month_count": len(months),
        "months": months,
        "frames": {
            tf: {
                "rows": len(df),
                "first_utc": df.index.min().isoformat(),
                "last_utc": df.index.max().isoformat(),
                "tick_count_sum": int(df.tick_count.sum())
            } for tf, df in frames.items()
        },
        "assembled_utc": datetime.now(timezone.utc).isoformat()
    }
    outdir.mkdir(parents=True, exist_ok=True)
    archive = outdir / f"{symbol}_{year}_UTC_7TF.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for tf in PERIODS:
            csv_data = frames[tf].to_csv(index_label="timestamp_utc", float_format="%.6f")
            z.writestr(f"{symbol}_{tf}_{year}_UTC.csv", csv_data)
        z.writestr("manifest.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    (outdir / f"{symbol}_{year}_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (outdir / f"{symbol}_{year}_SHA256.txt").write_text(f"{digest}  {archive.name}\n")
    print("V19_DONE", json.dumps({
        "symbol": symbol, "year": year, "months": len(months),
        "timeframes": {tf: len(frames[tf]) for tf in PERIODS},
        "zip_bytes": archive.stat().st_size, "sha256": digest
    }), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=SYMBOLS, required=True)
    parser.add_argument("--year", choices=(2025, 2026), type=int, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/v19_energies"))
    args = parser.parse_args()
    collect(args.symbol, args.year, args.out)
