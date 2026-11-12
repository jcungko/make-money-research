#!/usr/bin/env python3
"""V19: November 2026 read-only out-of-sample replay for the 22 locked portfolios.

Inputs: committed V19 2026 Exness archives through Oct 31; Exness PUBLIC
daily bid/ask tick ZIPs through Nov 12, 2026, via ticks.ex2archive.com.
No accounts, trading endpoints, automatic orders, or model re-optimization.

Trade semantics reproduce V19 screen: signal uses last closed bar, enter at
present bar's first quote, exit at future bar's first quote after H bars.
No SL/TP, fixed 1bp entry+exit slippage on top of observed spread.
PnL: unleveraged basis points of 1 unit of entry mid notional per leg,
combined 4 legs equally by arithmetic average.
"""
import argparse
import hashlib
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

import v19_strategy_screen as v19

NAMES = ("USOIL", "UKOIL")
START = pd.Timestamp("2026-11-01T00:00:00Z")
# This end is strictly less than the user's real-time current UTC timestamp (Nov 12).
END = pd.Timestamp("2026-11-13T00:00:00Z")
COLS = ("bid_open", "bid_high", "bid_low", "bid_close", "ask_open", "ask_high", "ask_low", "ask_close", "tick_count")
FRQ = {"M5":"5min","M15":"15min","M30":"30min","H1":"1h","H4":"4h"}
ZIP_PREFIX = "https://ticks.ex2archive.com/ticks"
SLIPPAGE = 0.0001


def unpack_one_csv(raw):
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = [name for name in z.namelist() if name.lower().endswith(".csv") and ".." not in name]
            if len(names) != 1:
                raise ValueError(f"unexpected ZIP contents: {names}")
            return z.read(names[0]), "complete_zip"
    # Some current-day Exness archives stream ZIP content without central directory.
    if len(raw) < 31 or raw[:4] != b"PK\x03\x04":
        raise ValueError("not ZIP and no recoverable local ZIP header")
    method = struct.unpack_from("<H", raw, 8)[0]
    name_len, extra_len = struct.unpack_from("<HH", raw, 26)
    offset = 30 + name_len + extra_len
    if method != 8 or offset >= len(raw):
        raise ValueError("unsupported partial ZIP")
    body = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw[offset:])
    if b"\n" not in body:
        raise ValueError("partial ZIP yielded no complete rows")
    return body[:body.rfind(b"\n")+1], "recovered_partial_zip"


def load_ticks_from_zip(session, symbol, date, upper_bound):
    dt = pd.Timestamp(date)
    date_part = dt.strftime("%Y_%m_%d")
    url = f"{ZIP_PREFIX}/{symbol}/2026/11/{dt.day:02d}/Exness_{symbol}_{date_part}.zip"
    response = session.get(url, timeout=(15, 90), headers={"Cache-Control":"no-cache", "User-Agent":"V19-Exness-public-Nov2026-replay"})
    if response.status_code == 404:
        return None, {"date":str(dt.date()), "url":url, "status":"404_missing_or_market_closed"}
    response.raise_for_status()
    csv_data, state = unpack_one_csv(response.content)
    frame = pd.read_csv(io.BytesIO(csv_data), header=None, names=["provider", "symbol", "ts", "bid", "ask"],
                        on_bad_lines="skip", low_memory=False)
    frame["ts"] = pd.to_datetime(frame.ts, utc=True, errors="coerce", format="mixed")
    frame["bid"] = pd.to_numeric(frame.bid, errors="coerce")
    frame["ask"] = pd.to_numeric(frame.ask, errors="coerce")
    target_day = pd.Timestamp(str(dt.date()),tz="UTC")
    frame = frame.loc[
        (frame.symbol == symbol) & (frame.ts >= target_day) &
        (frame.ts < target_day + pd.Timedelta(days=1)) &
        (frame.ts < upper_bound) &
        (frame.bid > 0) & (frame.ask >= frame.bid),
        ["ts", "bid", "ask"]
    ]
    frame = frame.drop_duplicates("ts", keep="last").sort_values("ts")
    if frame.empty:
        raise ValueError(f"{symbol} {dt.date()} had empty valid ticks")
    provenance = {
        "date": str(dt.date()), "url":url, "zip_status":state,
        "zip_sha256":hashlib.sha256(response.content).hexdigest(),
        "compressed_bytes":len(response.content),
        "valid_ticks":len(frame),
        "first_tick_utc":frame.ts.iloc[0].isoformat(),
        "last_tick_utc":frame.ts.iloc[-1].isoformat(),
        "source_last_modified":response.headers.get("Last-Modified")
    }
    return frame, provenance


