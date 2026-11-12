#!/usr/bin/env python3
"""V21: November 2026 independent out-of-sample replay of previously frozen 50 portfolios.

No orders or broker credentials. EXACT V19 signal definitions, next-bar open fills,
historical Bid/Ask and 1bp per-side slippage. Portfolio PnL is the average of four
separate leg PnLs at equal fixed notional (NOT cash USD or compound return).

NOTE: Input list is frozen in data/v21_crypto_screen/V21_filtered_top_profit_then_top_trades_50.json
No new parameter optimization permitted for November.
"""
from __future__ import annotations
import io, json, struct, sys, time, zipfile, zlib
from pathlib import Path
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, "scripts")
import v19_strategy_screen as engine
from v12_exness_collect import FIELDS

ROOT = Path("data/v21_crypto")
INPUT = Path("data/v21_crypto_screen/V21_filtered_top_profit_then_top_trades_50.json")
OUT = Path("data/v21_november_replay")
START = pd.Timestamp("2026-11-01T00:00:00Z")
CEILING = pd.Timestamp("2026-11-13T00:00:00Z")
SYMBOLS = ("BTCUSD", "ETHUSD")
DAYS = tuple(pd.date_range("2026-11-01", "2026-11-12", tz="UTC", freq="D"))
FRAMES = {"M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h"}

def recover_csv(raw: bytes):
    f = io.BytesIO(raw)
    if zipfile.is_zipfile(f):
        with zipfile.ZipFile(f) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".csv") and ".." not in n]
            if len(names) != 1: raise ValueError(f"unexpected CSV members {names}")
            return z.read(names[0]), "valid_complete_zip"
    if not raw.startswith(b"PK\x03\x04") or len(raw) < 35:
        raise ValueError("Not ZIP, partial ZIP, or missing ZIP header")
    method = struct.unpack_from("<H", raw, 8)[0]
    nlen, xlen = struct.unpack_from("<HH", raw, 26)
    off = 30 + nlen + xlen
    if method != 8 or off >= len(raw):
        raise ValueError("unsupported partial ZIP structure")
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    body = decoder.decompress(raw[off:]) + decoder.flush()
    if b"\n" not in body: raise ValueError("no complete CSV rows in incomplete ZIP")
    return body[:body.rfind(b"\n")+1], "recoverable_partial_zip"

def fetch_daily(session, symbol, day, effective):
    label = day.strftime("%Y-%m-%d")
    stamp = day.strftime("%Y_%m_%d")
    url = (f"https://ticks.ex2archive.com/ticks/{symbol}/2026/11/"
           f"{day.day:02d}/Exness_{symbol}_{stamp}.zip")
    err = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=(15, 100),
                headers={"Cache-Control": "no-cache", "User-Agent": "V21-Exness-November-replay/1.0"})
            response.raise_for_status()
            csv_data, status = recover_csv(response.content)
            data = pd.read_csv(io.BytesIO(csv_data), header=None,
                names=["provider","symbol","timestamp","bid","ask"],
                on_bad_lines="skip", low_memory=False)
            data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True,
                errors="coerce", format="mixed")
            data["bid"] = pd.to_numeric(data["bid"], errors="coerce")
            data["ask"] = pd.to_numeric(data["ask"], errors="coerce")
            data = data[(data["symbol"] == symbol) &
                (data["timestamp"] >= day) &
                (data["timestamp"] < day + pd.Timedelta(days=1)) &
                (data["timestamp"] < effective) &
                (data["bid"] > 0) & (data["ask"] >= data["bid"])]
            data = data.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
            if data.empty: raise ValueError("no valid tick rows before cutoff")
            last_tick = data["timestamp"].iloc[-1]
            data["bucket"] = data["timestamp"].dt.floor("5min")
            bars = data.groupby("bucket", sort=True).agg(
                bid_open=("bid", "first"), bid_high=("bid", "max"),
                bid_low=("bid", "min"), bid_close=("bid", "last"),
                ask_open=("ask", "first"), ask_high=("ask", "max"),
                ask_low=("ask", "min"), ask_close=("ask", "last"),
                tick_count=("bid", "size"))
            bars.index.name = "timestamp_utc"
            return bars, {
                "day": label, "url": url, "status": status,
                "archive_bytes": len(response.content), "valid_ticks": len(data),
                "first_tick_utc": data.timestamp.iloc[0].isoformat(),
                "last_tick_utc": last_tick.isoformat(), "m5_bars": len(bars),
                "last_modified": response.headers.get("Last-Modified")}
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:250]}"
            if attempt != 2: time.sleep(attempt+1)
    return None, {"day": label, "url": url, "status": "error", "error": err}

