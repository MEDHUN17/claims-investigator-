"""Proof Lab: labelled scenarios run through the REAL pipeline; expected.json evaluated with the shared check vocabulary."""
from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from . import config, jobs
from .api_demo import find_set, load_index, upload_set
from .api_review import run_case_gates
from .repo import Conflict, NotFound, get_repo

router = APIRouter(prefix="/api")

FORBIDDEN = ["fraud", "fraudulent", "fake", "lying", "liar", "forged", "scam", "cheat", "dishonest"]
JOB_TIMEOUT_S = 300.0


class RunBody(BaseModel):
    scenario_id: str = "all"


def load_expected(set_id: str) -> Optional[dict]:
    p = config.FIXTURES_DIR / set_id / "expected.json"
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    for wrap in ("checks", "expected"):
        if isinstance(raw.get(wrap), dict):
            raw = raw[wrap]
    return {k: v for k, v in raw.items() if "." in k}


def describe(key: str, want: Any) -> str:
    return {
        "calc.recomputed_total": f"Recomputed total equals {want}",
        "calc.proposed_settlement": "No settlement is proposed (unresolved terms)" if want is None else f"Proposed settlement equals {want}",
        "calc.duplicates_min": f"At least {want} duplicate line(s) flagged",
        "findings.types_include": f"Findings include types {want}",
        "hypotheses.has_benign": "A benign hypothesis is present" if want else "No benign hypothesis required",
        "requests.min_open": f"At least {want} evidence request(s) open",
        "injection_flags.min": f"At least {want} embedded instruction(s) flagged and ignored",
        "zones.mismatch": "Zone mismatch detected" if want else "No zone mismatch",
        "unresolved.contains_term": f"Unresolved list names '{want}'",
        "evidence.status": f"Evidence statuses {want}",
        "gates.all_pass": "All five gates pass" if want else "Gates are expected to flag a problem",
        "delta.stale_min": f"At least {want} finding(s) went stale on the new evidence",
        "delta.added_min": f"At least {want} finding(s) added by the new evidence",
        "revision.count": f"Exactly {want} revision(s) exist",
        "language.forbidden_absent": "No accusation language outside quoted source",
        "approval.void_after_new_evidence": "Earlier approval voided by the new evidence" if want else "Approval unaffected",
    }.get(key, f"{key} == {want}")


def _dec(v: Any) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _strip_quotes(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _strip_quotes(v) for k, v in o.items() if k != "quote"}
    if isinstance(o, list):
        return [_strip_quotes(x) for x in o]
    return o


def evaluate(case_id: str, expected: dict, ctx: dict) -> list[dict]:
    repo = get_repo()
    state = repo.get_state(case_id) or {}
    calc = state.get("calc") or {}
    revs = repo.revisions(case_id)
    # the twist may be processed as several revisions (one per upload, or coalesced): count what ALL revisions created after the base set changed
    after = [r for r in revs if int(r.get("rev", 0)) > int(ctx.get("base_rev", 0))]
    last_delta = {"stale": sorted({x for r in after for x in ((r.get("delta") or {}).get("stale") or [])}),
                  "added": sorted({x for r in after for x in ((r.get("delta") or {}).get("added") or [])})}
    out = []

    def add(key, ok, detail=""):
        out.append({"text": describe(key, expected[key]), "passed": bool(ok), "detail": detail})

    for key, want in expected.items():
        try:
            if key == "calc.recomputed_total":
                got = _dec(calc.get("recomputed_total"))
                add(key, got is not None and got == _dec(want), f"got {calc.get('recomputed_total')}")
            elif key == "calc.proposed_settlement":
                got = _dec(calc.get("proposed_settlement"))
                add(key, got == _dec(want), f"got {calc.get('proposed_settlement')}")
            elif key == "calc.duplicates_min":
                n = len(calc.get("duplicates") or [])
                add(key, n >= int(want), f"got {n}")
            elif key == "findings.types_include":
                types = {f.get("type") for f in state.get("findings", [])}
                missing = [t for t in want if t not in types]
                add(key, not missing, f"missing {missing}" if missing else f"found {sorted(types)}")
            elif key == "hypotheses.has_benign":
                has = any(h.get("benign") for h in state.get("hypotheses", []))
                add(key, has == bool(want), f"has_benign={has}")
            elif key == "requests.min_open":
                n = sum(1 for r in state.get("requests", []) if r.get("status", "open") == "open")
                add(key, n >= int(want), f"got {n}")
            elif key == "injection_flags.min":
                n = len(state.get("injection_flags") or [])
                add(key, n >= int(want), f"got {n}")
            elif key == "zones.mismatch":
                got = bool((state.get("zones") or {}).get("mismatch"))
                add(key, got == bool(want), f"got {got}")
            elif key == "unresolved.contains_term":
                terms = [str(x).lower() for x in (state.get("unresolved") or [])] + [str(u.get("term", "")).lower() for u in (calc.get("unresolved") or [])]
                add(key, any(str(want).lower() in t for t in terms), f"unresolved={terms[:8]}")
            elif key == "evidence.status":
                have = {}
                for e in repo.evidence_list(case_id):
                    have[e["filename"]] = e["status"]
                bad = {f: (have.get(f), s) for f, s in want.items() if have.get(f) != s}
                add(key, not bad, f"mismatches (got, wanted): {bad}" if bad else "all match")
            elif key == "gates.all_pass":
                res = run_case_gates(case_id)
                failed = [g["name"] for g in res if not g.get("passed")]
                add(key, (not failed) == bool(want), f"failed gates: {failed}" if failed else "all gates passed")
            elif key == "delta.stale_min":
                n = len(last_delta.get("stale") or [])
                add(key, n >= int(want), f"got {n}")
            elif key == "delta.added_min":
                n = len(last_delta.get("added") or [])
                add(key, n >= int(want), f"got {n}")
            elif key == "revision.count":
                add(key, len(revs) == int(want), f"got {len(revs)}")
            elif key == "language.forbidden_absent":
                blob = json.dumps(_strip_quotes(state), ensure_ascii=False).lower()
                hits = [w for w in FORBIDDEN if re.search(rf"\b{w}\b", blob)]
                add(key, (not hits) == bool(want), f"found {hits}" if hits else "none found")
            elif key == "approval.void_after_new_evidence":
                aid = ctx.get("approval_id")
                if not aid:
                    add(key, False, "scenario did not record an approval before the twist")
                else:
                    a = repo.approval(aid)
                    add(key, (a["status"] == "void") == bool(want), f"status={a['status']} reason={a.get('void_reason')}")
            else:
                add(key, False, "unknown check key (not in the lab vocabulary)")
        except Exception as e:  # a failing check is a failed assertion, never a crash
            add(key, False, f"check error: {type(e).__name__}: {e}"[:300])
    return out


