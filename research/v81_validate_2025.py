#!/usr/bin/env python3
"""2025 historical replication of *preselected 2026* EURUSDm V8.1 candidates.
Does not optimize 2025 parameters. Research only, no trading API calls.
"""
import argparse
import csv
import io
import json
import zipfile
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import numpy as np
import v81_daily_recurring as v81

SELECTED=[
 ("m15_momentum_8","trend",9,20,24,2.0),
 ("m15_momentum_8","trend",9,20,24,1.5),
 ("m15_momentum_8","trend",9,19,24,1.5),
 ("m15_momentum_8","trend",9,20,24,1.0),
 ("m15_momentum_8","trend",9,20,24,3.0),
 ("m15_momentum_8","trend",9,20,16,2.0),
]
def ts_key(x):
    x=str(x).strip().replace("T"," ")
    if len(x)>=16 and x[4] in ("-",".") and x[7] in ("-",".") and x[10]==" ":
        if x[4]==".":x=x.replace(".","-",2)
        return x[:14]+f"{int(x[14:16])//15*15:02d}"+":00"
    if x.isdigit() and len(x) in (10,13,16):
        dt=datetime.fromtimestamp(int(x)/(1000 if len(x)==13 else 1),tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:")+f"{(dt.minute//15)*15:02d}:00"
    raise ValueError("Bad tick time format "+repr(x))

def ticks_to_m15(src,dst):
    src=Path(src);dst=Path(dst)
    dst.parent.mkdir(parents=True,exist_ok=True)
    agg={}
    ticks=0;reverse_ticks=0;last_tick=None
    with zipfile.ZipFile(src) as z:
        members=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if not members:raise ValueError("No CSV in "+str(src))
        print("ZIP MEMBERS",[(x.filename,x.file_size) for x in z.infolist()],flush=True)
        with z.open(members[0]) as raw:
            reader=csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig",newline=""))
            cols=next(reader);col={x.strip().lower():i for i,x in enumerate(cols)}
            print("FIELDS",cols,flush=True)
            if not {"timestamp","bid","ask"}.issubset(col):raise ValueError("Bad columns "+str(cols))
            it,ib,ia=col["timestamp"],col["bid"],col["ask"]
            for v in reader:
                if not v:continue
                stamp=v[it].strip().replace("T"," ").replace(".","-",2)
                k=ts_key(stamp)
                bid=float(v[ib]);ask=float(v[ia])
                if bid<=0 or ask<bid:continue
                ticks+=1
                if last_tick is not None and stamp<last_tick:
                    reverse_ticks+=1
                last_tick=stamp
                row=agg.get(k)
                if row is None:
                    # k, bid O/H/L/C, ask O/H/L/C, count, first tick ts, last tick ts
                    agg[k]=[k,bid,bid,bid,bid,ask,ask,ask,ask,1,stamp,stamp]
                else:
                    row[2]=max(row[2],bid);row[3]=min(row[3],bid)
                    row[6]=max(row[6],ask);row[7]=min(row[7],ask)
                    if stamp<row[10]:
                        row[1]=bid;row[5]=ask;row[10]=stamp
                    if stamp>=row[11]:
                        row[4]=bid;row[8]=ask;row[11]=stamp
                    row[9]+=1
                if ticks%5000000==0:
                    print("PROCESSED TICKS",ticks,"LAST",k,"reverse",reverse_ticks,flush=True)
    rows=[agg[k][:10] for k in sorted(agg)]
    columns=["time_utc","bid_open","bid_high","bid_low","bid_close",
             "ask_open","ask_high","ask_low","ask_close","ticks"]
    df=pd.DataFrame(rows,columns=columns)
    print("CONVERT",ticks,len(df),df.time_utc.iloc[0],df.time_utc.iloc[-1],
          "out_of_chronology_raw_ticks",reverse_ticks)
    buf=io.StringIO()
    df.to_csv(buf,index=False)
    with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        z.writestr("EURUSDm_Exness_2025_M15.csv",buf.getvalue())
    return ticks,df


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--tick",required=True)
    ap.add_argument("--data",default="data/exness/EURUSDm_2025/eurusdm_exness_2025_m15.zip")
    ap.add_argument("--out",default="results/v81_daily_2025_validation")
    args=ap.parse_args()
    ticks,df=ticks_to_m15(args.tick,args.data)
    d=v81.load_m15(args.data)
    # This is an honest calendar-year replicate: same daily UTC rules in 2025.
    v81.FULL=tuple(f"2025-{j:02d}" for j in range(1,13))
    v81.RECENT=("2025-08","2025-09","2025-10")
    feat=v81.build_features(d)
    days,_=v81.signals_on_days(d,feat)
    denom=len([x for x in days if x.startswith("2025")])
    print("2025 ELIGIBLE DAYS",denom)
    rows=[]
    for key,flavor,entry,exit_h,sl,rr in SELECTED:
        plans,_,skipped=v81.make_daily_plan(d,days,feat,key,flavor,entry,exit_h)
        baseline_days=len([t for t in plans if t[1].startswith("2025")])
        for slip in (0.2,0.5,1.0):
            trades=v81.run(d,plans,sl,rr,slip)
            stats=v81.metrics(trades)
            row={
                "feature":key,"mode":flavor,"entry_utc":entry,"exit_utc":exit_h,
                "SL_pips":sl,"RR":rr,"slippage_pips_side":slip,
                "days_eligible":denom,"days_traded":baseline_days,
                "coverage":baseline_days/denom,"trades":stats["trades"],"netR":stats["netR"],
                "expectancyR":stats["expectancyR"],"profit_factor":stats["PF"],
                "winrate":stats["winrate"],"maxDD_R":stats["maxDD_R"],
                "profitable_months_2025":stats["positive_full_months"],
                "recent3_2025_positive":stats["recent_3_positive"],
                "monthly_R":json.dumps(stats["monthly_R"]),
                "monthly_trades":json.dumps(stats["monthly_n"]),
                "TP":stats["TP"],"SL":stats["SL"],"TIME":stats["TIME"]
            }
            rows.append(row)
            print("VALIDATION",json.dumps(row),flush=True)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/"selected2026_2025_replication.csv",index=False)
    meta={
      "source":"Exness public 2025 EURUSDm tick archive (stored GitHub Actions artifact)",
      "datefirst":str(d.t.min()),"datelast":str(d.t.max()),
      "tick_count":ticks,"M15_candles":len(d),"eligible_trading_days":denom,
      "selection":"Configurations preselected entirely on 2026 before reading 2025 results.",
      "caveats":["Not a prospective/live independent holdout; same broker historical feed",
      "2025 archive 1GB uncompressed, true per-tick fill ordering not simulated",
      "Slippage assumptions per side, swap excluded for intraday positions"]
    }
    (out/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print("METADATA",json.dumps(meta),flush=True)
if __name__=="__main__":main()
