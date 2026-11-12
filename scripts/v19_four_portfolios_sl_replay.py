#!/usr/bin/env python3
"""V19: replay 4 frozen oil-energy portfolios with mandatory fixed-price stop-loss.

All runs use unaltered signals and order times from 2025--2026 Oct screening
and 2026-Nov replay. Use actual Exness M5 bid/ask OHLC to model intrabar SL
instead of checking only parent-candle closes. Stopped legs cannot re-enter
until their original fixed-holding window finishes (conservative, reproducible).
One M5 bar does not reveal the first tick after a price spike; stops assume
trigger-at-stop or worse opening quote, plus 1bp additional exit slippage.
No real broker fills, no trading accounts or orders, no commissions, swaps.
"""
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

import v19_strategy_screen as v19
from v19_nov2026_22_replay import rebuild_frames

BASE=Path("data/v19_energies")
OUT=Path("results/v19_sl_research")
HIST=Path("data/v19_strategy_screen/V19_22_profit_then_orders_filtered.json")
NOV=Path("results/v19_november_2026/V19_nov2026_22_replay.json")
LEDGER=Path("results/v19_november_2026/V19_nov2026_leg_ledger.json")
WINNERS=("V19-065","V19-051","V19-043","V19-025")
STOP_BPS=(50,75,100,125,150,200,250,300,400)
DEFAULT_SL_BP=100
START_NOV=pd.Timestamp("2026-11-01T00:00:00Z")
END_NOV=pd.Timestamp("2026-11-12T18:00:00Z")


def load_nov_m5(symbol):
    path=Path(f"results/v19_november_2026/{symbol}_2026-11_M5_UTC.csv.gz")
    df=pd.read_csv(path,compression="gzip",index_col=0)
    df.index=pd.to_datetime(df.index,utc=True)
    df.index.name="timestamp_utc"
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("Bad November M5 structure")
    assert list(df.columns)==["bid_open","bid_high","bid_low","bid_close","ask_open","ask_high","ask_low","ask_close","tick_count"],df.columns
    return df


def to_m5_arrays(hist_m5, nov_m5=None):
    x=hist_m5.set_index("timestamp_utc")
    if nov_m5 is not None:
        x=pd.concat([x,nov_m5]).sort_index()
        x=x[~x.index.duplicated(keep="last")]
    return {
        "ts":x.index,
        "bid_open":x.bid_open.to_numpy(dtype=float),
        "bid_low":x.bid_low.to_numpy(dtype=float),
        "ask_open":x.ask_open.to_numpy(dtype=float),
        "ask_high":x.ask_high.to_numpy(dtype=float)
    }


def baseline_price(side, bid_entry, ask_entry, bid_exit, ask_exit):
    mid=(bid_entry+ask_entry)/2
    if side=="long":
        return (bid_exit*(1-v19.SLIPPAGE)-ask_entry*(1+v19.SLIPPAGE))/mid*10000
    return (bid_entry*(1-v19.SLIPPAGE)-ask_exit*(1+v19.SLIPPAGE))/mid*10000


def historical_legs(df, leg):
    symbol, tf, signal, side, holdstr, session=leg.split("|")
    hold=int(holdstr[1:])
    timestamps=df.timestamp_utc
    d=timestamps.dt
    month=((d.year-2025)*12+d.month-1).to_numpy(dtype=int)
    bid=df.bid_open.to_numpy(float)
    ask=df.ask_open.to_numpy(float)
    mid=(bid+ask)/2
    valid=np.isfinite(bid)&np.isfinite(ask)&np.isfinite(mid)&(mid>0)
    ids=np.arange(len(df))
    future=np.minimum(ids+hold,len(df)-1)
    allowed=v19.signals(df)[signal] & (ids+hold<len(df)) & valid & valid[future]
    if session!="all":
        allowed&=(d.hour.to_numpy()==int(session[:2]))&(d.minute.to_numpy()==0)
    entry_idx=v19.pick_nonoverlap(np.flatnonzero(allowed),hold)
    exit_idx=future[entry_idx]
    # Identical PnL/month-selection semantics as original V19 screening
    usable=(month[exit_idx]>=0)&(month[exit_idx]<22)
    entry_idx=entry_idx[usable]
    exit_idx=exit_idx[usable]
    trades=[]
    for j,k in zip(entry_idx,exit_idx):
        trade={
            "leg":leg,"symbol":symbol,"side":side,
            "entry":timestamps.iloc[int(j)],"time_exit":timestamps.iloc[int(k)],
            "entry_bid":float(bid[j]),"entry_ask":float(ask[j]),
            "exit_bid":float(bid[k]),"exit_ask":float(ask[k]),
            "period":"historical"
        }
        trade["baseline_bp"]=baseline_price(side,trade["entry_bid"],trade["entry_ask"],trade["exit_bid"],trade["exit_ask"])
        trades.append(trade)
    return trades


