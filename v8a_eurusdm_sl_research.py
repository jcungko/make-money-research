#!/usr/bin/env python3
"""V8-A EURUSDm M15 box breakout: fixed-percent stop study, research only.
No credentials, orders or alerts. Deterministic, next-bar fill, Bid/Ask exits.
"""
import csv
import datetime as dt
import io
import json
import math
import pathlib
import re
import statistics
import zipfile

DATA=pathlib.Path("data/exness/EURUSDm_2026/exness_eurusdm_2026_m5_m15_h1.zip")
PCT=[0.02,0.03,0.04,0.05,0.06,0.08,0.10,0.12,0.15,0.20,0.25,0.30]
N=20
MAX_WAIT=12
HOLD=96
RR=2.
ATR_N=14

def norm(s):
    return re.sub(r"[^a-z0-9]","",s.lower())

def parse_t(x):
    x=str(x).strip()
    if x.isdigit():
        v=int(x)
        if v>100000000000: return dt.datetime.fromtimestamp(v/1000,dt.timezone.utc)
        if v>1000000000: return dt.datetime.fromtimestamp(v,dt.timezone.utc)
    x=x.replace("Z","+00:00")
    try: d=dt.datetime.fromisoformat(x)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f","%Y.%m.%d %H:%M:%S","%Y.%m.%d %H:%M","%Y-%m-%d %H:%M"):
            try: d=dt.datetime.strptime(x,fmt); break
            except ValueError: continue
        else: raise
    if d.tzinfo is None: d=d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)

def read_bars():
    with zipfile.ZipFile(DATA) as z:
        names=[n for n in z.namelist() if n.lower().endswith(".csv") and re.search(r"m15|15m",n.lower())]
        if not names: raise ValueError("No M15 CSV members: "+repr(z.namelist()[:60]))
        print("M15_SOURCE_FILES",json.dumps(names))
        allrows={}
        for member in sorted(names):
            with z.open(member) as f:
                reader=csv.DictReader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
                fields=reader.fieldnames
                if not fields: continue
                d={norm(x):x for x in fields}
                print("CSV_HEADER",member, json.dumps(fields))
                def key(*poss):
                    for p in poss:
                        if norm(p) in d: return d[norm(p)]
                    return None
                timekey=key("time_utc","open_time_utc","timestamp_utc","timestamp","open_time","time","datetime","timeopenutc","utc","t")
                bid_o=key("bid_open","open_bid","bidopen","bid_o")
                bid_h=key("bid_high","high_bid","bidhigh","bid_h")
                bid_l=key("bid_low","low_bid","bidlow","bid_l")
                bid_c=key("bid_close","close_bid","bidclose","bid_c")
                ask_o=key("ask_open","open_ask","askopen","ask_o")
                ask_h=key("ask_high","high_ask","askhigh","ask_h")
                ask_l=key("ask_low","low_ask","asklow","ask_l")
                ask_c=key("ask_close","close_ask","askclose","ask_c")
                if not all([timekey,bid_o,bid_h,bid_l,bid_c,ask_o,ask_h,ask_l,ask_c]):
                    raise ValueError(f"Unrecognized M15 columns {member}: {fields}")
                for row in reader:
                    try:
                        t=parse_t(row[timekey])
                        if t.year!=2026 or t>dt.datetime(2026,11,9,23,59,tzinfo=dt.timezone.utc): continue
                        vals=[float(row[k]) for k in (bid_o,bid_h,bid_l,bid_c,ask_o,ask_h,ask_l,ask_c)]
                        if not all(v>0 and math.isfinite(v) for v in vals): continue
                        if vals[1]<max(vals[0],vals[3]) or vals[2]>min(vals[0],vals[3]): continue
                        if vals[5]<max(vals[4],vals[7]) or vals[6]>min(vals[4],vals[7]): continue
                        allrows[t]=(t,*vals)
                    except (ValueError,TypeError,KeyError) as exc:
                        if len(allrows)<3: print("PARSE_ISSUE",str(exc),repr(row)[:250])
                        continue
    bars=[dict(zip(("t","bo","bh","bl","bc","ao","ah","al","ac"),v)) for v in sorted(allrows.values())]
    if len(bars)<1000: raise ValueError("Too few M15 bars "+str(len(bars)))
    gap=sum(1 for i in range(1,len(bars)) if (bars[i]["t"]-bars[i-1]["t"]).total_seconds()!=900)
    spreads=[(b["ao"]-b["bo"])/.0001 for b in bars]
    print("DATA",json.dumps({"bars":len(bars),"start":str(bars[0]["t"]),"end":str(bars[-1]["t"]),
        "non15min_gaps":gap,"median_open_spread_pips":round(statistics.median(spreads),4),
        "p95_open_spread_pips":round(sorted(spreads)[int(.95*(len(spreads)-1))],4)}))
    return bars