def ticks_to_m5(ticks):
    data = ticks.copy()
    data["bucket"] = data.ts.dt.floor("5min")
    m5 = data.groupby("bucket",sort=True).agg(
        bid_open=("bid","first"),bid_high=("bid","max"),bid_low=("bid","min"),bid_close=("bid","last"),
        ask_open=("ask","first"),ask_high=("ask","max"),ask_low=("ask","min"),
        ask_close=("ask","last"),tick_count=("bid","size")
    )
    m5.index.name="timestamp_utc"
    return m5


def gather_november(root, end, session):
    out = {}
    manifest = {}
    for sym in NAMES:
        months = []
        for day in pd.date_range(START, end-pd.Timedelta(nanoseconds=1), freq="D"):
            last = None
            for attempt in range(3):
                try:
                    tick, details = load_ticks_from_zip(session, sym, day, end)
                    if tick is not None:
                        months.append(tick)
                    manifest.setdefault(sym,[]).append(details)
                    print("V19_SOURCE",sym,day.strftime("%Y-%m-%d"),details.get("status", details.get("valid_ticks")), flush=True)
                    last = None
                    break
                except Exception as exc:
                    last = exc
                    if attempt < 2:
                        time.sleep(2**attempt)
            if last is not None:
                raise RuntimeError(f"Failed {sym} {day}: {last}")
        if not months:
            raise RuntimeError(f"No November source ticks: {sym}")
        ticks = pd.concat(months,ignore_index=True).drop_duplicates("ts",keep="last").sort_values("ts")
        # Exclude source's active last M5 window until complete (this is a
        # conservative cutoff even when latest daily file is being updated).
        cutoff = min(end, ticks.ts.iloc[-1].floor("5min"))
        final = ticks[ticks.ts < cutoff]
        if final.empty:
            raise RuntimeError(f"No completed M5 window: {sym}")
        m5 = ticks_to_m5(final)
        if len(m5)<100:
            raise RuntimeError(f"Insufficient November history: {sym}")
        if m5.index.has_duplicates or not m5.index.is_monotonic_increasing:
            raise RuntimeError("M5 disordered")
        out[sym] = m5
        manifest[sym + "_summary"] = {
            "first_tick_utc":ticks.ts.iloc[0].isoformat(),
            "last_tick_utc":ticks.ts.iloc[-1].isoformat(),
            "last_complete_m5_candle_utc":m5.index[-1].isoformat(),
            "complete_m5_cutoff_exclusive_utc":cutoff.isoformat(),
            "m5_rows":len(m5),
            "total_ticks_used":int(m5.tick_count.sum()),
            "downloaded_day_archives":sum(1 for x in manifest[sym] if "valid_ticks" in x),
            "missing_days": [x["date"] for x in manifest[sym] if "status" in x]
        }
        print("V19_NOV_SOURCE_READY",sym,json.dumps(manifest[sym+"_summary"]), flush=True)
    return out, manifest


