"""Runs every Proof Lab scenario ONE AT A TIME against the running API (real pipeline, real model calls) and logs results.
Usage: backend/.venv/Scripts/python.exe scripts/run_lab.py
"""
import json
import pathlib
import time

import httpx

BASE = "http://127.0.0.1:8000/api"
OUT = pathlib.Path(__file__).resolve().parents[1] / "_lab_run.json"
c = httpx.Client(timeout=900)

scen = c.get(f"{BASE}/lab/scenarios").json()
print("scenarios:", [s["id"] for s in scen], flush=True)
rows_all = []
for s in scen:
    t = time.time()
    try:
        r = c.post(f"{BASE}/lab/run", json={"scenario_id": s["id"]})
        body = r.json() if r.status_code == 200 else {"error": r.text[:300]}
    except Exception as e:  # noqa
        body = {"error": repr(e)[:300]}
    dt = time.time() - t
    rows = body if isinstance(body, list) else body.get("rows", body)
    print(f"--- {s['id']} ({dt:.0f}s) http={r.status_code if 'r' in dir() else '?'}", flush=True)
    print(json.dumps(rows, indent=1)[:1500], flush=True)
    rows_all.append({"scenario": s["id"], "secs": round(dt), "rows": rows})
    OUT.write_text(json.dumps(rows_all, indent=1))
    time.sleep(8)
print("DONE", flush=True)
