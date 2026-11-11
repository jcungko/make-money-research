#!/usr/bin/env python3
"""Reproduce frozen Exness Monday strategies #11 #6 #18 on 2025 (research only).

All time stamps: UTC. 2025 is untouched validation data for strategy rules
previously selected using 2026; not a trade recommendation or fill guarantee.
Inputs: Exness monthly tick archives /ticks/{sym}/{year}/{month}/Exness_....zip.
Build bid+ask M5 OHLC, aggregate H4/H1/M30 using only complete prior bars,
open at first quote of entry M5 and close at first quote of exit M5.
BUY net price = exit_bid - entry_ask. SELL = entry_bid - exit_ask.
"""
import argparse
import collections
import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import statistics
import time
import urllib.request
import zipfile

SYMBOLS=("EURUSD","USDJPY","GBPUSD")
PIP={"EURUSD":0.0001,"USDJPY":0.01,"GBPUSD":0.0001}
RULES=[
    dict(code="#11",symbol="EURUSD",timeframe_minutes=240,rule="SMA3",entry_slot=16*12+6,hold_slots=48),
    dict(code="#6",symbol="USDJPY",timeframe_minutes=60,rule="BUY",entry_slot=8*12+6,hold_slots=24),
    dict(code="#18",symbol="GBPUSD",timeframe_minutes=30,rule="SMAR12",entry_slot=9*12,hold_slots=18)
]
DAYS=[(dt.date(2025,1,1)+dt.timedelta(days=i)).isoformat()
      for i in range((dt.date(2026,1,1)-dt.date(2025,1,1)).days)
      if (dt.date(2025,1,1)+dt.timedelta(days=i)).weekday()==0]
assert len(DAYS)==52
DATES=set(d.encode("ascii") for d in DAYS)

def get_one(symbol,month,root):
    dest=root/f"Exness_{symbol}_2025_{month:02d}.zip"
    url=f"https://ticks.ex2archive.com/ticks/{symbol}/2025/{month:02d}/{dest.name}"
    if not dest.exists():
        for retry in range(4):
            try:
                req=urllib.request.Request(url,headers={"User-Agent":"Exness-Mondays-2025-Replay/1.0"})
                with urllib.request.urlopen(req,timeout=100) as f, dest.open("wb") as w:
                    while True:
                        b=f.read(1024*1024)
                        if not b:break
                        w.write(b)
                break
            except Exception:
                if dest.exists():dest.unlink()
                if retry==3:raise
                time.sleep(2**retry)
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None:raise ValueError("corrupted "+str(dest))
    return (symbol,month),{"path":dest,"url":url,
        "compressed_bytes":dest.stat().st_size,
        "sha256":hashlib.sha256(dest.read_bytes()).hexdigest()}

def aggregate(bars,minutes):
    size=minutes//5
    result=[]
    for start in range(0,288,size):
        chunk=bars[start:start+size]
        if any(x is None for x in chunk):
            result.append(None)
            continue
        result.append([chunk[0][0],max(x[1] for x in chunk),min(x[2] for x in chunk),
                       chunk[-1][3],chunk[0][4],max(x[5] for x in chunk),
                       min(x[6] for x in chunk),chunk[-1][7],
                       sum(x[8] for x in chunk)])
    return result

