#!/usr/bin/env python3
"""Research-only audit of USOIL H1 3-bar majority SL5 TP10 for 2025/2026.
Tests limited, fixed rules against history. No live trades, no hyperparameter tuning.
"""
import io, json, zipfile
from pathlib import Path
import pandas as pd

LOT = 0.01
CONTRACT = 1000  # Simulation assumption; confirm on broker
VALUE = LOT*CONTRACT
STOP_USD=5.0
TP_USD=10.0
OUT=Path("results/usoil_h1_majority_generalization")
OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for year in (2025,2026):
    archive=Path(f"data/v19_energies/USOIL_{year}_UTC_7TF.zip")
    with zipfile.ZipFile(archive) as z:
        def load(tf):
            d=pd.read_csv(io.BytesIO(z.read(f"USOIL_{tf}_{year}_UTC.csv")))
            d["timestamp_utc"]=pd.to_datetime(d["timestamp_utc"], utc=True)
            return d.sort_values("timestamp_utc").set_index("timestamp_utc")
        h=load("H1")
        m=load("M5")
    # All features are based exclusively on finished candles before current entry.
    h["sma24"]=h.bid_close.shift(1).rolling(24,min_periods=24).mean()
    h["sma24_past"]=h["sma24"].shift(6)
    h["prev_bid_close"]=h.bid_close.shift(1)
    for i in range(30,len(h)):
        stamp=h.index[i]
        recent=h.iloc[i-3:i]
        bull=int((recent.bid_close>recent.bid_open).sum())
        bear=int((recent.bid_close<recent.bid_open).sum())
        side=1 if bull>=2 else (-1 if bear>=2 else 0)
        if not side:continue
        sub=m[(m.index>=stamp)&(m.index<stamp+pd.Timedelta(hours=1))]
        if sub.empty or sub.index[0]!=stamp:continue
        entry=float(sub.ask_open.iloc[0] if side==1 else sub.bid_open.iloc[0])
        exitp=float(sub.bid_close.iloc[-1] if side==1 else sub.ask_close.iloc[-1])
        sl=entry-side*STOP_USD/VALUE
        tp=entry+side*TP_USD/VALUE
        why="H1_CLOSE"
        ambiguous=False
        for bar in sub.itertuples():
            hi=float(bar.bid_high if side==1 else bar.ask_high)
            lo=float(bar.bid_low if side==1 else bar.ask_low)
            sl_hit=lo<=sl if side==1 else hi>=sl
            tp_hit=hi>=tp if side==1 else lo<=tp
            if sl_hit and tp_hit:
                exitp=sl;why="SL_BOTH_M5";ambiguous=True;break
            if sl_hit:exitp=sl;why="SL";break
            if tp_hit:exitp=tp;why="TP";break
        downtrend=bool(h.iloc[i].prev_bid_close<h.iloc[i].sma24 and h.iloc[i].sma24<h.iloc[i].sma24_past)
        uptrend=bool(h.iloc[i].prev_bid_close>h.iloc[i].sma24 and h.iloc[i].sma24>h.iloc[i].sma24_past)
        rows.append(dict(time_utc=stamp.isoformat(),year=year,month=stamp.strftime("%Y-%m"),
                         side="LONG" if side==1 else "SHORT",reason=why,usd=round((exitp-entry)*side*VALUE,4),
                         downtrend=downtrend,uptrend=uptrend,ambiguous=ambiguous))
d=pd.DataFrame(rows)
assert not d.empty
d.to_csv(OUT/"all_trades.csv",index=False)
# The 2026 Aug-Oct reference must be identical to original historical baseline.
ref=d[(d.month>="2026-08")&(d.month<="2026-11")]
assert len(ref)==1488,(len(ref),"2026 Aug-Oct count drift")
assert round(float(ref.usd.sum()),2)==-39.55,(ref.usd.sum(),"2026 Aug-Oct pnl drift")
variants={
 "ALL":pd.Series(True,index=d.index),
 "LONG_ONLY":d.side.eq("LONG"),
 "LONG_PLUS_TREND_SHORT":d.side.eq("LONG") | (d.side.eq("SHORT")&d.downtrend),
 "BOTH_SMA24_TREND":(d.side.eq("LONG")&d.uptrend) | (d.side.eq("SHORT")&d.downtrend)
}
def summarize(g):
    if g.empty:return {"n":0,"pnl":0.0,"win_rate_pct":None,"profit_factor":None}
    pos=float(g.loc[g.usd>0,"usd"].sum());neg=float(g.loc[g.usd<0,"usd"].sum())
    return {"n":len(g),"pnl":round(float(g.usd.sum()),2),"win_rate_pct":round(100*float((g.usd>0).mean()),2),
            "profit_factor":round(pos/abs(neg),4) if neg<0 else None,"tp":int((g.reason=="TP").sum()),"sl":int(g.reason.str.startswith("SL").sum())}
report={
 "method":"USOIL H1 2/3 close-open majority, entry each H1, SL5 TP10, H1 time exit",
 "source":"Exness Bid/Ask M5/H1 V19 USOIL, years 2025/2026",
 "assumptions":"0.01 lot, USOIL 1000 barrels per lot; bid/ask included, M5 first SL on ties; no slippage/commission/swap",
 "rules":{
  "ALL":"original both sides",
  "LONG_ONLY":"only LONG majority; no SHORT",
  "LONG_PLUS_TREND_SHORT":"LONG unfiltered; SHORT only if previous H1 bid close < 24 completed H1 SMA and SMA < SMA six H1 bars earlier",
  "BOTH_SMA24_TREND":"LONG only previous close > SMA24 and SMA rising; SHORT only previous close < SMA24 and SMA falling",
 },
 "cohorts":{},
 "variants":{},
}
for name, mask in variants.items():
    g=d[mask]
    per={month:summarize(x) for month,x in g.groupby("month")}
    cohorts={
      "2025":summarize(g[g.year==2025]),
      "2026_Jan_Jul":summarize(g[(g.month>="2026-01")&(g.month<="2026-08")]),
      "2026_Aug_Oct":summarize(g[(g.month>="2026-08")&(g.month<="2026-11")]),
      "2026_All":summarize(g[g.year==2026]),
      "all":summarize(g),
    }
    report["variants"][name]={"cohorts":cohorts,
                              "monthly":per,
                              "positive_months":sum(v["pnl"]>0 for v in per.values()),
                              "tested_months":len(per),
                              "positive_months_2025":sum(v["pnl"]>0 for k,v in per.items() if k.startswith("2025")),
                              "positive_months_2026":sum(v["pnl"]>0 for k,v in per.items() if k.startswith("2026"))}
    print(name,json.dumps(cohorts,ensure_ascii=False),flush=True)
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("AUDIT_DONE: 2026 Aug-Oct baseline reconciled")
