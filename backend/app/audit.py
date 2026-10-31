"""Tamper-evident SHA-256 hash chain for audit events, plus revision / approval hashing helpers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AuditEvent

GENESIS = "0" * 64


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def revision_hash(state: dict, prev_hash: str) -> str:
    """sha256 over canonical JSON of the state plus the previous revision's hash."""
    return sha256_text(canonical(state) + prev_hash)


def approval_hash(fields: dict) -> str:
    return sha256_text(canonical(fields))


def _entry_hash(prev_hash: str, chain: str, seq: int, ts: str, actor: str, action: str, payload: dict) -> str:
    return sha256_text(prev_hash + canonical({"chain": chain, "seq": seq, "ts": ts, "actor": actor, "action": action, "payload": payload}))


def append(session: Session, case_id: Optional[str], actor: str, action: str, payload: Optional[dict] = None) -> str:
    """Append an audit event inside the caller's transaction. Returns the new hash."""
    chain = case_id or "global"
    payload = json.loads(canonical(payload or {}))  # JSON-normalise so the stored form hashes identically
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:c))"), {"c": "audit:" + chain})
    last = session.execute(select(AuditEvent).where(AuditEvent.chain == chain).order_by(AuditEvent.seq.desc()).limit(1)).scalar_one_or_none()
    seq = (last.seq + 1) if last else 1
    prev = last.hash if last else GENESIS
    ts = iso(datetime.now(timezone.utc))
    h = _entry_hash(prev, chain, seq, ts, actor, action, payload)
    session.add(AuditEvent(chain=chain, case_id=case_id, seq=seq, ts=ts, actor=actor, action=action, payload=payload, prev_hash=prev, hash=h))
    session.flush()
    return h


def verify_chain(session: Session, case_id: Optional[str]) -> dict:
    """Recompute the whole chain. Returns {valid, count, broken_at_seq, reason}."""
    chain = case_id or "global"
    rows = session.execute(select(AuditEvent).where(AuditEvent.chain == chain).order_by(AuditEvent.seq)).scalars().all()
    prev = GENESIS
    expect = 1
    for r in rows:
        if r.seq != expect:
            return {"valid": False, "count": len(rows), "broken_at_seq": expect, "reason": "missing or reordered entry"}
        if r.prev_hash != prev:
            return {"valid": False, "count": len(rows), "broken_at_seq": r.seq, "reason": "prev_hash mismatch"}
        h = _entry_hash(prev, chain, r.seq, r.ts, r.actor, r.action, r.payload)
        if h != r.hash:
            return {"valid": False, "count": len(rows), "broken_at_seq": r.seq, "reason": "entry content does not match its hash"}
        prev = r.hash
        expect += 1
    return {"valid": True, "count": len(rows), "broken_at_seq": None, "reason": ""}
