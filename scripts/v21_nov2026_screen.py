#!/usr/bin/env python3
"""V21 November 2026 out-of-sample review of exactly 199 frozen 22-month portfolios.
No method selection is performed on November observations. Historical Exness Bid/Ask
and a one-basis-point slippage assumption per side are reused exactly.
Portfolio profit = average per-leg realized fixed-notional basis-point profit.
"""
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import requests
import numpy as np
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent))
import v12_exness_collect as reader
import v19_strategy_screen as engine

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "v21_crypto"
OUT = REPO / "data" / "v21_crypto_screen"
CUTOFF = pd.Timestamp("2026-11-12T20:00:00Z")
START = pd.Timestamp("2026-11-01T00:00:00Z")
OCT_START = pd.Timestamp("2026-10-01T00:00:00Z")
LEG_FIELDS = ("bid_open", "ask_open", "bid_close", "ask_close")

def load_month(symbol):
    monthly_url = f"https://ticks.ex2archive.com/ticks/{symbol}/2026/11/Exness_{symbol}_2026_11.zip"
    daily_url = f"https://ticks.ex2archive.com/ticks/{symbol}/2026/11/12/Exness_{symbol}_2026_11_12.zip"
    with requests.Session() as session:
        r = session.get(monthly_url, timeout=(20,180))
        r.raise_for_status()
        raw_month = r.content
        r = session.get(daily_url, timeout=(20,180))
        r.raise_for_status()
        raw_day = r.content
    if not zipfile.is_zipfile(io.BytesIO(raw_month)) or not zipfile.is_zipfile(io.BytesIO(raw_day)):
        raise ValueError(f"Not Exness monthly/daily ZIP for {symbol}")
    m5_month = reader.ticks_to_5m(raw_month, CUTOFF, START)
    m5_daily = reader.ticks_to_5m(raw_day, CUTOFF, pd.Timestamp("2026-11-12T00:00:00Z"))
    if m5_month.empty or m5_daily.empty:
        raise ValueError(f"No usable November month and day-12 ticks for {symbol}")
    if m5_daily.index.min() != pd.Timestamp("2026-11-12T00:00:00Z"):
        raise ValueError(f"Day-12 archive does not start at midnight for {symbol}")
    m5_month = m5_month.loc[m5_month.index < m5_daily.index.min()]
    m5 = reader.merge_parts([m5_month,m5_daily])
    latest=m5.index.max()
    if latest < CUTOFF - pd.Timedelta(hours=1):
        raise ValueError(f"Insufficient November data for {symbol}: latest 5m {latest}")
    frames=reader.build_frames(m5)
    result={}
    for tf, frame in frames.items():
        freq={"M5":"5min","M15":"15min","M30":"30min","H1":"1h","H4":"4h"}[tf]
        frame=frame.loc[frame.index + pd.Timedelta(freq) <= CUTOFF]
        result[tf]=frame.reset_index()
    return result, {"urls":[monthly_url,daily_url],
                    "monthly_zip_sha256":hashlib.sha256(raw_month).hexdigest(),
                    "daily12_zip_sha256":hashlib.sha256(raw_day).hexdigest(),
                    "archive_bytes":len(raw_month)+len(raw_day),
                    "last_usable_m5_utc":latest.isoformat(),
                    "frames":{tf:len(fr) for tf,fr in result.items()}}

