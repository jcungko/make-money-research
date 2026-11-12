#!/usr/bin/env python3
"""V22 November-to-date filter: replay October-survivor EAs on Exness public Bid/Ask ticks.
October survival list is immutable input, November data are fresh public Exness
quotes. All returns expressed in sum of basis points on equal notionals.
"""
import argparse, csv, hashlib, io, json, re, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests

import v22_17to20_month_screen as model
from v12_exness_collect import ticks_to_5m, merge_parts, build_frames, FIELDS

CUTOFF=pd.Timestamp('2026-11-12T19:55:00Z')
START=pd.Timestamp('2026-11-01T00:00:00Z')
SYMBOLS=('NVDA','AMD','AVGO','XOM','GOOGL')
SURVIVOR_CSV=Path('results/v22_oct2026_filter/kept_not_losing_2026_10.csv')
PATTERN=re.compile(
    r'(?P<symbol>NVDA|AMD|AVGO|XOM|GOOGL) '
    r'(?P<tf>M5|M15|M30|H1|H4) '
    r'(?P<family>[A-Z0-9_]+) '
    r'(?P<orientation>FOLLOW|FADE|LONG_ONLY|SHORT_ONLY) '
    r'(?P<regime>ANY|D1_ALIGN|W1_ALIGN) '
    r'entry_(?P<hour>\d{2}):00_UTC window_(?P<window>\d+)h '
    r'hold_(?P<hold>\d+)min$'
)

def download_archive(session,url):
    resp=session.get(url,timeout=(20,150))
    resp.raise_for_status()
    data=resp.content
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError(f'Invalid ZIP {url}')
    return data

def collect_november(out):
    savedir=out/'november_candles'
    savedir.mkdir(parents=True,exist_ok=True)
    info={}
    frames={}
    with requests.Session() as session:
        session.headers['User-Agent']='V22-Research-Exness-202611/1.0'
        for symbol in SYMBOLS:
            archive_urls=[
                f'https://ticks.ex2archive.com/ticks/{symbol}/2026/11/Exness_{symbol}_2026_11.zip',
                f'https://ticks.ex2archive.com/ticks/{symbol}/2026/11/12/Exness_{symbol}_2026_11_12.zip',
            ]
            sourceparts=[]
            entries=[]
            for url in archive_urls:
                b=download_archive(session,url)
                m5=ticks_to_5m(b,CUTOFF,START)
                if m5.empty:raise ValueError(f'Empty November source for {symbol}: {url}')
                entries.append(dict(url=url,zip_bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),
                                    m5_candles=int(len(m5)),first_utc=m5.index.min().isoformat(),
                                    last_utc=m5.index.max().isoformat()))
                sourceparts.append(m5)
                print('FETCH',symbol,entries[-1],flush=True)
            # Day-12 archive is fresher and takes precedence over overlapping monthly bars.
            earlier,later=sourceparts
            earlier=earlier.loc[~earlier.index.isin(later.index)]
            complete=merge_parts([earlier,later])
            # Using hourly aggregations from the complete five-minute bars ensures exact
            # baseline 5/15/30/60/240-minute UTC frame alignment.
            groups=build_frames(complete)
            # Rebuild last partial intraday candle only where future ticks exist; outcomes
            # are excluded if a complete exit candle is not available before CUTOFF.
            archive=savedir/f'{symbol}_202611_through_20261112_1955UTC_5TF.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                for tf,frame in groups.items():
                    z.writestr(f'{symbol}_{tf}_202611_UTC.csv',frame.to_csv(index_label='timestamp_utc',float_format='%.6f'))
            frames[symbol]=groups
            info[symbol]={'sources':entries,'m5_rows_merged':len(complete),
                          'first_utc':complete.index.min().isoformat(),
                          'last_m5_start_utc':complete.index.max().isoformat(),
                          'frames':{tf:len(v) for tf,v in groups.items()},
                          'saved_archive':str(archive)}
    return frames,info

def read_candidates(path):
    with path.open(newline='',encoding='utf-8-sig') as handle:
        rows=list(csv.DictReader(handle))
    if len(rows)!=2728:raise AssertionError(f'Unexpected baseline count: {len(rows)}')
    return rows

