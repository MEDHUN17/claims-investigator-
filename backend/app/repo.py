"""SQLAlchemy-backed implementation of the Repo protocol (SPEC.md) plus the extra operations INFRA's API needs.

INTEL consumes this through plain dicts only. Every query is scoped by case_id (directly, or via the evidence row's case).
"""
from __future__ import annotations

import copy
import hashlib
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, func, select, text, update

from . import audit, config, db, storage
from .models import (Approval, AuditEvent, Case, ClaimHistory, EvalRun, Event, Evidence, Extraction, Job, Passage,
                     Revision, utcnow)


class StaleRun(Exception):
    """Raised by commit_revision when the case's current_rev != base_rev."""


class NotFound(KeyError):
    pass


class Conflict(Exception):
    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra


def _id(prefix: str, n: int = 5) -> str:
    return f"{prefix}{secrets.token_hex(n)}"


def iso(dt: Optional[datetime]) -> Optional[str]:
    return audit.iso(dt) if dt else None


def dec(v: Any) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def role_for(amount: Optional[Decimal]) -> str:
    """Delegation of authority. Unknown amount escalates to the top authority."""
    if amount is None:
        return config.DELEGATION_TOP
    for limit, role in config.DELEGATION:
        if amount <= limit:
            return role
    return config.DELEGATION_TOP


def money_str(d: Optional[Decimal]) -> Optional[str]:
    return None if d is None else format(d.quantize(Decimal("0.01")), "f")


