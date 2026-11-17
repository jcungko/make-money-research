#!/usr/bin/env python3
"""Research-only USOIL H1 3-candle majority; no broker orders."""
import io, json, zipfile
from pathlib import Path
import pandas as pd

ARCHIVE=Path("data/v19_energies/USOIL_2026_UTC_7TF.zip")
OUT=Path("results/usoil_h1_majority_2026");OUT.mkdir(parents=True,exist_ok=True)
LOT=0.01
CONTRACT_SIZE=1000  # ASSUMPTION: verify Exness USOIL contract specification
USD_PER_PRICE=LOT*CONTRACT_SIZE
RISK_USD=10.0
STEP=RISK_USD/USD_PER_PRICE
with zipfile.ZipFile(ARCHIVE) as z:
    def load(tf):
        d=pd.read_csv(io.BytesIO(z.read(f"USOIL_{tf}_2026_UTC.csv")))
        d["timestamp_utc"]=pd.to_datetime(d["timestamp_utc"],utc=True)
        return d.sort_values("timestamp_utc").set_index("timestamp_utc")
    h=load("H1"); m=load("M5")
records=[]
for i in range(3,len(h)):
    start=h.index[i]
    if not ("2026-08-01"<=start.strftime("%Y-%m-%d")<"2026-11-01"):continue
    preceding=h.iloc[i-3:i]
    # Signal based on bid candle direction; bid quotes available to every observation
    bulls=int((preceding.bid_close>preceding.bid_open).sum())
    bears=int((preceding.bid_close<preceding.bid_open).sum())
    side=1 if bulls>=2 else (-1 if bears>=2 else 0)
    if side==0:continue
    end=start+pd.Timedelta(hours=1)
    segment=m[(m.index>=start)&(m.index<end)]
    if segment.empty:continue
    # Prevent treating a market gap or nonmatching hour as a fill.
    if segment.index[0]!=start:continue
    entry=float(segment.ask_open.iloc[0] if side==1 else segment.bid_open.iloc[0])
    exit_price=float(segment.bid_close.iloc[-1] if side==1 else segment.ask_close.iloc[-1])
    reason="H1_CLOSE"
    stop=entry-side*STEP; target=entry+side*STEP
    ambiguous=False
    for bar in segment.itertuples():
        high=float(bar.bid_high if side==1 else bar.ask_high)
        low=float(bar.bid_low if side==1 else bar.ask_low)
        stop_hit=low<=stop if side==1 else high>=stop
        target_hit=high>=target if side==1 else low<=target
        if stop_hit and target_hit:
            # Conservative assumption if both touched within same M5
            exit_price=stop; reason="SL_BOTH_M5";ambiguous=True;break
        if stop_hit:exit_price=stop;reason="SL";break
        if target_hit:exit_price=target;reason="TP";break
    gross=(exit_price-entry)*side*USD_PER_PRICE
    records.append(dict(time_utc=start.isoformat(),side="LONG" if side==1 else "SHORT",
      entry=entry,exit=exit_price,reason=reason,usd=round(gross,4),
      ambiguous_m5=ambiguous, m5_bars=len(segment)))
trades=pd.DataFrame(records)
if trades.empty:raise RuntimeError("No qualifying trades; check schema")
trades.to_csv(OUT/"trades.csv",index=False)
trades["month"]=trades.time_utc.str[:7]
def monthly(g):
    return dict(trades=len(g),wins=int((g.usd>0).sum()),losses=int((g.usd<0).sum()),
        flat=int((g.usd==0).sum()),win_rate_pct=round(100*(g.usd>0).mean(),2),
        gross_pnl_usd=round(g.usd.sum(),2),tp=int((g.reason=="TP").sum()),
        sl=int(g.reason.isin(["SL","SL_BOTH_M5"]).sum()),
        hour_close=int((g.reason=="H1_CLOSE").sum()),
        ambiguous_m5=int(g.ambiguous_m5.sum()))
report={"method":"USOIL H1 prior 3 bullish majority long / bearish majority short",
"data":"Exness V19 Standard unsuffixed 2026 bid/ask M5 and H1",
"period":"2026-08-01 through 2026-10-31 UTC",
"lot_assumed":LOT,"contract_size_assumed":CONTRACT_SIZE,
"one_price_unit_pnl_usd":USD_PER_PRICE,
"risk_and_target_usd":RISK_USD,
"stop_target_price_distance":STEP,
"entry":"first M5 quote at start of each H1; long ask open short bid open",
"exit":"SL/TP tested with M5 bid for long, ask for short; otherwise last M5 close",
"conservatism":"stop first when both barriers hit inside same M5",
"limitations":"M5 ambiguity; contract size not broker verified; no commission/swap/slippage; 5 minute close can be earlier than actual H1 end if missing ticks",
"monthly":{month:monthly(g) for month,g in trades.groupby("month")},
"total":monthly(trades)}
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report,ensure_ascii=False,indent=2))
