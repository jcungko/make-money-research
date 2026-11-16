#!/usr/bin/env python3
"""Fail-closed, hash-linked USDJPY checkpoint and bounded experiment index (stdlib only)."""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

PROTOCOL = "USDJPY-R1-20261116"
TOTAL = 96

def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def require(ok, msg):
    if not ok:
        raise ValueError("CHECKPOINT_INVALID: " + msg)

def state_check(s):
    require(isinstance(s, dict) and s.get("protocol") == PROTOCOL, "protocol")
    c, n = s.get("cursor"), s.get("completed")
    require(type(c) is int and 0 <= c <= TOTAL, "cursor")
    require(type(n) is int and n == c, "completed/cursor mismatch")
    return c

def report_check(root, state):
    reports = sorted(root.glob("run_*.json"))
    require(len(reports) == 1, "exactly one latest journal required")
    r = read(reports[0])
    require(r.get("protocol") == PROTOCOL, "journal protocol")
    require(r.get("status") in ("EXPERIMENTS_COMPLETED", "EXHAUSTED"), "not a successful journal")
    start = r.get("from_cursor")
    items = r.get("experiments", [])
    require(type(start) is int and type(items) is list, "journal shape")
    require(start + len(items) == state["cursor"], "journal cursor discontinuity")
    require(r["status"] != "EXHAUSTED" or state["cursor"] == TOTAL, "false EXHAUSTED")
    require(len(items) <= 2, "unbounded batch")
    for j, row in enumerate(items):
        expect = "UJ-R1-%03d" % (start + j)
        require(row.get("id") == expect, "non-sequential experiment")
        require(row.get("status") in ("REJECTED", "RESEARCH_CANDIDATE"), "invalid status")
        f = root / "experiments" / (expect + ".json")
        require(f.is_file(), "missing experiment proof " + expect)
        proof = read(f)
        require(proof.get("config", {}).get("id") == expect, "wrong proof ID")
        require(proof.get("status") == row["status"], "status/proof mismatch")
        require(proof.get("metrics", {}).get("trades") == row.get("trades"), "trade count mismatch")
        require(proof.get("metrics", {}).get("net_usd") == row.get("net_usd"), "PnL mismatch")
    return r, reports[0]

def verify(root):
    root = Path(root)
    s = read(root / "state.json")
    cursor = state_check(s)
    r, report_file = report_check(root, s)
    manifest = root / "manifest.json"
    if manifest.exists():
        m = read(manifest)
        require(m.get("version") == 2 and isinstance(m.get("files"), dict), "manifest schema")
        expected = ["state.json", "index.json", report_file.name]
        expected += ["experiments/" + item["id"] + ".json" for item in r["experiments"]]
        require(set(m["files"]) == set(expected), "manifest file set mismatch")
        for relative, expected_hash in m["files"].items():
            target = root / relative
            require(target.is_file() and digest(target) == expected_hash, "checksum " + relative)
        index = read(root / "index.json")
        require(index.get("protocol") == PROTOCOL, "index protocol")
        begin = index.get("start_cursor")
        rows = index.get("entries")
        require(type(begin) is int and 0 <= begin <= cursor, "index start")
        require(type(rows) is list and len(rows) == cursor - begin, "index continuity")
        for j, row in enumerate(rows):
            require(row.get("id") == "UJ-R1-%03d" % (begin + j), "index order")
            require(isinstance(row.get("sha256"), str) and len(row["sha256"]) == 64, "index checksum")
        require(index.get("cursor") == cursor, "index cursor")
        for row in r["experiments"]:
            match = next((x for x in rows if x["id"] == row["id"]), None)
            require(match is not None, "unindexed latest evidence")
            require(match["sha256"] == digest(root / "experiments" / (row["id"] + ".json")), "index proof hash")
        return s, index
    # Migration only: old artifact contained state + recent proof, without a checksum/index.
    require(not (root / "index.json").exists(), "unsealed index")
    return s, dict(protocol=PROTOCOL, start_cursor=cursor, cursor=cursor,
                   legacy_unindexed=cursor, entries=[])

def restore(source, target):
    s, idx = verify(source)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "state.json").write_text(json.dumps(s, indent=2) + "\n")
    (target / "index.json").write_text(json.dumps(idx, indent=2) + "\n")
    print(json.dumps({"checkpoint": "VERIFIED", "cursor": s["cursor"],
                      "indexed_since": idx["start_cursor"], "legacy_unindexed": idx.get("legacy_unindexed", 0)}))

def seal(target):
    root = Path(target)
    state = read(root / "state.json")
    cursor = state_check(state)
    idx_path = root / "index.json"
    report, report_path = report_check(root, state)
    before = report["from_cursor"]
    if idx_path.exists():
        index = read(idx_path)
        require(index["cursor"] == before, "old index cursor changed")
        require(len(index["entries"]) == before - index["start_cursor"], "old index gap")
    else:
        require(before == 0, "missing saved index on resume")
        index = dict(protocol=PROTOCOL, start_cursor=0, cursor=0, legacy_unindexed=0, entries=[])
    for item in report["experiments"]:
        f = root / "experiments" / (item["id"] + ".json")
        index["entries"].append(dict(id=item["id"], status=item["status"],
                                     sha256=digest(f), trades=item["trades"],
                                     net_usd=item["net_usd"]))
    index["cursor"] = cursor
    require(len(index["entries"]) == cursor - index["start_cursor"], "new index gap")
    idx_path.write_text(json.dumps(index, indent=2) + "\n")
    files = ["state.json", "index.json", report_path.name]
    files += ["experiments/" + item["id"] + ".json" for item in report["experiments"]]
    (root / "manifest.json").write_text(json.dumps(
        {"version": 2, "files": {f: digest(root / f) for f in files}}, indent=2) + "\n")
    verify(root)
    print(json.dumps({"checkpoint": "SEALED_VERIFIED", "cursor": cursor,
                      "current_proofs": len(report["experiments"])}))

def payload(target, event, run_id, job_status):
    root = Path(target)
    report = None
    try:
        logs = sorted(root.glob("run_*.json"))
        if logs:
            report = read(logs[-1])
    except (ValueError, OSError):
        pass
    result = dict(kind="NONE", run_id=int(run_id), cursor=0, candidates=[])
    if job_status != "success":
        result["kind"] = "ERROR"
    elif event in ("push", "workflow_dispatch"):
        result["kind"] = "TEST"
    elif report:
        candidates = [r["id"] for r in report.get("experiments", [])
                      if r.get("status") == "RESEARCH_CANDIDATE"]
        if candidates:
            result["kind"] = "CANDIDATE"
            result["candidates"] = candidates[:2]
        elif report.get("status") == "EXHAUSTED":
            result["kind"] = "EXHAUSTED"
    if report:
        result["cursor"] = min(max(int(report.get("from_cursor", 0)) +
                                   len(report.get("experiments", [])), 0), TOTAL)
    print(json.dumps(result, separators=(",", ":")))

if __name__ == "__main__":
    try:
        command = sys.argv[1]
        if command == "restore":
            restore(sys.argv[2], sys.argv[3])
        elif command == "seal":
            seal(sys.argv[2])
        elif command == "verify":
            verify(sys.argv[2])
            print("CHECKPOINT_VERIFIED")
        elif command == "payload":
            payload(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        else:
            raise ValueError("unsupported command")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(4)
