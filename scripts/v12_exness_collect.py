#!/usr/bin/env python3
"""V12: Collect Exness public 2026 tick archives and build UTC bid/ask OHLC bars.
Read-only research; no trading endpoints, accounts, tokens, or credentials.
"""
import argparse
import io
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

FRAMES = {'M5':'5min','M15':'15min','M30':'30min','H1':'1h','H4':'4h'}
FIELDS = {'bid_open':'first','bid_high':'max','bid_low':'min','bid_close':'last',
          'ask_open':'first','ask_high':'max','ask_low':'min','ask_close':'last',
          'tick_count':'sum'}


def archive_bytes(session, symbol, year, month):
    source = f'https://ticks.ex2archive.com/ticks/{symbol}/{year}/{month:02d}/Exness_{symbol}_{year}_{month:02d}.zip'
    for attempt in range(4):
        try:
            r = session.get(source, timeout=(20, 180))
            r.raise_for_status()
            if not zipfile.is_zipfile(io.BytesIO(r.content)):
                raise ValueError('Received payload is not a valid ZIP')
            return source, r.content
        except (requests.RequestException, ValueError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def ticks_to_5m(zipped, cutoff, start):
    parts = []
    with zipfile.ZipFile(io.BytesIO(zipped)) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith('.csv')]
        if not members:
            raise ValueError('ZIP contains no CSV')
        for member in members:
            with zf.open(member) as src:
                for chunk in pd.read_csv(src, usecols=['Timestamp','Bid','Ask'], chunksize=250_000,
                                         dtype={'Bid':'float64', 'Ask':'float64'}, low_memory=False):
                    ts = pd.to_datetime(chunk['Timestamp'], utc=True, errors='coerce', format='ISO8601')
                    valid = (ts >= start) & (ts < cutoff) & chunk['Bid'].notna() & chunk['Ask'].notna()
                    if not valid.any():
                        continue
                    c = chunk.loc[valid, ['Bid','Ask']].copy()
                    c.index = ts.loc[valid].dt.floor('5min')
                    g = c.groupby(level=0, sort=True).agg(
                        bid_open=('Bid','first'), bid_high=('Bid','max'), bid_low=('Bid','min'), bid_close=('Bid','last'),
                        ask_open=('Ask','first'), ask_high=('Ask','max'), ask_low=('Ask','min'), ask_close=('Ask','last'),
                        tick_count=('Bid','size'))
                    parts.append(g)
    if not parts:
        return pd.DataFrame(columns=list(FIELDS)).rename_axis('timestamp_utc')
    return pd.concat(parts).groupby(level=0,sort=True).agg(FIELDS).rename_axis('timestamp_utc')


def merge_parts(bars):
    return pd.concat(bars).sort_index(kind='stable').groupby(level=0,sort=True).agg(FIELDS).rename_axis('timestamp_utc')


def build_frames(m5):
    frames = {'M5':m5}
    for label, freq in FRAMES.items():
        if label == 'M5':
            continue
        g = m5.resample(freq, label='left', closed='left', origin='epoch').agg(FIELDS)
        frames[label] = g.loc[g['tick_count'] > 0]
    return frames


def collect(symbol, year, output):
    start = pd.Timestamp(f'{year}-01-01T00:00:00Z')
    current = pd.Timestamp(datetime.now(timezone.utc) - timedelta(minutes=10)).floor('5min')
    cutoff = min(current, pd.Timestamp(f'{year+1}-01-01T00:00:00Z'))
    if cutoff <= start:
        raise ValueError('Year is not yet available')
    end_month = 12 if cutoff.year > year else cutoff.month
    output.mkdir(parents=True, exist_ok=True)
    info = dict(symbol=symbol, year=year, source='Exness public tick history (standard no-suffix symbol)',
                url_pattern='https://ticks.ex2archive.com/ticks/{symbol}/{year}/{month:02d}/Exness_{symbol}_{year}_{month:02d}.zip',
                price_types=['bid','ask'], timezone='UTC', timeframes=list(FRAMES),
                last_complete_candle_cutoff_exclusive_utc=cutoff.isoformat(), months=[], errors=[], bars={})
    fragments = []
    with requests.Session() as session:
        for month in range(1, end_month + 1):
            try:
                url, data = archive_bytes(session, symbol, year, month)
                bars = ticks_to_5m(data, cutoff, start)
                if bars.empty:
                    raise ValueError('No valid prices were found')
                fragments.append(bars)
                info['months'].append(dict(month=month,url=url,zip_bytes=len(data),m5_bars=len(bars),
                                           first_utc=bars.index.min().isoformat(),last_utc=bars.index.max().isoformat()))
                print(f'{symbol} {year}-{month:02d}: {len(bars)} M5 candles from {len(data)} ZIP bytes', flush=True)
            except Exception as exc:
                error=f'{symbol} {year}-{month:02d}: {type(exc).__name__}: {str(exc)[:300]}'
                info['errors'].append(error)
                print('ERROR', error, flush=True)
    if fragments:
        bars = build_frames(merge_parts(fragments))
        for label, frame in bars.items():
            path = output / f'{symbol}_{label}_{year}_UTC.csv.gz'
            frame.to_csv(path, compression='gzip', float_format='%.6f')
            info['bars'][label] = dict(count=len(frame), path=path.name,
                                       first_utc=frame.index.min().isoformat(), last_utc=frame.index.max().isoformat())
    info['complete_monthly_download'] = not info['errors'] and len(info['months']) == end_month
    info['created_at_utc'] = datetime.now(timezone.utc).isoformat()
    (output / f'{symbol}_manifest.json').write_text(json.dumps(info,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('RESULT',json.dumps({'symbol':symbol,'complete':info['complete_monthly_download'],
                               'months':len(info['months']),'bars':info['bars'],'errors':info['errors']}),flush=True)
    if not info['complete_monthly_download']:
        raise RuntimeError('Partial data only: see manifest errors')


def self_test():
    import csv
    raw = io.StringIO()
    w = csv.writer(raw)
    w.writerow(['Exness','Symbol','Timestamp','Bid','Ask'])
    for second,bid in [(0,1.1000),(60,1.1010),(300,1.1020),(600,1.1030),(900,1.1040)]:
        t = pd.Timestamp('2026-01-01T00:00:00Z') + pd.Timedelta(seconds=second)
        w.writerow(['exness','EURUSD',t.isoformat().replace('+00:00','Z'),bid,bid+0.0002])
    z = io.BytesIO()
    with zipfile.ZipFile(z,'w') as out:
        out.writestr('ticks.csv',raw.getvalue())
    m5 = ticks_to_5m(z.getvalue(),pd.Timestamp('2026-01-02T00:00:00Z'),pd.Timestamp('2026-01-01T00:00:00Z'))
    assert len(m5)==4 and m5.iloc[0].bid_open==1.1 and m5.iloc[0].bid_close==1.101
    assert m5.iloc[0].tick_count==2 and len(build_frames(m5)['M15'])==2
    print('SELFTEST PASS')


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--symbol',choices=['EURUSD','USDJPY','GBPUSD'])
    p.add_argument('--year',type=int,default=2026)
    p.add_argument('--out',default='v12_exness_data')
    p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    if a.self_test:
        self_test()
    else:
        if not a.symbol: p.error('--symbol required')
        collect(a.symbol,a.year,Path(a.out))
