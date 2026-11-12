#!/usr/bin/env python3
"""V21: Add mandatory HARD price stop-loss to frozen 10 profitable Nov portfolios.

For each trade: entry at historical timeframe-open bid/ask, 1bp entry slippage;
protective stop at 1% from quoted entry (also sensitivity 0.5/1.5/2%).
Use observed M5 bid lows for BUY, ask highs for SELL; stop fill at stop or
first M5 open if the market gaps adversely; 1bp adverse exit slippage.
Otherwise original fixed-bars time exit. No TP, no leverage assumed.

No parameters selected on November. Results are research simulation, not MT5.
"""
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, "scripts")
import v19_strategy_screen as v19
import v21_november_replay as nov
from v12_exness_collect import FIELDS

ROOT = Path("data/v21_crypto")
INPUT = Path("data/v21_november_replay/V21_NOV_SURVIVORS.json")
NEAR = Path("data/v21_crypto_screen/v21_best_near_misses.json")
NOV_BASE = Path("data/v21_november_replay/V21_NOV_REPLAY.json")
OUT = Path("data/v21_sl_retest")
STOP_PCTS = (0.005, 0.01, 0.015, 0.02)
DEFAULT_PCT = 0.01
START = pd.Timestamp("2025-01-01T00:00:00Z")
NOV_START = pd.Timestamp("2026-11-01T00:00:00Z")
CUT = pd.Timestamp("2026-11-12T18:00:00Z")
MONTHS = v19.MONTHS + ["2026-11_partial"]
NOV_DAYS = tuple(pd.date_range("2026-11-01","2026-11-12",tz="UTC",freq="D"))
SYMBOLS = ("BTCUSD","ETHUSD")


def history_m5(symbol):
    blocks=[]
    for year in (2025,2026):
        p=ROOT / f"{symbol}_{year}_UTC_7TF.zip"
        with zipfile.ZipFile(p) as z:
            filename=f"{symbol}_M5_{year}_UTC.csv"
            f=pd.read_csv(io.BytesIO(z.read(filename)),index_col=0,parse_dates=[0])
            f.index=pd.to_datetime(f.index,utc=True)
            if len(f)<80000:raise ValueError(f"{symbol} {year} too few M5 rows {len(f)}")
            blocks.append(f)
    m5=pd.concat(blocks).sort_index()
    if m5.index.has_duplicates or not m5.index.is_monotonic_increasing:
        raise ValueError("duplicate/unsorted historic M5")
    return m5


def historical_full_frame(m5, tf):
    if tf=="M5": return m5
    # Identical OHLC aggregator to the 2025/2026 Exness V21 collection.
    f=m5.resample(nov.FRAMES[tf],label="left",closed="left",origin="epoch").agg(FIELDS)
    return f.loc[f.tick_count>0]


def build_entries(tf_bars, spec):
    signal=v19.signals(tf_bars)
    mask=signal[spec["signal"]]
    t=tf_bars.index
    index=np.arange(len(tf_bars),dtype=np.int64)
    end=np.minimum(index+spec["hold"],len(tf_bars)-1)
    bid=tf_bars.bid_open.to_numpy(dtype=float)
    ask=tf_bars.ask_open.to_numpy(dtype=float)
    mid=(bid+ask)/2
    good=np.isfinite(mid)&(mid>0)&np.isfinite(bid)&np.isfinite(ask)&(ask>=bid)
    valid=(index+spec["hold"] < len(index)) & good & good[end]
    candidates=np.flatnonzero(mask & valid & (t.hour==spec["hour"]) & (t.minute==0))
    # Freezing original nonoverlapping schedule is conservative after a stop.
    entries=v19.pick_nonoverlap(candidates,spec["hold"])
    ends=end[entries]
    long=spec["side"]=="long"
    old=(bid[ends]*(1-v19.SLIPPAGE)-ask[entries]*(1+v19.SLIPPAGE))/mid[entries]*10000 if long else (
        bid[entries]*(1-v19.SLIPPAGE)-ask[ends]*(1+v19.SLIPPAGE))/mid[entries]*10000
    return list(zip(entries.tolist(),ends.tolist(),old.tolist()))


