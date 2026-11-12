#!/usr/bin/env python3
"""Explain Nov 2026 zero signals for B3 of V19-065 (UKOIL H4 RSI7>70 short 00UTC)."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
import v19_strategy_screen as v19
from v19_nov2026_22_replay import rebuild_frames
from v19_four_portfolios_sl_replay import BASE,load_nov_m5,START_NOV,END_NOV

def run():
    m5=load_nov_m5("UKOIL")
    h4=rebuild_frames(BASE,"UKOIL",m5)["H4"]
    df=h4
    bid=df.bid_close.astype(float)
    ask=df.ask_close.astype(float)
    close=(bid+ask)/2
    diff=close.diff()
    gains=diff.clip(lower=0).ewm(alpha=1/7,adjust=False).mean()
    losses=(-diff.clip(upper=0)).ewm(alpha=1/7,adjust=False).mean()
    rs=gains/losses.replace(0,np.nan)
    previous_rsi=(100-100/(1+rs)).shift(1)
    exact=v19.signals(df)["rsi7_above_70"]
    predicted=(previous_rsi>70).fillna(False).to_numpy()
    assert np.array_equal(exact,predicted)
    ts=df.timestamp_utc
    month=(ts>=START_NOV)&(ts<END_NOV)
    novel=df.loc[month].copy()
    novel["previous_rsi7"]=previous_rsi[month].to_numpy()
    novel["qualified"]=exact[month.to_numpy()]
    novel["utc_hour"]=novel.timestamp_utc.dt.hour
    m0=novel.loc[(novel.utc_hour==0)&(novel.timestamp_utc.dt.minute==0)].copy()
    all_entries=novel.loc[novel.qualified].copy()
    byhour={f"{hour:02d}:00": {
        "bar_count":int((novel.utc_hour==hour).sum()),
        "rsi_above_70":int(((novel.utc_hour==hour)&novel.qualified).sum())
        } for hour in (0,4,8,12,16,20)}
    month_valid=[
        {"day_utc":str(t.date()),"utc_hour":int(t.hour),"rsi_prev":round(float(r),3)}
        for t,r in zip(all_entries.timestamp_utc,all_entries.previous_rsi7)]
    scheduled=[
        {"date_utc":str(row.timestamp_utc.date()),
        "bar_utc":row.timestamp_utc.isoformat(),
        "previous_closed_h4_rsi7":round(float(row.previous_rsi7),3) if pd.notna(row.previous_rsi7) else None,
        "above_70":bool(row.qualified),
        "bar_bid_open":round(float(row.bid_open),5),
        "bar_ask_open":round(float(row.ask_open),5)}
        for row in m0.itertuples()
    ]
    report={
        "portfolio":"V19-065",
        "bot":"B3",
        "leg":"UKOIL|H4|rsi7_above_70|short|H3|00utc",
        "period":"2026-11-01 through 2026-11-12 18:00 UTC exclusive",
        "source":"Existing frozen 2026-Nov M5 from Exness and 2025-2026 historical warm-up",
        "signal":"At H4 bars labelled 00:00 UTC (07:00 ICT), SHORT only when RSI7 of previous fully closed H4 bar > 70; fixed holding 3 H4 bars unless SL hits, hard SL 4%. No forced daily trade.",
        "scheduled_00utc_h4_bars":len(m0),
        "qualified_00utc_signals":int(m0.qualified.sum()),
        "maximum_00utc_prev_rsi7":round(float(m0.previous_rsi7.max()),5) if len(m0) else None,
        "minimum_00utc_prev_rsi7":round(float(m0.previous_rsi7.min()),5) if len(m0) else None,
        "h4_bars_all_schedules":len(novel),
        "qualified_h4_signals_at_any_hour":len(all_entries),
        "signal_by_h4_bar_start_hour":byhour,
        "all_00utc_checks":scheduled,
        "any_h4_rsi7_above_70":month_valid
    }
    out=Path("results/v19_sl_research/V19_065_B3_nov2026_zero_trades_diagnostic.json")
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("V19_B3_DIAGNOSTIC",json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    run()