class SqlRepo:
    # ------------------------------------------------------------------ cases
    def create_case(self, title: str, synthetic: bool = True, demo: bool = False) -> dict:
        with db.session() as s, s.begin():
            s.execute(text("SELECT pg_advisory_xact_lock(hashtext('case_seq'))"))
            seq = (s.execute(select(func.coalesce(func.max(Case.seq), 0))).scalar() or 0) + 1
            c = Case(id=_id("c_", 6), seq=seq, case_no=f"CLM-{datetime.now(timezone.utc).year}-{seq:04d}",
                     title=title.strip()[:300] or "Untitled claim", synthetic=synthetic, demo=demo)
            s.add(c)
            s.flush()
            audit.append(s, c.id, "system", "case.created", {"case_no": c.case_no, "title": c.title})
            cid = c.id
        return self.case(cid)

    def _case_row(self, s, case_id: str) -> Case:
        c = s.get(Case, case_id)
        if not c:
            raise NotFound(f"case {case_id} not found")
        return c

    def case(self, case_id: str) -> dict:
        with db.session() as s:
            c = self._case_row(s, case_id)
            return {"id": c.id, "case_no": c.case_no, "title": c.title, "synthetic": c.synthetic, "demo": c.demo,
                    "current_rev": c.current_rev, "created_at": iso(c.created_at), "updated_at": iso(c.updated_at)}

    def case_exists(self, case_id: str) -> bool:
        with db.session() as s:
            return s.get(Case, case_id) is not None

    def list_case_ids(self) -> list[str]:
        with db.session() as s:
            return list(s.execute(select(Case.id).order_by(Case.updated_at.desc())).scalars())

    def case_summary(self, case_id: str) -> dict:
        with db.session() as s:
            c = self._case_row(s, case_id)
            n_ev = s.execute(select(func.count()).select_from(Evidence).where(Evidence.case_id == case_id)).scalar() or 0
            state = None
            if c.current_rev:
                state = s.execute(select(Revision.state).where(Revision.case_id == case_id, Revision.rev == c.current_rev)).scalar_one_or_none()
            jobs = s.execute(select(Job).where(Job.case_id == case_id).order_by(Job.created_at.desc()).limit(5)).scalars().all()
            appr = s.execute(select(Approval).where(Approval.case_id == case_id, Approval.rev == c.current_rev, Approval.status == "active")).scalars().first()
            open_req = unresolved = 0
            if state:
                open_req = sum(1 for r in state.get("requests", []) if r.get("status", "open") == "open")
                unresolved = len(state.get("unresolved") or []) or len((state.get("calc") or {}).get("unresolved") or [])
            active_job = any(j.status in ("queued", "running", "interrupted") for j in jobs)
            last_failed = bool(jobs) and jobs[0].status == "failed" and not (jobs[0].error or "").startswith("stale")
            if n_ev == 0:
                status = "intake"
            elif active_job:
                status = "processing"
            elif last_failed:
                status = "failed"
            elif not c.current_rev:
                status = "intake"
            elif appr:
                status = "reviewed"
            elif open_req or unresolved:
                status = "evidence_needed"
            else:
                status = "ready_for_review"
            return {"id": c.id, "case_no": c.case_no, "title": c.title, "status": status, "unresolved": unresolved,
                    "open_requests": open_req, "evidence_count": n_ev, "rev": c.current_rev, "synthetic": c.synthetic,
                    "updated_at": iso(c.updated_at)}

    def touch_case(self, s, case_id: str) -> None:
        s.execute(update(Case).where(Case.id == case_id).values(updated_at=utcnow()))

    # --------------------------------------------------------------- evidence
    def new_evidence_id(self) -> str:
        with db.session() as s:
            while True:
                eid = "E-" + secrets.token_hex(3).upper()
                if not s.get(Evidence, eid):
                    return eid

    def find_by_sha(self, case_id: str, sha: str) -> Optional[dict]:
        with db.session() as s:
            e = s.execute(select(Evidence).where(Evidence.case_id == case_id, Evidence.sha256 == sha)).scalar_one_or_none()
            return self._ev_dict(e) if e else None

    def add_evidence(self, case_id: str, evidence_id: str, filename: str, mime: str, size: int, sha256: str, kind: str,
                     source_class: str, status: str, error: Optional[str], storage_rel: str, meta: Optional[dict] = None) -> dict:
        with db.session() as s, s.begin():
            self._case_row(s, case_id)
            e = Evidence(id=evidence_id, case_id=case_id, kind=kind, filename=filename, mime=mime, size=size, sha256=sha256,
                         source_class=source_class, status=status, error=error, meta=meta or {}, storage_rel=storage_rel)
            s.add(e)
            s.flush()
            audit.append(s, case_id, "system", "evidence.added", {"evidence_id": evidence_id, "filename": filename, "sha256": sha256, "status": status})
            self.touch_case(s, case_id)
            return self._ev_dict(e)

    @staticmethod
    def _ev_dict(e: Evidence) -> dict:
        return {"id": e.id, "case_id": e.case_id, "kind": e.kind, "filename": e.filename, "mime": e.mime, "size": e.size,
                "sha256": e.sha256, "source_class": e.source_class, "status": e.status, "error": e.error, "pages": e.pages,
                "meta": e.meta or {}, "uploaded_at": iso(e.uploaded_at)}

    def evidence_list(self, case_id: str) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(Evidence).where(Evidence.case_id == case_id).order_by(Evidence.uploaded_at, Evidence.id)).scalars().all()
            return [self._ev_dict(e) for e in rows]

    def evidence(self, evidence_id: str) -> dict:
        with db.session() as s:
            e = s.get(Evidence, evidence_id)
            if not e:
                raise NotFound(f"evidence {evidence_id} not found")
            return self._ev_dict(e)

    def evidence_out(self, evidence_id: str) -> dict:
        """EvidenceOut dict including latest extraction."""
        d = self.evidence(evidence_id)
        ex = self.latest_extraction(evidence_id)
        d["extraction"] = ex["payload"] if ex else None
        d["extraction_version"] = ex["version"] if ex else 0
        flags = []
        for f in ((ex or {}).get("payload") or {}).get("injection_flags") or []:
            flags.append(str(f.get("text", f)) if isinstance(f, dict) else str(f))
        d["injection_flags"] = flags
        return d

    def evidence_path(self, evidence_id: str) -> Path:
        with db.session() as s:
            e = s.get(Evidence, evidence_id)
            if not e:
                raise NotFound(f"evidence {evidence_id} not found")
            return storage.resolve_inside(e.storage_rel)

    def latest_extraction(self, evidence_id: str) -> Optional[dict]:
        with db.session() as s:
            x = s.execute(select(Extraction).where(Extraction.evidence_id == evidence_id).order_by(Extraction.version.desc()).limit(1)).scalar_one_or_none()
            if not x:
                return None
            return {"version": x.version, "payload": x.payload, "model": x.model, "human_corrected": x.human_corrected, "cached": x.cached}

    def save_extraction(self, evidence_id: str, payload: dict, model: str, cached: bool, human: bool = False) -> int:
        with db.session() as s, s.begin():
            e = s.get(Evidence, evidence_id)
            if not e:
                raise NotFound(f"evidence {evidence_id} not found")
            s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "ext:" + evidence_id})
            v = (s.execute(select(func.coalesce(func.max(Extraction.version), 0)).where(Extraction.evidence_id == evidence_id)).scalar() or 0) + 1
            s.add(Extraction(evidence_id=evidence_id, version=v, payload=payload, model=model or "", cached=bool(cached), human_corrected=human))
            audit.append(s, e.case_id, "human" if human else "system", "extraction.saved",
                         {"evidence_id": evidence_id, "version": v, "model": model, "cached": bool(cached), "human": human})
            return v

    def save_passages(self, evidence_id: str, passages: list[dict]) -> None:
        with db.session() as s, s.begin():
            s.execute(delete(Passage).where(Passage.evidence_id == evidence_id))
            for i, p in enumerate(passages):
                s.add(Passage(evidence_id=evidence_id, idx=i, page=p.get("page"), text=str(p.get("text", ""))))

    def passages(self, evidence_id: str) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(Passage).where(Passage.evidence_id == evidence_id).order_by(Passage.idx)).scalars().all()
            return [{"page": p.page, "text": p.text} for p in rows]

    def passages_by_evidence(self, case_id: str) -> dict[str, list[dict]]:
        return {e["id"]: self.passages(e["id"]) for e in self.evidence_list(case_id)}

    def set_evidence_status(self, evidence_id: str, status: str, error: Optional[str] = None, meta: Optional[dict] = None,
                            pages: Optional[int] = None, kind: Optional[str] = None) -> None:
        with db.session() as s, s.begin():
            e = s.get(Evidence, evidence_id)
            if not e:
                raise NotFound(f"evidence {evidence_id} not found")
            e.status = status
            e.error = error
            if meta:
                e.meta = {**(e.meta or {}), **meta}
            if pages is not None:
                e.pages = pages
            if kind and kind in storage.KINDS:
                e.kind = kind
            self.touch_case(s, e.case_id)

    # -------------------------------------------------------------- revisions
    def current_rev(self, case_id: str) -> int:
        with db.session() as s:
            return self._case_row(s, case_id).current_rev

    def get_state(self, case_id: str, rev: Optional[int] = None) -> Optional[dict]:
        with db.session() as s:
            if rev is None:
                rev = self._case_row(s, case_id).current_rev
            if not rev:
                return None
            st = s.execute(select(Revision.state).where(Revision.case_id == case_id, Revision.rev == rev)).scalar_one_or_none()
            return copy.deepcopy(st) if st is not None else None

    def revision_row(self, case_id: str, rev: int) -> Optional[dict]:
        with db.session() as s:
            r = s.execute(select(Revision).where(Revision.case_id == case_id, Revision.rev == rev)).scalar_one_or_none()
            return self._rev_dict(r) if r else None

    @staticmethod
    def _rev_dict(r: Revision, with_state: bool = False) -> dict:
        d = {"rev": r.rev, "created_at": iso(r.created_at), "trigger": r.trigger, "summary": r.summary,
             "delta": r.delta or {}, "hash": r.hash, "prev_hash": r.prev_hash}
        if with_state:
            d["state"] = r.state
        return d

    def revisions(self, case_id: str) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(Revision).where(Revision.case_id == case_id).order_by(Revision.rev)).scalars().all()
            return [self._rev_dict(r) for r in rows]

    def commit_revision(self, case_id: str, base_rev: int, state: dict, delta: dict, trigger_evidence_id: Optional[str], summary: str) -> int:
        with db.session() as s, s.begin():
            c = s.execute(select(Case).where(Case.id == case_id).with_for_update()).scalar_one_or_none()
            if not c:
                raise NotFound(f"case {case_id} not found")
            if c.current_rev != base_rev:
                raise StaleRun(f"case {case_id} is at rev {c.current_rev}, run was based on rev {base_rev}")
            rev = base_rev + 1
            state = copy.deepcopy(state)
            state["rev"] = rev
            prev_hash = s.execute(select(Revision.hash).where(Revision.case_id == case_id, Revision.rev == base_rev)).scalar_one_or_none() or audit.GENESIS
            h = audit.revision_hash(state, prev_hash)
            # trigger label
            trigger = (delta or {}).get("cause") or ""
            if trigger_evidence_id:
                ev = s.get(Evidence, trigger_evidence_id)
                if ev and ev.case_id == case_id:
                    trigger = trigger or f"{ev.id} {ev.filename} added"
            trigger = trigger or "re-analysis"
            # approvals bound to the previous revision (or any still-active one) are voided by the new revision
            active = s.execute(select(Approval).where(Approval.case_id == case_id, Approval.status == "active").with_for_update()).scalars().all()
            delta = copy.deepcopy(delta or {})
            for a in active:
                a.status = "void"
                a.void_reason = f"Voided by revision {rev}: {trigger}"
                audit.append(s, case_id, "system", "approval.voided", {"approval_id": a.id, "approval_rev": a.rev, "by_revision": rev, "reason": a.void_reason})
            delta["approval_voided"] = bool(active) or bool(delta.get("approval_voided"))
            s.add(Revision(case_id=case_id, rev=rev, state=state, delta=delta, trigger=trigger, trigger_evidence_id=trigger_evidence_id,
                           summary=summary or state.get("summary", "") or "", hash=h, prev_hash=prev_hash))
            c.current_rev = rev
            c.updated_at = utcnow()
            audit.append(s, case_id, "system", "revision.committed", {"rev": rev, "hash": h, "prev_hash": prev_hash, "trigger": trigger,
                                                                      "approval_voided": delta["approval_voided"]})
            return rev

    def verify_revisions(self, case_id: str) -> dict:
        """Recompute every revision hash and the prev_hash links."""
        with db.session() as s:
            rows = s.execute(select(Revision).where(Revision.case_id == case_id).order_by(Revision.rev)).scalars().all()
            prev = audit.GENESIS
            for r in rows:
                if r.prev_hash != prev or audit.revision_hash(r.state, prev) != r.hash:
                    return {"valid": False, "broken_at_rev": r.rev, "count": len(rows)}
                prev = r.hash
            return {"valid": True, "broken_at_rev": None, "count": len(rows)}

    # ------------------------------------------------------------------ events
    def log_event(self, case_id: str, kind: str, name: str, args: Any, result: Any, status: str, duration_ms: int) -> None:
        with db.session() as s, s.begin():
            if s.get(Case, case_id) is None:
                return
            s.add(Event(case_id=case_id, kind=kind if kind in ("stage", "tool", "provider", "audit") else "stage", name=str(name),
                        args=_jsonable(args), result=_jsonable(result), status=str(status), duration_ms=int(duration_ms or 0)))

    def activity(self, case_id: str, limit: int = 100) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(Event).where(Event.case_id == case_id).order_by(Event.id.desc()).limit(limit)).scalars().all()
            rows = list(reversed(rows))
            return [{"ts": iso(r.ts), "kind": r.kind, "name": r.name, "args": r.args if isinstance(r.args, dict) else {"value": r.args},
                     "result": r.result if isinstance(r.result, dict) else {"value": r.result}, "status": r.status, "duration_ms": r.duration_ms} for r in rows]

    # -------------------------------------------------------------------- jobs
    @staticmethod
    def _job_dict(j: Job) -> dict:
        return {"id": j.id, "case_id": j.case_id, "status": j.status, "base_rev": j.base_rev, "plan": j.plan or [], "error": j.error,
                "created_at": iso(j.created_at), "kind": j.kind, "attempts": j.attempts, "fingerprint": j.fingerprint,
                "trigger_evidence_id": j.trigger_evidence_id}

    def job(self, job_id: str) -> dict:
        with db.session() as s:
            j = s.get(Job, job_id)
            if not j:
                raise NotFound(f"job {job_id} not found")
            return self._job_dict(j)

    def jobs_for_case(self, case_id: str, limit: int = 20) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(Job).where(Job.case_id == case_id).order_by(Job.created_at.desc()).limit(limit)).scalars().all()
            return [self._job_dict(j) for j in rows]

    def has_active_job(self, case_id: str) -> bool:
        with db.session() as s:
            return s.execute(select(func.count()).select_from(Job).where(Job.case_id == case_id, Job.status.in_(("queued", "running", "interrupted")))).scalar() > 0

    def enqueue_job(self, case_id: str, kind: str = "process", trigger_evidence_id: Optional[str] = None, key: str = "") -> tuple[dict, bool]:
        """Idempotent: an identical queued/running job is returned instead of a duplicate. Returns (job, created)."""
        fp = hashlib.sha256(f"{kind}|{case_id}|{trigger_evidence_id or ''}|{key}".encode()).hexdigest()
        with db.session() as s, s.begin():
            c = self._case_row(s, case_id)
            s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "job:" + case_id})
            ex = s.execute(select(Job).where(Job.case_id == case_id, Job.fingerprint == fp, Job.status.in_(("queued", "running", "interrupted")))).scalars().first()
            if ex:
                return self._job_dict(ex), False
            j = Job(id=_id("J-", 4).upper(), case_id=case_id, kind=kind, status="queued", base_rev=c.current_rev, plan=[
                {"name": "ingest", "status": "done", "reason": ""}], fingerprint=fp, trigger_evidence_id=trigger_evidence_id)
            s.add(j)
            s.flush()
            audit.append(s, case_id, "system", "job.queued", {"job_id": j.id, "kind": kind, "trigger": trigger_evidence_id})
            return self._job_dict(j), True

    def claim_next_job(self) -> Optional[tuple[dict, list[dict]]]:
        """Claim the oldest queued job; coalesce every other queued job of the same case into it (one revision for a batch).
        base_rev is fixed here, at the moment analysis starts."""
        with db.session() as s, s.begin():
            j = s.execute(select(Job).where(Job.status == "queued").order_by(Job.created_at, Job.id).limit(1).with_for_update(skip_locked=True)).scalar_one_or_none()
            if not j:
                return None
            c = s.execute(select(Case).where(Case.id == j.case_id)).scalar_one()
            j.status = "running"
            j.started_at = utcnow()
            j.attempts += 1
            j.base_rev = c.current_rev
            j.error = None
            others = s.execute(select(Job).where(Job.case_id == j.case_id, Job.status == "queued", Job.id != j.id).order_by(Job.created_at, Job.id).with_for_update(skip_locked=True)).scalars().all()
            for o in others:
                o.status = "running"
                o.started_at = utcnow()
                o.attempts += 1
                o.base_rev = c.current_rev
                o.plan = [{"name": "ingest", "status": "done", "reason": ""}, {"name": "coalesced", "status": "running", "reason": f"merged into {j.id}"}]
            return self._job_dict(j), [self._job_dict(o) for o in others]

    def set_job_plan(self, job_id: str, plan: list[dict]) -> None:
        with db.session() as s, s.begin():
            j = s.get(Job, job_id)
            if j:
                j.plan = [{"name": str(p.get("name", "")), "status": p.get("status", "pending"), "reason": p.get("reason", "") or ""} for p in plan]

    def update_plan_step(self, job_id: str, name: str, status: str, reason: str = "") -> None:
        with db.session() as s, s.begin():
            j = s.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one_or_none()
            if not j:
                return
            plan = [dict(p) for p in (j.plan or [])]
            for p in plan:
                if p["name"] == name:
                    p["status"] = status
                    if reason:
                        p["reason"] = reason
                    break
            else:
                plan.append({"name": name, "status": status, "reason": reason})
            j.plan = plan

    def finish_job(self, job_id: str, status: str, error: Optional[str] = None) -> None:
        with db.session() as s, s.begin():
            j = s.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one_or_none()
            if not j:
                return
            plan = []
            for p in j.plan or []:
                p = dict(p)
                if p["status"] == "running":
                    p["status"] = "done" if status == "done" else "failed"
                elif p["status"] == "pending":
                    p["status"] = "skipped"
                    p["reason"] = p.get("reason") or ("not reached" if status != "done" else "not reported by pipeline")
                plan.append(p)
            j.plan = plan
            j.status = status
            j.error = error
            j.finished_at = utcnow()
            audit_action = "job.done" if status == "done" else "job.failed"
            audit.append(s, j.case_id, "system", audit_action, {"job_id": j.id, "error": error})

    def recover_jobs(self) -> list[str]:
        """Startup recovery: running -> interrupted -> re-queued as a retry of the SAME job row (nothing duplicated)."""
        ids: list[str] = []
        with db.session() as s, s.begin():
            rows = s.execute(select(Job).where(Job.status.in_(("running", "interrupted"))).order_by(Job.created_at).with_for_update()).scalars().all()
            for j in rows:
                if j.status == "running":
                    j.status = "interrupted"
                    j.error = "interrupted by restart"
                    audit.append(s, j.case_id, "system", "job.interrupted", {"job_id": j.id})
                j.status = "queued"
                j.plan = [{"name": "ingest", "status": "done", "reason": ""}, {"name": "retry", "status": "pending", "reason": f"re-queued after interruption (attempt {j.attempts + 1})"}]
                j.error = None
                audit.append(s, j.case_id, "system", "job.requeued", {"job_id": j.id, "attempt": j.attempts + 1})
                ids.append(j.id)
        return ids

    # --------------------------------------------------------------- approvals
    @staticmethod
    def _appr_dict(a: Approval) -> dict:
        return {"id": a.id, "rev": a.rev, "decision": a.decision, "reviewer": a.reviewer, "authority_role": a.authority_role,
                "note": a.note, "rupees": money_str(a.rupees), "hash": a.hash, "status": a.status, "void_reason": a.void_reason,
                "created_at": iso(a.created_at), "case_id": a.case_id}

    @staticmethod
    def _appr_fields(a: Approval, rev_hash: str) -> dict:
        return {"id": a.id, "case_id": a.case_id, "rev": a.rev, "rev_hash": rev_hash, "decision": a.decision, "reviewer": a.reviewer,
                "authority_role": a.authority_role, "note": a.note, "rupees": money_str(a.rupees), "created_at": iso(a.created_at)}

    def approvals(self, case_id: str) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(Approval).where(Approval.case_id == case_id).order_by(Approval.created_at)).scalars().all()
            return [self._appr_dict(a) for a in rows]

    def approval(self, approval_id: str) -> dict:
        with db.session() as s:
            a = s.get(Approval, approval_id)
            if not a:
                raise NotFound(f"approval {approval_id} not found")
            return self._appr_dict(a)

    def current_approval(self, case_id: str) -> Optional[dict]:
        with db.session() as s:
            c = self._case_row(s, case_id)
            a = s.execute(select(Approval).where(Approval.case_id == case_id, Approval.rev == c.current_rev, Approval.status == "active")
                          .order_by(Approval.created_at.desc()).limit(1)).scalar_one_or_none()
            return self._appr_dict(a) if a else None

    def approve(self, case_id: str, decision: str, reviewer: str, note: str = "") -> dict:
        reviewer = (reviewer or "").strip()
        if not reviewer or reviewer.lower() in {"system", "ai", "model", "auto", "claude", "gemini", "bot", "verity"}:
            raise Conflict("a named human reviewer is required; the system never approves", code="reviewer_required")
        if decision not in ("approve", "return", "escalate"):
            raise Conflict("decision must be approve, return or escalate", code="bad_decision")
        with db.session() as s, s.begin():
            c = s.execute(select(Case).where(Case.id == case_id).with_for_update()).scalar_one_or_none()
            if not c:
                raise NotFound(f"case {case_id} not found")
            if s.execute(select(func.count()).select_from(Job).where(Job.case_id == case_id, Job.status.in_(("queued", "running", "interrupted")))).scalar():
                raise Conflict("analysis is still running for this case; wait for it to finish before deciding", code="job_running")
            if not c.current_rev:
                raise Conflict("no analysed revision exists yet", code="no_revision")
            rev_row = s.execute(select(Revision).where(Revision.case_id == case_id, Revision.rev == c.current_rev)).scalar_one()
            calc = rev_row.state.get("calc") or {}
            amount = dec(calc.get("proposed_settlement"))
            role = config.DELEGATION_TOP if decision == "escalate" else role_for(amount)
            for prev in s.execute(select(Approval).where(Approval.case_id == case_id, Approval.status == "active", Approval.rev == c.current_rev)).scalars():
                prev.status = "void"
                prev.void_reason = "Superseded by a later decision on the same revision"
            a = Approval(id=_id("A-", 4).upper(), case_id=case_id, rev=c.current_rev, decision=decision, reviewer=reviewer[:120],
                         authority_role=role, note=(note or "")[:2000], rupees=amount, hash="", status="active", created_at=utcnow())
            a.hash = audit.approval_hash(self._appr_fields(a, rev_row.hash))
            s.add(a)
            s.flush()
            audit.append(s, case_id, f"human:{a.reviewer}", f"approval.{decision}", {"approval_id": a.id, "rev": a.rev, "rev_hash": rev_row.hash,
                                                                                     "approval_hash": a.hash, "authority_role": role, "rupees": money_str(amount)})
            c.updated_at = utcnow()
            return self._appr_dict(a)

    def verify_approval(self, approval_id: str) -> dict:
        with db.session() as s:
            a = s.get(Approval, approval_id)
            if not a:
                raise NotFound(f"approval {approval_id} not found")
            rev = s.execute(select(Revision).where(Revision.case_id == a.case_id, Revision.rev == a.rev)).scalar_one_or_none()
            if not rev:
                return {"valid": False, "recomputed_hash": "", "rev": a.rev, "reason": "revision missing", "status": a.status}
            rev_ok = audit.revision_hash(rev.state, rev.prev_hash) == rev.hash
            recomputed = audit.approval_hash(self._appr_fields(a, rev.hash))
            ok = recomputed == a.hash and rev_ok
            return {"valid": ok, "recomputed_hash": recomputed, "rev": a.rev, "status": a.status, "revision_hash_ok": rev_ok,
                    "reason": "" if ok else ("revision content does not match its hash" if not rev_ok else "approval fields do not match its hash")}

    def audit_verify(self, case_id: Optional[str]) -> dict:
        with db.session() as s:
            return audit.verify_chain(s, case_id)

    def audit_tail(self, case_id: str, limit: int = 50) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(AuditEvent).where(AuditEvent.chain == case_id).order_by(AuditEvent.seq.desc()).limit(limit)).scalars().all()
            return [{"seq": r.seq, "ts": r.ts, "actor": r.actor, "action": r.action, "payload": r.payload, "hash": r.hash} for r in reversed(rows)]

    # ---------------------------------------------------------- misc / history
    def claim_history(self, subject_key: str) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(ClaimHistory).where(func.upper(ClaimHistory.subject_key) == subject_key.strip().upper())).scalars().all()
            return [{"subject_key": r.subject_key, "claim_date": r.claim_date, "description": r.description, "amount": money_str(r.amount),
                     "synthetic": r.synthetic} for r in rows]

    def add_claim_history(self, subject_key: str, claim_date: Optional[str], description: str, amount: Optional[str]) -> None:
        with db.session() as s, s.begin():
            s.add(ClaimHistory(subject_key=subject_key, claim_date=claim_date, description=description, amount=dec(amount), synthetic=True))

    def save_eval_run(self, scenario_id: str, case_id: Optional[str], passed: bool, assertions: list, latency_ms: int) -> dict:
        with db.session() as s, s.begin():
            r = EvalRun(scenario_id=scenario_id, case_id=case_id, passed=passed, assertions=assertions, latency_ms=latency_ms)
            s.add(r)
            s.flush()
            return {"scenario_id": scenario_id, "passed": passed, "assertions": assertions, "latency_ms": latency_ms, "ran_at": iso(r.ran_at), "source": "stored"}

    def eval_results(self, latest_per_scenario: bool = True) -> list[dict]:
        with db.session() as s:
            rows = s.execute(select(EvalRun).order_by(EvalRun.ran_at.desc())).scalars().all()
            seen, out = set(), []
            for r in rows:
                if latest_per_scenario and r.scenario_id in seen:
                    continue
                seen.add(r.scenario_id)
                out.append({"scenario_id": r.scenario_id, "passed": r.passed, "assertions": r.assertions, "latency_ms": r.latency_ms,
                            "ran_at": iso(r.ran_at), "source": "stored"})
            return out

    def delete_demo_cases(self) -> int:
        """Delete only cases flagged demo (synthetic-demo). Returns the number deleted."""
        with db.session() as s, s.begin():
            ids = list(s.execute(select(Case.id).where(Case.demo.is_(True))).scalars())
            for cid in ids:
                s.execute(delete(Case).where(Case.id == cid))  # ON DELETE CASCADE removes children
                audit.append(s, None, "system", "demo.case_deleted", {"case_id": cid})
        import shutil
        for cid in ids:
            try:
                shutil.rmtree(storage.resolve_inside(cid), ignore_errors=True)
            except storage.UploadError:
                pass
        return len(ids)


def _jsonable(v: Any) -> Any:
    import json
    try:
        return json.loads(json.dumps(v, default=str))
    except Exception:
        return {"repr": repr(v)[:500]}


_repo: Optional[SqlRepo] = None


def get_repo() -> SqlRepo:
    global _repo
    if _repo is None:
        _repo = SqlRepo()
    return _repo