def rebuild_frames(history_dir, symbol, m5):
    """Preserve ALL historical Exness 2026 bars for indicator warm-up."""
    frames={}
    for tf,freq in FRQ.items():
        prior = v19.read_frame(history_dir, symbol, tf)
        old = prior[prior.timestamp_utc < START].copy()
        next_data = m5 if tf=="M5" else m5.resample(freq,origin="epoch",label="left",closed="left").agg({
            "bid_open":"first", "bid_high":"max", "bid_low":"min", "bid_close":"last",
            "ask_open":"first", "ask_high":"max", "ask_low":"min", "ask_close":"last",
            "tick_count":"sum"
        })
        next_data = next_data[next_data.tick_count > 0].copy()
        next_data = next_data.reset_index()
        frames[tf] = pd.concat([old,next_data],ignore_index=True)
        frames[tf] = frames[tf].drop_duplicates("timestamp_utc").sort_values("timestamp_utc").reset_index(drop=True)
        if not frames[tf].timestamp_utc.is_monotonic_increasing:
            raise RuntimeError(f"Unsorted frame {symbol} {tf}")
    return frames


def replay_one_leg(df, leg, cutoff):
    sym, tf, signal, side, hold_text, session = leg.split("|")
    hold = int(hold_text[1:])
    timestamp = df.timestamp_utc
    n=len(df)
    t=timestamp.dt
    openbid = df.bid_open.to_numpy(dtype=float)
    openask = df.ask_open.to_numpy(dtype=float)
    mid=(openbid+openask)/2
    valid=np.isfinite(mid)&(mid>0)&np.isfinite(openbid)&np.isfinite(openask)&(openask>=openbid)
    choices=v19.signals(df)
    if signal not in choices:
        raise ValueError(f"Unknown signal {signal}")
    allowed=choices[signal] & valid & (timestamp >= START).to_numpy() & (timestamp < cutoff).to_numpy()
    if session!="all":
        allowed &= (t.hour.to_numpy()==int(session[:2]))&(t.minute.to_numpy()==0)
    entries = v19.pick_nonoverlap(np.flatnonzero(allowed),hold)
    ledger=[]
    for i in entries:
        target=i+hold
        future_known = target<n
        if future_known:
            exit_time=timestamp.iloc[target]
            future_known=bool((exit_time<=cutoff) and valid[target])
        else:
            exit_time=None
        if future_known:
            if side=="long":
                pnl=(openbid[target]*(1-SLIPPAGE)-openask[i]*(1+SLIPPAGE))/mid[i]*10000
            elif side=="short":
                pnl=(openbid[i]*(1-SLIPPAGE)-openask[target]*(1+SLIPPAGE))/mid[i]*10000
            else:
                raise ValueError(side)
            ledger.append({"symbol":sym,"timeframe":tf,"leg":leg,"side":side,"status":"closed",
                           "entry_utc":timestamp.iloc[i].isoformat(),"exit_utc":exit_time.isoformat(),
                           "pnl_bp":round(float(pnl),6)})
        else:
            ledger.append({"symbol":sym,"timeframe":tf,"leg":leg,"side":side,"status":"open",
                           "entry_utc":timestamp.iloc[i].isoformat(),"exit_utc":None,"pnl_bp":None})
    return ledger


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--history",type=Path,default=Path("data/v19_energies"))
    parser.add_argument("--selected",type=Path,default=Path("data/v19_strategy_screen/V19_22_profit_then_orders_filtered.json"))
    parser.add_argument("--out",type=Path,default=Path("results/v19_november_2026"))
    parser.add_argument("--until",default="2026-11-12T18:00:00Z",
                        help="exclusive UTC upper limit; never use future times")
    args=parser.parse_args()
    cutoff=pd.Timestamp(args.until).tz_convert("UTC")
    if cutoff<=START or cutoff>END:
        raise ValueError("Invalid cutoff")
    selection=json.loads(args.selected.read_text())
    candidates=selection["retained"]
    assert len(candidates)==22 and all(len(c["legs"])==4 for c in candidates)
    args.out.mkdir(parents=True,exist_ok=True)
    with requests.Session() as session:
        nov_m5,source=gather_november(args.history,cutoff,session)

    # Persist derived portable M5 bars for independent replay.
    for sym,m5 in nov_m5.items():
        m5.to_csv(args.out/f"{sym}_2026-11_M5_UTC.csv.gz",compression="gzip",float_format="%.6f")
    frame_cache={sym:rebuild_frames(args.history,sym,nov_m5[sym]) for sym in NAMES}
    legs=sorted({item for q in candidates for item in q["legs"]})
    leg_results={}
    for leg in legs:
        sym,tf,*_=leg.split("|")
        record=replay_one_leg(frame_cache[sym][tf],leg,cutoff)
        leg_results[leg]=record
        print("V19_NOV_LEG",leg,len(record),sum(x["status"]=="closed" for x in record),
              round(sum(x["pnl_bp"] for x in record if x["status"]=="closed"),4),flush=True)

    rows=[]
    for item in candidates:
        all_legs=[leg_results[x] for x in item["legs"]]
        closed=sum((record for leg in all_legs for record in leg if record["status"]=="closed"),[])
        open_now=sum((record for leg in all_legs for record in leg if record["status"]=="open"),[])
        total_bp=sum(x["pnl_bp"] for x in closed)/4
        rows.append({
            "id":item["portfolio"],"family":item["family"],
            "historical_21plus_months":item["positive_months"],
            "historical_profit_bp":item["total_profit_bp"],
            "november_realized_profit_bp":round(float(total_bp),5),
            "november_closed_orders":len(closed),
            "november_open_orders":len(open_now),
            "november_total_order_signals":len(closed)+len(open_now),
            "november_winning_orders":sum(x["pnl_bp"]>0 for x in closed),
            "november_losing_orders":sum(x["pnl_bp"]<0 for x in closed),
            "leg_details":[{
                "leg":name,
                "closed_orders":sum(x["status"]=="closed" for x in leg_results[name]),
                "open_orders":sum(x["status"]=="open" for x in leg_results[name]),
                "realized_profit_bp":round(sum(x["pnl_bp"] for x in leg_results[name] if x["status"]=="closed"),5),
            }for name in item["legs"]],
        })
    rows.sort(key=lambda x:x["november_realized_profit_bp"],reverse=True)
    profits=sum(x["november_realized_profit_bp"]>0 for x in rows)
    losses=sum(x["november_realized_profit_bp"]<0 for x in rows)
    break_even=len(rows)-profits-losses
    result={
        "project":"V19","study":"Out-of-sample November 2026 replay of locked 22 selected four-leg energy strategies",
        "source_selection":str(args.selected),"no_reoptimization":True,"no_live_trade_execution":True,
        "month":"2026-11",
        "requested_cutoff_exclusive_utc":cutoff.isoformat(),
        "complete_m5_source_cutoff_by_symbol_utc":{sym:source[sym+"_summary"]["complete_m5_cutoff_exclusive_utc"] for sym in NAMES},
        "execution_assumptions":"Previous completed bar signal, open first bid/ask; exit at future frame open H bars later; no overlapping positions within each leg, different legs allowed hedged overlaps.",
        "costs":"Observed Bid-Ask spread plus 1bp slippage per side; no swaps, financing, commissions or margin rules",
        "pnl_units":"bp of equal unit notional allocated 1/4 per independent leg; monthly realized profit only, unfinished trades excluded from PnL",
        "counts":{"tested":len(rows),"profitable":profits,"losing":losses,"break_even":break_even},
        "source":source,"rows":rows
    }
    (args.out/"V19_nov2026_22_replay.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame([{k:v for k,v in r.items() if k!="leg_details"} for r in rows]).to_csv(args.out/"V19_nov2026_22_summary.csv",index=False)
    with (args.out/"V19_nov2026_leg_ledger.json").open("w") as f:
        json.dump(leg_results,f,ensure_ascii=False,indent=2)
    print("V19_NOV_FINAL",json.dumps({
        "cutoff":cutoff.isoformat(),"counts":result["counts"],
        "leaders":[{k:x[k] for k in ("id","november_realized_profit_bp","november_closed_orders","november_open_orders")} for x in rows[:5]],
        "tail":[{k:x[k] for k in ("id","november_realized_profit_bp","november_closed_orders","november_open_orders")} for x in rows[-5:]],
        "source_cutoffs":result["complete_m5_source_cutoff_by_symbol_utc"]
    }),flush=True)


if __name__=="__main__":
    main()