def list_scenarios() -> list[dict]:
    out = []
    for s in load_index().get("sets", []):
        exp = load_expected(s["id"])
        if exp is None:
            continue
        out.append({"id": s["id"], "title": s.get("title", s["id"]), "description": s.get("description", ""), "fixture_set": s["id"],
                    "assertions": [describe(k, v) for k, v in exp.items()], "apply_on": s.get("apply_on")})
    return out


def run_scenario(sid: str) -> dict:
    repo = get_repo()
    fset = find_set(sid)
    expected = load_expected(sid)
    if expected is None:
        raise NotFound(f"scenario '{sid}' has no expected.json")
    t0 = time.time()
    case = repo.create_case(f"Lab: {fset.get('title', sid)}", synthetic=True, demo=True)
    cid = case["id"]
    ctx: dict = {}
    problems: list[str] = []
    try:
        base = fset.get("apply_on")
        if base:
            upload_set(cid, find_set(base))
            if not jobs.wait_idle(cid, JOB_TIMEOUT_S):
                problems.append("base set did not finish in time")
            ctx["base_rev"] = repo.current_rev(cid)
            if "approval.void_after_new_evidence" in expected and repo.current_rev(cid) > 0:
                a = repo.approve(cid, "approve", "LAB HARNESS (test only, not a real reviewer)", "recorded by the Proof Lab to test approval voiding")
                ctx["approval_id"] = a["id"]
        upload_set(cid, fset)
        if not jobs.wait_idle(cid, JOB_TIMEOUT_S):
            problems.append("scenario did not finish in time")
        rows = evaluate(cid, expected, ctx)
    except Exception as e:
        rows = [{"text": "Scenario executed", "passed": False, "detail": f"{type(e).__name__}: {e}"[:300]}]
    for p in problems:
        rows.insert(0, {"text": "Pipeline completed in time", "passed": False, "detail": p})
    # surface failed jobs explicitly: a green row must never hide a pipeline failure
    failed_jobs = [j for j in repo.jobs_for_case(cid) if j["status"] == "failed"]
    for j in failed_jobs:
        rows.append({"text": "No pipeline job failed", "passed": False, "detail": (j.get("error") or "")[:300]})
    latency = int((time.time() - t0) * 1000)
    passed = bool(rows) and all(r["passed"] for r in rows)
    saved = repo.save_eval_run(sid, cid, passed, rows, latency)
    return {"scenario_id": sid, "passed": passed, "assertions": rows, "latency_ms": latency, "ran_at": saved["ran_at"], "source": "live", "case_id": cid}


@router.get("/lab/scenarios")
def scenarios():
    return list_scenarios()


@router.post("/lab/run")
def lab_run(body: RunBody):
    ids = [s["id"] for s in list_scenarios()] if body.scenario_id == "all" else [body.scenario_id]
    if not ids:
        raise Conflict("no scenarios available (fixtures/index.json and expected.json missing)", code="no_scenarios")
    return [run_scenario(i) for i in ids]


@router.get("/lab/results")
def lab_results():
    return get_repo().eval_results()
