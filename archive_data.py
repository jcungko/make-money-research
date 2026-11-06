"""Binance Vision public USD-M monthly archives (research-only, never trading)."""
import hashlib, io, time, xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd
import requests

BASE="https://data.binance.vision/data/futures/um/monthly"
S3="https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CACHE=Path(".cache/binance-archive")
CLIENT=requests.Session()
CLIENT.headers["User-Agent"]="MakeMoneyResearch/archive-data"
COLUMNS=["open_time","open","high","low","close","volume","close_time","quote_volume","count","taker_buy_volume","taker_buy_quote_volume","ignore"]

def closed_end_ms():
    ts=pd.Timestamp.now(tz="UTC")
    month=ts.to_period("M").to_timestamp().tz_localize("UTC")
    # Monthly archives can be late; do not assume latest month published until day 8 UTC.
    if ts.day<8: month=month-pd.DateOffset(months=1)
    return int(month.timestamp()*1000)

def months(start,end):
    a=pd.Timestamp(start,unit="ms",tz="UTC").to_period("M")
    b=pd.Timestamp(end-1,unit="ms",tz="UTC").to_period("M")
    return [str(x) for x in pd.period_range(a,b,freq="M")]

def get(url,optional=False):
    for i in range(3):
        try:
            r=CLIENT.get(url,timeout=(8,28))
            if r.status_code==404 and optional: return None
            if r.status_code in (403,418,429,451): raise ValueError(f"Archive source rejected access HTTP {r.status_code}")
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if i==2: raise
            time.sleep(1+i)
    raise ValueError("Archive download failed")

def archive(symbol,kind,month,optional=True):
    if not symbol.isalnum() or not symbol.endswith("USDT"): raise ValueError("Invalid futures symbol")
    if kind=="klines": rel=f"klines/{symbol}/15m/{symbol}-15m-{month}.zip"
    elif kind=="fundingRate": rel=f"fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
    else: raise ValueError("Bad dataset")
    path=CACHE/rel
    if path.exists(): raw=path.read_bytes()
    else:
        raw=get(BASE+"/"+rel,optional=optional)
        if raw is None: return None
        checksum=get(BASE+"/"+rel+".CHECKSUM",optional=True)
        if checksum:
            expected=checksum.decode("ascii").split()[0]
            if hashlib.sha256(raw).hexdigest().lower()!=expected.lower(): raise ValueError("SHA256 checksum failed: "+rel)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
    with ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if n.endswith(".csv") and ".." not in n]
        if len(names)!=1: raise ValueError("Unexpected ZIP layout")
        return z.read(names[0])

def listing():
    # Historical archive can include delisted contracts. This is NOT today's tradable universe.
    prefix="data/futures/um/monthly/klines/"
    continuation=None; symbols=[]
    ns={"x":"http://s3.amazonaws.com/doc/2006-03-01/"}
    for _ in range(12):
        params={"list-type":"2","prefix":prefix,"delimiter":"/","max-keys":"1000"}
        if continuation: params["continuation-token"]=continuation
        r=CLIENT.get(S3,params=params,timeout=(8,28))
        r.raise_for_status()
        root=ET.fromstring(r.content)
        for n in root.findall("x:CommonPrefixes/x:Prefix",ns):
            s=n.text[len(prefix):].strip("/")
            if s.endswith("USDT") and s.isalnum() and len(s)<35: symbols.append(s)
        if root.findtext("x:IsTruncated",default="false",namespaces=ns)!="true": break
        continuation=root.findtext("x:NextContinuationToken",namespaces=ns)
        if not continuation: raise ValueError("Truncated archive symbol index")
    else: raise ValueError("Too many symbol index pages")
    base=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","SUIUSDT","DOGEUSDT","LINKUSDT","ADAUSDT","1000PEPEUSDT","WIFUSDT","TAOUSDT"]
    names=[s for s in base if s in symbols]+sorted(set(symbols)-set(base))
    if not names: raise ValueError("No archive universe available")
    return names

def load(symbol,start,end):
    frames=[]; funding=[]; began=False
    for mon in months(start,end):
        raw=archive(symbol,"klines",mon)
        if raw is None:
            if began: raise ValueError(f"Missing interior kline archive {symbol} {mon}")
            continue
        began=True
        f=pd.read_csv(io.BytesIO(raw))
        if "open_time" not in f.columns: f=pd.read_csv(io.BytesIO(raw),header=None,names=COLUMNS)
        needed=["open_time","open","high","low","close","volume"]
        if not set(needed).issubset(f.columns): raise ValueError("Bad candles CSV schema")
        f=f[needed].apply(pd.to_numeric,errors="raise")
        frames.append(f)
        ff=archive(symbol,"fundingRate",mon,optional=False)
        y=pd.read_csv(io.BytesIO(ff))
        if not {"calc_time","last_funding_rate"}.issubset(y.columns): raise ValueError("Bad funding schema")
        if len(y):
            q=y[["calc_time","last_funding_rate"]].rename(columns={"calc_time":"time","last_funding_rate":"rate"})
            funding.append(q.apply(pd.to_numeric,errors="raise"))
    if not frames: raise ValueError("No contract archive")
    bars=pd.concat(frames,ignore_index=True)
    bars=bars[(bars.open_time>=start)&(bars.open_time+900000<=end)]
    bars=bars.drop_duplicates("open_time").sort_values("open_time")
    if len(bars)<96*30: raise ValueError("Under 30 days candles")
    ts=bars.open_time.to_numpy("int64")
    if (np.diff(ts)!=900000).any(): raise ValueError("Missing 15m candles, no interpolation")
    if (bars.low<=0).any() or (bars.low>bars[["open","close"]].min(axis=1)).any() or (bars.high<bars[["open","close"]].max(axis=1)).any(): raise ValueError("Invalid OHLC")
    if not funding: raise ValueError("No funding archive")
    df=bars.set_index(pd.to_datetime(bars.open_time,unit="ms",utc=True))[["open","high","low","close","volume"]].astype(float)
    ff=pd.concat(funding,ignore_index=True).drop_duplicates("time").sort_values("time")
    ff=ff[(ff.time>=start)&(ff.time<end)].copy()
    if ff.empty: raise ValueError("No funding events within history")
    ft=ff.time.to_numpy("int64")
    if (np.diff(ft)>2*86400000).any(): raise ValueError("Funding archive has gaps >48h")
    # Funding event has no mark price column. Proxy with last FULLY CLOSED
    # 15m candle close; never leak the future candle's close into funding.
    pos=np.searchsorted(ts+900000,ft,side="right")-1
    valid=pos>=0
    ff=ff.iloc[np.flatnonzero(valid)].copy()
    if ff.empty: raise ValueError("No funding events with historical price proxy")
    ff["mark"]=df.close.to_numpy()[pos[valid]]
    return df,ff.reset_index(drop=True)
