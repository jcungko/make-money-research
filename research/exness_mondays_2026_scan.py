#!/usr/bin/env python3
"""Exness Monday 2026 exploratory FX OHLC bid/ask backtest. No orders.
UTC Monday; January 05-November 09, 2026. Uses annual Exness ZIP snapshots.
Every candidate takes exactly one time-exit trade on every eligible Monday.
Open=first available tick in the M5 interval; both BUY and SELL include spread.
This is a parameter sweep on the same sample; NOT an out-of-sample validation.
"""
import argparse
import collections
import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import math
import pathlib
import statistics
import time
import urllib.request
import zipfile

SYMBOLS=("EURUSD","USDJPY","GBPUSD")
TIMEFRAMES=(5,15,30,60,240)
DAYS=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat()
      for i in range((dt.date(2026,11,11)-dt.date(2026,1,1)).days+1)
      if (dt.date(2026,1,1)+dt.timedelta(days=i)).weekday()==0]
assert len(DAYS)==45
DAYS_BYTES={x.encode() for x in DAYS}
URL="https://ticks.ex2archive.com/ticks/{s}/2026/Exness_{s}_2026.zip"
PIPS={"EURUSD":.0001,"GBPUSD":.0001,"USDJPY":.01}

def download(s, folder):
    dest=folder / (s+"_2026.zip")
    source=URL.format(s=s)
    if not dest.exists():
        last=None
        for n in range(3):
            try:
                r=urllib.request.Request(source,headers={"User-Agent":"Exness-Monday-Research/1.0"})
                with urllib.request.urlopen(r,timeout=90) as resp, dest.open("wb") as f:
                    while True:
                        c=resp.read(1024*1024)
                        if not c: break
                        f.write(c)
                break
            except Exception as e:
                last=e
                if dest.exists(): dest.unlink()
                if n==2: raise
                time.sleep(2+n*2)
    return s, str(dest)

def ticks_to_m5(s, p):
    # Sparse (day, M5 slot) OHLC Bid/Ask; counts are tick counts.
    results={d:[None]*288 for d in DAYS}
    count=0
    with zipfile.ZipFile(p) as z:
        names=[n for n in z.namelist() if n.endswith(".csv")]
        if not names: raise ValueError((s,"missing CSV"))
        for fname in names:
            with z.open(fname) as f:
                f.readline()
                for line in f:
                    # Native six-letter symbol CSV has 19-byte prefix before ISO date.
                    d=line[19:29]
                    if d not in DAYS_BYTES: continue
                    date=d.decode()
                    try:
                        hour=int(line[30:32])
                        minute=int(line[33:35])
                        slot=hour*12+minute//5
                        tail=line.rsplit(b",",2)
                        bid=float(tail[-2]); ask=float(tail[-1])
                        if not (bid>0 and ask>=bid): continue
                    except (ValueError,IndexError):
                        continue
                    row=results[date][slot]
                    if row is None:
                        # bid O H L C, ask O H L C, volume
                        results[date][slot]=[bid,bid,bid,bid,ask,ask,ask,ask,1]
                    else:
                        if bid>row[1]: row[1]=bid
                        if bid<row[2]: row[2]=bid
                        row[3]=bid
                        if ask>row[5]: row[5]=ask
                        if ask<row[6]: row[6]=ask
                        row[7]=ask
                        row[8]+=1
                    count+=1
    return results,count

def merge_tf(bars,tf):
    step=tf//5
    out=[]
    for j in range(0,288,step):
        bs=bars[j:j+step]
        # incomplete higher TF is excluded rather than invented
        if any(x is None for x in bs):
            out.append(None); continue
        out.append([bs[0][0],max(x[1] for x in bs),min(x[2] for x in bs),
                    bs[-1][3],bs[0][4],max(x[5] for x in bs),
                    min(x[6] for x in bs),bs[-1][7],sum(x[8] for x in bs)])
    return out

