#!/usr/bin/env python3
"""V22 independent Nov 2026 (as-of) replay of exactly 682 frozen configurations.

Uses public Exness November tick archives; no chart substitutions, no extrapolation
for days after last verified quote. Simulates original V22 bid/ask close-to-close
execution logic and November trades only, with 2 bps round-trip slippage.
"""
import argparse
import csv
import io
import json
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import v12_exness_collect as archive
import v22_strategy_screen as original

SYMBOLS=('NVDA','AMD','AVGO','XOM','GOOGL')
TFS=original.TFS
SOURCE_START=pd.Timestamp('2026-11-01T00:00:00Z')
SOURCE_END=pd.Timestamp('2026-12-01T00:00:00Z')
EPSILON=1e-8

def download_m5(session, symbol, end_utc):
    url=f'https://ticks.ex2archive.com/ticks/{symbol}/2026/11/Exness_{symbol}_2026_11.zip'
    status=dict(symbol=symbol,source_url=url,availability='unverified')
    data=None
    for attempt in range(3):
        try:
            r=session.get(url,timeout=(18,120))
            status['http_status']=r.status_code
            if r.status_code in (400,403,404,410):
                status['availability']='unavailable'
                status['error']=f'HTTP {r.status_code}; do not infer that the stock had no trading'
                return None,status
            r.raise_for_status()
            if not zipfile.is_zipfile(io.BytesIO(r.content)):
                raise ValueError('Unexpected ZIP content')
            data=r.content
            break
        except (requests.RequestException, ValueError) as exc:
            status['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
            if attempt==2:
                status['availability']='unavailable'
                return None,status
            time.sleep(2*(attempt+1))
    try:
        bars=archive.ticks_to_5m(data,end_utc,SOURCE_START)
        if bars.empty:
            raise ValueError('No November bid/ask ticks in available source')
        # Last observed M5 bucket might be partial within the upstream ZIP.
        # The replay later imposes a common fully-closed cutoff across all five.
        status.update(availability='available',zip_bytes=len(data),m5_rows=len(bars),
             first_m5_utc=bars.index[0].isoformat(),
             last_m5_bucket_utc=bars.index[-1].isoformat())
        return bars,status
    except Exception as exc:
        status['availability']='unavailable'
        status['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
        return None,status

def read_configurations(path):
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=682:
        raise ValueError(f'Expected 682 frozen V22 configurations; got {len(rows)}')
    if len({r['final_id'] for r in rows})!=682:
        raise ValueError('Duplicate final_id')
    return rows

def parse_legs(rows):
    alllegs={}
    ids={}
    for row in rows:
        configs=[]
        for part in row['components'].split(' | '):
            t=part.split()
            if len(t)!=8:
                raise ValueError(f'Unexpected component schema: {part}')
            sym,tf,family,orientation,regime,ent,win,hold=t
            if sym not in SYMBOLS or tf not in TFS:
                raise ValueError('Unknown asset or timeframe')
            if orientation not in ('FOLLOW','FADE','LONG_ONLY','SHORT_ONLY'):
                raise ValueError('Unknown orientation')
            if regime not in ('ANY','D1_ALIGN','W1_ALIGN'):
                raise ValueError('Unknown regime')
            if not (ent.startswith('entry_') and ent.endswith(':00_UTC') and
                    win.startswith('window_') and win.endswith('h') and
                    hold.startswith('hold_') and hold.endswith('min')):
                raise ValueError(f'Unexpected config format: {part}')
            hour=int(ent[6:8])
            window=int(win[7:-1])
            holdminutes=int(hold[5:-3])
            if holdminutes%TFS[tf][0]!=0:
                raise ValueError('Nonintegral hold bars')
            holdbars=holdminutes//TFS[tf][0]
            if holdbars not in TFS[tf][1]:
                raise ValueError(f'Unexpected historic V22 hold bars {tf} {holdbars}')
            if hour not in original.SESSIONS or window!=2:
                raise ValueError('Unexpected historical V22 session setting')
            key=(sym,tf,family,orientation,regime,hour,window,holdbars)
            alllegs[key]=None
            configs.append(key)
        if len(configs)!=int(row['n_strategies']):
            raise ValueError('Wrong number of components')
        ids[row['final_id']]=configs
    return ids,alllegs

def get_frames(dataset_root, novm5, common_cutoff):
    frames={}
    for sym in SYMBOLS:
        if sym not in novm5:
            continue
        nov5=novm5[sym].loc[novm5[sym].index<common_cutoff].copy()
        if nov5.empty:
            continue
        novframes=archive.build_frames(nov5)
        for tf in TFS:
            historic=original.load(dataset_root,sym,tf)
            latest=novframes[tf]
            frames[(sym,tf)]=pd.concat([historic,latest]).sort_index()
    return frames

def daily_week_signs(frames):
    directions={}
    for sym in SYMBOLS:
        m5=frames.get((sym,'M5'))
        if m5 is None:
            continue
        day,week=original.daily_weekly_directions(m5)
        directions[sym]=(day,week)
    return directions

def eval_component(key,frames,directions,common_cutoff):
    sym,tf,family,orientation,regime,hour,window,holdbars=key
    data=frames.get((sym,tf))
    if data is None:
        return None
    daylag,weeklag=directions[sym]
    idx=data.index
    days=idx.normalize()
    weeks=days-pd.to_timedelta(idx.dayofweek,unit='D')
    ds=np.nan_to_num(daylag.reindex(days).to_numpy(dtype='float64'),nan=0).astype('int8')
    ws=np.nan_to_num(weeklag.reindex(weeks).to_numpy(dtype='float64'),nan=0).astype('int8')
    signals=dict(original.signal_library(data,ds,ws))
    base=signals[family]
    if orientation=='FOLLOW': side=base.copy()
    elif orientation=='FADE': side=-base
    elif orientation=='LONG_ONLY': side=np.where(base>0,1,0)
    else: side=np.where(base<0,-1,0)

    eligible=(side!=0)
    if regime=='D1_ALIGN': eligible &= side==ds
    if regime=='W1_ALIGN': eligible &= side==ws
    minute=(idx.hour*60+idx.minute).to_numpy('int16')
    feasible=eligible & (minute>=hour*60) & (minute<min(hour*60+window*60,1440))

    n=len(data)
    entry=np.arange(n)
    exitid=np.minimum(entry+holdbars-1,n-1)
    ordinal=(idx.year*10000+idx.month*100+idx.day).to_numpy('int32')
    tfmin=TFS[tf][0]
    is_nov=(idx>=SOURCE_START)&(idx<common_cutoff)
    exit_fully_closed=(idx.asi8[exitid]+tfmin*60*1_000_000_000)<=common_cutoff.value
    valid=(is_nov & (idx.dayofweek<5) & (entry+holdbars-1<n)
        & (ordinal[exitid]==ordinal)
        & (idx.asi8[exitid]-idx.asi8<=tfmin*holdbars*60*1e9*2)
        & exit_fully_closed)
    askopen=data.ask_open.to_numpy(dtype='float64')
    bidopen=data.bid_open.to_numpy(dtype='float64')
    bidclose=data.bid_close.to_numpy(dtype='float64')
    askclose=data.ask_close.to_numpy(dtype='float64')
    midpoint=(askopen+bidopen)*.5
    longret=((bidclose[exitid]-askopen)/midpoint)*10000-original.SLIPPAGE_ROUND_TRIP_BPS
    shortret=((bidopen-askclose[exitid])/midpoint)*10000-original.SLIPPAGE_ROUND_TRIP_BPS
    valid&=(midpoint>0)&np.isfinite(longret)&np.isfinite(shortret)
    candidates=np.flatnonzero(feasible&valid)
    if len(candidates):
        dayfirst=np.r_[True,ordinal[candidates[1:]]!=ordinal[candidates[:-1]]]
        chosen=candidates[dayfirst]
        pnl=np.where(side[chosen]>0,longret[chosen],shortret[chosen])
        trades=[dict(date=str(idx[i].date()),entry_utc=idx[i].isoformat(),
            exit_utc=(idx[exitid[i]]+pd.Timedelta(minutes=tfmin)).isoformat(),
            direction='long' if side[i]>0 else 'short',
            net_bps=round(float(x),6)) for i,x in zip(chosen,pnl)]
    else: trades=[]
    return dict(symbol=sym,tf=tf,family=family,orientation=orientation,
        regime=regime,entry_hour_utc=hour,hold_bars=holdbars,
        trades=len(trades),net_bps=round(float(sum(t['net_bps'] for t in trades)),6),
        items=trades)

def write_csv(path,records,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        w.writerows(records)

def screen(dataset_root,selection_path,out):
    out.mkdir(parents=True,exist_ok=True)
    rows=read_configurations(selection_path)
    config_ids,alllegs=parse_legs(rows)
    nowutc=pd.Timestamp(datetime.now(timezone.utc))
    # Do not replay future minutes, and leave a 10-minute safety buffer.
    collect_cutoff=min(SOURCE_END,(nowutc-pd.Timedelta(minutes=10)).floor('5min'))
    if collect_cutoff<=SOURCE_START:
        raise ValueError('November 2026 period not yet reached')
    novm5={}
    statuses={}
    with requests.Session() as sess:
        sess.headers['User-Agent']='MakeMoneyV22Nov2026Research/1.0'
        for sym in SYMBOLS:
            bars,status=download_m5(sess,sym,collect_cutoff)
            statuses[sym]=status
            if bars is not None:novm5[sym]=bars
            print('NOV_SOURCE',json.dumps(status),flush=True)
    common_cutoff=min(
        (pd.Timestamp(bars.index[-1]) for bars in novm5.values()),
        default=SOURCE_START)
    # For a portfolio with a missing symbol, it must NOT be classified as breakeven.
    # Fully-closed bar cutoff is the last observed 5-minute bucket start.
    cutoff_ready=common_cutoff>SOURCE_START
    frames=get_frames(dataset_root,novm5,common_cutoff) if cutoff_ready else {}
    directions=daily_week_signs(frames)
    evaluated={}
    for key in alllegs:
        evaluated[key]=eval_component(key,frames,directions,common_cutoff) if cutoff_ready else None
    evaluated_keys=sum(value is not None for value in evaluated.values())
    raw_output=[]
    to_keep=[]
    removed=[]
    unverifiable=[]
    for r in rows:
        legs=config_ids[r['final_id']]
        itemized=[evaluated[k] for k in legs]
        lack=[k[0] for k,v in zip(legs,itemized) if v is None]
        if lack:
            state='unverifiable'
            pnl=None
            ntrades=None
        else:
            # V22 portfolio economics = equal-notional mean of each leg's net bps.
            pnl=round(float(np.mean([leg['net_bps'] for leg in itemized])),6)
            ntrades=sum(leg['trades'] for leg in itemized)
            state=('profitable' if pnl>EPSILON else 'losing' if pnl< -EPSILON else 'breakeven')
        output=dict(final_id=r['final_id'],old_v22_id=r['id'],category=r['category'],
          symbols=r['symbols'],historical_months_profitable=r['months_profitable'],
          historical_total_bps=r['total_bps'],historical_total_orders=r['total_orders_2025_2026'],
          november_status=state,november_net_bps='' if pnl is None else pnl,
          november_orders='' if ntrades is None else ntrades,
          november_start_utc=SOURCE_START.isoformat(),
          latest_common_cutoff_utc=common_cutoff.isoformat() if cutoff_ready else '',
          missing_sources=';'.join(sorted(set(lack))),components=r['components'])
        raw_output.append(output)
        if state=='profitable':to_keep.append(output)
        elif state=='unverifiable':unverifiable.append(output)
        else:removed.append(output)
    if len(to_keep)+len(removed)+len(unverifiable)!=682:
        raise AssertionError('Coverage accounting error')
    to_keep.sort(key=lambda r:(-float(r['november_net_bps']),-int(r['november_orders']),r['final_id']))
    removed.sort(key=lambda r:(r['november_status'],-float(r['november_net_bps']),r['final_id']))
    fields=list(raw_output[0])
    for name,records in [('v22_nov2026_profitable_survivors.csv',to_keep),
         ('v22_nov2026_removed_breakeven_or_loss.csv',removed),
         ('v22_nov2026_unverifiable.csv',unverifiable),
         ('v22_nov2026_all_682_with_results.csv',raw_output)]:
        write_csv(out/name,records,fields)

    components=[dict(key='|'.join(map(str,k)),**{y:x for y,x in v.items() if y!='items'}) for k,v in evaluated.items() if v is not None]
    component_fields=['key','symbol','tf','family','orientation','regime','entry_hour_utc',
         'hold_bars','trades','net_bps']
    write_csv(out/'v22_nov2026_unique_components.csv',components,component_fields)
    details={ '|'.join(map(str,k)):v for k,v in evaluated.items() if v is not None }
    (out/'v22_nov2026_component_trades.json').write_text(json.dumps(details,indent=2,ensure_ascii=False)+'\n')
    groups={k:dict(before=sum(r['category']==k for r in rows),
      profitable=sum(r['category']==k for r in to_keep),
      losing=sum(r['category']==k and r['november_status']=='losing' for r in removed),
      breakeven=sum(r['category']==k and r['november_status']=='breakeven' for r in removed),
      unverifiable=sum(r['category']==k for r in unverifiable))
      for k in ('triple','quad','quint')}
    metrics=dict(version='V22-NOV2026-PARTIAL-REPLAY',
       report_created_at_utc=nowutc.isoformat(),
       exness_november_archive_limit='As available at replay time; may be incomplete monthly archive',
       requested_month='2026-11',
       period_start_utc=SOURCE_START.isoformat(),
       common_closed_candle_cutoff_exclusive_utc=common_cutoff.isoformat() if cutoff_ready else None,
       periods_tested='2026-11-01 to common closed quote cutoff; NOT full month',
       november_sources=statuses,
       total_baseline=682,unique_components=len(alllegs),evaluated_components=evaluated_keys,
       survivors_profit=len(to_keep),
       removed_losing=sum(r['november_status']=='losing' for r in removed),
       removed_breakeven=sum(r['november_status']=='breakeven' for r in removed),
       unavailable_unverifiable=len(unverifiable),
       groups=groups,
       top20_survivors=to_keep[:20],
       pnl_assumption='Equal-notional mean of independent leg results, real CFD Bid/Ask OHLC + extra 2 bps round-trip slippage; not real USD P&L',
       caveats=['Month November is still in progress. Results valid only through cutoff.',
          'Signals and exit rules replay V22 backtest logic using completed input candles.',
          'No margin, financing, real slippage, tax or per-account commissions modelled.',
          'Unavailable market sources are never classified as zero-profit losses.',
          'In-sample survivor selection can overfit, never automatically live-trade.'])
    (out/'november_replay_summary.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    print('V22_NOVEMBER_FINAL',json.dumps({k:metrics[k] for k in
          ('total_baseline','unique_components','evaluated_components','common_closed_candle_cutoff_exclusive_utc',
          'survivors_profit','removed_losing','removed_breakeven','unavailable_unverifiable','groups')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('data/v22_exness'))
    p.add_argument('--selection',type=Path,default=Path('results/v22_profit_orders_filter/v22_final_682_strategies.csv'))
    p.add_argument('--out',type=Path,default=Path('results/v22_november_2026'))
    a=p.parse_args()
    screen(a.data,a.selection,a.out)
