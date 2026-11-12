#!/usr/bin/env python3
"""V17: pack independently sourced Exness 2026 bid/ask candles into 7 UTC frames.
Research only. Never connects to MT5, brokerage, keys, or trading endpoints.
"""
import argparse
import io
import json
import zipfile
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

FRAMES = ('M5', 'M15', 'M30', 'H1', 'H4')
COLS = ('bid_open','bid_high','bid_low','bid_close',
        'ask_open','ask_high','ask_low','ask_close','tick_count')
AGG = {
    'bid_open':'first','bid_high':'max','bid_low':'min','bid_close':'last',
    'ask_open':'first','ask_high':'max','ask_low':'min','ask_close':'last',
    'tick_count':'sum'
}

def check_bars(frame, symbol, timeframe):
    if frame.empty or frame.index.tz is None:
        raise ValueError(f'{symbol} {timeframe}: empty data or non-UTC timestamps')
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f'{symbol} {timeframe}: duplicate or unsorted timestamps')
    if not all(c in frame for c in COLS):
        raise ValueError(f'{symbol} {timeframe}: missing required columns')
    if frame[list(COLS)].isna().any().any():
        raise ValueError(f'{symbol} {timeframe}: NaN values')
    for side in ('bid', 'ask'):
        if ((frame[f'{side}_high'] < frame[[f'{side}_open',f'{side}_close',f'{side}_low']].max(axis=1)) |
            (frame[f'{side}_low'] > frame[[f'{side}_open',f'{side}_close']].min(axis=1))).any():
            raise ValueError(f'{symbol} {timeframe}: OHLC invariant failed')
    if (frame['bid_close'] > frame['ask_close']).any() or (frame['tick_count'] <= 0).any():
        raise ValueError(f'{symbol} {timeframe}: crossed quotes or zero ticks')

def load_csv(path):
    out = pd.read_csv(path, index_col=0, parse_dates=[0])
    out.index = pd.DatetimeIndex(pd.to_datetime(out.index, utc=True), name='timestamp_utc')
    return out

def build_from_m5(m5, freq, first_full=None):
    bars = m5.resample(freq, label='left', closed='left').agg(AGG)
    bars = bars.loc[bars.tick_count > 0].copy()
    if first_full is not None:
        bars = bars.loc[bars.index >= first_full]
    # A bucket is complete only if the M5 source reaches the calendar boundary.
    # This deliberately omits the latest potentially partial daily/weekly candle.
    cutoff = m5.index.max() + pd.Timedelta(minutes=5)
    bar_end = bars.index + (pd.Timedelta(days=1) if freq == '1D' else pd.Timedelta(days=7))
    return bars.loc[bar_end <= cutoff]

def pack(symbol, root, outdir, run_id, year):
    found = list(root.rglob(f'{symbol}_M5_{year}_UTC.csv.gz'))
    if len(found) != 1:
        raise ValueError(f'{symbol}: expected one M5 archive, found {len(found)}')
    folder = found[0].parent
    source_manifest = folder / f'{symbol}_manifest.json'
    if not source_manifest.is_file():
        raise ValueError(f'{symbol}: missing V12 provenance manifest')
    provenance = json.loads(source_manifest.read_text(encoding='utf-8'))
    if provenance.get('symbol') != symbol or provenance.get('year') != year:
        raise ValueError(f'{symbol}: inconsistent source provenance')
    if not provenance.get('complete_monthly_download') or provenance.get('errors'):
        raise ValueError(f'{symbol}: upstream monthly archive incomplete; check V12 manifest')

    raw = {}
    for tf in FRAMES:
        p = folder / f'{symbol}_{tf}_{year}_UTC.csv.gz'
        if not p.is_file():
            raise ValueError(f'{symbol}: missing {tf} source frame')
        raw[tf] = load_csv(p)
        check_bars(raw[tf], symbol, tf)
    m5 = raw['M5']
    day = build_from_m5(m5, '1D')
    first_monday = m5.index.min().normalize()
    if first_monday.weekday() != 0:
        first_monday += pd.Timedelta(days=7-first_monday.weekday())
    week = build_from_m5(m5, 'W-MON', first_monday)
    check_bars(day, symbol, 'D1')
    check_bars(week, symbol, 'W1')
    raw['D1'], raw['W1'] = day, week

    meta = {
        'version':'V17', 'symbol':symbol, 'price_source':'Exness publicly archived ticks',
        'price_type':'bid_and_ask', 'timezone':'UTC', 'year':year,
        'source_v12_workflow_run_id':run_id,
        'source_months':provenance.get('months',[]),
        'source_cutoff_utc':provenance.get('last_complete_candle_cutoff_exclusive_utc'),
        'note':'D1 and W1 derived from M5 using UTC calendar, weekly Monday 00 UTC; latest partial daily/weekly bucket excluded. Forex market holidays/weekends remain gaps. M5-H4 retain original V12 bars.',
        'frames':{
            tf:{'rows':len(bars),
                'first':bars.index.min().isoformat(),
                'last':bars.index.max().isoformat()}
            for tf,bars in raw.items()
        },
        'assembled_at_utc':datetime.now(timezone.utc).isoformat()
    }
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / f'{symbol}_{year}_UTC_7TF.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for tf, bars in raw.items():
            # UTF-8 CSV with timestamp_utc index, all nine bid/ask + tick_count fields.
            payload = bars.to_csv(index_label='timestamp_utc',float_format='%.6f')
            z.writestr(f'{symbol}_{tf}_{year}_UTC.csv',payload)
        z.writestr('manifest.json',json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    (outdir / f'{symbol}_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'symbol':symbol, 'zip':str(target), 'bytes':target.stat().st_size,
                      'frames':{k:v['rows'] for k,v in meta['frames'].items()}},ensure_ascii=False),flush=True)

if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--input',required=True,type=Path)
    cli.add_argument('--out',default='data/v17_exness_2026',type=Path)
    cli.add_argument('--run-id',type=int,default=42964857297)
    cli.add_argument('--year',type=int,choices=[2025,2026],default=2026)
    args = cli.parse_args()
    for s in ('EURUSD','USDJPY','GBPUSD'):
        pack(s,args.input,args.out,args.run_id,args.year)