def november_legs(df,leg,ledger):
    symbol, tf, signal, side, holdstr, session=leg.split("|")
    hold=int(holdstr[1:])
    dates=df.timestamp_utc
    bytime=pd.Series(np.arange(len(dates)),index=dates)
    bid=df.bid_open.to_numpy(float)
    ask=df.ask_open.to_numpy(float)
    trades=[]
    for event in ledger[leg]:
        if event["status"]!="closed":
            raise ValueError(f"Unclosed November trade not supported for {leg}: {event}")
        when=pd.Timestamp(event["entry_utc"])
        until=pd.Timestamp(event["exit_utc"])
        if not (START_NOV<=when<END_NOV and until<=END_NOV):
            raise ValueError("November ledger outside study interval")
        i=int(bytime.loc[when])
        j=int(bytime.loc[until])
        if i+hold!=j:
            raise ValueError(f"November timeframe hold mismatch {leg} {when}")
        tr={"leg":leg,"symbol":symbol,"side":side,
            "entry":when,"time_exit":until,
            "entry_bid":float(bid[i]),"entry_ask":float(ask[i]),
            "exit_bid":float(bid[j]),"exit_ask":float(ask[j]),
            "period":"november"}
        tr["baseline_bp"]=baseline_price(side,tr["entry_bid"],tr["entry_ask"],tr["exit_bid"],tr["exit_ask"])
        if abs(tr["baseline_bp"]-event["pnl_bp"])>0.00004:
            raise ValueError(f"November ledger/PnL mismatch {leg}: {tr['baseline_bp']} / {event['pnl_bp']}")
        trades.append(tr)
    return trades


def apply_stop(trades,m5,sl_bp):
    """Explicit SL price from Ask for long, Bid for short; stop uses exit side quote."""
    t_arr=m5["ts"].asi8
    bopen,blow=m5["bid_open"],m5["bid_low"]
    aopen,ahigh=m5["ask_open"],m5["ask_high"]
    entry=np.array([t["entry"].value for t in trades],dtype=np.int64)
    closing=np.array([t["time_exit"].value for t in trades],dtype=np.int64)
    starts=np.searchsorted(t_arr,entry,side="left")
    ends=np.searchsorted(t_arr,closing,side="left")
    pnl=np.empty(len(trades),dtype=float)
    stopped=np.zeros(len(trades),dtype=bool)
    actual_exits=[]
    slippage=v19.SLIPPAGE
    for i,(tr,start,end) in enumerate(zip(trades,starts,ends)):
        if not (start<end<=len(t_arr)):
            raise ValueError(f"Missing M5 coverage {tr['leg']} {tr['entry']}--{tr['time_exit']} {start} {end}")
        side=tr["side"]
        x_bid=tr["entry_bid"]
        x_ask=tr["entry_ask"]
        mid=(x_bid+x_ask)/2
        if side=="long":
            level=x_ask*(1-sl_bp/10000)
            hits=np.flatnonzero(blow[start:end]<=level)
            if len(hits):
                index=start+int(hits[0])
                fill=min(float(level),float(bopen[index]))
                pnl[i]=(fill*(1-slippage)-x_ask*(1+slippage))/mid*10000
                stopped[i]=True
                actual_exits.append(pd.Timestamp(t_arr[index],tz="UTC"))
                continue
        elif side=="short":
            level=x_bid*(1+sl_bp/10000)
            hits=np.flatnonzero(ahigh[start:end]>=level)
            if len(hits):
                index=start+int(hits[0])
                fill=max(float(level),float(aopen[index]))
                pnl[i]=(x_bid*(1-slippage)-fill*(1+slippage))/mid*10000
                stopped[i]=True
                actual_exits.append(pd.Timestamp(t_arr[index],tz="UTC"))
                continue
        else:
            raise ValueError(side)
        pnl[i]=tr["baseline_bp"]
        actual_exits.append(tr["time_exit"])
    return {
        "pnl":pnl,
        "stops":stopped,
        "exits":pd.DatetimeIndex(actual_exits),
        "trades":trades
    }


