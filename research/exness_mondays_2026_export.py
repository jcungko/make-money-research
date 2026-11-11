#!/usr/bin/env python3
"""Export 45 Mondays x 3 symbols x M5/M15/M30/H1/H4, zipped UTF-8 CSV."""
import csv
import io
import json
import pathlib
import sys
import zipfile

SYMBOLS=("EURUSD","USDJPY","GBPUSD")
TIMEFRAMES=(5,15,30,60,240)
FIELDS=["symbol","date_utc","bar_start_utc","bid_o","bid_h","bid_l","bid_c",
        "ask_o","ask_h","ask_l","ask_c","tick_volume"]

def aggregate(m5,tf):
    n=tf//5
    out=[]
    for k in range(0,288,n):
        a=m5[k:k+n]
        if any(x is None for x in a):
            out.append(None);continue
        out.append([
            a[0][0],max(x[1] for x in a),min(x[2] for x in a),a[-1][3],
            a[0][4],max(x[5] for x in a),min(x[6] for x in a),a[-1][7],
            sum(x[8] for x in a)])
    return out

def main(root):
    manifest=json.loads((root/"manifest.json").read_text())
    days=list(manifest["symbols"]["EURUSD"]["per_monday"].keys())
    out=root/"exness_mondays_2026_15timeframes.zip"
    files={}
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for s in SYMBOLS:
            data={d:[None]*288 for d in days}
            with (root/(s+"_M5_MONDAYS_2026.csv")).open(newline="") as f:
                for r in csv.DictReader(f):
                    i=int(r["bar_start_utc"][11:13])*12+int(r["bar_start_utc"][14:16])//5
                    data[r["date_utc"]][i]=[
                        *[float(r[k]) for k in ("bid_o","bid_h","bid_l","bid_c",
                            "ask_o","ask_h","ask_l","ask_c")],int(r["ticks"])]
            for tf in TIMEFRAMES:
                suffix=f"M{tf}" if tf<60 else f"H{tf//60}"
                fn=f"{s}_{suffix}_MONDAYS_2026.csv"
                string=io.StringIO()
                w=csv.writer(string)
                w.writerow(FIELDS)
                counts={}
                for d in days:
                    candles=aggregate(data[d],tf)
                    counts[d]=sum(x is not None for x in candles)
                    for i,c in enumerate(candles):
                        if c is None:continue
                        minute=i*tf
                        w.writerow([s,d,f"{d}T{minute//60:02d}:{minute%60:02d}:00Z",*c])
                z.writestr(fn,string.getvalue())
                files[fn]={"rows":sum(counts.values()),"counts_per_date":counts}
    manifest["ohlc_export"]={"filename":out.name,"files":files,"unavailable_bars":
        "Gaps not interpolated; any higher-timeframe bar with missing component M5 is excluded."}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
    print("ARCHIVE",out,out.stat().st_size,"COMPONENTS",len(files))
    print("ROWS",{k:v["rows"] for k,v in files.items()})

if __name__=="__main__":
    main(pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "./exness_mondays_2026"))