def family_and_lookbacks():
    yield "BUY",0
    yield "SELL",0
    for base in ("MOM","REV","MOM2","REV2"):
        yield base,1 if not base.endswith("2") else 2
    for n in (3,5,8,12):
        yield "SMA"+str(n),n
        yield "SMAR"+str(n),n

def signal(bars,idx,mode):
    if mode=="BUY": return 1
    if mode=="SELL": return -1
    if idx<0 or bars[idx] is None: return 0
    prev=bars[idx]
    if mode=="MOM" or mode=="REV":
        delta=prev[3]-prev[0]
        d=1 if delta>0 else -1 if delta<0 else 0
        return -d if mode=="REV" else d
    if mode in ("MOM2","REV2"):
        if idx<1 or bars[idx-1] is None:return 0
        delta=prev[3]-bars[idx-1][0]
        d=1 if delta>0 else -1 if delta<0 else 0
        return -d if mode=="REV2" else d
    n=int(mode[4:] if mode.startswith("SMAR") else mode[3:])
    if idx+1<n: return 0
    trailing=bars[idx-n+1:idx+1]
    if any(b is None for b in trailing): return 0
    avg=sum(x[3] for x in trailing)/n
    delta=prev[3]-avg
    d=1 if delta>0 else -1 if delta<0 else 0
    return -d if mode.startswith("SMAR") else d