def parse_component(s):
    m=PATTERN.fullmatch(s.strip())
    if not m:raise ValueError('Unrecognized config '+repr(s))
    a=m.groupdict()
    a['hour']=int(a['hour'])
    a['window']=int(a['window'])
    a['hold']=int(a['hold'])
    if a['hold'] % model.TFS[a['tf']][0]:raise ValueError(f'Invalid hold {s}')
    return a

def component_key(c):
    return (c['symbol'],c['tf'],c['family'],c['orientation'],c['regime'],c['hour'],c['window'],c['hold'])

def replay_component(c,store):
    symbol,tf=c['symbol'],c['tf']
    bundle=store[symbol,tf]
    (ordinal,midx,minute,day,week,hdict,signalmap)=bundle
    base=signalmap[c['family']]
    orient=c['orientation']
    if orient=='FOLLOW':side=base
    elif orient=='FADE':side=-base
    elif orient=='LONG_ONLY':side=np.where(base>0,1,0)
    elif orient=='SHORT_ONLY':side=np.where(base<0,-1,0)
    else:raise ValueError(orient)
    eligible=(side!=0)
    if c['regime']=='D1_ALIGN':eligible &= side==day
    elif c['regime']=='W1_ALIGN':eligible &= side==week
    start=c['hour']*60
    window=(minute>=start)&(minute<min(start+c['window']*60,1440))
    holdbars=c['hold']//model.TFS[tf][0]
    valid,lr,sr=hdict[holdbars]
    good=np.flatnonzero(eligible&window&valid)
    if len(good):
        first=np.r_[True,ordinal[good[1:]]!=ordinal[good[:-1]]]
        good=good[first]
    pertrade=np.where(side[good]>0,lr[good],sr[good])
    result={}
    for month in (202610,202611):
        indices=good[midx[good]==model.MONTH_ID[month]]
        rets=pertrade[midx[good]==model.MONTH_ID[month]]
        result[month]=dict(bps=float(rets.sum()),trades=len(rets),days=[int(d) for d in ordinal[indices]],
                           daily_bps={str(int(d)):round(float(r),6) for d,r in zip(ordinal[indices],rets)})
    return result