def base_history(symbol):
    filename = ROOT / f"{symbol}_2026_UTC_7TF.zip"
    with zipfile.ZipFile(filename) as archive:
        meta = json.loads(archive.read("manifest.json"))
        if not meta["complete_months"] or meta["month_count_ok"] != 10:
            raise ValueError(f"{symbol} Jan-Oct history not verified complete")
        csv = archive.read(f"{symbol}_M5_2026_UTC.csv")
    data = pd.read_csv(io.BytesIO(csv), index_col=0, parse_dates=[0])
    data.index = pd.to_datetime(data.index, utc=True)
    if len(data) < 50000 or data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise ValueError(f"{symbol} historical M5 validation error")
    if data.index.max().strftime("%Y-%m") != "2026-10":
        raise ValueError(f"{symbol} historical tail is not October 2026")
    return data

def resample(m5, frame):
    if frame == "M5": return m5
    f = m5.resample(FRAMES[frame], label="left", closed="left", origin="epoch").agg(FIELDS)
    return f.loc[f.tick_count > 0]

def select_legs(portfolios):
    legs = sorted(set(leg for x in portfolios for leg in x["legs"]))
    specs = {}
    for leg in legs:
        sym, tf, signal, side, hold, session = leg.split("|")
        if sym not in SYMBOLS or tf not in FRAMES or side not in ("long", "short"):
            raise ValueError(f"Unsupported pre-selected leg {leg}")
        if not session.endswith("utc") or not hold.startswith("H"):
            raise ValueError(f"Invalid entry/hold {leg}")
        specs[leg] = dict(symbol=sym, timeframe=tf, signal=signal,
            side=side, hold=int(hold[1:]), hour=int(session[:2]))
    return specs