def simulate_stop(full_m5, tf_bars, spec, stop_pct, cutoff):
    schedules=build_entries(tf_bars,spec)
    m5times=full_m5.index
    m5num=m5times.asi8
    tnum=tf_bars.index.asi8
    bid_open=full_m5.bid_open.to_numpy(dtype=float)
    bid_low=full_m5.bid_low.to_numpy(dtype=float)
    ask_open=full_m5.ask_open.to_numpy(dtype=float)
    ask_high=full_m5.ask_high.to_numpy(dtype=float)
    tf_bid=tf_bars.bid_open.to_numpy(dtype=float)
    tf_ask=tf_bars.ask_open.to_numpy(dtype=float)
    slipp=v19.SLIPPAGE
    records=[]
    for i,j,baseline in schedules:
        et=tf_bars.index[i]
        xt=tf_bars.index[j]
        if xt >= cutoff or et < START:continue
        entry_bid=tf_bid[i]
        entry_ask=tf_ask[i]
        mid=(entry_bid+entry_ask)*0.5
        buy=spec["side"]=="long"
        open_price=entry_ask*(1+slipp) if buy else entry_bid*(1-slipp)
        stop_level=entry_ask*(1-stop_pct) if buy else entry_bid*(1+stop_pct)
        left=int(np.searchsorted(m5num,tnum[i],side="left"))
        right=int(np.searchsorted(m5num,tnum[j],side="left"))
        stopped=False
        stop_time=None
        exit_quote=tf_bid[j] if buy else tf_ask[j]
        if right > len(m5num):raise ValueError("M5 search range outside candles")
        for k in range(left,right):
            if buy:
                hit=np.isfinite(bid_low[k]) and (bid_low[k]<=stop_level)
                if hit:
                    # On quote gap, first M5 bid open can be worse than stop price.
                    exit_quote=min(stop_level,bid_open[k])
            else:
                hit=np.isfinite(ask_high[k]) and (ask_high[k]>=stop_level)
                if hit:
                    exit_quote=max(stop_level,ask_open[k])
            if hit:
                stopped=True
                stop_time=m5times[k]
                break
        exit_price=exit_quote*(1-slipp) if buy else exit_quote*(1+slipp)
        points=((exit_price-open_price) if buy else (open_price-exit_price))/mid*10000
        realized=stop_time if stopped else xt
        if realized>=cutoff:continue
        if realized.year==2026 and realized.month==11: period="2026-11_partial"
        else:period=realized.strftime("%Y-%m")
        if period not in MONTHS:continue
        records.append({"entry_utc":et.isoformat(),"exit_utc":realized.isoformat(),
                        "scheduled_exit_utc":xt.isoformat(),
                        "pnl_bp":float(points),"old_pnl_bp":float(baseline),
                        "is_stop":bool(stopped),"stop_quote":float(stop_level),
                        "entry_quote":float(entry_ask if buy else entry_bid),
                        "period":period})
    return records


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sel=json.loads(INPUT.read_text())
    if len(sel)!=10 or len(set(x["id"] for x in sel))!=10:
        raise ValueError("Frozen list must contain exactly 10 V21 portfolios")
    specs=nov.select_legs(sel)
    if len(specs)!=14: raise ValueError(f"expected 14 distinct bots, found {len(specs)}")
    expected={r["id"]:r for r in json.loads(NEAR.read_text())}
    nov_before=json.loads(NOV_BASE.read_text())
    before={r["id"]:r for r in nov_before["results"]}
    meta={"study":"V21 10-portfolio original + HARD SL retrade simulation",
          "as_of_utc":CUT.isoformat(),"months":MONTHS,
          "stop_percent_levels":[100*x for x in STOP_PCTS],
          "default_sl_pct":100*DEFAULT_PCT,
          "policy":"Each leg sets absolute stop at entry quoted price +/- percent; intrabar M5 bid_low/ask_high; gap executed at worse M5 opening quote; 1bp slippage each way; if not triggered, fixed timed exit.",
          "conservative":"Stops may close earlier, but original fixed-hold entry spacing is retained. Other bots are independent and can overlap.",
          "limitations":["M5 OHLC cannot prove exact tick order, partial 5-minute bars may hide worse real fill","No swap/commission/funding, SL liquidity effects or margin","Partial November: only exits before UTC 2026-11-12 18:00","Backtest dates 2025 to 2026-10 were used for discovery, high overfitting risk"],
          "symbols":{},"parity_errors":[],"baseline_november_parity":[],
          "per_strategy":{},"portfolios":{},"status":"UNVERIFIED"}
    histories={}
    with requests.Session() as sess:
        for symbol in SYMBOLS:
            hist=history_m5(symbol)
            days=[];fetched=[]
            for day in NOV_DAYS:
                bars,info=nov.fetch_daily(sess,symbol,day,CUT)
                if bars is None:
                    raise RuntimeError(f"missing {symbol} November {info}")
                days.append(info);fetched.append(bars)
                print("NOV",symbol,day.strftime("%Y-%m-%d"),len(bars),info["status"],flush=True)
            recent=pd.concat(fetched).sort_index()
            # Require all completed Nov 1-11 days to have 288 M5 candles.
            for day in NOV_DAYS[:-1]:
                count=int(((recent.index>=day)&(recent.index<day+pd.Timedelta(days=1))).sum())
                if count<280:raise RuntimeError(f"gappy {symbol} Nov {day}: {count}")
            full=pd.concat([hist,recent]).sort_index()
            if full.index.has_duplicates:raise RuntimeError(f"duplicate {symbol} M5 data")
            histories[symbol]=full
            meta["symbols"][symbol]={"historical_m5":len(hist),"november_m5":len(recent),
                "november_days":days,"last_candle_utc":recent.index.max().isoformat()}
    all_ledgers={}
    for symbol in SYMBOLS:
        data=histories[symbol]
        for tf in sorted(set(v["timeframe"] for v in specs.values() if v["symbol"]==symbol)):
            bars=historical_full_frame(data,tf)
            for leg, sp in specs.items():
                if sp["symbol"]!=symbol or sp["timeframe"]!=tf:continue
                outcomes={}
                for pct in STOP_PCTS+(0.0,):
                    rows=simulate_stop(data,bars,sp,pct,CUT) if pct>0 else None
                    if pct==0:
                        # no-SL zero-run calculated using same schedule; November reconciliation
                        # The original standalone trades are time-held without stop.
                        raw=build_entries(bars,sp)
                        rows=[]
                        for i,j,points in raw:
                            exitdate=bars.index[j]
                            if exitdate>=CUT or exitdate<START:continue
                            period="2026-11_partial" if exitdate>=NOV_START else exitdate.strftime("%Y-%m")
                            if period in MONTHS:
                                rows.append({"period":period,"pnl_bp":points,
                                             "entry_utc":bars.index[i].isoformat(),
                                             "exit_utc":exitdate.isoformat(),"is_stop":False})
                    key=str(pct)
                    monthly=[float(sum(x["pnl_bp"] for x in rows if x["period"]==month)) for month in MONTHS]
                    trades=[sum(x["period"]==month for x in rows) for month in MONTHS]
                    stops=[sum(x["period"]==month and x["is_stop"] for x in rows) for month in MONTHS]
                    outcomes[key]={"monthly_bp":monthly,"trades_monthly":trades,
                        "stops_monthly":stops,"total_bp":sum(monthly),"trades":len(rows),
                        "stops":sum(stops),"november_bp":monthly[22],
                        "november_trades":trades[22]}
                    if pct==DEFAULT_PCT:all_ledgers[leg]=rows
                if leg not in expected:raise RuntimeError(f"{leg} absent from original V21 50-pool")
                original=expected[leg]["monthly_bp"]
                parity=max(abs(x-y) for x,y in zip(outcomes["0.0"]["monthly_bp"][:22],original))
                if parity>0.05:meta["parity_errors"].append({"leg":leg,"max_bp":round(parity,5)})
                meta["per_strategy"][leg]={"baseline_max_error_bp":round(parity,6),"scenarios":outcomes}
                print("BOT",leg,"parity_bp",round(parity,5),
                      "nov_baseline",round(outcomes["0.0"]["november_bp"],3),
                      "nov_SL1",round(outcomes[str(DEFAULT_PCT)]["november_bp"],3),flush=True)
    for p in sel:
        by_stop={}
        for pct in (0.0,)+STOP_PCTS:
            rows=[meta["per_strategy"][leg]["scenarios"][str(pct)] for leg in p["legs"]]
            monthly=[sum(r["monthly_bp"][i] for r in rows)/4 for i in range(23)]
            ntrades=[sum(r["trades_monthly"][i] for r in rows) for i in range(23)]
            stops=[sum(r["stops_monthly"][i] for r in rows) for i in range(23)]
            by_stop[str(pct)]={"monthly_bp":[round(float(x),5) for x in monthly],
              "profit_2025_bp":round(sum(monthly[:12]),4),
              "profit_2026_jan_oct_bp":round(sum(monthly[12:22]),4),
              "november_partial_bp":round(monthly[22],5),
              "positive_months_2025_oct2026":int(sum(x>0 for x in monthly[:22])),
              "has_both_years_positive":sum(monthly[:12])>0 and sum(monthly[12:22])>0,
              "november_positive":monthly[22]>0,
              "number_trades_history":sum(ntrades[:22]),
              "number_trades_november":ntrades[22],
              "stop_events_history":sum(stops[:22]),
              "stop_events_november":stops[22]}
        base=by_stop["0.0"]["november_partial_bp"]
        prior=before[p["id"]]["november_profit_bp"]
        novdiff=abs(base-prior)
        if novdiff>0.05:meta["baseline_november_parity"].append({"id":p["id"],"delta_bp":round(novdiff,5)})
        meta["portfolios"][p["id"]]={"legs":p["legs"],"composition":p["composition"],
            "original_november_bp":prior,"original_22month_bp":p["historical_2025_to_oct2026_bp"],
            "scenarios":by_stop}
    if meta["parity_errors"] or meta["baseline_november_parity"]:
        meta["status"]="FAILED_HISTORICAL_OR_NOVEMBER_PARITY_NOT_APPROVED"
    else:
        meta["status"]="PASS_VALIDATED_SL_BACKTEST"
    tally={}
    for pct in STOP_PCTS:
        k=str(pct)
        rows=[p["scenarios"][k] for p in meta["portfolios"].values()]
        tally[k]={"sl_percent":100*pct,"count":len(rows),
                  "positive_both_years":sum(p["has_both_years_positive"] for p in rows),
                  "positive_all_22":sum(p["positive_months_2025_oct2026"]==22 for p in rows),
                  "positive_november":sum(p["november_positive"] for p in rows),
                  "positive_all_22_and_november":sum(
                      p["positive_months_2025_oct2026"]==22 and p["november_positive"] for p in rows),
                  "stops_history_sum_all_portfolios":sum(p["stop_events_history"] for p in rows)}
    meta["overview"]=tally
    (OUT/"V21_SL_RETEST_FULL.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n")
    with (OUT/"V21_SL_1PCT_TRADES.csv").open("w",newline="") as f:
        columns=["leg","entry_utc","exit_utc","scheduled_exit_utc","pnl_bp","old_pnl_bp",
                 "is_stop","stop_quote","entry_quote","period"]
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for leg,rows in all_ledgers.items():
            for item in rows:writer.writerow({"leg":leg,**item})
    summary=["# V21: SL backtest on the 10 frozen portfolios",
        "SL is an absolute stop-loss from quoted entry on each of four legs.",
        "Fill tested on 5-minute observed Bid/Ask high/low; adverse gap and 1bp slippage.",
        "Stop 1% is the default defined **before** reviewing November results.",
        f"Validation: {meta['status']}.","",
        "|SL|Profitable both years|22/22 profitable months|Nov profitable|22/22 and Nov|",
        "|---|---:|---:|---:|---:|"]
    for k,v in tally.items():
        summary.append(f"|{v['sl_percent']:.2f}%|{v['positive_both_years']}|{v['positive_all_22']}|{v['positive_november']}|{v['positive_all_22_and_november']}|")
    summary.extend(["","See V21_SL_RETEST_FULL.json for each portfolio monthly P&L and each of its four bots.",
        "No real orders. Does not include swap or commissions.",
        "Data only through 2026-11-12 18:00 UTC, not the full November month."])
    (OUT/"V21_SL_RETEST_REPORT.md").write_text("\n".join(summary)+"\n")
    print("V21_SL_FINAL",json.dumps({"status":meta["status"],"overview":tally,
        "parity_errors":meta["parity_errors"][:5],
        "november_errors":meta["baseline_november_parity"][:5]}),flush=True)


if __name__=="__main__":
    main()
