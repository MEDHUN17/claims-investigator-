"""Test-only fakes: FakeProvider (scripted model) and FakeRepo (in-memory Repo). NEVER imported by app code."""
from __future__ import annotations

import copy
import json
import re
import uuid
from pathlib import Path

from app.providers import ProviderUnavailable


class StaleRun(Exception):
    pass


class FakeRepo:
    def __init__(self, root: Path):
        self.root = root
        self.ev_rows: dict[str, dict] = {}
        self.paths: dict[str, Path] = {}
        self.extractions: dict[str, list[dict]] = {}
        self._passages: dict[str, list[dict]] = {}
        self.revisions: dict[int, dict] = {}
        self.deltas: dict[int, dict] = {}
        self.events: list[tuple] = []
        self.plans: dict = {}
        self.cur = 0
        self.n = 0

    # --- test helpers ---
    def add_file(self, name: str, data: bytes | str, kind: str | None = None, mime: str = "") -> str:
        self.n += 1
        eid = f"E-{self.n:02d}"
        p = self.root / name
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        self.paths[eid] = p
        self.ev_rows[eid] = {"id": eid, "kind": kind or "other", "filename": name, "mime": mime, "sha256": "x" * 64,
                              "source_class": "claimant", "uploaded_at": f"2026-10-31T10:{self.n:02d}:00", "status": "stored"}
        return eid

    # --- Repo protocol ---
    def case(self, case_id): return {"id": case_id}
    def evidence_list(self, case_id): return [dict(v) for v in self.ev_rows.values()]
    def evidence_path(self, evidence_id): return self.paths[evidence_id]

    def latest_extraction(self, evidence_id):
        xs = self.extractions.get(evidence_id)
        return copy.deepcopy(xs[-1]) if xs else None

    def save_extraction(self, evidence_id, payload, model, cached, human=False):
        xs = self.extractions.setdefault(evidence_id, [])
        xs.append({"version": len(xs) + 1, "payload": copy.deepcopy(payload), "model": model, "human_corrected": human})
        return len(xs)

    def save_passages(self, evidence_id, passages): self._passages[evidence_id] = copy.deepcopy(passages)
    def passages(self, evidence_id): return copy.deepcopy(self._passages.get(evidence_id, []))

    def set_evidence_status(self, evidence_id, status, error=None, meta=None, pages=None, kind=None):
        e = self.ev_rows[evidence_id]
        e["status"], e["error"] = status, error
        if kind:
            e["kind"] = kind

    def current_rev(self, case_id): return self.cur
    def get_state(self, case_id, rev=None):
        r = rev if rev is not None else self.cur
        return copy.deepcopy(self.revisions.get(r))

    def commit_revision(self, case_id, base_rev, state, delta, trigger_evidence_id, summary):
        if base_rev != self.cur:
            raise StaleRun(f"case at rev {self.cur}, run based on {base_rev}")
        self.cur += 1
        self.revisions[self.cur] = copy.deepcopy(state)
        self.deltas[self.cur] = copy.deepcopy(delta)
        return self.cur

    def log_event(self, case_id, kind, name, args, result, status, duration_ms):
        self.events.append((kind, name, args, result, status))

    def set_job_plan(self, job_id, plan): self.plans[job_id] = copy.deepcopy(plan)


def _ctx_from_parts(parts) -> dict:
    for p in parts:
        t = p.get("text", "")
        m = re.search(r"UNTRUSTED_DOCUMENT name='case_context'\n(.*)\nUNTRUSTED_DOCUMENT>>>", t, re.S)
        if m:
            return json.loads(m.group(1))
    return {}


class FakeProvider:
    """Scripted stand-in for ProviderChain. `readers` maps reader task -> dict (or callable(parts)->dict);
    `planner` is a callable(ctx, revision:bool, parts)->dict."""

    def __init__(self, readers=None, planner=None, down: bool = False):
        self.readers, self.planner, self.down = readers or {}, planner, down
        self.calls: list[dict] = []

    def health(self):
        return {"configured": True, "providers": [], "message": "fake"}

    def generate_json(self, system, parts, schema=None, temperature=0, max_tokens=4096, cache_key=None, validate=None, timeout=None, role="planner"):
        text = "\n".join(p.get("text", "") for p in parts)
        self.calls.append({"system": system, "text": text, "parts": parts, "role": role})
        if self.down:
            raise ProviderUnavailable("fake provider down")
        usage = {"provider": "fake", "model": "fake-1", "role": role, "tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "cached": False}
        if "PLANNER" in system:
            ctx = _ctx_from_parts(parts)
            obj = self.planner(ctx, "THIS IS A REVISION" in system, parts)
        else:
            task = ("photo" if "vehicle photo" in text else "narrative" if "claimant/witness statement" in text else
                    "policy" if "policy terms ONLY" in text else "estimate" if "repair estimate" in text else "other")
            r = self.readers[task]
            obj = r(parts) if callable(r) else r
        if validate:
            obj = validate(obj)
        return obj, usage