def build_ticks(symbol, files):
    result={d:[None]*288 for d in DAYS}
    ticks=0
    for (s,m),entry in sorted(files.items()):
        if s!=symbol:continue
        with zipfile.ZipFile(entry["path"]) as z:
            names=[x for x in z.namelist() if x.lower().endswith(".csv")]
            if not names:raise ValueError(f"no CSV in {entry['path']}")
            for name in names:
                with z.open(name) as f:
                    f.readline() # quoted header
                    for line in f:
                        day=line[19:29]
                        if day not in DATES:continue
                        try:
                            hour=int(line[30:32]);minute=int(line[33:35])
                            index=hour*12+minute//5
                            if not (0<=index<288):continue
                            ask_bid=line.rsplit(b",",2)
                            bid=float(ask_bid[-2]);ask=float(ask_bid[-1])
                        except (IndexError,ValueError):continue
                        if not (0<bid<=ask):continue
                        r=result[day.decode()][index]
                        if r is None:
                            result[day.decode()][index]=[bid,bid,bid,bid,ask,ask,ask,ask,1]
                        else:
                            r[1]=max(r[1],bid);r[2]=min(r[2],bid);r[3]=bid
                            r[5]=max(r[5],ask);r[6]=min(r[6],ask);r[7]=ask
                            r[8]+=1
                        ticks+=1
    return result,ticks

def direction(bars,rule,idx):
    if rule=="BUY":return 1
    if rule.startswith("SMAR"):n=int(rule[4:]);opposite=True
    elif rule.startswith("SMA"):n=int(rule[3:]);opposite=False
    else:raise ValueError(rule)
    chunk=bars[idx-n+1:idx+1]
    if len(chunk)!=n or any(x is None for x in chunk):return None
    delta=bars[idx][3]-sum(c[3] for c in chunk)/n
    d=1 if delta>0 else -1 if delta<0 else 0
    return (-d if opposite else d) if d else None

def run(symbol_data):
    results={x["code"]:[] for x in RULES}
    for config in RULES:
        symbol=config["symbol"];tf=config["timeframe_minutes"];entry=config["entry_slot"]
        exit_=entry+config["hold_slots"];period=tf//5
        prev=entry//period-1
        for day in DAYS:
            m5=symbol_data[symbol][day]
            higher=aggregate(m5,tf)
            side=direction(higher,config["rule"],prev)
            e=m5[entry];x=m5[exit_]
            if e is None or x is None or side is None:
                results[config["code"]].append({"day":day,"pips":None,"reason":"signal_or_entry_or_exit_gap",
                                                "direction":side})
                continue
            profit=(x[0]-e[4]) if side==1 else (e[0]-x[4])
            results[config["code"]].append({"day":day,"pips":round(profit/PIP[symbol],5),
                                           "direction":"BUY" if side==1 else "SELL"})
    return results