def replay_spec(leg, cfg, frame, sig, cutoff):
    n=len(frame)
    if cfg["signal"] not in sig:
        raise ValueError(f"Unknown V19 signal {cfg['signal']} in {leg}")
    ts=frame.index
    hours=ts.hour.to_numpy()
    minutes=ts.minute.to_numpy()
    i=np.arange(n)
    end=i+cfg["hold"]
    possible=end<n
    e=np.minimum(end,n-1)
    bid=frame.bid_open.to_numpy(dtype=float)
    ask=frame.ask_open.to_numpy(dtype=float)
    mid=(bid+ask)/2
    valid=np.isfinite(mid)&(mid>0)&np.isfinite(ask)&np.isfinite(bid)&(ask>=bid)
    qualified = sig[cfg["signal"]] & possible & valid & valid[e]
    entries=np.flatnonzero(qualified & (hours==cfg["hour"]) & (minutes==0))
    entries=engine.pick_nonoverlap(entries, cfg["hold"])
    ends=e[entries]
    direction=cfg["side"]
    if direction=="long":
        points=(bid[ends]*(1-engine.SLIPPAGE)-ask[entries]*(1+engine.SLIPPAGE))/mid[entries]*10000
    else:
        points=(bid[entries]*(1-engine.SLIPPAGE)-ask[ends]*(1+engine.SLIPPAGE))/mid[entries]*10000
    exit_dates=ts[ends]
    keep=(exit_dates<cutoff) & (exit_dates>=START)
    selected=np.flatnonzero(keep)
    nov_entries=entries[selected]
    nov_ends=ends[selected]
    nov_pnl=points[selected]
    rows=[{"leg":leg,"entry_utc":ts[start].isoformat(),
           "exit_utc":ts[stop].isoformat(), "pnl_bp":round(float(gain),6)}
          for start,stop,gain in zip(nov_entries,nov_ends,nov_pnl)]
    october=(exit_dates>=pd.Timestamp("2026-10-01T00:00:00Z"))&(exit_dates<START)
    return {"leg":leg,"november_bp":float(nov_pnl.sum()),"november_trades":len(nov_pnl),
            "october_replay_bp":float(points[october].sum()),
            "last_entry_utc":ts[nov_entries[-1]].isoformat() if len(nov_entries) else None,
            "last_exit_utc":ts[nov_ends[-1]].isoformat() if len(nov_ends) else None},rows

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    portfolios=json.loads(INPUT.read_text())["portfolios"]
    if len(portfolios)!=50 or len({x["id"] for x in portfolios})!=50:
        raise ValueError("Must replay exactly 50 distinct frozen portfolios")
    specs=select_legs(portfolios)
    now=pd.Timestamp.now(tz="UTC")
    cutoff=min(now.floor("5min")-pd.Timedelta(minutes=5), CEILING)
    report={"method":"V21 exact V19 signal replay of frozen 50 portfolios",
        "source_frozen_50":str(INPUT),"date_start_utc":START.isoformat(),
        "planned_date_end_exclusive_utc":CEILING.isoformat(),"asof_utc":now.isoformat(),
        "last_closed_m5_cutoff_exclusive_utc":cutoff.isoformat(),
        "spread":"archived Exness Bid/Ask", "assumed_slippage_per_side_bp":1,
        "excluded_costs":["swap","broker commissions","liquidation","market impact"],
        "units":"fixed-notional portfolio basis points (four legs equally weighted)",
        "symbols":{},"validation":{},"results":[],
        "status":"INCOMPLETE_DATA_DO_NOT_FILTER","errors":[]}
    history={}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                hist=base_history(symbol)
                pieces=[]; days=[]
                for day in DAYS:
                    bars,meta=fetch_daily(session,symbol,day,cutoff)
                    days.append(meta)
                    if bars is not None: pieces.append(bars)
                    print("V21_NOV_TICKS",symbol,meta["day"],meta["status"],
                          meta.get("m5_bars"),meta.get("error"),flush=True)
                missing=[d["day"] for d in days if d["status"]=="error"]
                # Don't infer a missing day as a zero-profit interval.
                if missing: report["errors"].append(f"{symbol}: unavailable days: {missing}")
                if not pieces: raise ValueError("No November data recovered")
                recent=pd.concat(pieces).sort_index()
                if recent.index.has_duplicates: raise ValueError("Duplicate November M5 buckets")
                all_m5=pd.concat([hist,recent]).sort_index()
                if all_m5.index.has_duplicates: raise ValueError("Duplicate historical/recent timestamps")
                if all_m5.index.max()<pd.Timestamp("2026-11-12T00:00:00Z"):
                    report["errors"].append(f"{symbol}: no quotes on Nov12")
                # Verify no day has less than 250 closed candles before Nov12.
                for day in DAYS[:-1]:
                    d=recent.loc[(recent.index>=day)&(recent.index<day+pd.Timedelta(days=1))]
                    if len(d)<250:
                        report["errors"].append(f"{symbol} {day.date()}: only {len(d)}/288 possible M5 bars")
                max_bucket=recent.index.max()
                report["symbols"][symbol]={"source_days":days,"historical_m5_bars":len(hist),
                    "nov_m5_bars":len(recent),
                    "first_nov_m5_utc":recent.index.min().isoformat(),
                    "last_nov_m5_utc":max_bucket.isoformat()}
                history[symbol]=all_m5
            except Exception as exc:
                report["errors"].append(f"{symbol}: {type(exc).__name__}: {exc}")
    if len(history)!=len(SYMBOLS):
        report["errors"].append("One or more symbol histories are missing")
    if report["errors"]:
        (OUT/"V21_NOV_REPLAY.json").write_text(json.dumps(report,indent=2)+"\n")
        (OUT/"V21_NOV_REPLAY.md").write_text("# V21 Nov replay: incomplete data; no methods rejected\n\n"+
            "\n".join("- "+x for x in report["errors"])+"\n")
        print("V21_FINAL_DATA_INCOMPLETE",json.dumps(report["errors"]),flush=True)
        return
    # Use a common and observed time cutoff across both symbols.
    observed=min(history[s].index.max() for s in SYMBOLS)
    valid_cutoff=min(cutoff,observed)
    report["last_closed_m5_cutoff_exclusive_utc"]=valid_cutoff.isoformat()
    legs_results={}
    trade_rows=[]
    audit_source=json.loads(Path("data/v21_crypto_screen/v21_best_near_misses.json").read_text())
    previous={x["id"]:x for x in audit_source}
    for symbol in SYMBOLS:
        for frame in sorted(set(c["timeframe"] for c in specs.values() if c["symbol"]==symbol)):
            bars=resample(history[symbol],frame)
            signals=engine.signals(bars)
            for leg,cfg in specs.items():
                if cfg["symbol"]!=symbol or cfg["timeframe"]!=frame:continue
                detail,rows=replay_spec(leg,cfg,bars,signals,valid_cutoff)
                legs_results[leg]=detail
                trade_rows.extend(rows)
                if leg in previous:
                    expected=float(previous[leg]["monthly_bp"][21])
                    err=abs(detail["october_replay_bp"]-expected)
                    report["validation"][leg]={"oct2026_expected_bp":expected,
                        "oct2026_replayed_bp":round(detail["october_replay_bp"],5),
                        "absolute_error_bp":round(err,5)}
                    if err>0.5:
                        report["errors"].append(f"October parity failure {leg}: {err:.4f} bp")
                print("V21_NOV_LEG",leg,round(detail["november_bp"],3),
                    detail["november_trades"],flush=True)
    if len(legs_results)!=len(specs):
        report["errors"].append(f"Only {len(legs_results)} of {len(specs)} legs replayed")
    nov=[]
    for p in portfolios:
        if any(x not in legs_results for x in p["legs"]):continue
        legs=[legs_results[x] for x in p["legs"]]
        pnl=sum(x["november_bp"] for x in legs)/4
        trades=sum(x["november_trades"] for x in legs)
        nov.append({"id":p["id"],"composition":p["composition"],
            "november_profit_bp":round(pnl,5), "november_closed_trades":trades,
            "historical_2025_to_oct2026_bp":p["total_bp"],
            "legs":p["legs"],"leg_november_bp":[round(x["november_bp"],5) for x in legs],
            "leg_november_trades":[x["november_trades"] for x in legs],
            "passed_november_profit_filter":pnl>0})
    if report["errors"]:
        report["status"]="BLOCKED_DATA_OR_PARITY_ERROR_DO_NOT_FILTER"
        report["results"]=nov
        report["original_portfolios"]=len(portfolios)
        report["validated_profit_filter_count"]=None
    else:
        report["status"]="PASS_COMPLETE_DATA_AND_PARITY"
        report["results"]=sorted(nov,key=lambda x:(-x["november_profit_bp"],x["id"]))
        report["original_portfolios"]=len(portfolios)
        report["validated_profit_filter_count"]=sum(x["passed_november_profit_filter"] for x in nov)
        report["excluded_breakeven_or_negative"]=len(nov)-report["validated_profit_filter_count"]
    (OUT/"V21_NOV_REPLAY.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    import csv
    with (OUT/"V21_NOV_CLOSED_TRADES.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["leg","entry_utc","exit_utc","pnl_bp"])
        w.writeheader();w.writerows(trade_rows)
    if report["status"]=="PASS_COMPLETE_DATA_AND_PARITY":
        rows=[x for x in report["results"] if x["passed_november_profit_filter"]]
        (OUT/"V21_NOV_SURVIVORS.json").write_text(json.dumps(rows,indent=2)+"\n")
        title=(f"# V21 November 2026 replay through {valid_cutoff.isoformat()}\n\n"
           f"All 50 checked; positive {len(rows)}, excluded {len(nov)-len(rows)}.\n"
           "Spread and 1bp/slippage/side included; swap and commission excluded.\n")
    else:
        title=("# V21 November 2026 replay NOT VERIFIED — no strategies removed\n\n"
            +"\n".join("- "+error for error in report["errors"])+"\n")
    (OUT/"V21_NOV_REPLAY.md").write_text(title,encoding="utf-8")
    print("V21_NOV_SUMMARY",json.dumps({"status":report["status"],
        "original":len(portfolios),"pass":report.get("validated_profit_filter_count"),
        "errors":report["errors"],"cutoff":valid_cutoff.isoformat()}),flush=True)

if __name__=="__main__":
    main()