def summarize_portfolio(portfolio,results,sl_bp,window):
    name=portfolio["portfolio"]
    parts=[results[l] for l in portfolio["legs"]]
    # Each leg allocated exactly a quarter of fixed portfolio notional.
    all_pnl=np.concatenate([p["pnl"] for p in parts])/4
    all_stop=np.concatenate([p["stops"] for p in parts])
    all_exit=pd.DatetimeIndex(np.concatenate([p["exits"].asi8 for p in parts])).tz_localize("UTC")
    total=sum(float(np.sum(p["pnl"])) for p in parts)/4
    ledger_count=sum(len(p["pnl"]) for p in parts)
    summary={
        "portfolio":name,"sl_bp":sl_bp,"period":window,
        "total_profit_bp":round(total,5),
        "trades":ledger_count,
        "stop_count":int(all_stop.sum()),
        "stop_fraction":round(float(all_stop.mean()),4) if ledger_count else 0,
        "worst_single_leg_trade_bp":round(float(np.min(all_pnl)*4),5) if ledger_count else None,
        "worst_portfolio_allocated_trade_bp":round(float(np.min(all_pnl)),5) if ledger_count else None,
        "winning_orders":int((all_pnl>0).sum()),
        "losing_orders":int((all_pnl<0).sum()),
        "by_leg":[{
            "leg":l,
            "trades":len(results[l]["pnl"]),
            "stop_count":int(results[l]["stops"].sum()),
            "realized_bp_unweighted":round(float(results[l]["pnl"].sum()),5)
        } for l in portfolio["legs"]]
    }
    if window=="historical":
        periods=pd.PeriodIndex(all_exit.tz_convert(None),freq="M")
        labels=[pd.Period(yy,freq="Y") for yy in ()] # keep compatible with old pandas versions
        months=[pd.Period(f"{yy}-{mm:02d}",freq="M") for yy,n in ((2025,12),(2026,10)) for mm in range(1,n+1)]
        per_month=[float(all_pnl[np.array(periods==m)].sum()) for m in months]
        summary.update({
            "positive_months":int(np.count_nonzero(np.array(per_month)>0)),
            "month_total":22,
            "profit_2025_bp":round(float(sum(per_month[:12])),5),
            "profit_2026_jan_oct_bp":round(float(sum(per_month[12:])),5),
            "min_month_bp":round(float(min(per_month)),5),
            "max_month_bp":round(float(max(per_month)),5),
            "monthly_bp":[round(x,5) for x in per_month],
            "max_month_end_equity_drawdown_bp":round(float(maximum_drawdown(per_month)),5)
        })
    return summary