def stats(nums):
    if not nums:return None
    plus=sum(x for x in nums if x>0)
    minus=-sum(x for x in nums if x<0)
    maximum=0;current=0;max_bad=0;bad=0
    for x in nums:
        current=current+1 if x>0 else 0
        maximum=max(maximum,current)
        bad=bad+1 if x<0 else 0
        max_bad=max(max_bad,bad)
    return {"trades":len(nums),"wins":sum(x>0 for x in nums),
            "losses":sum(x<0 for x in nums),"flat":sum(x==0 for x in nums),
            "win_rate_pct":round(100*sum(x>0 for x in nums)/len(nums),2),
            "net_pips":round(sum(nums),3),
            "gross_win_pips":round(plus,3),"gross_loss_pips":round(minus,3),
            "profit_factor":round(plus/minus,3) if minus else None,
            "median_pips":round(statistics.median(nums),3),
            "best_pips":round(max(nums),3),"worst_pips":round(min(nums),3),
            "max_positive_streak":maximum,"max_negative_streak":max_bad}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="results/exness_mondays_2025")
    args=p.parse_args()
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    raw=out/"monthly_exness_zips";raw.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        downloads=dict(pool.map(lambda sm:get_one(sm[0],sm[1],raw),
                                [(s,m) for s in SYMBOLS for m in range(1,13)]))
    print("DOWNLOADED",len(downloads),"ZIPs",sum(f["compressed_bytes"] for f in downloads.values())//1024//1024,"MiB",flush=True)
    dataset={};ticks={}
    for symbol in SYMBOLS:
        bars,nticks=build_ticks(symbol,downloads)
        dataset[symbol]=bars;ticks[symbol]=nticks
        print("TICKS",symbol,nticks,"mondays",sum(any(x for x in bars[d]) for d in DAYS),flush=True)
    outcomes=run(dataset)
    missing={code:[x["day"] for x in result if x["pips"] is None] for code,result in outcomes.items()}
    monthly=[]
    combined=[]
    for d in DAYS:
        v=[next(x for x in outcomes[c["code"]] if x["day"]==d)["pips"] for c in RULES]
        combined.append({"day":d,"pips":round(sum(v),4) if all(x is not None for x in v) else None})
    for month in range(1,13):
        dates=[d for d in DAYS if d[5:7]==f"{month:02d}"]
        vals={c["code"]:[next(x for x in outcomes[c["code"]] if x["day"]==d)["pips"] for d in dates] for c in RULES}
        port=[x["pips"] for x in combined if x["day"] in dates]
        monthly.append({"month":f"2025-{month:02d}","mondays":len(dates),
                        "bots":{k:round(sum(a),3) if all(z is not None for z in a) else None for k,a in vals.items()},
                        "combined_pips":round(sum(port),3) if all(z is not None for z in port) else None,
                        "profitable_combined":sum(z is not None and z>0 for z in port),
                        "losing_combined":sum(z is not None and z<0 for z in port)})
    summary={
        "year":2025,"monday_dates":DAYS,"timezone":"UTC",
        "pricing":"entry/exit at first M5 tick, BUY ask->bid, SELL bid->ask",
        "method":"same frozen 2026 strategy rules, no retuning",
        "source":"Exness ex2archive.com monthly tick CSV ZIP (historical indicative quotes)",
        "archive_files":[{"symbol":sm[0],"month":sm[1],"url":d["url"],
                          "compressed_bytes":d["compressed_bytes"],"sha256":d["sha256"]}
                         for sm,d in sorted(downloads.items())],
        "monday_tick_counts":ticks,
        "missing_days":missing,
        "per_bot":{c["code"]:{**c,"metrics":stats([x["pips"] for x in outcomes[c["code"]] if x["pips"] is not None])}
                   for c in RULES},
        "portfolio_unweighted_pips":stats([x["pips"] for x in combined if x["pips"] is not None]),
        "monthly":monthly,
        "notes":["Additive pips are not USD P&L or risk-normalized returns.",
                 "Spread at M5 first ticks included; other fees, swaps, slippage and broker execution excluded.",
                 "2025 validation is held back from 2026 optimization, but dates predate strategy selection; not prospective forward test.",
                 "Missing any required M5 candle excludes day; do not silently fill missing quotes."]
    }
    with (out/"trades_2025_3bots.csv").open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["monday_utc","11_eurusd_h4_sma3","6_usdjpy_h1_buy","18_gbpusd_m30_smar12",
                    "combined_unweighted_pips","direction_11","direction_6","direction_18"])
        for i,d in enumerate(DAYS):
            a=[outcomes[c["code"]][i] for c in RULES]
            w.writerow([d]+[x["pips"] for x in a]+[combined[i]["pips"]]+[x["direction"] for x in a])
    with (out/"monthly_2025_3bots.csv").open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["month","mondays","#11 EURUSD","#6 USDJPY","#18 GBPUSD","combined_pips","positive_combined","negative_combined"])
        for x in monthly:
            w.writerow([x["month"],x["mondays"],x["bots"]["#11"],x["bots"]["#6"],x["bots"]["#18"],
                        x["combined_pips"],x["profitable_combined"],x["losing_combined"]])
    (out/"report_2025_3bots.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print("FINAL_REPORT",json.dumps({k:v for k,v in summary.items() if k not in ("archive_files","monday_dates")},ensure_ascii=False),flush=True)
    if any(missing.values()):
        raise SystemExit("Missing complete trade days: "+str(missing))
    print("VALIDATED_COMPLETE_52_MONDAYS",flush=True)

if __name__=="__main__":main()
