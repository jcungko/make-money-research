#!/usr/bin/env python3
"""Snapshot public Exness daily ticks for 10-12 Nov 2026 and screen 23:00 ICT.
Research only. No order submission and no credentials.
"""
import io, json, struct, sys, zipfile, zlib
from pathlib import Path
import numpy as np
import pandas as pd
import requests

SYMBOLS=('EURUSD','GBPUSD','USDJPY')
DATES=('2026-11-10','2026-11-11','2026-11-12')
FRAMES={'M5':'5min','M15':'15min','M30':'30min','H1':'1h','H4':'4h'}
TARGET=pd.Timestamp('2026-11-12T16:00:00Z')
PIP={'EURUSD':0.0001,'GBPUSD':0.0001,'USDJPY':0.01}

def unzip_csv(raw):
    """Recover whole tick rows when a current-day ZIP lacks its central directory."""
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=[n for n in z.namelist() if n.lower().endswith('.csv') and '..' not in n]
            if len(names)!=1: raise ValueError('unexpected CSV list')
            return z.read(names[0]), 'complete_zip'
    if not raw.startswith(b'PK\x03\x04') or len(raw)<30:
        raise ValueError('not a zip local header')
    method=struct.unpack_from('<H',raw,8)[0]
    name_length,extra_length=struct.unpack_from('<HH',raw,26)
    start=30+name_length+extra_length
    if method!=8 or start>=len(raw): raise ValueError('unsupported incomplete ZIP')
    decoder=zlib.decompressobj(-zlib.MAX_WBITS)
    data=decoder.decompress(raw[start:])+decoder.flush()
    if b'\n' not in data: raise ValueError('incomplete ZIP lacks complete CSV rows')
    return data[:data.rfind(b'\n')+1],'recovered_partial_zip'

def fetch_day(sess,symbol,day):
    p=pd.Timestamp(day)
    url=f'https://ticks.ex2archive.com/ticks/{symbol}/{p.year}/{p.month:02d}/{p.day:02d}/Exness_{symbol}_{day.replace("-","_")}.zip'
    resp=sess.get(url,timeout=(12,55),headers={'Cache-Control':'no-cache','User-Agent':'MakeMoneyExnessSnapshot/1.0'})
    resp.raise_for_status()
    data,status=unzip_csv(resp.content)
    return url,data,status,{'download_bytes':len(resp.content),'last_modified':resp.headers.get('Last-Modified')}

def read_ticks(data,symbol,day,cutoff):
    f=pd.read_csv(io.BytesIO(data),header=None,names=['provider','symbol','ts','bid','ask'],on_bad_lines='skip',low_memory=False)
    f['ts']=pd.to_datetime(f.ts,utc=True,errors='coerce',format='mixed')
    f['bid']=pd.to_numeric(f.bid,errors='coerce')
    f['ask']=pd.to_numeric(f.ask,errors='coerce')
    beg=pd.Timestamp(day,tz='UTC')
    valid=(f.ts>=beg)&(f.ts<beg+pd.Timedelta(days=1))&(f.ts<cutoff)&(f.bid>0)&(f.ask>=f.bid)&(f.symbol==symbol)
    f=f.loc[valid,['ts','bid','ask']].drop_duplicates('ts',keep='last').sort_values('ts')
    if f.empty: raise ValueError('no valid ticks before cutoff')
    return f

def frames_from_ticks(raw):
    data=raw.copy()
    data['bucket']=data.ts.dt.floor('5min')
    m5=data.groupby('bucket',sort=True).agg(bid_open=('bid','first'),bid_high=('bid','max'),bid_low=('bid','min'),bid_close=('bid','last'),ask_open=('ask','first'),ask_high=('ask','max'),ask_low=('ask','min'),ask_close=('ask','last'),ticks=('bid','size'))
    agg={'bid_open':'first','bid_high':'max','bid_low':'min','bid_close':'last','ask_open':'first','ask_high':'max','ask_low':'min','ask_close':'last','ticks':'sum'}
    return {tf:m5.resample(freq,origin='epoch',label='left',closed='left').agg(agg).dropna(subset=['bid_open','bid_close','ask_open','ask_close']) for tf,freq in FRAMES.items()}

def ema_sign(f):
    if len(f)<24:return 0
    price=f.bid_close
    return int(np.sign(price.ewm(span=9,adjust=False).mean().iloc[-1]-price.ewm(span=21,adjust=False).mean().iloc[-1]))

