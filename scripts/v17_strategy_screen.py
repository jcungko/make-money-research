#!/usr/bin/env python3
"""V17: exploratory strategy census on Exness 2025 + 2026 Bid/Ask M5 archives.
Read-only. No MT5 connection, brokerage orders, or credentials.
All times are UTC; a signal is always shifted by one completed source candle.
"""
import argparse
import collections
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
TFS = ("M5", "M15", "M30", "H1", "H4", "D1", "W1")
HOLD_HOURS = (1, 2, 4, 6, 8, 12)
HOURS = tuple(range(24))
SLIPPAGE_PIPS_PER_SIDE = 0.1
CUTOFF_MONTHS = tuple(f"2025-{m:02d}" for m in range(1, 13)) + tuple(f"2026-{m:02d}" for m in range(1, 11))
MONTH_TO_CODE = {m: k for k, m in enumerate(CUTOFF_MONTHS)}
NOV_CODE = len(CUTOFF_MONTHS)


def load_data(root, symbol):
    frames = {}
    for yr in (2025, 2026):
        path = root / f"v17_exness_{yr}" / f"{symbol}_{yr}_UTC_7TF.zip"
        if not path.is_file():
            raise FileNotFoundError(f"Missing source {path}")
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("manifest.json"))
            if meta.get("symbol") != symbol or meta.get("year") != yr:
                raise ValueError(f"Unexpected provenance for {path}")
            for tf in TFS:
                fn = f"{symbol}_{tf}_{yr}_UTC.csv"
                f = pd.read_csv(io.BytesIO(z.read(fn)), index_col=0, parse_dates=[0])
                f.index = pd.to_datetime(f.index, utc=True)
                if not f.index.is_monotonic_increasing or f.index.has_duplicates:
                    raise ValueError(f"Bad chronological index for {symbol} {yr} {tf}")
                frames.setdefault(tf, []).append(f)
    frames = {tf: pd.concat(parts).sort_index() for tf, parts in frames.items()}
    for tf, f in frames.items():
        assert not f.index.has_duplicates, (tf, "duplicates")
        assert (f.ask_open >= f.bid_open).all(), (tf, "crossed prices")
        assert f.index.tz is not None
    return frames


