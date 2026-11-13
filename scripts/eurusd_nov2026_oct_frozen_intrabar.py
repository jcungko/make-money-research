#!/usr/bin/env python3
"""Strict no-retuning November forward test of October seven intrabar EURUSD M5 rules."""
import io, json, hashlib, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from eurusd_oct2026_intrabar_screen import prepare_frame,fill_trades,metrics,SESSION_HOURS,BASE_EXTRA_PIPS,STRESS_EXTRA_PIPS

OCT = Path("results/eurusd_oct2026_intrabar/exploratory_oct_positive_top100.csv")
OUT = Path("results/eurusd_nov2026_oct_frozen_intrabar")
SRC = "https://ticks.ex2archive.com/ticks/EURUSD/2026/11/Exness_EURUSD_2026_11.zip"
IDS = ["OI0238","OI0230","OI0229","OI0237","OI0226","OI0234","OI0225"]
CFG = {
"OI0238":(1.5,"overlap_12_17",5.,8.),
"OI0230":(.8,"overlap_12_17",5.,8.),
"OI0229":(.8,"overlap_12_17",3.,4.),
"OI0237":(1.5,"overlap_12_17",3.,4.),
"OI0226":(.8,"all",5.,8.),
"OI0234":(1.5,"all",5.,8.),
"OI0225":(.8,"all",3.,4.)}
START=pd.Timestamp("2026-11-01T00:00:00Z")
END=pd.Timestamp("2026-11-13T00:00:00Z")

