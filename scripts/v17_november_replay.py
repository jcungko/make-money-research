#!/usr/bin/env python3
"""V17: independently replay the eight selected Exness strategies in November 2026.
Read-only. Historic Exness V17 M5 archive + refreshed public daily tick ZIPs.
No trading APIs or credentials. Exact entry/exit scheme is V17 strategy_screen.py.
"""
import io
import json
import struct
import time
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from v17_strategy_screen import signal_generator

DATA_DIR = Path("data/v17_exness_2026")
OUT = Path("results/v17_november_2026")
SPECS = (
    (2,"USDJPY","M15","ema_3_8",18,2,-1,"long_only"),
    (6,"USDJPY","D1","close_vs_sma_10",14,6,-1,"long_only"),
    (9,"USDJPY","M5","close_vs_sma_40",18,2,-1,"long_only"),
    (10,"USDJPY","M15","rsi50_7",18,2,-1,"long_only"),
    (11,"USDJPY","M5","ema_8_21",18,2,-1,"long_only"),
    (12,"USDJPY","D1","return_1",18,2,-1,"long_only"),
    (13,"USDJPY","D1","body_1",18,2,-1,"long_only"),
    (15,"EURUSD","H4","return_20",14,1,1,"long_only"),
)
COLS = ("bid_open","bid_high","bid_low","bid_close",
        "ask_open","ask_high","ask_low","ask_close","tick_count")
AGG = {
    "bid_open":"first","bid_high":"max","bid_low":"min","bid_close":"last",
    "ask_open":"first","ask_high":"max","ask_low":"min","ask_close":"last",
    "tick_count":"sum"
}
PIP = {"USDJPY":0.01,"EURUSD":0.0001}
START = pd.Timestamp("2026-11-01T00:00:00Z")
TODAY = pd.Timestamp("2026-11-12T00:00:00Z")
END = pd.Timestamp("2026-11-13T00:00:00Z")


def unzip_csv(raw):
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            files=[n for n in z.namelist() if n.lower().endswith(".csv") and ".." not in n]
            if len(files)!=1:
                raise ValueError("unexpected tick ZIP member list")
            return z.read(files[0]), "valid_zip"
    if not raw.startswith(bytes((80,75,3,4))) or len(raw)<35:
        raise ValueError("not a valid ZIP or recoverable partial ZIP")
    method=struct.unpack_from("<H",raw,8)[0]
    nlen,xlen=struct.unpack_from("<HH",raw,26)
    if method!=8 or 30+nlen+xlen>=len(raw):
        raise ValueError("unsupported partial ZIP deflate compression")
    decoder=zlib.decompressobj(-zlib.MAX_WBITS)
    body=decoder.decompress(raw[30+nlen+xlen:])+decoder.flush()
    if b"\n" not in body:
        raise ValueError("no complete tick records in truncated ZIP")
    return body[:body.rfind(b"\n")+1],"recovered_partial_zip"


def fresh_ticks(session,symbol,day):
    date=pd.Timestamp(day)
    ds=date.strftime("%Y_%m_%d")
    url=f"https://ticks.ex2archive.com/ticks/{symbol}/{date.year}/{date.month:02d}/{date.day:02d}/Exness_{symbol}_{ds}.zip"
    last=None
    for attempt in range(3):
        try:
            resp=session.get(url,timeout=(10,75),headers={"User-Agent":"V17-Exness-research-read-only/1.0","Cache-Control":"no-cache"})
            resp.raise_for_status()
            raw,status=unzip_csv(resp.content)
            df=pd.read_csv(io.BytesIO(raw),header=None,names=["provider","symbol","timestamp","bid","ask"],
                on_bad_lines="skip",low_memory=False)
            df["timestamp"]=pd.to_datetime(df["timestamp"],utc=True,errors="coerce",format="mixed")
            df["bid"]=pd.to_numeric(df["bid"],errors="coerce")
            df["ask"]=pd.to_numeric(df["ask"],errors="coerce")
            begin=pd.Timestamp(day,tz="UTC")
            df=df[(df["symbol"]==symbol)&(df["timestamp"]>=begin)&
                  (df["timestamp"]<begin+pd.Timedelta(days=1))&
                  (df["timestamp"]>=START)&(df["timestamp"]<END)&
                  (df["bid"]>0)&(df["ask"]>=df["bid"])]
            df=df.sort_values("timestamp").drop_duplicates("timestamp",keep="last")
            if df.empty:
                raise ValueError("no valid quotes")
            info={"url":url,"date":str(day),"zip_status":status,"download_bytes":len(resp.content),
                  "tick_count":len(df),"last_modified":resp.headers.get("Last-Modified"),
                  "first_tick_utc":df["timestamp"].iloc[0].isoformat(),
                  "last_tick_utc":df["timestamp"].iloc[-1].isoformat()}
            return df,info
        except Exception as e:
            last=e
            if attempt<2:time.sleep(attempt+1)
    raise RuntimeError(f"{symbol} {day}: {last}")