def maximum_drawdown(series):
    a=np.r_[0,np.cumsum(series)]
    return float(np.max(np.maximum.accumulate(a)-a))


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    source=json.loads(HIST.read_text())
    selected={p["portfolio"]:p for p in source["retained"] if p["portfolio"] in WINNERS}
    assert len(selected)==4
    nov=json.loads(NOV.read_text())
    month_results={p["id"]:p for p in nov["rows"]}
    past_ledger=json.loads(LEDGER.read_text())
    unique_legs=sorted(set(leg for p in selected.values() for leg in p["legs"]))
    print("V19_SL_DATA",len(unique_legs),"unique legs",flush=True)
    symbols=sorted({leg.split("|")[0] for leg in unique_legs})
    frames={}
    frames_nov={}
    m5_hist={}
    m5_nov={}
    for symbol in symbols:
        hist_m5=v19.read_frame(BASE,symbol,"M5")
        hist_nov_m5=load_nov_m5(symbol)
        m5_hist[symbol]=to_m5_arrays(hist_m5)
        m5_nov[symbol]=to_m5_arrays(hist_m5,hist_nov_m5)
        frames_nov.update({(symbol,tf):fr for tf,fr in rebuild_frames(BASE,symbol,hist_nov_m5).items()})
        for leg in unique_legs:
            sym,tf,*_=leg.split("|")
            if sym==symbol and (sym,tf) not in frames:
                frames[(sym,tf)]=v19.read_frame(BASE,sym,tf)
        print("V19_SL_M5",symbol,"history",len(m5_hist[symbol]["ts"]),"nov added",len(hist_nov_m5),flush=True)
    history={}
    november={}
    for leg in unique_legs:
        sym,tf,*_=leg.split("|")
        history[leg]=historical_legs(frames[(sym,tf)],leg)
        november[leg]=november_legs(frames_nov[(sym,tf)],leg,past_ledger)
        print("V19_SL_LEG",leg,"hist",len(history[leg]),"nov",len(november[leg]),flush=True)

    # Explicit sanity checks ensure we replicate original NO-SL backtests.
    for pid in WINNERS:
        p=selected[pid]
        year_count=sum(len(history[l]) for l in p["legs"])
        assert year_count==p["total_entries"],f"History trade mismatch {pid}: {year_count} vs {p['total_entries']}"
        h_total=sum(sum(x["baseline_bp"] for x in history[l]) for l in p["legs"])/4
        n_total=sum(sum(x["baseline_bp"] for x in november[l]) for l in p["legs"])/4
        if abs(h_total-p["total_profit_bp"])>0.001:
            raise ValueError(f"Historical P&L baseline mismatch {pid}: {h_total} vs {p['total_profit_bp']}")
        if abs(n_total-month_results[pid]["november_realized_profit_bp"])>0.001:
            raise ValueError(f"November P&L mismatch {pid}: {n_total} vs {month_results[pid]['november_realized_profit_bp']}")
        print("V19_SL_BASELINE_OK",pid,year_count,round(h_total,5),round(n_total,5),flush=True)

    strategies=[]
    for sl in STOP_BPS:
        calculated_hist={leg:apply_stop(history[leg],m5_hist[leg.split("|")[0]],sl) for leg in unique_legs}
        calculated_nov={leg:apply_stop(november[leg],m5_nov[leg.split("|")[0]],sl) for leg in unique_legs}
        for pid in WINNERS:
            p=selected[pid]
            train=summarize_portfolio(p,calculated_hist,sl,"historical")
            test=summarize_portfolio(p,calculated_nov,sl,"november")
            strategies.append({"portfolio":pid,"stop_basis_points":sl,"stop_pct":round(sl/100,3),"historical":train,"november":test})
            print("V19_SL_SETTING",pid,sl,"months",train["positive_months"],"history",train["total_profit_bp"],"nov",test["total_profit_bp"],"novorders",test["trades"],"hist stops",train["stop_count"],flush=True)
    baseline={pid:{
        "historical_bp":selected[pid]["total_profit_bp"],
        "historical_positive_months":selected[pid]["positive_months"],
        "november_bp":month_results[pid]["november_realized_profit_bp"],
        "historical_orders":selected[pid]["total_entries"],
        "november_orders":month_results[pid]["november_closed_orders"],
    } for pid in WINNERS}
    # Default chosen BEFORE validation, no tuning on 2026 Nov.
    main_results=[r for r in strategies if r["stop_basis_points"]==DEFAULT_SL_BP]
    comparison=[]
    for x in strategies:
        h=x["historical"];n=x["november"]
        comparison.append({
            "portfolio":x["portfolio"],"sl_bp":x["stop_basis_points"],"sl_pct":x["stop_pct"],
            "history_months_positive":h["positive_months"],
            "history_profit_bp":h["total_profit_bp"],
            "history_min_month_bp":h["min_month_bp"],
            "history_largest_month_end_dd_bp":h["max_month_end_equity_drawdown_bp"],
            "history_stop_count":h["stop_count"],
            "november_profit_bp":n["total_profit_bp"],
            "november_orders":n["trades"],
            "november_stop_count":n["stop_count"],
            "november_worst_trade_bp":n["worst_single_leg_trade_bp"],
            "positive_both_years":h["profit_2025_bp"]>0 and h["profit_2026_jan_oct_bp"]>0,
            "positive_november":n["total_profit_bp"]>0
        })
    output={
        "project":"V19",
        "strategy_selection":"The four positively performing 2026-Nov portfolios from prior deduplication",
        "selection_ids":list(WINNERS),
        "history_period":"2025-01-01 through 2026-10-31 inclusive UTC",
        "november_period":"2026-11-01 through completed M5 candles prior to 2026-11-12 18:00 UTC (original frozen snapshot)",
        "sl_definition":"Hard stop from entry Ask for buys and entry Bid for sells. For buy stop test M5 Bid lows; for sell test M5 Ask highs; fill at stop level or worse M5 opening quote when gap crosses, then apply 1 bp exit slippage. Stop on broker requires actual MT5 implementation and confirmation; this only simulates.",
        "fixed_pct_100bps_default":"1.00% of entry execution price for every bot on both commodities; fixed close after original number of timeframe bars if stop never hit",
        "sl_bp_values":list(STOP_BPS),
        "no_reoptimizing_on_november":True,
        "trade_selection":"Signals & time entries identical to old no-SL version; after stop, do not reactivate same leg until previously scheduled hold has ended.",
        "remaining_limitations":"M5 intra-bar quote extremes cannot reveal exact stop fill/spread at the tick of trigger. No swap, commissions, order rejection, or MT5 broker stop-distance validation. Return is fixed-notional bp, NOT USD. Portfolio positions can overlap.",
        "baseline":baseline,
        "fixed_1pct_default":main_results,
        "comparison":comparison,
        "all_scenarios":strategies
    }
    (OUT/"V19_four_portfolios_with_SL_report.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame(comparison).to_csv(OUT/"V19_SL_sensitivity_4_portfolios.csv",index=False)
    print("V19_SL_FINAL",json.dumps({
        "default_1pct": [x for x in comparison if x["sl_bp"]==DEFAULT_SL_BP],
        "all_historical_months_positive":[x for x in comparison if x["history_months_positive"]==22],
        "baseline":baseline
    }),flush=True)


if __name__=="__main__":
    main()
