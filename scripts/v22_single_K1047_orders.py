#!/usr/bin/env python3
"""Auditable V22-K1047 AVGO November 2026 completed order-level trade log."""
import csv,json,zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import v22_17to20_month_screen as model

SYMBOL='AVGO'
BASE=Path('data/v22_exness')
MONTH=202611
model.MONTHS=model.MONTHS+[MONTH]
model.MONTH_ID={v:i for i,v in enumerate(model.MONTHS)}
OUT=Path('results/v22_single_K1047')
OUT.mkdir(parents=True,exist_ok=True)

def load_nov(tf):
    path=Path('results/v22_nov2026_filter/november_candles')/'AVGO_202611_through_20261112_1955UTC_5TF.zip'
    with zipfile.ZipFile(path) as z:
        with z.open(f'AVGO_{tf}_202611_UTC.csv') as f:
            return pd.read_csv(f,parse_dates=['timestamp_utc'],index_col='timestamp_utc')

m5=pd.concat([model.load(BASE,SYMBOL,'M5'),load_nov('M5')]).sort_index()
m5.index=pd.DatetimeIndex(m5.index).tz_convert('UTC')
ds,ws=model.daily_weekly_directions(m5)
d=pd.concat([model.load(BASE,SYMBOL,'M15'),load_nov('M15')]).sort_index()
d.index=pd.DatetimeIndex(d.index).tz_convert('UTC')
ordinal,midx,minutes,direcday,direcweek,hdict=model.prepare(d,'M15',ds,ws)
signals=dict(model.signal_library(d,direcday,direcweek))
side=signals['RSI_14_40']
good=np.flatnonzero((side!=0)&(side==direcday)&(minutes>=15*60)&(minutes<17*60)&hdict[8][0])
first=np.r_[True,ordinal[good[1:]]!=ordinal[good[:-1]]] if len(good) else np.array([],dtype=bool)
good=good[first]
good=good[midx[good]==model.MONTH_ID[MONTH]]
valid,lr,sr=hdict[8]
entries=[]
for i in good:
    j=i+7
    direction='LONG' if side[i]>0 else 'SHORT'
    r=float(lr[i] if direction=='LONG' else sr[i])
    x=dict(date_utc=d.index[i].strftime('%Y-%m-%d'),
        entry_time_utc=d.index[i].isoformat(),
        exit_bar_start_utc=d.index[j].isoformat(),
        nominal_exit_candle_close_utc=(d.index[j]+pd.Timedelta(minutes=15)).isoformat(),
        side=direction,
        entry_executable_ask_or_bid=round(float(d.ask_open.iloc[i] if direction=='LONG' else d.bid_open.iloc[i]),6),
        exit_executable_bid_or_ask=round(float(d.bid_close.iloc[j] if direction=='LONG' else d.ask_close.iloc[j]),6),
        spread_and_2bps_extra_slippage_adjusted_pnl_bps=round(r,6))
    entries.append(x)
with (OUT/'K1047_nov2026_trades.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(entries[0]))
    writer.writeheader();writer.writerows(entries)
summary={
    'strategy_id':'V22-K1047',
    'symbol':SYMBOL,
    'timeframe':'M15',
    'signal':'RSI_14_40',
    'regime':'D1_ALIGN',
    'orientation':'FOLLOW',
    'entry_utc':'first eligible candle between 15:00 and 17:00 UTC',
    'exit':'at close of 8th 15-minute candle',
    'stop_loss':None,'take_profit':None,
    'research_exness_spread':'Bid/Ask included',
    'assumed_additional_roundtrip_slippage_bps':2,
    'month':MONTH,
    'november_data_cutoff':'2026-11-12T19:55:00Z',
    'november_trades':len(entries),
    'november_pnl_bps':sum(x['spread_and_2bps_extra_slippage_adjusted_pnl_bps'] for x in entries),
    'trades':entries,
    'generated_utc':datetime.now(timezone.utc).isoformat()
}
assert len(entries)==5,len(entries)
assert abs(summary['november_pnl_bps']-142.903024)<0.00001, summary['november_pnl_bps']
(OUT/'K1047_nov2026_detail.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
print('FINAL',json.dumps(summary,ensure_ascii=False),flush=True)