def replay_legs(symbol, tf, ids, novframe):
    historical = engine.read_frame(DATA,symbol,tf)
    df = pd.concat([historical, novframe], ignore_index=True)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df = df.drop_duplicates("timestamp_utc").sort_values("timestamp_utc").reset_index(drop=True)
    if df["timestamp_utc"].iloc[-1] >= CUTOFF:
        raise AssertionError("Unexpected non-complete candle at cutoff")
    when = df["timestamp_utc"]
    h = when.dt.hour.to_numpy()
    mins = when.dt.minute.to_numpy()
    bid = df.bid_open.to_numpy(dtype=float)
    ask = df.ask_open.to_numpy(dtype=float)
    mid = (bid + ask) / 2
    good = (np.isfinite(bid) & np.isfinite(ask) & np.isfinite(mid) & (mid > 0))
    sigs = engine.signals(df)
    n = len(df)
    ix = np.arange(n, dtype=np.int64)
    times = when.to_numpy()
    results = {}
    for name in ids:
        sym, timeframe, signal, side, holdpart, session = name.split("|")
        hold = int(holdpart[1:])
        hour = int(session[:2])
        endix = np.minimum(ix + hold,n - 1)
        valid = (ix+hold < n) & good & good[endix]
        ses = (h == hour) & (mins == 0)
        qualified = np.flatnonzero(sigs[signal] & ses & valid)
        entry = engine.pick_nonoverlap(qualified,hold)
        exitindex = endix[entry]
        if side == "long":
            pnl = (bid[exitindex]*(1-engine.SLIPPAGE) - ask[entry]*(1+engine.SLIPPAGE)) / mid[entry] * 10000
        else:
            pnl = (bid[entry]*(1-engine.SLIPPAGE) - ask[exitindex]*(1+engine.SLIPPAGE)) / mid[entry] * 10000
        exit_times = when.iloc[exitindex]
        nov = (exit_times >= START) & (exit_times < CUTOFF)
        octo = (exit_times >= OCT_START) & (exit_times < START)
        pnl_nov = pnl[np.asarray(nov)]
        exit_nov = exit_times.loc[nov].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_list()
        entry_nov = when.iloc[entry[np.asarray(nov)]].dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_list()
        results[name] = {
            "nov_realized_bp":float(pnl_nov.sum()),
            "oct_replayed_bp":float(pnl[np.asarray(octo)].sum()),
            "nov_closed_trades":int(len(pnl_nov)),
            "nov_winning_trades":int((pnl_nov > 0).sum()),
            "nov_losing_trades":int((pnl_nov < 0).sum()),
            "nov_trades":[{"open_utc":o,"close_utc":e,"pnl_bp":round(float(p),6)}
                          for o,e,p in zip(entry_nov,exit_nov,pnl_nov)],
        }
    return results

