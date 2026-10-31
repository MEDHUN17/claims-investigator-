"""End-to-end check of the USP path against a RUNNING API (real pipeline, real Gemini calls, real database).

rear_vs_front -> analysis -> human approval -> twist evidence -> stale diff -> approval voided -> gates.
Usage: backend/.venv/Scripts/python.exe scripts/e2e_check.py [--set rear_vs_front] [--twist-files witness_statement.txt garage_report.pdf]
Prints measured timings and PASS/FAIL per assertion. Never prints secrets.
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api"
FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
client = httpx.Client(timeout=180)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def wait_idle(cid: str, label: str, limit: int = 420):
    t0 = time.time()
    while True:
        d = client.get(f"{BASE}/cases/{cid}").json()
        if not [j for j in d["jobs"] if j["status"] in ("queued", "running")]:
            return d, time.time() - t0
        if time.time() - t0 > limit:
            print(f"TIMEOUT waiting for {label}")
            sys.exit(2)
        time.sleep(3)


def summarise(d: dict, title: str) -> None:
    s = d.get("state") or {}
    print(f"\n=== {title}: status={d['case']['status']} rev={d['case']['rev']}")
    print("summary:", (s.get("summary") or "")[:300])
    print("hypotheses:", [(h["id"], h["kind"], h["rank"]) for h in s.get("hypotheses", [])])
    print("findings:", [(f["id"], f["type"], f["status"]) for f in s.get("findings", [])])
    print("requests:", [(r["id"], r["status"], r["pairs_separated"], r.get("outcome")) for r in s.get("requests", [])])
    c = s.get("calc") or {}
    print("calc:", {k: c.get(k) for k in ("quoted_total", "recomputed_total", "proposed_settlement")}, "unresolved:", [u["term"] for u in c.get("unresolved", [])])
    z = s.get("zones") or {}
    print("zones:", z.get("narrative"), z.get("photo"), z.get("estimate"), "mismatch=", z.get("mismatch"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="rear_vs_front")
    ap.add_argument("--twist-files", nargs="*", default=["witness_statement.txt", "garage_report.pdf"])
    a = ap.parse_args()

    h = client.get(f"{BASE}/health").json()
    check("health ok + db", h["ok"], h["db"])
    check("ai configured", h["ai"]["configured"], h["ai"].get("message", ""))

    t0 = time.time()
    r = client.post(f"{BASE}/demo/load", json={"fixture_set": a.set}).json()
    cid = r["case"]["id"]
    d, dt = wait_idle(cid, "initial analysis")
    print(f"initial analysis wall time: {time.time() - t0:.0f}s (case {cid})")
    summarise(d, "after initial load")
    s = d["state"] or {}
    rev1 = d["case"]["rev"]
    check("evidence all extracted", all(e["status"] == "extracted" for e in d["evidence"]), str([e["status"] for e in d["evidence"]]))
    check("benign hypothesis present", any(x["benign"] for x in s.get("hypotheses", [])))
    check("data-error hypothesis present", any(x["kind"] == "data_error" for x in s.get("hypotheses", [])))
    check("zones mismatch (rear vs front)", (s.get("zones") or {}).get("mismatch") is True)
    check("at least 1 open request", any(x["status"] == "open" for x in s.get("requests", [])))
    check("planner ran (not degraded)", "unavailable" not in (s.get("summary") or "").lower(), (s.get("summary") or "")[:90])
    g = client.post(f"{BASE}/cases/{cid}/gates").json()
    check("5 gates pass on initial", all(x["passed"] for x in g), str({x["name"]: x["passed"] for x in g}))
    stale_before = {f["id"] for f in s.get("findings", []) if f["status"] == "active"}

    ap_r = client.post(f"{BASE}/cases/{cid}/approve", json={"decision": "approve", "reviewer": "E2E Reviewer", "note": "pre-twist sign-off"})
    check("approval accepted", ap_r.status_code == 200, f"{ap_r.status_code} {ap_r.text[:120] if ap_r.status_code != 200 else ''}")
    d = client.get(f"{BASE}/cases/{cid}").json()
    check("approval bound to current rev", bool(d.get("approval_current")) and d["approval_current"]["rev"] == d["case"]["rev"])

    # ---- the jury moment: new evidence ----
    t1 = time.time()
    for name in a.twist_files:
        p = FIX / "twist_secondary_impact" / name
        with open(p, "rb") as fh:
            up = client.post(f"{BASE}/cases/{cid}/evidence", files={"file": (name, fh)})
        print("upload", name, up.status_code)
    d, _ = wait_idle(cid, "twist revision")
    twist_secs = time.time() - t1
    print(f"twist wall time: {twist_secs:.0f}s")
    summarise(d, "after twist")
    s2 = d["state"] or {}
    revs = d["revisions"]
    latest = max(revs, key=lambda x: x["rev"])
    delta = latest["delta"]
    print("delta:", {k: delta[k] for k in ("cause", "added", "revised", "resolved", "stale", "unchanged", "approval_voided")})
    check("new revision created", d["case"]["rev"] > rev1, f"{rev1}->{d['case']['rev']}")
    check("delta has lines", len(delta["lines"]) > 0, str(len(delta["lines"])))
    check("only some findings touched (not a full re-run)", delta["unchanged"] > 0 or len(delta["stale"]) < max(1, len(s.get("findings", []))), f"unchanged={delta['unchanged']} stale={len(delta['stale'])}")
    check("approval voided", d.get("approval_current") is None and any(x["status"] == "void" for x in d["approvals"]), str([(x["rev"], x["status"], x.get("void_reason")) for x in d["approvals"]]))
    check("delta flags approval_voided", delta.get("approval_voided") is True)
    check("zones mismatch resolved by twist", (s2.get("zones") or {}).get("mismatch") is False)
    check("a request moved to received", any(x["status"] == "received" for x in s2.get("requests", [])))
    g2 = client.post(f"{BASE}/cases/{cid}/gates").json()
    check("5 gates pass after twist", all(x["passed"] for x in g2), str({x["name"]: x["passed"] for x in g2}))
    rep = client.get(f"{BASE}/cases/{cid}/report.pdf")
    check("report.pdf is a PDF", rep.status_code == 200 and rep.content[:4] == b"%PDF", f"{rep.status_code} {len(rep.content)} bytes")

    bad = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed; failed: {bad}")
    print("case id:", cid)
    json.dump({"case": cid, "results": results, "twist_secs": twist_secs}, open(FIX.parent / "_e2e_last.json", "w"))


if __name__ == "__main__":
    main()
