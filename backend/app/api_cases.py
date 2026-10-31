"""Case, job, activity, revision, request-status and finding-challenge routes."""
from __future__ import annotations

import copy
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from . import jobs
from .repo import Conflict, NotFound, get_repo

router = APIRouter(prefix="/api")


class CaseCreate(BaseModel):
    title: str = "Untitled claim"


class StatusBody(BaseModel):
    status: Literal["open", "received", "dropped"]


class ChallengeBody(BaseModel):
    note: str = ""


def case_detail(case_id: str, activity_limit: int = 100) -> dict:
    repo = get_repo()
    return {
        "case": repo.case_summary(case_id),
        "evidence": [repo.evidence_out(e["id"]) for e in repo.evidence_list(case_id)],
        "state": repo.get_state(case_id),
        "revisions": repo.revisions(case_id),
        "approvals": repo.approvals(case_id),
        "jobs": repo.jobs_for_case(case_id),
        "activity": repo.activity(case_id, activity_limit),
        "approval_current": repo.current_approval(case_id),
    }


@router.get("/cases")
def list_cases():
    repo = get_repo()
    return [repo.case_summary(cid) for cid in repo.list_case_ids()]


@router.post("/cases")
def create_case(body: CaseCreate):
    repo = get_repo()
    c = repo.create_case(body.title)
    return repo.case_summary(c["id"])


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    return case_detail(case_id)


@router.post("/cases/{case_id}/analyze")
def analyze(case_id: str):
    repo = get_repo()
    job, _created = repo.enqueue_job(case_id, "analyze", None, key=f"rev{repo.current_rev(case_id)}")
    jobs.worker.notify()
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    return get_repo().job(job_id)


@router.get("/cases/{case_id}/activity")
def activity(case_id: str, limit: int = 100):
    repo = get_repo()
    repo.case(case_id)
    return repo.activity(case_id, max(1, min(limit, 500)))


@router.get("/cases/{case_id}/revisions")
def revisions(case_id: str):
    repo = get_repo()
    repo.case(case_id)
    return repo.revisions(case_id)


@router.get("/cases/{case_id}/revisions/{rev}")
def revision(case_id: str, rev: int):
    repo = get_repo()
    row = repo.revision_row(case_id, rev)
    state = repo.get_state(case_id, rev)
    if not row or state is None:
        raise NotFound(f"revision {rev} not found")
    return {"revision": row, "state": state}


@router.get("/cases/{case_id}/audit")
def audit_info(case_id: str):
    repo = get_repo()
    repo.case(case_id)
    return {"chain": repo.audit_verify(case_id), "revisions": repo.verify_revisions(case_id), "tail": repo.audit_tail(case_id, 30)}


def _guard_idle(case_id: str) -> None:
    if get_repo().has_active_job(case_id):
        raise Conflict("analysis is running for this case; try again when it finishes", code="job_running")


@router.post("/cases/{case_id}/requests/{rid}/status")
def request_status(case_id: str, rid: str, body: StatusBody):
    repo = get_repo()
    _guard_idle(case_id)
    base = repo.current_rev(case_id)
    state = repo.get_state(case_id)
    if not state:
        raise Conflict("no analysed revision yet", code="no_revision")
    state = copy.deepcopy(state)
    req = next((r for r in state.get("requests", []) if r.get("id") == rid), None)
    if not req:
        raise NotFound(f"request {rid} not found")
    before = req.get("status", "open")
    req["status"] = body.status
    delta = {"cause": f"Request {rid} marked {body.status} (was {before})", "added": [], "revised": [], "resolved": [], "stale": [],
             "unchanged": len(state.get("findings", [])), "lines": [], "approval_voided": False}
    rev = repo.commit_revision(case_id, base, state, delta, None, f"Request {rid} status {before} -> {body.status}")
    return {"rev": rev, "request": req}


@router.post("/cases/{case_id}/findings/{fid}/challenge")
def challenge_finding(case_id: str, fid: str, body: ChallengeBody):
    repo = get_repo()
    _guard_idle(case_id)
    base = repo.current_rev(case_id)
    state = repo.get_state(case_id)
    if not state:
        raise Conflict("no analysed revision yet", code="no_revision")
    state = copy.deepcopy(state)
    f = next((x for x in state.get("findings", []) if x.get("id") == fid), None)
    if not f:
        raise NotFound(f"finding {fid} not found")
    note = (body.note or "").strip()
    f["status"] = "stale"
    f["stale_reason"] = "Challenged by reviewer" + (f": {note}" if note else "")
    delta = {"cause": f"Reviewer challenged {fid}", "added": [], "revised": [], "resolved": [], "stale": [fid],
             "unchanged": max(len(state.get("findings", [])) - 1, 0), "approval_voided": False,
             "lines": [{"finding_id": fid, "change": "stale", "before": f.get("body"), "after": None, "reason": f["stale_reason"], "refs": []}]}
    rev = repo.commit_revision(case_id, base, state, delta, None, f"Finding {fid} challenged by reviewer")
    job, _ = repo.enqueue_job(case_id, "analyze", None, key=f"challenge-{fid}-rev{rev}")
    jobs.worker.notify()
    return {"rev": rev, "job": job}