def main():
    if pd.Timestamp(datetime.now(timezone.utc)) < CUTOFF:
        raise RuntimeError("Specified cutoff is in the future")
    path=OUT/"V21_portfolio_combinations_audit.json"
    audit=json.loads(path.read_text())
    portfolios=audit["all_passing_portfolios"]
    if len(portfolios) != 199:
        raise RuntimeError(f"Original frozen portfolio count changed: {len(portfolios)}")
    near=json.loads((OUT/"v21_best_near_misses.json").read_text())
    lookup={r["id"]:r for r in near}
    leg_ids=sorted(set(leg for p in portfolios for leg in p["legs"]))
    grouped={}
    for name in leg_ids:
        s,tf,*_=name.split("|")
        grouped.setdefault((s,tf),[]).append(name)
    data={}
    manifest={}
    for sym in ("BTCUSD","ETHUSD"):
        data[sym],manifest[sym]=load_month(sym)
        print("V21_NOV_DATA",sym,manifest[sym],flush=True)
    calculations={}
    for (sym,tf), names in grouped.items():
        x=replay_legs(sym,tf,names,data[sym][tf])
        calculations.update(x)
        print("V21_NOV_REPLAY",sym,tf,len(names),flush=True)
    oct_checks=[]
    for name in leg_ids:
        reference=float(lookup[name]["monthly_bp"][21])
        actual=calculations[name]["oct_replayed_bp"]
        diff=actual-reference
        oct_checks.append({"name":name,"reference_oct_bp":reference,"replayed_oct_bp":actual,"difference_bp":diff})
    mismatches=[q for q in oct_checks if abs(q["difference_bp"]) > 0.06]
    if mismatches:
        print("V21_OCT_MISMATCHES",json.dumps(mismatches[:15]),flush=True)
        raise AssertionError(f"{len(mismatches)}/{len(oct_checks)} October baseline validation failed")
    print("V21_OCT_VALIDATED",len(oct_checks),flush=True)
    survivors=[]; rejected=[]; zero=[]
    for p in portfolios:
        legs=p["legs"]
        trade_count=sum(calculations[x]["nov_closed_trades"] for x in legs)
        all_total=sum(calculations[x]["nov_realized_bp"] for x in legs)
        bp=all_total/len(legs)
        row={"id":p["id"],"composition":p["composition"],"leg_count":len(legs),"legs":legs,
             "nov_realized_equal_notional_bp":round(bp,6),
             "nov_closed_trades_component_sum":trade_count,
             "leg_nov_bp":{x:round(calculations[x]["nov_realized_bp"],6) for x in legs},
             "previous_profit_2025_bp":p["profit_2025_bp"],
             "previous_profit_2026_janoct_bp":p["profit_2026_JanOct_bp"],
             "previous_min_22month_bp":p["min_month_bp"]}
        if bp < -1e-8: rejected.append(row)
        elif bp > 1e-8: survivors.append(row)
        else:
            survivors.append(row)
            zero.append(row["id"])
    survivors.sort(key=lambda r:r["nov_realized_equal_notional_bp"],reverse=True)
    rejected.sort(key=lambda r:r["nov_realized_equal_notional_bp"])
    out={"test_name":"V21 original 199 portfolios November forward-screen",
         "prepared_at_utc":datetime.now(timezone.utc).isoformat(),
         "test_start_inclusive_utc":START.isoformat(),
         "test_end_exclusive_utc":CUTOFF.isoformat(),
         "data_source":"Exness public Bid/Ask tick archive mirror, ongoing November monthly files",
         "source_files":manifest,
         "strategy_count_before":len(portfolios),
         "removed_negative_november":len(rejected),
         "remaining":len(survivors),
         "positive":len(survivors)-len(zero),
         "zero_realized_bp":len(zero),
         "negative":len(rejected),
         "single_legs_covered":len(leg_ids),
         "october_replay_validation_max_absolute_difference_bp":max(abs(r["difference_bp"]) for r in oct_checks),
         "aggregate_method":"equal-weighted arithmetic mean of 4 independent leg fixed-notional bp P&L; position returns booked by exit month",
         "caveats":["November 2026 is incomplete; only exits before cutoff counted",
                    "In-sample selected on January 2025-October 2026; forward test in November",
                    "Historical Exness spread included; 1bp slippage per side estimated; swap, commissions, margin, and actual fills excluded",
                    "No SL or TP simulated in these original 199 candidate rules; do not treat as deployment-ready",
                    "Component bots may trade simultaneously; duplicate/overlapping trades remain possible",
                    "Zero-bp results are retained (not losing) but cannot be labeled profitable"],
         "surviving_portfolios":survivors,
         "excluded_portfolios":rejected,
         "zero_bp_ids":zero,
         "individual_leg_results":calculations,
         "october_replay_checks":oct_checks}
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/"V21_nov2026_forward_199.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    records=[{k:v for k,v in r.items() if k not in ("legs","leg_nov_bp")} for r in survivors+rejected]
    for r in records:
        r["kept"] = r["nov_realized_equal_notional_bp"] >= 0
    pd.DataFrame(records).to_csv(OUT/"V21_nov2026_forward_199.csv",index=False)
    lines=["# V21 November 2026 forward test — frozen 199 portfolios","",
           f"Exness BTCUSD / ETHUSD real historical Bid/Ask. Test **{START.strftime('%Y-%m-%d')} through {(CUTOFF-pd.Timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M')} UTC**.","",
           f"- Before: {len(portfolios)}",
           f"- Eliminated for negative November realized bp: **{len(rejected)}**",
           f"- Remaining: **{len(survivors)}**",
           f"- Positive November: {len(survivors)-len(zero)}",
           f"- Exactly zero November: {len(zero)}",
           f"- October reproduction validated on {len(oct_checks)} individual strategies",
           "",
           "## Surviving portfolios (sorted by November performance)",
           "",
           "| Strategy | November bp | Trades (sum across bots) | Components |",
           "|---|---:|---:|---|"]
    for r in survivors:
        lines.append(f"| {r['id']} | {r['nov_realized_equal_notional_bp']:.3f} | {r['nov_closed_trades_component_sum']} | {r['composition']} |")
    lines.extend(["","## Excluded portfolios","",
           "| Strategy | November bp | Closed trades |","|---|---:|---:|"])
    for r in rejected:
        lines.append(f"| {r['id']} | {r['nov_realized_equal_notional_bp']:.3f} | {r['nov_closed_trades_component_sum']} |")
    lines.extend(["","## Limits","","Forward period still incomplete. Spread and 1bp-per-side slippage are modeled, but swap/commission, execution latency, liquidation, SL and TP are excluded. No real-money trading recommendation."])
    (OUT/"V21_nov2026_forward_199.md").write_text("\n".join(lines)+"\n")
    print("V21_NOV_RESULT",json.dumps({"before":len(portfolios),"removed":len(rejected),"remaining":len(survivors),
            "positive":len(survivors)-len(zero),"zero":len(zero),"validation_max_abs_bp":out["october_replay_validation_max_absolute_difference_bp"],
            "top_survivors":[{"id":r["id"],"bp":r["nov_realized_equal_notional_bp"],"trades":r["nov_closed_trades_component_sum"]} for r in survivors[:15]],
            "bottom_removed":[{"id":r["id"],"bp":r["nov_realized_equal_notional_bp"]} for r in rejected[:5]]}),flush=True)

if __name__=="__main__":
    main()
