#!/usr/bin/env python3
"""Audit V19-065 B1/B3 trades, Nov 2026 signal/session/data fidelity.

These are existing frozen snapshots; not MT5 EA operational status checks.
"""
import json
from pathlib import Path
import pandas as pd
import numpy as np
import v19_strategy_screen as v19
from v19_nov2026_22_replay import rebuild_frames,replay_one_leg
from v19_four_portfolios_sl_replay import BASE,load_nov_m5,START_NOV,END_NOV

B1="USOIL|H1|range_top_20|long|H2|08utc"
B3="UKOIL|H4|rsi7_above_70|short|H3|00utc"
OUT=Path("results/v19_sl_research/V19_065_B1_B3_signal_data_audit.json")
TZ="Asia/Ho_Chi_Minh"

def h_coverage(m5,t,period):
    idx=m5.index
    win=m5.loc[(idx>=t)&(idx<t+pd.Timedelta(hours=period))]
    if len(win)==0:
        return dict(has_ohlc_bar=False,first_m5=None,last_m5=None,
                    m5_candles=0,first_quote_delay_minutes=None,
                    expected_m5_per_full_session=int(period*12))
    return dict(
        has_ohlc_bar=True,
        first_m5=win.index[0].isoformat(),
        last_m5=win.index[-1].isoformat(),
        m5_candles=len(win),
        first_quote_delay_minutes=int((win.index[0]-t)/pd.Timedelta(minutes=1)),
        expected_m5_per_full_session=int(period*12),
        valid_bid_ask=bool(np.all(np.isfinite(win.bid_open)) and np.all(np.isfinite(win.ask_open)) and (win.ask_open>=win.bid_open).all()),
        sum_tick_count=int(win.tick_count.sum())
    )

