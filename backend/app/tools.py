"""Closed tool registry. Args are validated; every call is logged via repo.log_event(kind='tool').
Model-proposed calls are PROPOSALS: unknown or non-executable tools are rejected and logged."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx
from rapidfuzz import fuzz

from . import calc as calcmod
from .rank import request_key

OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"

# name -> (required arg types, executable_by_analysis_worker)
SPECS: dict[str, tuple[dict[str, type], bool]] = {
    "read_policy_clause": ({"query": str}, True),
    "check_estimate_totals": ({}, True),
    "lookup_claim_history": ({"vehicle_or_policy": str}, True),
    "weather_lookup": ({"date": str, "lat": float, "lon": float}, True),
    "create_evidence_request": ({"text": str, "kind": str, "resolves": list}, True),
    "save_revision": ({}, False),   # performed by the API worker on commit, never by a model proposal
    "export_report": ({}, False),   # performed by GET /report.pdf on explicit user action
}


class ToolError(Exception):
    pass


class ToolRegistry:
    def __init__(self, repo, case_id: str, http: Optional[httpx.Client] = None):
        self.repo, self.case_id = repo, case_id
        self.http = http or httpx.Client(timeout=12)
        self.pending_requests: list[dict] = []
        self.results: list[dict] = []

    # ---- dispatcher ----
    def call(self, name: str, args: Optional[dict] = None, proposed_by: str = "pipeline") -> dict:
        args = args or {}
        t0 = time.time()
        spec = SPECS.get(name)
        if spec is None:
            return self._log(name, args, {"error": "unknown tool; closed registry"}, "rejected", t0)
        types, executable = spec
        if not executable:
            return self._log(name, args, {"error": "not executable by the analysis worker"}, "rejected", t0)
        for k, tp in types.items():
            if k not in args or not (isinstance(args[k], tp) or (tp is float and isinstance(args[k], int))):
                return self._log(name, args, {"error": f"invalid or missing argument {k!r}"}, "rejected", t0)
        extra = set(args) - set(types)
        if extra:
            return self._log(name, args, {"error": f"unexpected arguments {sorted(extra)}"}, "rejected", t0)
        try:
            res = getattr(self, "_t_" + name)(**args)
            status = "ok" if not res.get("unavailable") else "unavailable"
        except Exception as e:  # tool failure is reported, never hidden
            res, status = {"error": f"{type(e).__name__}: {str(e)[:160]}"}, "error"
        res["proposed_by"] = proposed_by
        return self._log(name, args, res, status, t0)

    def _log(self, name, args, result, status, t0):
        try:
            self.repo.log_event(self.case_id, "tool", name, args, result, status, int((time.time() - t0) * 1000))
        except Exception:
            pass
        self.results.append({"tool": name, "args": args, "status": status, "result": result})
        return result

    # ---- tools ----
    def _evidence(self, kind: str) -> list[dict]:
        return [e for e in self.repo.evidence_list(self.case_id) if e.get("kind") == kind]

    def _t_read_policy_clause(self, query: str) -> dict:
        hits = []
        for e in self._evidence("policy"):
            for p in self.repo.passages(e["id"]):
                for line in p["text"].splitlines():
                    if len(line.strip()) < 6:
                        continue
                    sc = fuzz.partial_ratio(query.lower(), line.lower())
                    if sc >= 70:
                        hits.append({"evidence_id": e["id"], "page": p["page"], "text": line.strip()[:300], "score": int(sc)})
        hits.sort(key=lambda h: -h["score"])
        return {"matches": hits[:3], "unavailable": not hits}

    def _t_check_estimate_totals(self) -> dict:
        lines, qt = [], None
        for e in self._evidence("estimate"):
            x = self.repo.latest_extraction(e["id"])
            if x:
                for li in x["payload"].get("line_items", []):
                    lines.append({**li, "evidence_id": e["id"]})
                q = x["payload"].get("quoted_total")
                qt = (q.get("value") if isinstance(q, dict) else q) or qt
        c = calcmod.compute(lines, None, False, quoted_total=qt)
        return {"quoted_total": c["quoted_total"], "recomputed_total": c["recomputed_total"], "arithmetic_corrections": c["arithmetic_corrections"], "duplicates": c["duplicates"]}

    def _t_lookup_claim_history(self, vehicle_or_policy: str) -> dict:
        fn = getattr(self.repo, "claim_history", None)
        if fn is None:
            return {"unavailable": True, "reason": "claim history table not available through the repo"}
        rows = fn(vehicle_or_policy)
        return {"rows": rows, "label": "synthetic table", "unavailable": False}

    def _t_weather_lookup(self, date: str, lat: float, lon: float) -> dict:
        retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            r = self.http.get(OPEN_METEO, params={"latitude": lat, "longitude": lon, "start_date": date, "end_date": date,
                                                  "daily": "precipitation_sum,weathercode,temperature_2m_max", "timezone": "auto"})
            if r.status_code != 200:
                return {"unavailable": True, "reason": f"Open-Meteo HTTP {r.status_code}"}
            j = r.json()
            d = j.get("daily", {})
            return {"date": date, "precipitation_mm": (d.get("precipitation_sum") or [None])[0], "weather_code": (d.get("weathercode") or [None])[0],
                    "temp_max_c": (d.get("temperature_2m_max") or [None])[0],
                    "provenance": {"dataset": "Open-Meteo archive (ERA5 reanalysis)", "timezone": j.get("timezone"), "retrieved_at": retrieved, "lat": lat, "lon": lon}}
        except httpx.HTTPError as e:
            return {"unavailable": True, "reason": f"weather service unreachable ({type(e).__name__})"}

    def _t_create_evidence_request(self, text: str, kind: str, resolves: list) -> dict:
        key = request_key(self.case_id, text)
        if all(r["key"] != key for r in self.pending_requests):
            self.pending_requests.append({"key": key, "text": text, "kind": kind, "resolves": resolves})
        return {"key": key}