def strategies(m5):
    # State is deliberately one trade every Monday, no optimized daily abstention.
    rankings=[]
    # At least one full H4 candle on Monday is available by 08:00.
    for symbol in SYMBOLS:
        data=m5[symbol]
        tfs={day:{tf:merge_tf(data[day],tf) for tf in TIMEFRAMES} for day in DAYS}
        for entry_slot in range(8*12,20*12+1,6): # 08:00-20:00 UTC, 30m step
            for hold in (30,60,90,120,180,240):
                exit_slot=entry_slot+hold//5
                if exit_slot>=288:continue
                for tf in TIMEFRAMES:
                    step=tf//5
                    idx=entry_slot//step-1 # last fully completed TF candle
                    for mode,_ in family_and_lookbacks():
                        sides=[]
                        net=[]
                        for day in DAYS:
                            ent=data[day][entry_slot]
                            ext=data[day][exit_slot]
                            side=signal(tfs[day][tf],idx,mode)
                            if ent is None or ext is None or side==0:break
                            # fills at M5 opening quote: BUY ask->bid, SELL bid->ask
                            raw=(ext[0]-ent[4]) if side==1 else (ent[0]-ext[4])
                            net.append(round(raw/PIPS[symbol],5))
                            sides.append(side)
                        if len(net)!=45:continue
                        wins=sum(x>0 for x in net)
                        losses=sum(x<0 for x in net)
                        gross=round(sum(net),3)
                        rankings.append({
                            "symbol":symbol,"tf":("M"+str(tf) if tf<60 else "H"+str(tf//60)),
                            "entry_utc":f"{entry_slot//12:02d}:{entry_slot%12*5:02d}",
                            "hold_minutes":hold,"rule":mode,"profitable_mondays":wins,
                            "losing_mondays":losses,"flat_mondays":45-wins-losses,
                            "net_pips":gross,"median_pips":round(statistics.median(net),3),
                            "max_loss_pips":round(min(net),3),
                            "profit_pips_first30":round(sum(net[:30]),3),
                            "profitable_first30":sum(x>0 for x in net[:30]),
                            "profitable_last15":sum(x>0 for x in net[30:]),
                            "_directions":"".join("+" if x==1 else "-" for x in sides),
                            "_daily":net
                        })
    rankings.sort(key=lambda r:(-r["profitable_mondays"],-r["net_pips"],r["symbol"],r["tf"]))
    # Exact trade-path duplicates are not independent strategies.
    distinct=[]
    fingerprints=set()
    for r in rankings:
        fp=(r["symbol"],r["entry_utc"],r["hold_minutes"],r["_directions"])
        if fp in fingerprints:continue
        fingerprints.add(fp)
        distinct.append(r)
    return rankings,distinct

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="./exness_mondays_2026")
    args=ap.parse_args()
    root=pathlib.Path(args.output)
    root.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fetched=dict(pool.map(lambda s: download(s,root),SYMBOLS))
    m5={}; manifest={"source":"Exness public tick-history archive (indicative, not MT5 execution ticks)",
                     "data_urls":{s:URL.format(s=s) for s in SYMBOLS},
                     "date_range":f"{DAYS[0]}..{DAYS[-1]}",
                     "timezone":"UTC",
                     "method":"Bid/Ask M5 OHLC from ticks, derive M15/M30/H1/H4; one trade per Monday; fill at first tick of M5 entry and exit bars",
                     "symbols":{}}
    for symbol in SYMBOLS:
        bars,n=ticks_to_m5(symbol,fetched[symbol])
        m5[symbol]=bars
        per_day={d:{"bars_M5":sum(x is not None for x in bars[d]),
                    "ticks":sum(x[8] for x in bars[d] if x)} for d in DAYS}
        manifest["symbols"][symbol]={"archive_bytes":pathlib.Path(fetched[symbol]).stat().st_size,
                  "sha256":hashlib.sha256(pathlib.Path(fetched[symbol]).read_bytes()).hexdigest(),
                  "monday_ticks":n,
                  "complete_M5_mondays":sum(x["bars_M5"]==288 for x in per_day.values()),
                  "per_monday":per_day}
        with (root/(symbol+"_M5_MONDAYS_2026.csv")).open("w",newline="") as fp:
            w=csv.writer(fp);w.writerow(["symbol","date_utc","bar_start_utc","bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c","ticks"])
            for d in DAYS:
                for i,x in enumerate(bars[d]):
                    if x:
                        w.writerow([symbol,d,f"{d}T{i//12:02d}:{(i%12)*5:02d}:00Z",*x])
    all_ranked,distinct=strategies(m5)
    fields=("symbol","tf","entry_utc","hold_minutes","rule","profitable_mondays",
           "losing_mondays","flat_mondays","net_pips","median_pips",
           "max_loss_pips","profitable_first30","profitable_last15")
    with (root/"ranked_50_distinct.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in distinct[:50]:w.writerow({k:r[k] for k in fields})
    with (root/"ranked_all_distinct.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in distinct:w.writerow({k:r[k] for k in fields})
    with (root/"top50_daily_pips.csv").open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["rank","symbol","rule","timeframe","entry_utc","hold_minutes",*DAYS])
        for i,r in enumerate(distinct[:50],1):
            w.writerow([i,r["symbol"],r["rule"],r["tf"],r["entry_utc"],r["hold_minutes"],*r["_daily"]])
    manifest["scanned_variants"]=len(all_ranked)
    manifest["distinct_trade_paths"]=len(distinct)
    manifest["max_positive_days"]=distinct[0]["profitable_mondays"] if distinct else None
    manifest["disclaimer"]="Highly optimized in-sample only. No stop-loss, commission, swap, slippage, outages, or live broker fills. No statistically valid forward performance claim."
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print("MANIFEST",json.dumps({k:v for k,v in manifest.items() if k!="symbols"}))
    print("COVERAGE",json.dumps({s:{"total_monday_ticks":v["monday_ticks"],"complete_M5_mondays":v["complete_M5_mondays"],"incomplete_mondays":{d:x["bars_M5"] for d,x in v["per_monday"].items() if x["bars_M5"]!=288}} for s,v in manifest["symbols"].items()}))
    print("TOP50_JSON",json.dumps([{k:v for k,v in r.items() if not k.startswith("_")} for r in distinct[:50]],ensure_ascii=False))
    print("DISTRIBUTION",json.dumps(collections.Counter(r["profitable_mondays"] for r in distinct).most_common(15)))
if __name__=="__main__":main()