def indicators(b):
    n=len(b)
    tr=[0.]*n; pdm=[0.]*n; mdm=[0.]*n
    for i in range(1,n):
        up=b[i]["bh"]-b[i-1]["bh"]
        dn=b[i-1]["bl"]-b[i]["bl"]
        pdm[i]=up if up>dn and up>0 else 0
        mdm[i]=dn if dn>up and dn>0 else 0
        tr[i]=max(b[i]["bh"]-b[i]["bl"],abs(b[i]["bh"]-b[i-1]["bc"]),abs(b[i]["bl"]-b[i-1]["bc"]))
    atr=[float("nan")]*n; adx=[float("nan")]*n; er=[float("nan")]*n
    smtr=sum(tr[1:15]); sp=sum(pdm[1:15]); sm=sum(mdm[1:15])
    atr[14]=smtr/14
    dx=[float("nan")]*n
    for i in range(14,n):
        if i>14:
            smtr=smtr-smtr/14+tr[i]
            sp=sp-sp/14+pdm[i]
            sm=sm-sm/14+mdm[i]
            atr[i]=smtr/14
        denom=sp+sm
        dx[i]=100*abs(sp-sm)/denom if denom else 0
    adx[27]=sum(dx[14:28])/14
    for i in range(28,n):
        adx[i]=(adx[i-1]*13+dx[i])/14
    moves=[0]+[abs(b[i]["bc"]-b[i-1]["bc"]) for i in range(1,n)]
    total=sum(moves[1:21])
    for i in range(20,n):
        if i>20: total+=moves[i]-moves[i-20]
        er[i]=abs(b[i]["bc"]-b[i-20]["bc"])/total if total>0 else 0.
    return atr,adx,er

def signals(b,atr,adx,er,box_width_max=3.5):
    n=len(b); events=[]; i=30
    while i<n-2:
        a=atr[i]; x=adx[i]; e=er[i]
        if not (a>0 and math.isfinite(x) and x<20 and e<.35):
            i+=1; continue
        box=b[i-19:i+1]
        hi=max(v["bh"] for v in box); lo=min(v["bl"] for v in box)
        ratio=(hi-lo)/a
        if not (1.5<=ratio<=box_width_max):
            i+=1; continue
        broke=False
        for j in range(i+1,min(i+MAX_WAIT+1,n-1)):
            c=b[j]
            body=abs(c["bc"]-c["bo"])
            rang=c["bh"]-c["bl"]
            threshold=.15*atr[j-1] if math.isfinite(atr[j-1]) else .15*a
            bullish=c["bc"]>hi+threshold
            bearish=c["bc"]<lo-threshold
            if bullish or bearish:
                if rang>0 and body/rang>=.5 and ((bullish and c["bc"]>c["bo"]) or (bearish and c["bc"]<c["bo"])):
                    events.append((j+1,1 if bullish else -1,hi,lo,j))
                broke=True
                i=j+1
                break
        if not broke: i=min(i+MAX_WAIT+1,n-1)
    print("SIGNALS",json.dumps({"count":len(events),"buy":sum(1 for e in events if e[1]==1),"sell":sum(1 for e in events if e[1]==-1),
        "box_width_max":box_width_max}))
    return events

