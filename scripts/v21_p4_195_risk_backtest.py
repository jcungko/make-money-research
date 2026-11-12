#!/usr/bin/env python3
"""V21-P4-195 risk overlay — reproducible, READ-ONLY, not an MT5 Expert Advisor.

Frozen four original V19 signal/entry rules; add H1 ATR14 stops and shared risk
controls. Uses archived Exness Bid/Ask M5 quotes, including November daily data.

All account money and crypto units are a NORMALIZED research simulation only:
does NOT convert quantities to Exness lots or model broker margin/swap/fees.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0,"scripts")
import v19_strategy_screen as engine
from v12_exness_collect import FIELDS
from v21_november_replay import fetch_daily

ROOT=Path("data/v21_crypto")
SOURCE=Path("data/v21_crypto_screen/V21_portfolio_combinations_audit.json")
OUT=Path("data/v21_p4_195_risk")
HISTORY_START=pd.Timestamp("2025-01-01T00:00:00Z")
HISTORY_END=pd.Timestamp("2026-11-01T00:00:00Z")
NOV_END=pd.Timestamp("2026-11-13T00:00:00Z")
START_CASH=10000.0
SLIPPAGE=0.0001
ATR_MULT=2.0
PER_TRADE_RISK=.002
MAX_BTC_OPEN_RISK=.006
MAX_ACCOUNT_OPEN_RISK=.01
MAX_GROSS_NOTIONAL_MULT=2.0
MIN_TRADE_RISK=.0005
MAX_DAILY_DRAWDOWN=.02
TIMEFRAMES={"M30":"30min","H1":"1h","H4":"4h"}
SELECTED=(
    "BTCUSD|H1|range_top_20|long|H2|08utc",
    "BTCUSD|H1|above_sma_50|short|H8|00utc",
    "BTCUSD|M30|ema_below_3_10|long|H8|20utc",
    "BTCUSD|H4|range_top_20|short|H3|20utc",
)
MONTHS=[f"{yr}-{mo:02d}" for yr,max_m in ((2025,12),(2026,11)) for mo in range(1,max_m+1)]

def read_history():
    pieces=[]
    for year,months in ((2025,12),(2026,10)):
        path=ROOT/f"BTCUSD_{year}_UTC_7TF.zip"
        with zipfile.ZipFile(path) as archive:
            meta=json.loads(archive.read("manifest.json"))
            if meta.get("complete_months") is not True or meta.get("month_count_ok") != months:
                raise ValueError(f"incomplete Exness BTCUSD {year} tick history")
            raw=archive.read(f"BTCUSD_M5_{year}_UTC.csv")
        part=pd.read_csv(io.BytesIO(raw),index_col=0)
        part.index=pd.to_datetime(part.index,utc=True)
        pieces.append(part)
    return pd.concat(pieces).sort_index()

def read_november():
    today=pd.Timestamp.now(tz="UTC")
    cap=min(NOV_END,today.floor("5min")-pd.Timedelta(minutes=5))
    bars=[];status=[]
    with requests.Session() as sess:
        for day in pd.date_range("2026-11-01","2026-11-12",tz="UTC"):
            frame,meta=fetch_daily(sess,"BTCUSD",day,cap)
            status.append(meta)
            print("NOV_SOURCE",meta["day"],meta["status"],meta.get("m5_bars"),flush=True)
            if frame is not None:
                if day>=cap:
                    continue
                # The last tick bucket may not contain five full minutes.
                tick_last=pd.Timestamp(meta["last_tick_utc"])
                last_safe=min(tick_last.floor("5min"),cap)
                frame=frame[frame.index<last_safe]
                if not frame.empty:bars.append(frame)
    errors=[x for x in status if x["status"]=="error"]
    if errors: raise RuntimeError("Missing November day(s): "+json.dumps(errors)[:1200])
    if len(bars)!=12: raise RuntimeError(f"Expected twelve daily M5 sets, got {len(bars)}")
    nov=pd.concat(bars).sort_index()
    if nov.index.has_duplicates:raise RuntimeError("duplicate November minute buckets")
    if nov.index.max()<pd.Timestamp("2026-11-12T00:00:00Z"):
        raise RuntimeError("November quotes do not reach the November 12 UTC day")
    # BTCUSD indicative history is expected to have very dense 24x7 quotes.
    for day in pd.date_range("2026-11-01","2026-11-11",tz="UTC"):
        c=((nov.index>=day)&(nov.index<day+pd.Timedelta(days=1))).sum()
        if c<280:raise RuntimeError(f"Missing M5 coverage on {day.date()}: {c}/288")
    return nov,status

def resample(m5,tf):
    if tf=="M5":return m5
    out=m5.resample(TIMEFRAMES[tf],closed="left",label="left",origin="epoch").agg(FIELDS)
    return out.loc[out.tick_count>0]

def specs():
    with SOURCE.open() as handle:
        audit=json.load(handle)
    record=next(x for x in audit["all_passing_portfolios"] if x["id"]=="V21-P4-195")
    if tuple(record["legs"])!=SELECTED:
        raise ValueError("Frozen P4-195 changed. Abort rather than silently optimize.")
    data=json.loads(Path("data/v21_crypto_screen/v21_best_near_misses.json").read_text())
    expected={r["id"]:r for r in data}
    if any(leg not in expected for leg in SELECTED):
        raise ValueError("Missing baseline single-bot backtests")
    return expected,record

def build_events(m5, cutoff):
    frames={tf:resample(m5,tf) for tf in TIMEFRAMES}
    # ATR from completed H1 candles only; not from still-forming entry candle.
    h1=frames["H1"]
    prev=(h1.bid_close+h1.ask_close).div(2).shift(1)
    high=(h1.bid_high+h1.ask_high).div(2)
    low=(h1.bid_low+h1.ask_low).div(2)
    tr=pd.concat([high-low,(high-prev).abs(),(low-prev).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14,min_periods=14).mean().shift(1)
    # ATR value at the H1 open is computed from 14 previous finished H1 candles.
    atr_m5=atr.reindex(m5.index,method="ffill")
    atr_lookup=atr_m5.to_dict()
    events=[]
    for order,leg in enumerate(SELECTED):
        sym,tf,signal,side,hold,session=leg.split("|")
        f=frames[tf]
        ts=f.index
        flags=engine.signals(f)[signal]
        h=int(session[:2])
        nb=int(hold[1:])
        arr=np.arange(len(f))
        valid=np.isfinite(f.bid_open)&np.isfinite(f.ask_open)&(f.bid_open>0)&(f.ask_open>=f.bid_open)
        eligible=np.flatnonzero(flags & valid.to_numpy() &
             (ts.hour==h)&(ts.minute==0)&(arr+nb<len(f)))
        eligible=engine.pick_nonoverlap(eligible,nb)
        for idx in eligible:
            when=ts[idx]
            if when>=cutoff: continue
            exit_at=ts[idx+nb]
            # Prevent lookahead when an apparently closed timeframe candle is actually incomplete.
            if not pd.notna(when) or when not in atr_lookup:continue
            events.append(dict(bot=leg, order=order, ts=when, exit_at=exit_at,
                tf=tf, side=side, atr=float(atr_lookup[when]) if pd.notna(atr_lookup[when]) else float("nan"),
                bid=float(f.bid_open.iloc[idx]),ask=float(f.ask_open.iloc[idx]),
                exit_bid=float(f.bid_open.iloc[idx+nb]),exit_ask=float(f.ask_open.iloc[idx+nb])))
    events.sort(key=lambda e:(e["ts"],e["order"]))
    return events

def verify_reference(events, expected):
    by_leg_month=defaultdict(lambda:defaultdict(float))
    for e in events:
        if not HISTORY_START<=e["exit_at"]<HISTORY_END:
            continue
        middle=(e["bid"]+e["ask"])/2
        if e["side"]=="long":
            pnl=(e["exit_bid"]*(1-SLIPPAGE)-e["ask"]*(1+SLIPPAGE))/middle*10000
        else:
            pnl=(e["bid"]*(1-SLIPPAGE)-e["exit_ask"]*(1+SLIPPAGE))/middle*10000
        by_leg_month[e["bot"]][e["exit_at"].strftime("%Y-%m")]+=pnl
    differences={}
    for leg in SELECTED:
        exp=expected[leg]["monthly_bp"]
        calc=[by_leg_month[leg].get(m,0.0) for m in MONTHS[:22]]
        largest=max(abs(x-y) for x,y in zip(calc,exp))
        differences[leg]=dict(max_abs_diff_bp=round(largest,5),
            replay_total_bp=round(sum(calc),4),
            original_total_bp=expected[leg]["total_bp"])
    return differences

def risk_test(m5,events,cutoff):
    orders=defaultdict(list)
    for event in events:
        orders[event["ts"]].append(event)
    bid_open=m5.bid_open.to_numpy(dtype=float)
    ask_open=m5.ask_open.to_numpy(dtype=float)
    bid_low=m5.bid_low.to_numpy(dtype=float)
    ask_high=m5.ask_high.to_numpy(dtype=float)
    bid_close=m5.bid_close.to_numpy(dtype=float)
    ask_close=m5.ask_close.to_numpy(dtype=float)
    times=m5.index
    cash=START_CASH
    open_positions=[]
    completed=[]
    event_counts=Counter()
    day_lock_count=0
    day=None
    day_equity_start=START_CASH
    day_paused=False
    equity_peak=START_CASH
    deepest=0.0
    eq_min=START_CASH
    snapshots=[]
    last_equity=START_CASH

    def mark(bo,ao):
        v=cash
        for p in open_positions:
            if p["side"]=="long":
                v+=(bo*(1-SLIPPAGE)-p["entry_fill"])*p["qty"]
            else:
                v+=(p["entry_fill"]-ao*(1+SLIPPAGE))*p["qty"]
        return v

    def close_position(p, t, raw_price, why, gap=False):
        nonlocal cash
        if p["side"]=="long":
            fill=raw_price*(1-SLIPPAGE)
            profit=(fill-p["entry_fill"])*p["qty"]
        else:
            fill=raw_price*(1+SLIPPAGE)
            profit=(p["entry_fill"]-fill)*p["qty"]
        cash+=profit
        completed.append(dict(bot=p["bot"],entry_utc=p["opened"].isoformat(),
            exit_utc=t.isoformat(),reason=why,qty_btc=round(p["qty"],8),
            entry_fill=round(p["entry_fill"],5),stop=round(p["stop"],5),
            exit_fill=round(fill,5),profit_usd=round(profit,6),
            initial_risk_usd=round(p["initial_risk"],5),
            realized_r=round(profit/p["initial_risk"],6),
            gap_through_sl=gap))
        event_counts[why]+=1

    for i,t in enumerate(times):
        if t>=cutoff:break
        bo,ao=bid_open[i],ask_open[i]
        if not np.isfinite(bo+ao) or bo<=0 or ao<bo:
            continue
        current_day=t.strftime("%Y-%m-%d")
        if current_day!=day:
            day=current_day
            day_equity_start=mark(bo,ao)
            day_paused=False
        # Existing stops and time exits are active even when the daily entry lock is on.
        remain=[]
        for p in open_positions:
            if t>=p["planned_exit"]:
                close_position(p,t,bo if p["side"]=="long" else ao,"TIME")
            else:
                remain.append(p)
        open_positions=remain
        liveeq=mark(bo,ao)
        if not day_paused and liveeq<day_equity_start*(1-MAX_DAILY_DRAWDOWN):
            day_paused=True
            day_lock_count+=1
        for order in orders.get(t,()):
            if order["bot"] in [p["bot"] for p in open_positions]:
                raise RuntimeError(f"Overlapping same-bot trade {order['bot']} at {t}")
            if day_paused:
                event_counts["DENIED_DAILY_LIMIT"]+=1
                continue
            a=order["atr"]
            spread=ao-bo
            if not np.isfinite(a) or a<=0:
                event_counts["DENIED_ATR_WARMUP"]+=1
                continue
            dist=max(ATR_MULT*a,3*spread)
            side=order["side"]
            fill=ao*(1+SLIPPAGE) if side=="long" else bo*(1-SLIPPAGE)
            stop=fill-dist if side=="long" else fill+dist
            if stop<=0:
                event_counts["DENIED_INVALID_SL"]+=1
                continue
            worst=stop*(1-SLIPPAGE) if side=="long" else stop*(1+SLIPPAGE)
            per_btc=(fill-worst) if side=="long" else (worst-fill)
            if per_btc<=0:
                event_counts["DENIED_INVALID_RISK"]+=1
                continue
            eq=max(mark(bo,ao),0)
            reserved=sum(x["initial_risk"] for x in open_positions)
            allowed=min(eq*PER_TRADE_RISK,
                eq*MAX_BTC_OPEN_RISK-reserved,
                eq*MAX_ACCOUNT_OPEN_RISK-reserved)
            qty=max(0,allowed)/per_btc
            active_notional=sum(x["qty"]*x["entry_mid"] for x in open_positions)
            notional_room=max(0,eq*MAX_GROSS_NOTIONAL_MULT-active_notional)
            qty=min(qty,notional_room/max((ao+bo)/2,1e-9))
            actual_risk=qty*per_btc
            if eq<=0 or actual_risk < eq*MIN_TRADE_RISK:
                event_counts["DENIED_EXPOSURE_OR_BTC_CAP"]+=1
                continue
            open_positions.append(dict(bot=order["bot"],opened=t,side=side,
                planned_exit=order["exit_at"],entry_fill=fill,entry_mid=(ao+bo)/2,
                stop=stop,qty=qty,initial_risk=actual_risk))
            event_counts["OPENED"]+=1
        # For trades entered at this bar's open, check intrabar stop in same M5.
        remain=[]
        for p in open_positions:
            if p["side"]=="long" and bid_low[i]<=p["stop"]:
                raw=min(bo,p["stop"])
                close_position(p,t,raw,"SL",bo<p["stop"])
            elif p["side"]=="short" and ask_high[i]>=p["stop"]:
                raw=max(ao,p["stop"])
                close_position(p,t,raw,"SL",ao>p["stop"])
            else:
                remain.append(p)
        open_positions=remain
        # Use end-of-bar equity to measure mark-to-market drawdown, including SL.
        last_equity=mark(bid_close[i],ask_close[i])
        equity_peak=max(last_equity,equity_peak)
        deepest=max(deepest,(equity_peak-last_equity)/equity_peak*100)
        eq_min=min(eq_min,last_equity)
        if t.hour==23 and t.minute==55:
            snapshots.append(dict(time_utc=t.isoformat(),equity_usd=round(last_equity,4),
                balance_usd=round(cash,4),open_positions=len(open_positions)))
    # Do not mark pending positions as closed or assign unearned PnL.
    months_usd=defaultdict(float)
    months_count=Counter()
    for p in completed:
        month=p["exit_utc"][:7]
        months_usd[month]+=p["profit_usd"]
        months_count[month]+=1
    monthly=[dict(month=m,realized_pnl_usd=round(months_usd[m],2),
        realized_pnl_pct_initial=round(months_usd[m]/START_CASH*100,5),
        closed_trades=int(months_count[m]),positive=bool(months_usd[m]>0))
        for m in MONTHS]
    by_bot=defaultdict(lambda:dict(realized_usd=0.0,closed_trades=0,stopouts=0))
    for p in completed:
        q=by_bot[p["bot"]]
        q["realized_usd"]+=p["profit_usd"]
        q["closed_trades"]+=1
        q["stopouts"]+=p["reason"]=="SL"
    for item in by_bot.values():
        item["realized_usd"]=round(item["realized_usd"],2)
    pending=[dict(bot=p["bot"],entry_utc=p["opened"].isoformat(),
        planned_exit_utc=p["planned_exit"].isoformat(),initial_risk_usd=round(p["initial_risk"],2))
        for p in open_positions]
    return dict(initial_equity_usd=START_CASH,final_balance_usd=round(cash,2),
        marked_equity_usd=round(last_equity,2),
        max_drawdown_pct=round(deepest,4),
        min_marked_equity_usd=round(eq_min,2),
        completed_trades=len(completed),
        stopouts=sum(x["reason"]=="SL" for x in completed),
        pending=pending,risk_events=dict(event_counts),
        daily_entry_lock_trigger_days=day_lock_count,
        positive_months_2025_to_oct2026=int(sum(x["positive"] for x in monthly[:22])),
        positive_months_from_jan2025_to_nov_partial=int(sum(x["positive"] for x in monthly)),
        monthly=monthly,by_bot=dict(by_bot),trades=completed,
        end_of_day_equity=snapshots)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    baseline,record=specs()
    history=read_history()
    nov,source=read_november()
    m5=pd.concat([history,nov]).sort_index()
    if m5.index.has_duplicates:
        raise RuntimeError("Overlapping Nov and historical prices")
    newest_tick=pd.Timestamp(source[-1]["last_tick_utc"])
    cutoff=min(NOV_END,pd.Timestamp.now(tz="UTC").floor("5min")-pd.Timedelta(minutes=5),
        newest_tick.floor("5min"))
    m5=m5[m5.index<cutoff]
    if len(m5)<180000:raise RuntimeError("Insufficient M5 price history")
    events=build_events(m5,cutoff)
    parity=verify_reference(events,baseline)
    worst_parity=max(v["max_abs_diff_bp"] for v in parity.values())
    if worst_parity>0.5:
        result=dict(status="FAILED_HISTORICAL_PARITY",parity=parity,
            message="Do not interpret risk overlay PnL until entry/exit parity is fixed")
        (OUT/"V21_P4_195_RISK_AUDIT.json").write_text(json.dumps(result,indent=2)+"\n")
        raise RuntimeError(f"Historical replay parity too poor: {worst_parity:.4f} bp")
    sim=risk_test(m5,events,cutoff)
    risk=dict(sl_formula="2 x completed H1 ATR14 with floor 3 x live observed spread",
        per_trade_initial_stop_risk_pct=PER_TRADE_RISK*100,
        total_btc_initial_stop_risk_pct=MAX_BTC_OPEN_RISK*100,
        total_account_initial_stop_risk_pct=MAX_ACCOUNT_OPEN_RISK*100,
        max_gross_btc_notional_to_equity=MAX_GROSS_NOTIONAL_MULT,
        min_trade_risk_pct=MIN_TRADE_RISK*100,
        daily_equity_loss_pause_new_entries_pct=MAX_DAILY_DRAWDOWN*100,
        daily_stop_rule="pause entries until next UTC date; NO forced flattening",
        default_exit="original time-based exit if SL not hit",
        entry_execution="long Ask / short Bid plus 1bp adverse slippage",
        exit_execution="long Bid / short Ask plus 1bp adverse slippage",
        sl_intrabar="5-minute Bid low (long) / Ask high (short), stop-first after entry",
        gap_rule="if M5 open is through stop, use worse opening price")
    result={k:v for k,v in sim.items() if k not in ("trades","end_of_day_equity")}
    result.update(status="BACKTEST_MODEL_ONLY",symbol="BTCUSD",portfolio="V21-P4-195",
        all_four_bots_preserved=list(SELECTED),source="Exness public indicative Bid/Ask ticks",
        last_complete_m5_exclusive_utc=cutoff.isoformat(),
        historical_months="2025-01 to 2026-10",
        november_month="2026-11 PARTIAL THROUGH cutoff",
        risk_config=risk,
        baseline_22m_equal_notional_bp=record["total_bp"],
        original_monthly_equal_notional_bp=record["monthly_bp"],
        original_nov_partial_equal_notional_bp=32.03916,
        original_baseline_parity_by_bot=parity,
        caveats=["Account USD and BTC quantity are normalized, not Exness contract lots.",
            "No swap, overnight financing, platform commission, broker-specific lot steps, margin, liquidation, or exact live slippage.",
            "Monthly realized PnL is attributed to closing month; open November positions remain unrealized.",
            "Daily 2% loss pause is not a guaranteed maximal loss; stops/gaps may exceed budgets.",
            "ATR stops and total risk caps change the strategy; original 22/22 profit is not inherited.",
            "This uses in-sample 2025-2026 parameters; walk-forward needed."])
    (OUT/"V21_P4_195_RISK_AUDIT.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,default=lambda o: o.item() if isinstance(o,np.generic) else str(o))+"\n")
    with (OUT/"V21_P4_195_RISK_TRADES.csv").open("w",newline="") as handle:
        w=csv.DictWriter(handle,fieldnames=["bot","entry_utc","exit_utc","reason","qty_btc",
            "entry_fill","stop","exit_fill","profit_usd","initial_risk_usd","realized_r","gap_through_sl"])
        w.writeheader();w.writerows(sim["trades"])
    with (OUT/"V21_P4_195_EQUITY_DAILY.csv").open("w",newline="") as handle:
        w=csv.DictWriter(handle,fieldnames=["time_utc","equity_usd","balance_usd","open_positions"])
        w.writeheader();w.writerows(sim["end_of_day_equity"])
    text=["# V21-P4-195 with ATR Stop Loss and total BTC/account risk limits",
        "",f"Validation: max original historical entry/exit parity error {worst_parity:.5f} bp",
        f"Status: {result['status']}",
        f"Data cutoff (UTC): {result['last_complete_m5_exclusive_utc']}",
        f"Research account starting equity: {START_CASH:,.2f} USD",
        f"Ending marked equity: {result['marked_equity_usd']:,.2f} USD",
        f"Maximum marked drawdown: {result['max_drawdown_pct']:.3f}%",
        f"Completed trades: {result['completed_trades']}, stopouts: {result['stopouts']}",
        f"Historical months positive 2025-01..2026-10: {result['positive_months_2025_to_oct2026']}/22",
        "", "## Research risk settings",
        json.dumps(risk,indent=2),"","## Monthly realized PnL (% initial 10k USD)",
        "| Month | Closed trades | USD PnL | Initial capital % |",
        "|---|---:|---:|---:|"]
    for m in sim["monthly"]:
        text.append(f"| {m['month']} | {m['closed_trades']} | {m['realized_pnl_usd']:+.2f} | {m['realized_pnl_pct_initial']:+.5f}% |")
    text+=["","Historical monthly bp are under different equal-notional sizing; do not compare numeric magnitudes directly.",
            "No real-money trading, no guarantee of positive months."]
    (OUT/"V21_P4_195_RISK_REPORT.md").write_text("\n".join(text)+"\n")
    print("V21_RISK_RESULT",json.dumps({k:result[k] for k in [
        "status","portfolio","last_complete_m5_exclusive_utc","final_balance_usd","marked_equity_usd",
        "max_drawdown_pct","completed_trades","stopouts","positive_months_2025_to_oct2026",
        "daily_entry_lock_trigger_days"]}),flush=True)
    print("V21_RISK_MONTHLY",json.dumps(sim["monthly"]),flush=True)

if __name__=="__main__":
    main()