def main():
    sources=json.loads(Path("results/v19_november_2026/V19_nov2026_22_replay.json").read_text())
    sel=next(x for x in sources["rows"] if x["id"]=="V19-065")
    output={"study":"V19-065 B1/B3 entry-time audit, signal eligibility and source coverage",
            "source_period":"2026-11-01 to 2026-11-12 18:00 UTC exclusive",
            "server_mt5_live_status":"unknown (no access to deployed VPS/EA runtime logs)",
            "source_archive_summary":{},
            "checks":{}}
    for label,leg in (("B1",B1),("B3",B3)):
        sym,tf,indicator,side,holdstr,at=leg.split("|")
        new_m5=load_nov_m5(sym)
        data=rebuild_frames(BASE,sym,new_m5)[tf]
        mask=(data.timestamp_utc>=START_NOV)&(data.timestamp_utc<END_NOV)
        sliced=data.loc[mask].copy().reset_index(drop=True)
        # Calculate formula on full history, avoiding lookahead / arbitrary warmup
        full_signal=v19.signals(data)[indicator]
        sliced["qualified"]=full_signal[mask.to_numpy()]
        if label=="B1":
            cl=(data.bid_close+data.ask_close)/2
            hi=(data.bid_high+data.ask_high)/2
            lo=(data.bid_low+data.ask_low)/2
            past_hi=hi.shift(2).rolling(20,min_periods=20).max()
            past_lo=lo.shift(2).rolling(20,min_periods=20).min()
            pastclose=cl.shift(1)
            loc=(pastclose-past_lo)/(past_hi-past_lo).replace(0,np.nan)
            indicator_values=loc[mask.to_numpy()].to_numpy()
            assert np.array_equal((loc>0.75).fillna(False).to_numpy(),full_signal)
            predicate="previous_completed_H1_close_position_within_prior_20_H1_high_low_range > 0.75"
        else:
            cl=(data.bid_close+data.ask_close)/2
            diff=cl.diff()
            g=diff.clip(lower=0).ewm(alpha=1/7,adjust=False).mean()
            l=(-diff.clip(upper=0)).ewm(alpha=1/7,adjust=False).mean()
            rr=g/l.replace(0,np.nan)
            rsi=(100-100/(1+rr)).shift(1)
            indicator_values=rsi[mask.to_numpy()].to_numpy()
            assert np.array_equal((rsi>70).fillna(False).to_numpy(),full_signal)
            predicate="RSI7_from_previous_completed_H4_bar > 70"
        sliced["indicator_value"]=indicator_values
        correct=sliced[(sliced.timestamp_utc.dt.hour==int(at[:2]))&(sliced.timestamp_utc.dt.minute==0)].copy()
        per_date=[]
        for x in correct.itertuples():
            t=x.timestamp_utc
            o=h_coverage(new_m5,t,1 if tf=="H1" else 4)
            per_date.append({
                "date_ict":(t+pd.Timedelta(hours=7)).strftime("%Y-%m-%d"),
                "candle_label_utc":t.isoformat(),
                "candle_label_ict":t.tz_convert(TZ).isoformat(),
                "indicator_value":round(float(x.indicator_value),5) if pd.notna(x.indicator_value) else None,
                "qualified":bool(x.qualified),
                "candle_open_bid":round(float(x.bid_open),6),
                "candle_open_ask":round(float(x.ask_open),6),
                "candle_data_tick_count":int(x.tick_count),
                "first_quote_of_candle":o
            })
        replay=replay_one_leg(data,leg,END_NOV)
        closed=[x for x in replay if x["status"]=="closed"]
        opens=[x for x in replay if x["status"]=="open"]
        total_expected=next(x for x in sel["leg_details"] if x["leg"]==leg)
        assert len(closed)==total_expected["closed_orders"] and len(opens)==total_expected["open_orders"],(leg,closed,opens,total_expected)
        assert sum(x["qualified"] for x in per_date)==len(replay)
        hist=v19.read_frame(BASE,sym,tf)
        histmask=v19.signals(hist)[indicator]
        hh=hist.timestamp_utc.dt
        historical_counts=int((histmask & (hh.hour==int(at[:2])) & (hh.minute==0)).sum())
        hist_days=pd.Series(hist.timestamp_utc.dt.date).nunique()
        # 2025 Jan - 2026 Oct hist entries by script for evidence that bot is functional.
        output["checks"][label]={
            "leg":leg,
            "signal_definition":predicate,
            "session_hours_utc":int(at[:2]),
            "session_label_hour_ict":(int(at[:2])+7)%24,
            "timeframe":tf,
            "nov_bar_count_all_hours":len(sliced),
            "nov_scheduled_bars":len(correct),
            "qualified_nov_scheduled_bars":int(correct.qualified.sum()),
            "other_hours_qualified_bars":int((sliced.qualified & ~sliced.index.isin(correct.index)).sum()),
            "nov_closed_orders":len(closed),
            "nov_open_orders":len(opens),
            "nov_qualified_min":round(float(correct.indicator_value.min()),5),
            "nov_qualified_max":round(float(correct.indicator_value.max()),5),
            "historical_qualifying_session_bars_count":historical_counts,
            "historical_distinct_calendar_days_in_dataset":int(hist_days),
            "days_with_no_candle_data":sum(not x["first_quote_of_candle"]["has_ohlc_bar"] for x in per_date),
            "days_with_available_m5_at_exact_label":sum(x["first_quote_of_candle"]["first_quote_delay_minutes"]==0 for x in per_date),
            "sessions":per_date
        }
        src=sources["source"][sym]
        output["source_archive_summary"][sym]={
            "archives_ok":len([x for x in src if x.get("valid_ticks")]),
            "archives_missing_or_market_closed":[x["date"] for x in src if "status" in x],
            "first_market_tick_each_day_utc":{x["date"]:x["first_tick_utc"] for x in src if x.get("valid_ticks")},
            "m5_available_from":new_m5.index[0].isoformat(),
            "m5_available_until":new_m5.index[-1].isoformat(),
            "m5_row_count":len(new_m5)
        }
        print("V19_B1B3",label, "scheduled",len(per_date),"qualified",sum(x["qualified"] for x in per_date),
            "closed",len(closed),"full_quote_at_bucket",sum(x["first_quote_of_candle"]["first_quote_delay_minutes"]==0 for x in per_date),
            "historical_signal_session_bars",historical_counts,flush=True)
    output["interpretation"]={
        "b1":"At 08:00 UTC USOIL H1, all US market-open trading dates available; range_top20 fires only if previous price closes in top quarter of prior 20-bar range.",
        "b3":"00:00 UTC H4 label has no tradable quote on all 9 days: first tick near 01:10 UTC; aggregated candle opens at first actual trade quote. RSI7 stayed below 70, so even at delayed executable quote time no trigger in frozen strategy.",
        "disclaimer":"Backtesting tick data does not prove a running MT5 EA or VPS is healthy, to verify runtime check Journal/Experts logs."
    }
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print("V19_B1B3_DONE",json.dumps({k:{key:val for key,val in v.items() if key!="sessions"} for k,v in output["checks"].items()}),flush=True)

if __name__=="__main__":
    main()
