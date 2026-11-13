#!/usr/bin/env python3
"""Build Exness EURUSD UTC M1/M5 October 2026 from archived Bid/Ask ticks.

Research-only extraction. No credentials, live orders, strategy testing or execution.
"""
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

URL = "https://ticks.ex2archive.com/ticks/EURUSD/2026/10/Exness_EURUSD_2026_10.zip"
START = pd.Timestamp("2026-10-01T00:00:00Z")
END = pd.Timestamp("2026-11-01T00:00:00Z")
OUT = Path("data/exness/EURUSD_2026_10_M1_M5")
AGG = {
    "bid_open": "first", "bid_high": "max", "bid_low": "min", "bid_close": "last",
    "ask_open": "first", "ask_high": "max", "ask_low": "min", "ask_close": "last",
    "spread_open_pips": "first", "spread_close_pips": "last",
    "spread_min_pips": "min", "spread_max_pips": "max",
    "tick_count": "sum",
}

def aggregate_ticks(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        csv_members = sorted(m for m in source.namelist() if m.lower().endswith(".csv"))
        if not csv_members:
            raise ValueError("No CSV members in Exness ZIP")
        parts = []
        seen = 0
        clean = 0
        crossed = 0
        null_rows = 0
        out_of_period = 0
        first = None
        last = None
        prev = None
        for member in csv_members:
            with source.open(member) as stream:
                for chunk in pd.read_csv(stream, usecols=["Timestamp", "Bid", "Ask"],
                                         dtype={"Bid": "float64", "Ask": "float64"},
                                         chunksize=250000):
                    seen += len(chunk)
                    ts = pd.to_datetime(chunk["Timestamp"], utc=True, errors="coerce", format="ISO8601")
                    good = ts.notna() & chunk["Bid"].notna() & chunk["Ask"].notna()
                    null_rows += int((~good).sum())
                    in_month = (ts >= START) & (ts < END)
                    out_of_period += int((good & ~in_month).sum())
                    valid = good & in_month
                    if not valid.any():
                        continue
                    time = pd.DatetimeIndex(ts.loc[valid])
                    if not time.is_monotonic_increasing or (prev is not None and time[0] < prev):
                        raise ValueError("Original tick timestamps are out of order")
                    prev = time[-1]
                    first = time[0] if first is None else first
                    last = time[-1]
                    c = chunk.loc[valid, ["Bid", "Ask"]].copy()
                    crossed += int((c["Ask"] < c["Bid"]).sum())
                    clean += len(c)
                    c["spread_pips"] = (c["Ask"] - c["Bid"]) * 10000
                    c.index = time.floor("min")
                    by = c.groupby(level=0, sort=True).agg(
                        bid_open=("Bid", "first"), bid_high=("Bid", "max"),
                        bid_low=("Bid", "min"), bid_close=("Bid", "last"),
                        ask_open=("Ask", "first"), ask_high=("Ask", "max"),
                        ask_low=("Ask", "min"), ask_close=("Ask", "last"),
                        spread_open_pips=("spread_pips", "first"),
                        spread_close_pips=("spread_pips", "last"),
                        spread_min_pips=("spread_pips", "min"),
                        spread_max_pips=("spread_pips", "max"),
                        tick_count=("Bid", "size"),
                    )
                    parts.append(by)
        if not parts:
            raise ValueError("No usable EURUSD ticks in requested month")
        m1 = pd.concat(parts).groupby(level=0, sort=True).agg(AGG)
        m1.index.name = "timestamp_utc"
        return m1, {
            "zip_csv_members": csv_members, "tick_rows_read": seen,
            "tick_rows_used": clean, "invalid_tick_rows": null_rows,
            "out_of_month_rows": out_of_period, "crossed_quote_ticks": crossed,
            "first_tick_utc": first.isoformat(), "last_tick_utc": last.isoformat(),
        }

def check(bars, label):
    if bars.empty or not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise AssertionError(label + ": missing/unsorted/duplicate candles")
    if bars.index.tz is None or bars.index.min() < START or bars.index.max() >= END:
        raise AssertionError(label + ": timestamps outside UTC month")
    if (bars["tick_count"] <= 0).any() or bars.isna().any().any():
        raise AssertionError(label + ": invalid tick count / missing values")
    for side in ("bid", "ask"):
        if ((bars[f"{side}_high"] < bars[[f"{side}_open",f"{side}_close",f"{side}_low"]].max(axis=1)) |
            (bars[f"{side}_low"] > bars[[f"{side}_open",f"{side}_close"]].min(axis=1))).any():
            raise AssertionError(label + ": OHLC invariant violation")

def main():
    response = requests.get(URL, timeout=(30, 240))
    response.raise_for_status()
    payload = response.content
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError("Exness response was not a valid ZIP")
    m1, audit = aggregate_ticks(payload)
    m5 = m1.resample("5min", closed="left", label="left").agg(AGG)
    m5 = m5.loc[m5["tick_count"] > 0].copy()
    for label, frame in (("M1", m1), ("M5", m5)):
        check(frame, label)
    if int(m1["tick_count"].sum()) != audit["tick_rows_used"] or int(m5["tick_count"].sum()) != audit["tick_rows_used"]:
        raise AssertionError("M1/M5 source tick totals do not reconcile")
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / "EURUSD_2026_10_M1_M5_UTC.zip"
    bar_info = {}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for label, frame in (("M1",m1),("M5",m5)):
            csv = frame.to_csv(index_label="timestamp_utc", float_format="%.6f")
            blob = csv.encode("utf-8")
            out.writestr(f"EURUSD_2026_10_{label}_UTC.csv", blob)
            bar_info[label] = {"count": len(frame), "first_utc": frame.index.min().isoformat(),
                               "last_utc": frame.index.max().isoformat(),
                               "csv_sha256": hashlib.sha256(blob).hexdigest()}
    daily = []
    for day, group in m1.groupby(m1.index.strftime("%Y-%m-%d")):
        day5 = m5.loc[m5.index.strftime("%Y-%m-%d") == day]
        daily.append({"utc_date":day,"m1_bars":len(group),"m5_bars":len(day5),
                      "ticks":int(group["tick_count"].sum())})
    manifest = {
        "symbol": "EURUSD", "account_price_variant": "no suffix (not EURUSDm)",
        "provider": "Exness public tick history", "source_url": URL,
        "source_zip_sha256": hashlib.sha256(payload).hexdigest(),
        "source_zip_bytes": len(payload),
        "requested_period_utc": ["2026-10-01T00:00:00Z","2026-11-01T00:00:00Z"],
        "source_fields": ["Timestamp","Bid","Ask"], "timezone": "UTC",
        "aggregation": "first/high/low/last over observed ticks; empty no-quote minutes omitted; M5 from M1",
        "pip_size": 0.0001, "audit": audit, "frames": bar_info,
        "prior_v17_M5_count_oct2026": 6285,
        "M5_count_matches_prior_manifest": len(m5) == 6285,
        "daily_utc": daily, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "warnings": ["Exness price indications are not proof of MT5 execution quality or fills.",
                     "No-price windows are not filled with synthetic candles.",
                     "UTC timestamps may differ from broker-server chart labels."]
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"frames":bar_info, "audit":audit,
                      "matches_prior_M5":manifest["M5_count_matches_prior_manifest"]}, ensure_ascii=False), flush=True)
if __name__ == "__main__":
    main()