def tick_to_m5(ticks,cutoff):
    ticks=ticks[ticks["timestamp"]<cutoff].copy()
    ticks["bucket"]=ticks["timestamp"].dt.floor("5min")
    m5=ticks.groupby("bucket",sort=True).agg(
        bid_open=("bid","first"),bid_high=("bid","max"),bid_low=("bid","min"),bid_close=("bid","last"),
        ask_open=("ask","first"),ask_high=("ask","max"),ask_low=("ask","min"),ask_close=("ask","last"),
        tick_count=("bid","size"))
    m5.index.name="timestamp_utc"
    return m5


def read_history(symbol):
    with zipfile.ZipFile(DATA_DIR/f"{symbol}_2026_UTC_7TF.zip") as z:
        p=f"{symbol}_M5_2026_UTC.csv"
        f=pd.read_csv(io.BytesIO(z.read(p)),index_col=0,parse_dates=[0])
        f.index=pd.to_datetime(f.index,utc=True)
        meta=json.loads(z.read("manifest.json"))
        if meta.get("symbol")!=symbol or meta.get("year")!=2026:
            raise ValueError("unexpected historical source")
        if not f.index.is_monotonic_increasing or f.index.has_duplicates:
            raise ValueError("historic M5 invalid")
        return f,meta


def make_frame(m5,tf):
    if tf=="M5":return m5
    freq={"M15":"15min","H4":"4h","D1":"1D"}[tf]
    f=m5.resample(freq,label="left",closed="left",origin="epoch").agg(AGG)
    return f[f.tick_count>0]


