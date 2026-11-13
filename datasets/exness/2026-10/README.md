# Project X — Exness tick-derived M1/M5 candles, October 2026

This isolated Git branch stores **14** historical candle datasets (7 trading symbols × 2 timeframes). The ongoing automation on the repository's main branch is not changed.

- UTC range: 2026-10-01 through 2026-10-31.
- Instruments: EURUSD, GBPUSD, USDJPY (not JPYUSD), DXY, XAGUSD, XAUUSD, BTCUSD.
- Raw data: Exness-labelled Bid/Ask monthly tick ZIPs on the public **third-party** archive \`https://ticks.ex2archive.com/\`. They have not yet been independently reconciled with an official Exness tick-history download.
- This export uses **unsuffixed** instruments rather than Exness Standard symbols ending in \`m\`. Broker/account feeds may differ.
- Candle construction: no fill of minutes without ticks; original Bid/Ask quote data aggregated to bid and ask OHLC. Fields also include tick count, arithmetic mean quote spread, first/last tick times.
- Source and output hashes and row counts: [manifest.json](manifest.json).

## Restore CSV datasets

The files named \`*.csv.gz.base64\` are base64-encoded compressed CSV files, stored in text form.

Clone/download **this branch** and run:

\`\`\`sh
python datasets/exness/2026-10/restore.py
\`\`\`

The script validates SHA-256 and produces 14 ordinary CSV files in \`datasets/exness/2026-10/restored_csv/\`.

These price quotes are indicative, not a guarantee of actual fills, slippage, commissions or future performance. Avoid look-ahead and include spread and execution costs in all backtests.
