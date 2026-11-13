#!/usr/bin/env python3
"""V20: download and audit genuine Exness EURUSDm tick ZIP. No order/account APIs.

Monthly archives are kept byte-identical for reproducibility. No OHLC substitution.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
import zipfile

PIP = 0.0001
ROOT = 'https://ticks.ex2archive.com/ticks/EURUSDm'


def source_url(month: str, day: str | None = None) -> str:
    year, mon = month.split('-')
    if day:
        d = dt.date.fromisoformat(day)
        if d.strftime('%Y-%m') != month:
            raise ValueError('day and month mismatch')
        return f'{ROOT}/{year}/{mon}/{d.day:02d}/Exness_EURUSDm_{year}_{mon}_{d.day:02d}.zip'
    return f'{ROOT}/{year}/{mon}/Exness_EURUSDm_{year}_{mon}.zip'


def archive_name(month: str, day: str | None = None) -> str:
    return source_url(month, day).rsplit('/', 1)[-1]


def parse_utc_ms(ts: str) -> int:
    value = dt.datetime.fromisoformat(ts.strip().replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0):
        raise ValueError('timestamp must be explicitly UTC')
    if value.microsecond % 1000 != 0:
        raise ValueError('timestamp has sub-ms fractions: collector cannot silently round')
    return ((value.toordinal()-dt.datetime(1970,1,1).toordinal())*86400
            + value.hour*3600 + value.minute*60 + value.second)*1000 + value.microsecond//1000


def download(url: str, target: Path, tries: int=3, timeout: int=70):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix+'.part')
    errors = []
    for k in range(tries):
        tmp.unlink(missing_ok=True)
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'V20-Micro-Scalping-Research/1.0', 'Accept':'application/zip'})
            with urllib.request.urlopen(req, timeout=timeout) as response, tmp.open('wb') as f:
                if response.status != 200:
                    raise OSError(f'HTTP status {response.status}')
                while True:
                    chunk = response.read(1024*1024)
                    if not chunk: break
                    f.write(chunk)
            if tmp.stat().st_size < 1000 or not zipfile.is_zipfile(tmp):
                raise ValueError('downloaded bytes are too small or not a complete ZIP')
            tmp.replace(target)
            return {'downloaded_bytes': target.stat().st_size,'download_url':url}
        except Exception as e:
            errors.append(f'{type(e).__name__}: {e}')
            if k+1 < tries: time.sleep(min(2**k, 8))
    tmp.unlink(missing_ok=True)
    raise RuntimeError(f'Download failed after {tries} attempts: '+ ' | '.join(errors))


def quantile(values: list[float], fraction: float):
    if not values: return None
    values.sort()
    return round(values[round(fraction*(len(values)-1))], 5)


def audit_zip(path: Path, month: str, day: str | None=None, min_ticks=1000) -> dict:
    if not zipfile.is_zipfile(path): raise ValueError(f'bad or incomplete ZIP: {path}')
    start = parse_utc_ms((day or month+'-01') + 'T00:00:00.000Z')
    end = start+86400000 if day else parse_utc_ms((str((dt.date.fromisoformat(month+'-01').replace(day=28) + dt.timedelta(days=4)).replace(day=1)))+'T00:00:00.000Z')
    n=0; first=last=None; prev=None; invalid=0; duplicates=0; subsec=0
    close_delta_2=close_delta_100=close_delta_300=0
    max_gap_ms=0; gaps_gt_60s=0; gaps_gt_5m=0
    reservoir=[]; rng=random.Random(200613)
    head=[]; tail=[]
    with zipfile.ZipFile(path) as z:
        csv_files=[m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith('.csv')]
        if not csv_files: raise ValueError('ZIP contains no CSV')
        if len(csv_files)>32: raise ValueError('unexpectedly many CSV members')
        for f in csv_files:
            if f.file_size<100: continue
            with z.open(f) as binary:
                reader=csv.DictReader(io.TextIOWrapper(binary,encoding='utf-8-sig',newline=''))
                names=set(reader.fieldnames or [])
                if not {'Exness','Symbol','Timestamp','Bid','Ask'}.issubset(names):
                    raise ValueError(f'Missing header columns in {f.filename}: {names}')
                for row in reader:
                    try:
                        if row['Symbol'].strip() != 'EURUSDm':
                            raise ValueError('not EURUSDm quote')
                        ts=parse_utc_ms(row['Timestamp'])
                        bid=float(row['Bid']);ask=float(row['Ask'])
                        if not start<=ts<end:
                            raise ValueError('tick out of requested time interval')
                        if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask < 10):
                            raise ValueError('crossed/nonfinite/nonpositive quote')
                        if prev is not None and ts<prev:raise ValueError('out-of-order timestamp')
                        spread=(ask-bid)/PIP
                        if not math.isfinite(spread) or spread > 100:
                            raise ValueError('unreasonable spread >100 pips')
                    except Exception as ex:
                        invalid+=1
                        raise ValueError(f'Invalid tick row #{n+invalid} in {f.filename}: {ex}') from ex
                    if prev is not None:
                        gap=ts-prev;max_gap_ms=max(max_gap_ms,gap)
                        if gap<=2:close_delta_2+=1
                        if gap<=100:close_delta_100+=1
                        if gap<=300:close_delta_300+=1
                        if gap>60000:gaps_gt_60s+=1
                        if gap>300000:gaps_gt_5m+=1
                        if gap==0:duplicates+=1
                    prev=ts;last=ts;first=ts if first is None else first;n+=1
                    subsec+= int(ts % 1000 != 0)
                    if n<=3:head.append({'timestamp_utc':row['Timestamp'],'bid':bid,'ask':ask,'spread_pips':round(spread,5)})
                    if len(tail)==3:tail.pop(0)
                    tail.append({'timestamp_utc':row['Timestamp'],'bid':bid,'ask':ask,'spread_pips':round(spread,5)})
                    if len(reservoir)<10000:reservoir.append(spread)
                    else:
                        j=rng.randrange(n)
                        if j<len(reservoir):reservoir[j]=spread
    if n<min_ticks:raise ValueError(f'ONLY {n} valid ticks, minimum {min_ticks}')
    if subsec==0:raise ValueError('No sub-second timestamps; cannot test millisecond quote alignment')
    return {
        'status':'AUDITED','symbol':'EURUSDm','month':month,'day':day,
        'source_kind':'Exness historical indicative bid/ask tick archive, not execution records',
        'zip_filename':path.name,'zip_bytes':path.stat().st_size,
        'zip_sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),
        'csv_members':[x.filename for x in csv_files],
        'tick_count':n,'first_timestamp_ms':first,'last_timestamp_ms':last,
        'first_timestamp_utc':dt.datetime.fromtimestamp(first/1000,dt.timezone.utc).isoformat(),
        'last_timestamp_utc':dt.datetime.fromtimestamp(last/1000,dt.timezone.utc).isoformat(),
        'subsecond_timestamps':subsec,'subsecond_ratio':round(subsec/n,5),
        'timestamp_resolution_ms':1,'nondecreasing_time':True,
        'same_millisecond_adjacent_pairs':duplicates,
        'successive_tick_pairs_le_2ms':close_delta_2,
        'successive_tick_pairs_le_100ms':close_delta_100,
        'successive_tick_pairs_le_300ms':close_delta_300,
        'max_gap_s':round(max_gap_ms/1000,3),'gaps_gt_60s':gaps_gt_60s,'gaps_gt_5min':gaps_gt_5m,
        'spread_pips_approx_quantiles_from_reservoir_10000':{'min':quantile(reservoir.copy(),0),
          'p50':quantile(reservoir.copy(),0.5),'p95':quantile(reservoir.copy(),0.95),
          'p99':quantile(reservoir.copy(),0.99),'max':quantile(reservoir.copy(),1)},
        'sample_first_quotes':head,'sample_last_quotes':tail,
        'validation_notes':['Quotes may be sparse despite 1ms timestamp notation',
                            '2ms/100ms/300ms checks describe hypothetical quote observation only',
                            'Do not infer broker execution speed from quote timestamp precision',
                            'Large market closures/weekends are not treated as corrupt price gaps']
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--month',required=True,help='YYYY-MM')
    p.add_argument('--day',help='YYYY-MM-DD (current-month data only)')
    p.add_argument('--out',type=Path,default=Path('v20_exness_data'))
    p.add_argument('--tries',type=int,default=3)
    p.add_argument('--local',type=Path,help='Audit an existing, genuinely downloaded source ZIP, never synthetic')
    a=p.parse_args()
    try:
        dt.date.fromisoformat(a.month+'-01')
        if a.day: dt.date.fromisoformat(a.day)
        url=source_url(a.month,a.day)
        a.out.mkdir(parents=True,exist_ok=True)
        path=a.local or a.out/archive_name(a.month,a.day)
        result={'download_url':url,'source_from_local':bool(a.local)}
        if not a.local: result.update(download(url,path,a.tries))
        report={**result,**audit_zip(path,a.month,a.day)}
        dest=a.out/f'audit_{a.day.replace("-","_") if a.day else a.month.replace("-","_")}.json'
        dest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps({'status':'AUDITED','month':a.month,'day':a.day,
                          'ticks':report['tick_count'],'spread':report['spread_pips_approx_quantiles_from_reservoir_10000'],
                          'max_gap_s':report['max_gap_s'],'source_sha':report['zip_sha256'],
                          'artifact':str(path),'audit':str(dest)},ensure_ascii=False),flush=True)
        return 0
    except Exception as e:
        a.out.mkdir(parents=True,exist_ok=True)
        (a.out/f'failure_{a.day.replace("-","_") if a.day else a.month.replace("-","_")}.json').write_text(json.dumps({
            'status':'DATA_ERROR','month':a.month,'day':a.day,'requested_url':source_url(a.month,a.day),
            'error_type':type(e).__name__,'error':str(e),'tick_backtest_status':'NOT_RUN'},indent=2)+'\n')
        print(f'V20 COLLECTION FAILED {type(e).__name__}: {e}',file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())