#!/usr/bin/env python3
"""Update frozen USDJPY D1-42 through completed UTC sessions, research only."""
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "research_usdjpy"))
from exness_nov12_snapshot import fetch_day, read_ticks, frames_from_ticks
import d1_consistency as v1

DAYS = ("2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16")
CUTOFF = pd.Timestamp("2026-11-17T00:00:00Z")
OUT = ROOT / "results" / "usdjpy_d1_consistency_20261117" / "refresh_20261117"
FIELDS = dict(bid_open="first", bid_high="max", bid_low="min", bid_close="last",
              ask_open="first", ask_high="max", ask_low="min", ask_close="last",
              tick_count="sum")
CONFIG = dict(id="D1-42", family="three_fade", stop_atr=0.25,
              entry_hour_utc=1, rr=1.0)

def save(report):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(
        report, indent=2, ensure_ascii=False,
        default=lambda x: x.item() if hasattr(x, "item") else str(x)
    ) + "\n", encoding="utf-8")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    now = pd.Timestamp.now(tz="UTC")
    report = dict(
        protocol="D1-42-FROZEN-FORWARD-HISTORICAL-REPLAY-20261117",
        created_utc=now.isoformat(), excluded_incomplete_utc_day="2026-11-17",
        target_days_utc=list(DAYS),
        source="Exness public daily tick archives (USDJPY standard symbol)",
        branch="research/usdjpy-d1-consistency-20261117",
        status="STARTED", day_sources=[], source_errors=[],
        strategy=CONFIG, changes_to_strategy=False, real_trading=False,
        costs=dict(bid_ask=True, baseline_slippage_pips_per_side=0.20,
                   baseline_commission_usd_roundtrip=0.07,
                   stress_slippage_pips_per_side=0.70,
                   stress_commission_usd_roundtrip=0.10, actual_exness_costs_verified=False))
    if now < CUTOFF:
        report.update(status="BLOCKED_DATE", explanation="Nov 16 UTC is not closed")
        save(report)
        raise RuntimeError("Source UTC date not yet closed")
    old_m5, old_d1, old_meta = v1.load(2026)
    assert old_d1.timestamp_utc.dt.strftime("%Y-%m-%d").max() == "2026-11-10"
    assert old_m5.timestamp_utc.dt.strftime("%Y-%m-%d").max() == "2026-11-10"
    old_ready, old_groups = v1.prepare(old_m5, old_d1)
    reference = v1.simulate(old_ready, old_groups, CONFIG)
    refstats = v1.stats(reference)
    assert refstats["n"] == 146 and abs(refstats["net_usd"] - 0.66894) < 0.001, "frozen baseline mismatch"
    report["old_source"] = old_meta
    report["baseline_before_refresh"] = refstats

    fresh = []
    with requests.Session() as session:
        for day in DAYS:
            try:
                url, raw, zip_status, header = fetch_day(session, "USDJPY", day)
                ticks = read_ticks(raw, "USDJPY", day, CUTOFF)
                frame = frames_from_ticks(ticks)["M5"].rename(columns={"ticks":"tick_count"})
                last = ticks.ts.iloc[-1]
                first = ticks.ts.iloc[0]
                # Require quotes sufficiently near the expected end of each *closed* weekday.
                required = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=(20 if day=="2026-11-13" else 23),minutes=45)
                assert last >= required, f"archive ends too early ({last} < {required})"
                assert len(frame) >= 150, f"insufficient M5 bars {len(frame)}"
                assert frame.index.is_monotonic_increasing and not frame.index.has_duplicates
                assert (frame.bid_open <= frame.ask_open).all() and (frame.bid_close <= frame.ask_close).all()
                frame = frame.rename_axis("timestamp_utc").reset_index()
                assert frame.timestamp_utc.dt.strftime("%Y-%m-%d").eq(day).all()
                fresh.append(frame)
                report["day_sources"].append(dict(
                    date=day,status="VERIFIED_CLOSED",source_url=url,
                    archive_sha256=hashlib.sha256(raw).hexdigest(), zip_status=zip_status,
                    ticks=len(ticks),m5_bars=len(frame),
                    first_utc=first.isoformat(),last_utc=last.isoformat(),**header))
                print("VERIFIED", day, len(ticks), len(frame), str(last), flush=True)
            except Exception as exc:
                error=dict(date=day,error=type(exc).__name__+": "+str(exc)[:400])
                report["source_errors"].append(error)
                print("MISSING",json.dumps(error),flush=True)

    # Never bridge a missing weekday with signals from stale previous bars.
    good={d["date"] for d in report["day_sources"]}
    contiguous=[]
    for day in DAYS:
        if day not in good:break
        contiguous.append(day)
    if not contiguous:
        report.update(status="NO_CONTIGUOUS_NEW_DATA",
                      explanation="No safely replayable dates after the old Nov 10 archive")
        save(report)
        raise RuntimeError("Cannot verify Nov 11 source; refuse to generate PnL")
    new = pd.concat(fresh,ignore_index=True)
    new = new[new.timestamp_utc.dt.strftime("%Y-%m-%d").isin(contiguous)].copy()
    new = new.sort_values("timestamp_utc").reset_index(drop=True)
    # Preserve the source bid/ask OHLC; no interpolated prices.
    new_day=(new.set_index("timestamp_utc").resample("1D",label="left",closed="left")
             .agg(FIELDS).dropna(subset=["bid_open","ask_close"]))
    new_day=new_day[new_day.tick_count>0].rename_axis("timestamp_utc").reset_index()
    assert new_day.timestamp_utc.dt.strftime("%Y-%m-%d").tolist()==contiguous

    appended_m5=pd.concat([old_m5,new],ignore_index=True)
    appended_d1=pd.concat([old_d1,new_day],ignore_index=True)
    d, group=v1.prepare(appended_m5,appended_d1)
    run=v1.simulate(d,group,CONFIG,slip=0.20,commission=0.07)
    stress=v1.simulate(d,group,CONFIG,slip=0.70,commission=0.10)
    before=[t for t in run if t["day"]<="2026-11-10"]
    assert before==reference, "old historical ledger changed; fail closed"
    added=[t for t in run if t["day"]>"2026-11-10"]
    added_stress=[t for t in stress if t["day"]>"2026-11-10"]

    import csv
    for filename, records in (("new_trades.csv",added),("all_trades_updated.csv",run)):
        if records:
            with (OUT/filename).open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=list(records[0]))
                writer.writeheader();writer.writerows(records)
    new.to_csv(OUT/"USDJPY_M5_new_closed_days.csv.gz",index=False,compression="gzip")
    new_day.to_csv(OUT/"USDJPY_D1_new_closed_days.csv",index=False)

    report.update(
        status="COMPLETE" if len(contiguous)==len(DAYS) else "PARTIAL",
        contiguous_verified_days=contiguous,
        ignored_noncontiguous_days=[x for x in DAYS if x not in contiguous],
        full_to_utc_day=contiguous[-1],
        new_m5_rows=len(new),new_d1_rows=len(new_day),
        new_trades=added,new_period=v1.stats(added),
        new_period_stress=v1.stats(added_stress),
        updated_cumulative=v1.stats(run),
        updated_cumulative_stress=v1.stats(stress),
        disclaimer="Past historical replay, not forward verification. D1-42 was previously rejected; costs are hypothetical.")
    save(report)
    print("FINAL",json.dumps({k:report[k] for k in (
        "status","contiguous_verified_days","new_period","updated_cumulative"
    )},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