def trade_ledger(symbol,source,frames,last_complete_exclusive):
    results=[]
    m5=frames["M5"]
    times=m5.index
    nanos=times.asi8
    steps_len=len(times)
    pip=PIP[symbol]
    for sid,spair,tf,signal_name,hour,hold,polarity,side in SPECS:
        if spair!=symbol:continue
        gen=dict(signal_generator(frames[tf]))
        if signal_name not in gen:
            raise ValueError(f"Missing strategy signal {sid}: {signal_name}")
        raw=gen[signal_name]
        shifted=raw.shift(1,fill_value=0).reindex(times,method="ffill").fillna(0).to_numpy(dtype=np.int8)
        base=np.flatnonzero((times.hour==hour)&(times.minute==0)&
            (times>=START)&(times<END)&(shifted*polarity>0)).astype(int)
        if side!="long_only":raise ValueError("V17 selection expected long-only")
        for i in base:
            end_idx=i+12*hold-1
            if end_idx>=steps_len:
                results.append({"strategy":sid,"symbol":symbol,"status":"PENDING_NOT_EXITED",
                                "entry_utc":times[i].isoformat(),"exit_utc":None,"pnl_pips":None})
                continue
            # V17: whole holding span must consist of contiguous five-minute OHLC bars.
            if nanos[end_idx]-nanos[i]!=(12*hold-1)*300_000_000_000:
                continue
            end=times[end_idx]+pd.Timedelta(minutes=5)
            if end>last_complete_exclusive:
                results.append({"strategy":sid,"symbol":symbol,"status":"PENDING_NOT_EXITED",
                                "entry_utc":times[i].isoformat(),"exit_utc":None,"pnl_pips":None})
                continue
            pnl=(float(m5.bid_close.iloc[end_idx])-float(m5.ask_open.iloc[i]))/pip - 0.2
            results.append({"strategy":sid,"symbol":symbol,"status":"CLOSED",
                "entry_utc":times[i].isoformat(),"exit_utc":times[end_idx].isoformat(),
                "pnl_pips":round(pnl,3)})
    return results


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    now=pd.Timestamp.now(tz="UTC")
    # Never include incomplete 5-minute candles. Today is 12 November in Vietnam.
    safety_cutoff=min(now.floor("5min")-pd.Timedelta(minutes=5),END)
    dataset={"created_utc":now.isoformat(),"safety_cutoff_exclusive_utc":safety_cutoff.isoformat(),
      "requested_date_ict":"2026-11-12","strategies":[s[0] for s in SPECS],
      "execution":"entry long at ask_open; exit at bid_close after H hours; extra 0.2 pip full round trip",
      "symbols":{},"trades":[],"errors":[]}
    with requests.Session() as sess:
        for symbol in PIP:
            history,meta=read_history(symbol)
            # Fetch Nov 11 and 12: previous Exness archive has complete M5 only through Nov 10.
            parts=[];sources=[]
            for day in ("2026-11-11","2026-11-12"):
                try:
                    ticks,info=fresh_ticks(sess,symbol,day)
                    parts.append(ticks)
                    sources.append(info)
                    print("SOURCE",symbol,day,len(ticks),info["last_tick_utc"],flush=True)
                except Exception as exc:
                    dataset["errors"].append(str(exc))
                    print("ERROR",symbol,day,str(exc),flush=True)
            if not parts:
                raise RuntimeError(f"{symbol}: no fresh daily tick prices were retrieved")
            combined=pd.concat(parts,ignore_index=True).sort_values("timestamp")
            last_tick=pd.Timestamp(combined.timestamp.max())
            # Latest tick bucket may be partial even though the calendar interval is complete.
            last_tick_bucket=last_tick.floor("5min")
            verified_exclusive=min(safety_cutoff,last_tick_bucket)
            recent=tick_to_m5(combined,verified_exclusive)
            if recent.empty:
                raise RuntimeError(f"{symbol}: no complete new 5m candles")
            if recent.index.min() > pd.Timestamp("2026-11-11T00:10:00Z"):
                raise RuntimeError(f"{symbol}: no near-midnight data for Nov 11")
            if not any(s["date"]=="2026-11-12" for s in sources):
                # Do not pretend the current date has been backtested if its quotes are missing.
                raise RuntimeError(f"{symbol}: current day public ticks unavailable")
            # Do not overwrite historical archive points with current-day snapshots.
            concat=pd.concat([history, recent]).sort_index()
            concat=concat[~concat.index.duplicated(keep="first")]
            if concat.index.max()<pd.Timestamp("2026-11-12T00:00:00Z"):
                raise RuntimeError(f"{symbol}: recent quotes do not cover 12 Nov")
            # Detect missing 5-minute bars on weekday Nov 11, when Forex market is open.
            nov11=concat.loc["2026-11-11T00:00:00Z":"2026-11-11T23:55:00Z"]
            valid_ranges=np.diff(nov11.index.asi8)==300_000_000_000
            if (not len(nov11)) or len(nov11)<280:
                raise RuntimeError(f"{symbol}: Nov11 source incomplete ({len(nov11)}/288 possible M5 buckets)")
            # Quote gaps are preserved, never filled with invented candles. Individual
            # trades crossing a gap are already disqualified by trade_ledger().
            gaps = int((~valid_ranges).sum())
            print("DATA_GAPS", symbol, "Nov11", gaps, "M5 gaps",flush=True)
            frames={tf:make_frame(concat,tf) for tf in {spec[2] for spec in SPECS if spec[1]==symbol}}
            frames["M5"]=concat
            ledger=trade_ledger(symbol,meta,frames,verified_exclusive)
            dataset["trades"].extend(ledger)
            dataset["symbols"][symbol]={
                "historical_source":"V17 Exness 2026 UTC seven-timeframe archive",
                "archive_last_M5_utc":history.index.max().isoformat(),
                "new_source_tick_history":sources,
                "fresh_last_tick_utc":last_tick.isoformat(),
                "last_completed_m5_candle_utc":concat.index.max().isoformat(),
                "cutoff_exclusive_utc":verified_exclusive.isoformat(),
                "total_closed_trades":sum(t["status"]=="CLOSED" for t in ledger),
                "data_provenance":meta.get("source_months")
            }
    by_strategy=[]
    for sid,spair,tf,name,hour,hold,polarity,side in SPECS:
        closed=[x for x in dataset["trades"] if x["strategy"]==sid and x["status"]=="CLOSED"
            and x["exit_utc"][:7]=="2026-11"]
        pending=[x for x in dataset["trades"] if x["strategy"]==sid and x["status"]!="CLOSED"]
        pnl=sum(t["pnl_pips"] for t in closed)
        by_strategy.append({"id":sid,"symbol":spair,"timeframe":tf,"signal":name,
            "entry_hour_utc":hour,"entry_hour_ict":(hour+7)%24,
            "holding_hours":hold,"direction":"long_only" if side=="long_only" else side,
            "closed_trades":len(closed),"winning_trades":sum(t["pnl_pips"]>0 for t in closed),
            "losing_trades":sum(t["pnl_pips"]<0 for t in closed),
            "profit_pips":round(pnl,3),"pending_entries":len(pending),
            "last_closed_trade_exit_utc":max((x["exit_utc"] for x in closed),default=None)})
    dataset["result"]=by_strategy
    dataset["total_closed_trades"]=sum(x["closed_trades"] for x in by_strategy)
    dataset["total_profit_pips"]=round(sum(x["profit_pips"] for x in by_strategy),3)
    dataset["all_8_positive"]=all(x["profit_pips"]>0 for x in by_strategy)
    dataset["all_sources_complete"]=not dataset["errors"]
    (OUT/"report.json").write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pd.DataFrame(dataset["trades"]).sort_values(["entry_utc","strategy"]).to_csv(OUT/"trades.csv",index=False)
    pd.DataFrame(by_strategy).to_csv(OUT/"summary.csv",index=False)
    print("FINAL_V17_NOVEMBER",json.dumps({"asof_utc":now.isoformat(),"result":by_strategy,
            "total_profit_pips":dataset["total_profit_pips"],
            "total_closed_trades":dataset["total_closed_trades"],
            "errors":dataset["errors"]},ensure_ascii=False),flush=True)
    if dataset["errors"]:
        raise RuntimeError("Snapshot has missing source days: do not consider complete.")

if __name__=="__main__":
    main()