def signal_generator(f):
    """Generate distinct, fully rule-based directional signals in {-1, 0, +1}.
    These signals are computed at candle-close; caller shifts to next candle.
    """
    p = (f.bid_close + f.ask_close) / 2
    op = (f.bid_open + f.ask_open) / 2
    hi = (f.bid_high + f.ask_high) / 2
    lo = (f.bid_low + f.ask_low) / 2
    # Momentum and mean-reversion use identical evidence but distinct execution polarity.
    for n in (1, 2, 3, 4, 6, 8, 12, 20):
        yield f"return_{n}", np.sign(p - p.shift(n)).fillna(0).astype(np.int8)
    for fast, slow in ((3, 8), (5, 13), (8, 21), (13, 34), (21, 55)):
        a = p.ewm(span=fast, adjust=False).mean()
        b = p.ewm(span=slow, adjust=False).mean()
        z = np.sign(a-b)
        z.iloc[:slow] = 0
        yield f"ema_{fast}_{slow}", z.fillna(0).astype(np.int8)
    for n in (5, 10, 20, 40):
        mean = p.rolling(n, min_periods=n).mean()
        yield f"close_vs_sma_{n}", np.sign(p-mean).fillna(0).astype(np.int8)
    for n in (7, 14, 21):
        diff = p.diff()
        gain = diff.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        loss = (-diff.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rsi = 100 * gain / (gain+loss).replace(0,np.nan)
        mid = np.sign(rsi - 50)
        mid.iloc[:n+1] = 0
        yield f"rsi50_{n}", mid.fillna(0).astype(np.int8)
        for cutoff in (35, 40):
            z = pd.Series(np.select((rsi<cutoff, rsi>100-cutoff),(1,-1),default=0), index=f.index, dtype=np.int8)
            z.iloc[:n+1] = 0
            yield f"rsi_extreme_{n}_{cutoff}", z
    for n in (3, 5, 10, 20):
        previous_hi = hi.shift(1).rolling(n,min_periods=n).max()
        previous_lo = lo.shift(1).rolling(n,min_periods=n).min()
        z = pd.Series(np.select((p>previous_hi,p<previous_lo),(1,-1),default=0), index=f.index, dtype=np.int8)
        yield f"close_breakout_{n}", z
    for n in (1, 2, 4):
        z = np.sign(p - op.shift(n-1)).fillna(0).astype(np.int8)
        yield f"body_{n}", z


def prepare_signal(frame, m5_index, chosen_tf):
    for name, raw_signal in signal_generator(frame):
        # Critical: the candle that supplies this signal must have CLOSED
        # before the M5 entry. A source feature is made tradable only at
        # the following source candle's start, never on its own open.
        lagged = raw_signal.shift(1,fill_value=0)
        # D1 and W1 source candles are Monday/UTC anchored in the source archive.
        aligned = lagged.reindex(m5_index,method="ffill").fillna(0)
        yield name, aligned.to_numpy(dtype=np.int8,copy=False)


def build_calendar(m5):
    ts = m5.index
    # Entry 00 minutes at each hour, exactly on an archived quote M5 bar.
    hours = ts.hour.to_numpy()
    minutes = ts.minute.to_numpy()
    by_hour = {h:np.flatnonzero((hours==h)&(minutes==0)).astype(np.int32) for h in HOURS}
    month_string = ts.strftime("%Y-%m")
    code = np.array([MONTH_TO_CODE.get(s, NOV_CODE if s=="2026-11" else -1) for s in month_string],dtype=np.int16)
    return by_hour, code, ts.asi8


def exit_pips(m5, by_hour, code, times_ns, pip, hold_hours):
    n = len(m5)
    long_raw = m5.bid_close.to_numpy(dtype=float)
    ask_exit = m5.ask_close.to_numpy(dtype=float)
    long_entry = m5.ask_open.to_numpy(dtype=float)
    short_entry = m5.bid_open.to_numpy(dtype=float)
    out={}
    slip = SLIPPAGE_PIPS_PER_SIDE * 2
    for hold in hold_hours:
        steps = int(hold * 12)
        valid = np.zeros(n,dtype=bool)
        bound = np.arange(0,n-steps+1,dtype=np.int32)
        stop = bound + steps-1
        contiguous = times_ns[stop] - times_ns[bound] == (steps-1)*5*60*1_000_000_000
        valid[bound[contiguous]] = True
        buy = np.full(n,np.nan,dtype=float)
        sell = np.full(n,np.nan,dtype=float)
        ix = bound[contiguous]
        ex = ix+steps-1
        buy[ix] = (long_raw[ex]-long_entry[ix])/pip - slip
        sell[ix] = (short_entry[ix]-ask_exit[ex])/pip - slip
        completed_month = np.full(n, -1, dtype=np.int16)
        completed_month[ix] = code[ex]
        out[hold] = (valid,buy,sell,completed_month)
    return out


def max_drawdown(seq):
    if len(seq)==0:
        return 0.0
    cs=np.cumsum(seq)
    peak=np.maximum.accumulate(np.r_[0,cs])
    return float(np.max(peak-np.r_[0,cs]))


def screen_symbol(root, symbol):
    frames=load_data(root,symbol)
    m5=frames["M5"]
    by_hour, mcode, ticks = build_calendar(m5)
    pip=0.01 if symbol=="USDJPY" else 0.0001
    outcomes=exit_pips(m5,by_hour,mcode,ticks,pip,HOLD_HOURS)
    counters=collections.Counter()
    passed=[]
    nearest=[]
    nfeatures=0
    for tf in TFS:
        for name, signal in prepare_signal(frames[tf], m5.index, tf):
            nfeatures+=1
            for hour, base in by_hour.items():
                if not len(base):
                    continue
                ss=signal[base]
                for hold in HOLD_HOURS:
                    valid, long_pips, short_pips, close_month = outcomes[hold]
                    month_ix=close_month[base]
                    for polarity in (1,-1):
                        directions=(ss * polarity)
                        for side in ("both","long_only","short_only"):
                            eligible = valid[base] & (month_ix>=0) & (directions != 0)
                            if side=="long_only":
                                eligible &= directions==1
                            elif side=="short_only":
                                eligible &= directions==-1
                            selected = base[eligible]
                            dir_selected = directions[eligible]
                            counters["candidates"] += 1
                            if not len(selected):
                                continue
                            mc = close_month[selected]
                            pnl = np.where(dir_selected==1,long_pips[selected],short_pips[selected])
                            # A single bad/crossed/missing bid/ask quote must invalidate a test.
                            if not np.isfinite(pnl).all():
                                counters["invalid_quote"]+=1
                                continue
                            month_sum = np.bincount(mc,weights=pnl,minlength=NOV_CODE+1)
                            month_n = np.bincount(mc,minlength=NOV_CODE+1)
                            if min(month_n[:NOV_CODE])==0:
                                continue
                            counters["every_month_has_trades"]+=1
                            month_wins = int((month_sum[:NOV_CODE] > 1e-9).sum())
                            counters[f"profitable_exactly_{month_wins}_of_22"] += 1
                            if month_wins>=19:
                                fingerprint = hashlib.sha256(
                                    np.asarray(selected, dtype="<i4").tobytes()
                                    + np.asarray(dir_selected, dtype=np.int8).tobytes()
                                    + bytes([hold])
                                ).hexdigest()
                                months = {m: round(float(v), 3) for m, v in zip(CUTOFF_MONTHS, month_sum[:NOV_CODE])}
                                nearest.append({
                                    "symbol": symbol, "signal_timeframe": tf, "signal": name,
                                    "entry_hour_utc": int(hour), "holding_hours": int(hold),
                                    "polarity": "follow" if polarity == 1 else "reverse",
                                    "side": side, "profitable_months": month_wins,
                                    "profit_pips_2025": round(float(month_sum[:12].sum()), 3),
                                    "profit_pips_2026_jan_oct": round(float(month_sum[12:NOV_CODE].sum()), 3),
                                    "profit_pips_total": round(float(month_sum[:NOV_CODE].sum()), 3),
                                    "months_non_positive": [m for m, v in months.items() if v <= 0],
                                    "monthly_pips": months,
                                    "num_trades": int(month_n[:NOV_CODE].sum()),
                                    "min_month_trades": int(np.min(month_n[:NOV_CODE])),
                                    "win_rate": round(float((pnl[mc < NOV_CODE] > 0).mean()), 4),
                                    "max_drawdown_pips": round(max_drawdown(pnl[mc < NOV_CODE]), 3),
                                    "fingerprint": fingerprint
                                })
                            if month_wins!=NOV_CODE:
                                continue
                            p2025 = float(month_sum[:12].sum())
                            p2026 = float(month_sum[12:NOV_CODE].sum())
                            if p2025<=0 or p2026<=0:
                                continue
                            counters["all_22_months_profitable"]+=1
                            if np.min(month_n[:NOV_CODE])>=4:
                                counters["min_4_trades_per_month"]+=1
                            if np.min(month_n[:NOV_CODE])>=8:
                                counters["min_8_trades_per_month"]+=1
                            # Exact execution-sequence deduplication: cosmetic signal
                            # names and identical direction sets count only once.
                            fingerprint=hashlib.sha256(np.asarray(selected,dtype="<i4").tobytes()+
                                np.asarray(dir_selected,dtype=np.int8).tobytes()+
                                bytes([hold])).hexdigest()
                            clean_pnl=pnl[np.argsort(selected)]
                            passed.append({
                                "symbol":symbol,"signal_timeframe":tf,"signal":name,
                                "entry_hour_utc":hour,"holding_hours":hold,
                                "polarity":"follow" if polarity==1 else "reverse",
                                "side":side,"num_trades":int(month_n[:NOV_CODE].sum()),
                                "smallest_month_trades":int(np.min(month_n[:NOV_CODE])),
                                "profit_pips_2025":round(p2025,3),"profit_pips_2026_jan_oct":round(p2026,3),
                                "min_month_pips":round(float(np.min(month_sum[:NOV_CODE])),3),
                                "profit_pips_total":round(p2025+p2026,3),
                                "win_rate":round(float((pnl[mc<NOV_CODE]>0).mean()),4),
                                "max_drawdown_pips":round(max_drawdown(clean_pnl),3),
                                "nov_2026_partial_pips":round(float(month_sum[NOV_CODE]),3),
                                "nov_2026_partial_trades":int(month_n[NOV_CODE]),
                                "monthly_pips":{m:round(float(v),3) for m,v in zip(CUTOFF_MONTHS,month_sum[:NOV_CODE])},
                                "fingerprint":fingerprint
                            })
    nearest.sort(key=lambda r: (r["profitable_months"], r["profit_pips_total"]), reverse=True)
    print(json.dumps({"symbol":symbol,"features":nfeatures,"checked":counters["candidates"],
        "with_trades_every_month":counters["every_month_has_trades"],
        "profitable_all_22":counters["all_22_months_profitable"],
        "with_4plus_trades":counters["min_4_trades_per_month"]}),flush=True)
    return passed, dict(counters), nearest[:30], {tf:len(f) for tf,f in frames.items()}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=Path("data"))
    ap.add_argument("--out",type=Path,default=Path("results/v17_strategy_screen"))
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    began=time.perf_counter()
    all_passed=[]
    nearest=[]
    bysymbol={}
    all_counts=collections.Counter()
    for sym in SYMBOLS:
        results, counts, near, sizes=screen_symbol(args.input,sym)
        all_passed.extend(results)
        nearest.extend(near)
        bysymbol[sym]={"counts":counts,"source_rows":sizes}
        all_counts.update(counts)
    # Duplicates may be distinct parameter labels but identical live executions.
    unique = {}
    for r in all_passed:
        key=(r["symbol"],r["fingerprint"])
        old=unique.get(key)
        if old is None or (r["profit_pips_total"],r["min_month_pips"]) > (old["profit_pips_total"],old["min_month_pips"]):
            unique[key]=r
    unique_list=list(unique.values())
    unique_list.sort(key=lambda r:(r["min_month_pips"],r["profit_pips_total"]),reverse=True)
    all_passed.sort(key=lambda r:(r["min_month_pips"],r["profit_pips_total"]),reverse=True)
    near_list = sorted(nearest, key=lambda r: (r["profitable_months"], r["profit_pips_total"]), reverse=True)
    near_unique = {(r["symbol"],r["fingerprint"]) for r in near_list}
    summary = {
        "research":"V17 Exness public 2025/2026 multi-timeframe strategy census",
        "status":"EXPLORATORY_BACKTEST_ONLY_NOT_APPROVED_FOR_LIVE_TRADING",
        "symbols":list(SYMBOLS),"data_years":[2025,2026],
        "calendar_complete_months":list(CUTOFF_MONTHS),
        "2026_november":"partial_as_of_Nov10_UTC_excluded_from_all_months_criterion",
        "entry_hours_utc":list(HOURS),"holds_hours":list(HOLD_HOURS),
        "timeframes":list(TFS),
        "entry_exit":"enter at M5 next decision bar open, exit at M5 close after fixed H hours",
        "no_lookahead":"all signal features use only previous fully closed source-timeframe candle",
        "execution_model":"buy at ask_open sell at bid_open; exit long bid_close short ask_close; 0.1 pip additional adverse slippage each side",
        "limitations":["indicative Exness quotes, not broker-executed MT5 fills",
            "no swap financing, no special news slippage, no commissions beyond observed bid/ask spread",
            "no stop loss or forced liquidation; fixed holding horizon only",
            "D1 W1 use UTC calendar not necessarily MT5 broker server time",
            "strategy mining creates severe data-snooping risk, all 22 months are used as selection set",
            "not an untouched out-of-sample demonstration"],
        "counts":dict(all_counts),
        "unique_all_22_months_profitable":len(unique_list),
        "per_symbol":bysymbol,
        "strongest_by_minimum_month_pips":unique_list[:25],
        "near_miss_highest_months": [
            [r["profitable_months"], r["profit_pips_total"], r["symbol"], r["signal_timeframe"],
             r["signal"], r["entry_hour_utc"], r["holding_hours"],
             1 if r["polarity"] == "follow" else -1, r["side"]]
            for r in near_list
        ],
        "qualified_19_or_more_details": near_list,
        "screened_19_or_more_configs": len(near_list),
        "screened_19_or_more_unique_execution_signatures": len(near_unique),
        "screened_19_or_more_positive_both_years": sum(
            r["profit_pips_2025"] > 0 and r["profit_pips_2026_jan_oct"] > 0 for r in near_list
        ),
        "elapsed_seconds":round(time.perf_counter()-began,1)
    }
    (args.out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pd.DataFrame(all_passed).drop(columns=["monthly_pips","fingerprint"],errors="ignore").to_csv(args.out/"all_qualifying_configs.csv",index=False)
    pd.DataFrame(unique_list).drop(columns=["monthly_pips","fingerprint"],errors="ignore").to_csv(args.out/"unique_qualifying_configs.csv",index=False)
    (args.out/"all_unique_details.json").write_text(json.dumps(unique_list,ensure_ascii=False)+"\n",encoding="utf-8")
    (args.out/"all_19plus_details.json").write_text(json.dumps(near_list,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    pd.DataFrame(near_list).drop(columns=["monthly_pips","fingerprint"],errors="ignore").to_csv(
        args.out/"all_19plus_profit_report.csv",index=False
    )
    print("FINAL_COUNT",json.dumps({k:summary[k] for k in ("counts","unique_all_22_months_profitable","elapsed_seconds")}),flush=True)

if __name__=="__main__":
    main()
