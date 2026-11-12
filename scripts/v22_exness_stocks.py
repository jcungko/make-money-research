#!/usr/bin/env python3
"""V22 Exness public stock ticks -> seven UTC bid/ask OHLC timeframes. Research-only."""
import argparse, io, json, time, zipfile
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import requests
from v12_exness_collect import ticks_to_5m, merge_parts, build_frames, FIELDS

SYMBOLS = ('NVDA','NIO','AMD','AVGO','SPCX','XPEV','LI','XOM','GOOGL')

def fetch(session, symbol, year, month):
    url = f'https://ticks.ex2archive.com/ticks/{symbol}/{year}/{month:02d}/Exness_{symbol}_{year}_{month:02d}.zip'
    for attempt in range(3):
        try:
            r = session.get(url,timeout=(12,120))
            if r.status_code in (400,403,404,410):
                return url, None, f'HTTP {r.status_code}'
            r.raise_for_status()
            data=r.content
            if not zipfile.is_zipfile(io.BytesIO(data)):
                raise ValueError('Invalid ZIP')
            return url,data,None
        except (requests.RequestException,ValueError) as exc:
            if attempt==2:
                return url,None,f'{type(exc).__name__}: {str(exc)[:170]}'
            time.sleep(attempt+1)

def frames_from_m5(m5,start,end):
    result=build_frames(m5)
    result['D1']=m5.resample('1D',label='left',closed='left').agg(FIELDS)
    result['W1']=m5.resample('W-MON',label='left',closed='left').agg(FIELDS)
    return {k:v.loc[(v.tick_count>0)&(v.index>=start)&(v.index<end)].copy() for k,v in result.items()}

def validate(frame,label):
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f'{label}: empty, duplicate or unordered')
    if frame[list(FIELDS)].isna().any().any() or not (frame.tick_count>0).all():
        raise ValueError(f'{label}: missing values or zero ticks')
    for side in ('bid','ask'):
        op,hi,lo,cl=[frame[f'{side}_{key}'] for key in ('open','high','low','close')]
        if ((hi<op)|(hi<cl)|(hi<lo)|(lo>op)|(lo>cl)).any():
            raise ValueError(f'{label}: OHLC violation')
    if (frame.bid_close>frame.ask_close).any():
        raise ValueError(f'{label}: Bid higher than Ask')

def collect(symbol,year,output):
    start=pd.Timestamp(f'{year}-01-01T00:00:00Z')
    end=pd.Timestamp('2026-11-01T00:00:00Z') if year==2026 else pd.Timestamp('2026-01-01T00:00:00Z')
    expected=list(range(1,11 if year==2026 else 13))
    excluded=[]
    if symbol=='SPCX':
        excluded=expected if year==2025 else [m for m in expected if m<6]
    expected=[m for m in expected if m not in excluded]
    meta=dict(version='V22',symbol=symbol,year=year,source='Exness public tick archive',
        timezone='UTC',price_types=['bid','ask'],volume_type='tick_count (not exchange shares)',
        start_inclusive=start.isoformat(),end_exclusive=end.isoformat(),
        timeframes=['M5','M15','M30','H1','H4','D1','W1'],
        expected_months=expected,prelisting_months_excluded=excluded,
        downloaded_months=[],missing_months=[],frames={})
    output.mkdir(parents=True,exist_ok=True)
    parts=[]
    with requests.Session() as session:
        session.headers['User-Agent']='V22-Public-Exness-Research/1.0'
        for month in expected:
            url,data,error=fetch(session,symbol,year,month)
            if error:
                meta['missing_months'].append(dict(month=month,url=url,error=error))
                print('MISSING',symbol,year,month,error,flush=True)
                continue
            try:
                m5=ticks_to_5m(data,end,start)
                if m5.empty: raise ValueError('No valid ticks')
                parts.append(m5)
                meta['downloaded_months'].append(dict(month=month,url=url,zip_bytes=len(data),
                    m5_rows=len(m5),first=m5.index.min().isoformat(),last=m5.index.max().isoformat()))
                print('OK',symbol,year,month,len(m5),flush=True)
            except Exception as exc:
                meta['missing_months'].append(dict(month=month,url=url,error=f'{type(exc).__name__}: {str(exc)[:180]}'))
                print('INVALID',symbol,year,month,str(exc),flush=True)
    if parts:
        try:
            frames=frames_from_m5(merge_parts(parts),start,end)
            for tf,bars in frames.items():
                validate(bars,tf)
                meta['frames'][tf]=dict(rows=len(bars),first=bars.index.min().isoformat(),last=bars.index.max().isoformat())
            target=output/f'{symbol}_{year}_UTC_7TF.zip'
            with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                for tf,bars in frames.items():
                    z.writestr(f'{symbol}_{tf}_{year}_UTC.csv',bars.to_csv(index_label='timestamp_utc',float_format='%.6f'))
            meta['archive']=target.name
            meta['archive_bytes']=target.stat().st_size
        except Exception as exc:
            meta['processing_error']=f'{type(exc).__name__}: {str(exc)[:180]}'
    meta['status']=('complete' if expected and len(meta['downloaded_months'])==len(expected) and len(meta['frames'])==7
        else 'not_applicable' if not expected else 'partial' if meta['frames'] else 'unavailable')
    meta['generated_at_utc']=datetime.now(timezone.utc).isoformat()
    (output/f'{symbol}_{year}_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    print('RESULT',json.dumps(dict(symbol=symbol,year=year,status=meta['status'],months=len(meta['downloaded_months']),
       missing=len(meta['missing_months']),frames={k:v['rows'] for k,v in meta['frames'].items()})),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--symbol',required=True,choices=SYMBOLS)
    p.add_argument('--year',required=True,type=int,choices=(2025,2026))
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    collect(a.symbol,a.year,a.out)
