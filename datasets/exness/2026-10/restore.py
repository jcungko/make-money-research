#!/usr/bin/env python3
"""Restore and verify the 14 October 2026 Exness M1/M5 candle CSV files."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

folder = Path(__file__).resolve().parent
manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
out_dir = folder / "restored_csv"
out_dir.mkdir(exist_ok=True)
verified = 0

for symbol_info in manifest["symbols"]:
    symbol = symbol_info["symbol"]
    for tf in ("M1", "M5"):
        info = symbol_info[tf]
        encoded = (folder / f"{symbol}_{tf}.csv.gz.base64").read_text(encoding="ascii")
        payload = base64.b64decode(encoded.strip(), validate=True)
        actual = hashlib.sha256(payload).hexdigest()
        if len(payload) != info["gzip_bytes"] or actual != info["gzip_sha256"]:
            raise ValueError(f"{symbol} {tf}: compressed file size or SHA-256 mismatch")
        csv_bytes = gzip.decompress(payload)
        rows = csv_bytes.count(b"\n") - 1
        if rows != info["rows"]:
            raise ValueError(f"{symbol} {tf}: {rows} rows, expected {info['rows']}")
        path = out_dir / f"{symbol}_{tf}_2026-10.csv"
        path.write_bytes(csv_bytes)
        print(f"PASS {symbol} {tf}: {rows:,} candles -> {path}")
        verified += 1

if verified != 14:
    raise RuntimeError(f"Unexpected number of candle files: {verified}")
print("SUCCESS: all 14 candle files verified and extracted.")
