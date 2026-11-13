#!/usr/bin/env python3
"""V22 isolated prospective EURUSDm daily archive. Research only: never trades, trains, or scores."""
from __future__ import annotations
import argparse, io, json, sys, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests
from v22_prospective_collect import MIN_DATE, inspect_zip, collect

BACKFILL_DAYS = 7

def plan_days(today:date, requested:str="", lookback:int=BACKFILL_DAYS):
    if requested:
        day=date.fromisoformat(requested)
        if day<MIN_DATE or day>=today: raise ValueError("Requested UTC date must be fully closed and >= 2026-11-14")
        return [day]
    last=today-timedelta(days=1)
    if last<MIN_DATE: return []
    first=max(MIN_DATE,last-timedelta(days=lookback-1))
    return [first+timedelta(days=i) for i in range((last-first).days+1)]

def preflight():
    day=date(2026,11,14)
    def fixture(data):
        out=io.BytesIO()
        with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:z.writestr("ticks.csv",data)
        return out.getvalue()
    header="Timestamp,Bid,Ask,Symbol\n2026-11-14T22:00:00.001Z,1.10000,1.10009,EURUSDm\n2026-11-14T22:00:00.050Z,1.10002,1.10011,EURUSDm\n"
    plain="exness,EURUSDm,2026-11-14T22:00:00.001Z,1.10000,1.10009\n"
    for content,count in ((header,2),(plain,1)):
        info=inspect_zip(fixture(content.encode()),day)
        assert info["rows"]==count and info["spread_median_points"]==9 and len(info["source_sha256"])==64
    assert plan_days(date(2026,11,14))==[]
    assert plan_days(date(2026,11,15))==[day]
    assert len(plan_days(date(2026,11,22)))==7
    try: plan_days(date(2026,11,14),"2026-11-14")
    except ValueError:pass
    else:raise AssertionError("Open date accepted")
    try:inspect_zip(fixture(b"Timestamp,Bid,Ask\n2026-11-14T10:00:00Z,1.2,1.1\n"),day)
    except ValueError:pass
    else:raise AssertionError("Crossed quote accepted")
    print("PRECHECK_PASS: schema/headerless, UTC, spread, SHA, date guard and invalid quotes")

def process(today:date,out:Path,requested:str="",lookback:int=BACKFILL_DAYS,execute:bool=False):
    days=plan_days(today,requested,lookback)
    out.mkdir(parents=True,exist_ok=True)
    report={"project":"V22 readonly prospective EURUSDm Bid/Ask capture",
        "run_utc":datetime.now(timezone.utc).isoformat(),"date_utc":str(today),
        "first_allowed_date_utc":str(MIN_DATE),
        "source":"https://ticks.ex2archive.com/ticks/EURUSDm/",
        "never_generate_labels_or_trade":True,"days":[]}
    errors=0; valid=0
    for day in days:
        url=f"https://ticks.ex2archive.com/ticks/EURUSDm/{day.year}/{day.month:02d}/{day.day:02d}/Exness_EURUSDm_{day:%Y_%m_%d}.zip"
        item={"utc_day":str(day),"source_url":url,
              "checked_utc":datetime.now(timezone.utc).isoformat()}
        if not execute:item["status"]="PREFLIGHT_NO_NETWORK"
        else:
            try:
                collect(day,out)
                manifest=json.loads((out/f"manifest_{day:%Y_%m_%d}.json").read_text())
                item.update({"status":"SEALED_VALID_SOURCE","rows":manifest["rows"],
                    "sha256":manifest["source_sha256"],
                    "first_ms":manifest["first_ms"],"last_ms":manifest["last_ms"],
                    "spread_median_points":manifest["spread_median_points"],
                    "adjacent_identical_duplicates":manifest["adjacent_identical_duplicates"],
                    "same_timestamp_quote_pairs":manifest["same_timestamp_quote_pairs"],
                    "max_quote_gap_ms":manifest["max_quote_gap_ms"]})
                valid+=1
            except requests.exceptions.HTTPError as exc:
                code=exc.response.status_code if exc.response is not None else None
                item.update({"status":"UNAVAILABLE_HTTP_404" if code==404 else "FETCH_HTTP_ERROR",
                    "http_status":code,"error":str(exc)[:350]})
                if code!=404:errors+=1
            except requests.exceptions.RequestException as exc:
                item.update({"status":"FETCH_NETWORK_ERROR","error":str(exc)[:350]});errors+=1
            except Exception as exc:
                item.update({"status":"REJECTED_INVALID_SOURCE",
                    "error":f"{type(exc).__name__}: {str(exc)[:350]}"});errors+=1
            if item["status"]!="SEALED_VALID_SOURCE":
                (out/f"unavailable_{day:%Y_%m_%d}.json").write_text(json.dumps(item,indent=2)+"\n")
        report["days"].append(item)
        print(json.dumps(item),flush=True)
    report.update({"status":"NOT_STARTED" if not days else
         "ERROR" if errors else "SOME_UNAVAILABLE" if valid<len(days) else "ALL_VALID",
         "validated_days":valid,"unavailable_days":len(days)-valid,
         "warnings":["404 does not prove weekend market closure or data completeness",
                     "GitHub artifact retention 90 days is not long-term backup",
                     "Schedule may be delayed/dropped; manually backfill missed dates"]})
    (out/"RUN_MANIFEST.json").write_text(json.dumps(report,indent=2)+"\n")
    print("V22_CAPTURE_STATUS",report["status"],"valid",valid,"unavailable",len(days)-valid,flush=True)
    return 1 if errors else 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=["preflight","collect"],default="preflight")
    parser.add_argument("--day",default="")
    parser.add_argument("--lookback",type=int,default=BACKFILL_DAYS)
    parser.add_argument("--out",type=Path,default=Path("v22_prospective_daily"))
    args=parser.parse_args()
    if args.lookback<1 or args.lookback>7:parser.error("Lookback must be 1..7")
    if args.mode=="preflight":
        preflight()
        return process(datetime.now(timezone.utc).date(),args.out,args.day,args.lookback,False)
    return process(datetime.now(timezone.utc).date(),args.out,args.day,args.lookback,True)
if __name__=="__main__":sys.exit(main())