def rsi(series):
    if len(series)<20:return None
    diff=series.diff()
    u=diff.clip(lower=0).ewm(alpha=1/14,adjust=False).mean().iloc[-1]
    d=(-diff.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean().iloc[-1]
    return round(float(100*u/(u+d)),2) if u+d>0 else 50.0

def atr(f,pip):
    if len(f)<16:return None
    c=f.bid_close.shift(1)
    tr=pd.concat([f.bid_high-f.bid_low,(f.bid_high-c).abs(),(f.bid_low-c).abs()],axis=1).max(axis=1)
    return round(float(tr.tail(14).mean()/pip),2)

def screen(symbol,raw,days,cutoff):
    pip=PIP[symbol]
    all_frames=frames_from_ticks(raw)
    frames={tf:f.loc[f.index+pd.Timedelta(FRAMES[tf])<=cutoff] for tf,f in all_frames.items()}
    h4,h1,m30,m15,m5=(frames[t] for t in ('H4','H1','M30','M15','M5'))
    quote=raw.iloc[-1]
    spread=float((quote.ask-quote.bid)/pip)
    median_spread=float(((raw.ask-raw.bid)/pip).tail(1000).median())
    h4_trend=int(np.sign(h4.bid_close.iloc[-1]-h4.bid_close.iloc[-4])) if len(h4)>=4 else 0
    h1_trend=ema_sign(h1)
    m30_trend=ema_sign(m30)
    m15_trend=ema_sign(m15)
    score=h4_trend+2*h1_trend+m30_trend+m15_trend
    direction='BUY' if score>=3 else 'SELL' if score<=-3 else 'WAIT'
    ap=atr(m15,pip)
    stop=round(max(8 if symbol!='USDJPY' else 10,(ap or 10)*1.4),1)
    result={
       'symbol':symbol,'asof_utc':quote.ts.isoformat(),
       'bid':float(quote.bid),'ask':float(quote.ask),
       'spread_pips':round(spread,2),'median_spread_pips':round(median_spread,2),
       'trend_H4':h4_trend,'trend_H1':h1_trend,'trend_M30':m30_trend,'trend_M15':m15_trend,
       'score':score,'direction_preliminary':direction,
       'direction_confirmed':h4_trend==h1_trend==m30_trend and h1_trend!=0,
       'rsi_M5':rsi(m5.bid_close),'atr14_M15_pips':ap,
       'suggested_SL_pips':stop,'suggested_TP_pips':round(stop*1.5,1),
       'closed_bars':{tf:len(fr) for tf,fr in frames.items()},
       'latest_closed_M5_utc':str(m5.index[-1]) if len(m5) else None,
       'days':days,'trade_status':'NO_ORDER_PLACED',
       'condition_at_23_ict':'Enter only if fresh H4/H1/M30 trend alignment, M5 break of last 3 completed candles in same direction, and current spread <= 2x trailing median; otherwise NO_TRADE.'
    }
    return result,frames

def main():
    now=pd.Timestamp.now(tz='UTC')
    cutoff=min(now.floor('5min')-pd.Timedelta(minutes=5),TARGET)
    dest=Path('results/exness_nov12_2026')
    dest.mkdir(parents=True,exist_ok=True)
    report={'created_utc':now.isoformat(),'target_entry_utc':TARGET.isoformat(),
      'target_entry_ict':'2026-11-12 23:00:00+07:00',
      'last_complete_M5_cutoff_exclusive_utc':cutoff.isoformat(),
      'source':'Exness public tick-history archive (indicative)',
      'execution':'RESEARCH_ONLY, no orders or API credentials',
      'symbols':{},'errors':[]}
    sess=requests.Session()
    for symbol in SYMBOLS:
        parts=[];days=[]
        for day in DATES:
            try:
                url,data,status,details=fetch_day(sess,symbol,day)
                ticks=read_ticks(data,symbol,day,cutoff)
                parts.append(ticks)
                days.append({'date_utc':day,'status':status,'source':url,
                  'ticks':len(ticks),'first_utc':ticks.ts.iloc[0].isoformat(),
                  'last_utc':ticks.ts.iloc[-1].isoformat(),**details})
                print('OK',symbol,day,status,len(ticks),ticks.ts.iloc[-1],flush=True)
            except Exception as e:
                msg=f'{symbol} {day}: {type(e).__name__}: {str(e)[:180]}'
                report['errors'].append(msg)
                print('ERROR',msg,flush=True)
        if parts:
            raw=pd.concat(parts,ignore_index=True).drop_duplicates('ts',keep='last').sort_values('ts')
            try:
                model,frames=screen(symbol,raw,days,cutoff)
                report['symbols'][symbol]=model
                for tf,frame in frames.items():
                    frame.to_csv(dest/f'{symbol}_{tf}_recent.csv.gz',compression='gzip')
            except Exception as e:
                report['errors'].append(f'MODEL {symbol}: {type(e).__name__}: {e}')
    eligible=[x for x in report['symbols'].values() if x['direction_preliminary']!='WAIT' and x['direction_confirmed']]
    eligible.sort(key=lambda x:(abs(x['score']),-x['spread_pips']/max(x['suggested_SL_pips'],1)),reverse=True)
    report['top_conditional_candidate']=eligible[0]['symbol'] if eligible else None
    report['win_probability']='NOT_ESTIMABLE_FROM_THREE_DAYS'
    (dest/'latest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('SUMMARY',json.dumps({'cutoff':str(cutoff),'symbols':list(report['symbols']),
      'errors':report['errors'],'top':report['top_conditional_candidate']}),flush=True)
    if len(report['symbols'])!=3:sys.exit(1)

if __name__=='__main__':main()