def test(b,events,sl_pct,rr=2,slip_pips=0.0):
    n=len(b); idx=-1; trades=[]
    for entry_i,side,hi,lo,sign_i in events:
        if entry_i<=idx+4:continue
        e=b[entry_i]
        slip=slip_pips*.0001
        entry=e["ao"]+slip if side==1 else e["bo"]-slip
        risk=entry*sl_pct/100
        stop=entry-side*risk; target=entry+side*rr*risk
        exit_i=min(n-1,entry_i+HOLD-1)
        realized=0; why="timeout"
        for k in range(entry_i,exit_i+1):
            z=b[k]
            if side==1:
                touch_stop=z["bl"]<=stop
                touch_tp=z["bh"]>=target
            else:
                touch_stop=z["ah"]>=stop
                touch_tp=z["al"]<=target
            if touch_stop:
                realized=-1-slip/risk; why="stop"; exit_i=k; break
            if touch_tp:
                realized=rr-slip/risk; why="tp"; exit_i=k; break
        else:
            z=b[exit_i]; x=z["bc"]-slip if side==1 else z["ac"]+slip
            realized=side*(x-entry)/risk
        trades.append(dict(entry_i=entry_i,exit_i=exit_i,t=b[entry_i]["t"],side=side,r=realized,why=why,box=(hi-lo)/entry*100))
        idx=exit_i
    return trades

def metrics(ts):
    if not ts: return {"n":0,"expectancy":None,"PF":None,"win":None,"maxDD":None,"total_R":0,"months_pos":0,"months":0}
    r=[t["r"] for t in ts]
    peak=0; cum=0; dd=0
    for v in r:
        cum+=v; peak=max(peak,cum); dd=max(dd,peak-cum)
    pos=sum(x for x in r if x>0); neg=-sum(x for x in r if x<0)
    by_month={}
    for t in ts:
        k=t["t"].strftime("%Y-%m")
        by_month[k]=by_month.get(k,0)+t["r"]
    return {"n":len(r),"expectancy":round(statistics.mean(r),4),
        "PF":round(pos/neg,3) if neg>0 else None,
        "win":round(100*sum(v>0 for v in r)/len(r),2),
        "maxDD":round(dd,2),"total_R":round(sum(r),2),
        "months_pos":sum(v>0 for v in by_month.values()),"months":len(by_month)}

def main():
    b=read_bars()
    atr,adx,er=indicators(b)
    out={"method":"V8A sideway N20 ADX14<20 ER20<0.35 width/ATR1.5-3.5; freeze box upto12bars; breakout close > 0.15ATR beyond range and body>=50%; enter next M15 open; Bid/Ask fills; stop-first; hold<=96bars; RR=2; one position; slip 0","data":"Exness EURUSDm 2026-01-01 to 2026-11-09"}
    for width in (3.5,5.0):
        ev=signals(b,atr,adx,er,width)
        results=[]
        for pct in PCT:
            alltr=test(b,ev,pct)
            train=[t for t in alltr if t["t"]<dt.datetime(2026,9,1,tzinfo=dt.timezone.utc)]
            hold=[t for t in alltr if t["t"]>=dt.datetime(2026,9,1,tzinfo=dt.timezone.utc)]
            results.append({"SL_pct":pct,"train":metrics(train),"holdout":metrics(hold),"all":metrics(alltr)})
        out["w"+str(width)]=results
        print("RESULTS WIDTH",width,"sl%, train:n/E/PF/DD; holdout:n/E/PF/DD; total:n/E/PF/DD")
        for v in results:
            def fmt(m):
                return f'{m["n"]}/{m["expectancy"]}/{m["PF"]}/{m["maxDD"]}'
            print(f'{v["SL_pct"]:.3f}%',fmt(v["train"]),fmt(v["holdout"]),fmt(v["all"]))
        eligible=[v for v in results if v["train"]["n"]>=25]
        if eligible:
            winner=max(eligible,key=lambda v:(v["train"]["expectancy"],v["train"]["PF"] or 0))
            stress=test(b,ev,winner["SL_pct"],slip_pips=.2)
            print("DEVELOPMENT_WINNER",winner["SL_pct"],"PCT; HOLDOUT_NOT_USED_TO_SELECT",json.dumps(winner))
            print("WINNER_WITH_0.2PIP_ADVERSE_SLIPPAGE",json.dumps(metrics(stress)))
        out["signals_width_"+str(width)]=len(ev)
    pathlib.Path("results").mkdir(exist_ok=True)
    file=pathlib.Path("results/v8a_eurusdm_sl_study_2026.json")
    file.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("RESULT_JSON",str(file))
if __name__=="__main__":main()
