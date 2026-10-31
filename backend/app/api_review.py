"""Reviewer decision, approval verification, report PDF and gates."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from .repo import Conflict, NotFound, get_repo

router = APIRouter(prefix="/api")


class ApproveBody(BaseModel):
    decision: Literal["approve", "return", "escalate"]
    reviewer: str
    note: str = ""


@router.post("/cases/{case_id}/approve")
def approve(case_id: str, body: ApproveBody):
    return get_repo().approve(case_id, body.decision, body.reviewer, body.note)


@router.get("/approvals/{approval_id}/verify")
def verify(approval_id: str):
    return get_repo().verify_approval(approval_id)


@router.get("/cases/{case_id}/report.pdf")
def report_pdf(case_id: str, rev: Optional[int] = None):
    from . import report

    pdf = report.build_pdf(get_repo(), case_id, rev)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="verity-{case_id}.pdf"'})


def run_case_gates(case_id: str) -> list[dict]:
    repo = get_repo()
    state = repo.get_state(case_id)
    if state is None:
        raise Conflict("no analysed revision yet; gates need a state to check", code="no_revision")
    try:
        from . import gates  # INTEL
    except ImportError as e:
        raise Conflict(f"gates module unavailable: {e}", code="gates_unavailable")
    return gates.run_gates(state, repo.passages_by_evidence(case_id))


@router.post("/cases/{case_id}/gates")
def gates_route(case_id: str):
    return run_case_gates(case_id)