def main(out):
    if not datetime.now(timezone.utc)>CUTOFF.to_pydatetime():
        raise ValueError('Cutoff lies in the future')
    out.mkdir(parents=True,exist_ok=True)
    survivors=read_candidates(SURVIVOR_CSV)
    specs={}
    for entry in survivors:
        parts=[parse_component(s) for s in entry['components'].split(' | ')]
        if len(parts)!=int(entry['n_strategies']):raise AssertionError('Wrong component count')
        specs[entry['id']]=parts
    newframes,sources=collect_november(out)
    # Keep the precise historic model and backtest code, merely extend its
    # month-id registry to include the new out-of-sample November observations.
    model.MONTHS=model.MONTHS+[202611]
    model.MONTH_ID={month:i for i,month in enumerate(model.MONTHS)}
    store={}
    needs={(p['symbol'],p['tf']) for parts in specs.values() for p in parts}
    for symbol in SYMBOLS:
        oldm5=model.load(Path('data/v22_exness'),symbol,'M5')
        fullm5=pd.concat([oldm5,newframes[symbol]['M5']]).sort_index()
        if fullm5.index.has_duplicates:raise AssertionError(f'Duplicate merged M5 {symbol}')
        ds,ws=model.daily_weekly_directions(fullm5)
        for sym,tf in sorted(needs):
            if sym!=symbol:continue
            old=model.load(Path('data/v22_exness'),symbol,tf)
            full=pd.concat([old,newframes[symbol][tf]]).sort_index()
            if full.index.has_duplicates:raise AssertionError(f'Duplicate {symbol}/{tf}')
            prepared=model.prepare(full,tf,ds,ws)
            signals=dict(model.signal_library(full,prepared[3],prepared[4]))
            store[symbol,tf]=(*prepared,signals)
            print('MODEL',symbol,tf,len(full),len(signals),flush=True)
    cache={}
    for entry in survivors:
        for c in specs[entry['id']]:
            key=component_key(c)
            if key not in cache:cache[key]=replay_component(c,store)
    print('UNIQUE_COMPONENTS',len(cache),flush=True)
    retained=[]
    rejected=[]
    for entry in survivors:
        components=specs[entry['id']]
        vals=[cache[component_key(c)] for c in components]
        oct_bps=float(np.mean([x[202610]['bps'] for x in vals]))
        oct_record=float(entry['pnl_202610_bps'])
        if abs(oct_bps-oct_record)>0.001:
            raise AssertionError(f'Oct-2026 replay mismatch {entry["id"]}: reproduced {oct_bps} original {oct_record}')
        nov_bps=float(np.mean([x[202611]['bps'] for x in vals]))
        unique_days=sorted(set(d for x in vals for d in x[202611]['days']))
        total_trades=sum(x[202611]['trades'] for x in vals)
        r=dict(entry)
        r['nov_2026_bps']=round(nov_bps,6)
        r['nov_trades_all_components']=total_trades
        r['nov_unique_trading_days']=len(unique_days)
        r['nov_last_trade_date_utc']=str(unique_days[-1]) if unique_days else ''
        r['nov_data_cutoff_utc']=CUTOFF.isoformat()
        if nov_bps<-1e-8:rejected.append(r)
        else:retained.append(r)
    retained.sort(key=lambda r:(-int(r['months_profitable']),-float(r['nov_2026_bps']),
                                -float(r['total_bps']),r['id']))
    rejected.sort(key=lambda r:(-int(r['months_profitable']),-float(r['total_bps']),r['id']))
    fields=list(retained[0] if retained else rejected[0])
    for filename,group in [('surviving_oct_and_nov_to_date.csv',retained),
                           ('rejected_nov_to_date_losses.csv',rejected)]:
        with (out/filename).open('w',newline='',encoding='utf-8-sig') as dest:
            writer=csv.DictWriter(dest,fieldnames=fields)
            writer.writeheader();writer.writerows(group)
    types=('single','pair','triple','quad','quint')
    report={
      'version':'V22-2026-NOV-PARTIAL',
      'cutoff_exclusive_utc':CUTOFF.isoformat(),
      'cutoff_vietnam_time':'2026-11-13 02:55 GMT+7',
      'month_status':'INCOMPLETE: results only through cutoff, not full 2026-11',
      'baseline_oct_survivors':len(survivors),
      'nov_rejected':len(rejected),
      'nov_kept':len(retained),
      'nov_kept_positive':sum(float(r['nov_2026_bps'])>1e-8 for r in retained),
      'nov_kept_zero':sum(abs(float(r['nov_2026_bps']))<=1e-8 for r in retained),
      'source_method':'Exness public 2026-11 month ZIP + 2026-11-12 daily ZIP, bid/ask M5 aggregated to M15/M30/H1/H4',
      'monthly_return_formula':'daily first eligible trade; long Ask open/Bid close, short Bid open/Ask close; 2bps additional round-trip slippage; equal-weight component monthly sum',
      'october_2026_replay':'all 2728 baseline rows checked within 0.001bps',
      'model_components_unique':len(cache),
      'data_sources':sources,
      'by_type':{
        t:{'before':sum(x['category']==t for x in survivors),
           'kept':sum(x['category']==t for x in retained),
           'removed':sum(x['category']==t for x in rejected)} for t in types},
      'by_original_months_positive':{
        str(m):{'before':sum(int(x['months_profitable'])==m for x in survivors),
                'kept':sum(int(x['months_profitable'])==m for x in retained),
                'removed':sum(int(x['months_profitable'])==m for x in rejected)}
        for m in (17,18,19,20)},
      'top20_survivors':[{k:x[k] for k in ('id','category','months_profitable','symbols',
          'nov_2026_bps','nov_trades_all_components','profit_2025_bps',
          'profit_2026_bps','total_bps','components')} for x in retained[:20]],
      'created_at_utc':datetime.now(timezone.utc).isoformat()
    }
    (out/'filter_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('FINAL',json.dumps({k:report[k] for k in ('cutoff_exclusive_utc','baseline_oct_survivors','nov_kept','nov_rejected',
                'nov_kept_positive','nov_kept_zero','model_components_unique','by_type','by_original_months_positive')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('results/v22_nov2026_filter'))
    a=p.parse_args()
    main(a.out)