def main():
  oct_bytes=OCT.read_bytes()
  oct_df=pd.read_csv(io.BytesIO(oct_bytes)).set_index("id")
  assert set(oct_df.index)==set(IDS) and len(oct_df)==7
  for ident in IDS:
    row=oct_df.loc[ident]
    sp,sess,sl,tp=CFG[ident]
    observed=(row["frame"],row["style"],int(row["entry_sec"]),int(row["exit_sec"]),
              float(row["signal_move_min_pips"]),float(row["spread_max_pips"]),
              row["session_utc"],float(row["sl_pips"]),float(row["tp_pips"]))
    expected=("M5","momentum",60,285,3.5,sp,sess,sl,tp)
    assert observed==expected,(ident,observed,expected)
  r=requests.get(SRC,timeout=(30,240))
  r.raise_for_status()
  raw=r.content
  assert zipfile.is_zipfile(io.BytesIO(raw))
  pieces=[]
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for name in z.namelist():
      if name.lower().endswith(".csv"):
        with z.open(name) as f:
          for chunk in pd.read_csv(f,usecols=["Timestamp","Bid","Ask"],chunksize=250000):
            pieces.append(chunk)
  if not pieces: raise RuntimeError("No csv in tick archive")
  f=pd.concat(pieces,ignore_index=True)
  tm=pd.to_datetime(f["Timestamp"],utc=True,format="ISO8601",errors="coerce")
  valid=tm.notna() & f["Bid"].notna() & f["Ask"].notna()
  sel=valid & (tm>=START) & (tm<END)
  if not sel.any(): raise RuntimeError("November source has no valid ticks")
  t=tm[sel].astype("int64").to_numpy(dtype=np.int64)
  bid=f.loc[sel,"Bid"].to_numpy(dtype=np.float64)
  ask=f.loc[sel,"Ask"].to_numpy(dtype=np.float64)
  if np.any(np.diff(t)<0) or np.any(bid>ask):
    raise RuntimeError("Bad tick timestamps or crossed quote")
  base=prepare_frame(t,bid,ask,300,60,285,30)
  records=[]
  trades=[]
  for ident in IDS:
    cap,sess,sl,tp=CFG[ident]
    mask=(np.abs(base["delta"])>=3.5)&(base["spread_prior"]<=cap)&(base["spread_prior"]>=0.0)
    hrs=SESSION_HOURS[sess]
    if hrs is not None: mask &= (base["hour"]>=hrs[0])&(base["hour"]<hrs[1])
    entry=base["entry"][mask];deadline=base["deadline"][mask];starts=base["start"][mask]
    dirs=np.sign(base["delta"][mask]).astype(np.int8)
    gross,exitidx,reasons=fill_trades(entry,deadline,dirs,bid,ask,sl,tp)
    net=gross-BASE_EXTRA_PIPS
    stress=gross-STRESS_EXTRA_PIPS
    m=metrics(net)
    records.append({"id":ident,"oct_trades":int(oct_df.loc[ident,"n_oct"]),
       "oct_net_pips":float(oct_df.loc[ident,"oct_net_pips"]),
       "nov_trades":m["n"],"nov_net_pips":m["sum_pips"],
       "nov_stress_net_pips":round(float(stress.sum()),4),
       "nov_win_pct":m["win_pct"],"nov_profit_factor":m["profit_factor"],
       "nov_max_drawdown_pips":m["max_dd_pips"],"nov_avg_pips":m["avg_pips"],
       "nov_buy_count":int((dirs==1).sum()),"nov_sell_count":int((dirs==-1).sum())})
    for j in range(len(entry)):
      bar=pd.Timestamp(int(starts[j]),tz="UTC")
      trades.append({"id":ident,"date_utc":bar.strftime("%Y-%m-%d"),
        "bar_utc":bar.isoformat(),
        "entry_utc":pd.Timestamp(int(t[entry[j]]),tz="UTC").isoformat(),
        "exit_quote_utc":pd.Timestamp(int(t[exitidx[j]]),tz="UTC").isoformat(),
        "side":"BUY" if dirs[j]==1 else "SELL",
        "entry_bid":float(bid[entry[j]]),"entry_ask":float(ask[entry[j]]),
        "exit_bid":float(bid[exitidx[j]]),"exit_ask":float(ask[exitidx[j]]),
        "exit_reason": "TIME" if reasons[j]==0 else ("SL" if reasons[j]==1 else "TP"),
        "net_pips":round(float(net[j]),5),"stress_net_pips":round(float(stress[j]),5)})
  OUT.mkdir(parents=True,exist_ok=True)
  pd.DataFrame(records).to_csv(OUT/"method_summary.csv",index=False)
  led=pd.DataFrame(trades)
  led.to_csv(OUT/"trade_ledger.csv",index=False)
  if len(led):
    daily=led.groupby(["date_utc","id"],as_index=False).agg(trades=("id","size"),
      net_pips=("net_pips","sum"),stress_net_pips=("stress_net_pips","sum"))
  else:
    daily=pd.DataFrame(columns=["date_utc","id","trades","net_pips","stress_net_pips"])
  daily.to_csv(OUT/"daily_pnl.csv",index=False)
  details={
    "status":"completed","source_url":SRC,
    "source_sha256":hashlib.sha256(raw).hexdigest(),
    "source_bytes":len(raw),"archive_tick_rows":len(f),"replay_tick_rows":len(t),
    "archive_first_tick_utc":tm[valid].iloc[0].isoformat(),
    "archive_last_tick_utc":tm[valid].iloc[-1].isoformat(),
    "replay_first_tick_utc":pd.Timestamp(int(t[0]),tz="UTC").isoformat(),
    "replay_last_tick_utc":pd.Timestamp(int(t[-1]),tz="UTC").isoformat(),
    "requested_cutoff_exclusive_utc":END.isoformat(),
    "october_frozen_list_sha256":hashlib.sha256(oct_bytes).hexdigest(),
    "no_november_tuning":True,
    "same_original_october_engine":True,
    "baseline_extra_round_trip_pips":BASE_EXTRA_PIPS,
    "stress_extra_round_trip_pips":STRESS_EXTRA_PIPS,
    "includes_historical_bid_ask_spread":True,
    "commission_included":False,
    "execution_model":"First observed quote after 60s entry; first observed TP or SL, else last observed quote <=285s in same 5m candle.",
    "method_results":records,
    "generated_at_utc":datetime.now(timezone.utc).isoformat(),
    "warnings":["Not real MT5 fills, account commissions excluded.",
      "Archive may end earlier than request cutoff; see archive_last_tick_utc.",
      "Variants are correlated: never add their pip gains as diversified PnL.",
      "Selection based on profitable October rules is exploratory."]}
  (OUT/"summary.json").write_text(json.dumps(details,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  lines=["# EURUSD November 2026 forward replay: seven October-frozen M5 strategies","",
    f"Source last tick: {details['archive_last_tick_utc']}",
    f"Last included tick: {details['replay_last_tick_utc']}",
    f"Replay tick count: {len(t)}",
    "Costs: historical Bid/Ask spread +0.2 pip round-trip; stressed +0.5 pip round-trip. No additional commission.", "",
    "| ID | Oct pips | Nov trades | Nov pips | Stress pips | Win rate % | PF | BUY / SELL |",
    "|---|---:|---:|---:|---:|---:|---:|---|"]
  for x in records:
    lines.append(f"| {x['id']} | {x['oct_net_pips']} | {x['nov_trades']} | {x['nov_net_pips']} | {x['nov_stress_net_pips']} | {x['nov_win_pct']} | {x['nov_profit_factor']} | {x['nov_buy_count']} / {x['nov_sell_count']} |")
  lines += ["","Daily results in daily_pnl.csv; all individual trades in trade_ledger.csv.",
    "October strategy parameters were not changed. Historical research only, not approved for live trading.",""]
  (OUT/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
  print(json.dumps(details,ensure_ascii=False),flush=True)

if __name__=="__main__": main()
