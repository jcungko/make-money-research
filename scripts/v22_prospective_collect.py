#!/usr/bin/env python3
"""Collect unopened, CLOSED Exness EURUSDm daily Bid/Ask ZIPs after frozen V22 registration.
Read-only; no price labels, backtest, model fit, account access, credentials, or trade orders.
Data must later be independently designated prospectively before analysis.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,re,sys,zipfile
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from collections import Counter
import requests

MIN_DATE=date(2026,11,14)

def validate_requested_day(value:str,now_utc:datetime|None=None)->date:
    day=date.fromisoformat(value)
    today=(now_utc or datetime.now(timezone.utc)).date()
    if day<MIN_DATE:raise ValueError(f'V22 prospective collector forbids dates before {MIN_DATE}')
    if day>=today:raise ValueError('Do not collect an unfinished current or future UTC date')
    return day

def inspect_zip(raw:bytes,day:date):
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError('Incomplete or invalid ZIP: reject, do not recover partial rows')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        bad=z.testzip()
        if bad:raise ValueError('ZIP CRC failure: '+bad)
        csv_files=[n for n in z.namelist() if n.lower().endswith('.csv') and '..' not in n]
        if len(csv_files)!=1:raise ValueError('Expected exactly one CSV inside source archive')
        with z.open(csv_files[0]) as f:
            data=io.TextIOWrapper(f,encoding='utf-8-sig',newline='')
            # Exness historical monthly ZIPs often include CSV headers, while daily
            # snapshots can use headerless [provider,symbol,timestamp,bid,ask].
            # Inspect the first record and parse BOTH explicitly, never skip one.
            import itertools
            rdr=csv.reader(data)
            first=next(rdr,None)
            if first is None:raise ValueError('Empty CSV')
            if {'Timestamp','Bid','Ask'}.issubset(first):
                mapping={key:first.index(key) for key in ['Timestamp','Bid','Ask']}
                dr=({'Timestamp':v[mapping['Timestamp']], 'Bid':v[mapping['Bid']], 'Ask':v[mapping['Ask']]} for v in rdr)
            else:
                def to_row(v):
                    if len(v)<5 or v[1].strip()!='EURUSDm':
                        raise ValueError('Unexpected headerless daily CSV symbol/layout')
                    return {'Timestamp':v[2], 'Bid':v[3], 'Ask':v[4]}
                dr=(to_row(v) for v in itertools.chain([first],rdr))
            n=0;dup=0;ties=0;gap_max_ms=0;min_ts=None;max_ts=None;last_key=None;last_ts=None
            sps=[]
            for row in dr:
                text=row['Timestamp'].strip()
                if not text.endswith('Z'):raise ValueError('Expected UTC timestamp Z')
                ts=datetime.fromisoformat(text.replace('Z','+00:00'))
                if ts.date()!=day:raise ValueError('Timestamp outside requested UTC date')
                ms=int(ts.timestamp()*1000)
                bid=int(round(float(row['Bid'])*100000));ask=int(round(float(row['Ask'])*100000))
                if bid<=0 or ask<bid:raise ValueError('Crossed or nonpositive quote')
                if abs(float(row['Bid'])*100000-bid)>.001 or abs(float(row['Ask'])*100000-ask)>.001:
                    raise ValueError('Price precision exceeds 1/100000')
                if last_ts is not None and ms<last_ts:raise ValueError('Out-of-order tick timestamps')
                if last_ts is not None:
                    if ms==last_ts:ties+=1
                    gap_max_ms=max(gap_max_ms,ms-last_ts)
                k=(ms,bid,ask)
                dup+=int(last_key==k)
                min_ts=ms if min_ts is None else min_ts
                max_ts=ms
                last_key=k;last_ts=ms;n+=1
                # Fractional-price tick QC; bounded sample for lightweight manifest.
                if n<=10000 or n%100==0:sps.append(ask-bid)
    if n==0:raise ValueError('No ticks (could be closed market OR unpublished archive); do not infer market closure')
    import statistics
    return {'rows':n,'adjacent_identical_duplicates':dup,'same_timestamp_quote_pairs':ties,
            'first_ms':min_ts,'last_ms':max_ts,'max_quote_gap_ms':gap_max_ms,
            'spread_sample_size':len(sps),'spread_median_points':statistics.median(sps),
            'spread_max_sample_points':max(sps),'csv_member':csv_files[0],'source_sha256':hashlib.sha256(raw).hexdigest()}

def collect(day:date,out:Path):
    p=day.strftime('%Y_%m_%d')
    url=f'https://ticks.ex2archive.com/ticks/EURUSDm/{day.year}/{day.month:02d}/{day.day:02d}/Exness_EURUSDm_{p}.zip'
    with requests.Session() as ss:
        res=ss.get(url,timeout=(20,140),headers={'User-Agent':'V22-Prospective-ReadOnly/1.0','Cache-Control':'no-cache'})
        res.raise_for_status();raw=res.content
        info=inspect_zip(raw,day)
        info.update({'requested_utc_day':str(day),'source_url':url,
                     'response_last_modified':res.headers.get('Last-Modified'),
                     'run_utc':datetime.now(timezone.utc).isoformat(),
                     'prereg_sha256':'f2dd2f22b86ca031f8e9694d3dad0c192d2ca5235de07ff7134bfed49b88eeb5',
                     'status':'SEALED_RAW_PROSPECTIVE_NO_MODEL_OUTCOMES',
                     'is_broker_execution':False,
                     'cannot_automatically_claim_clean_oos':True})
    out.mkdir(parents=True,exist_ok=True)
    (out/f'Exness_EURUSDm_{p}.zip').write_bytes(raw)
    (out/f'manifest_{p}.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps({'date':str(day),'rows':info['rows'],'sha256':info['source_sha256'],'url':url}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--date',default=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat())
    p.add_argument('--out',type=Path,default=Path('v22_prospective_daily'))
    a=p.parse_args();day=validate_requested_day(a.date);collect(day,a.out)