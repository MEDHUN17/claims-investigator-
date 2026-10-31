"""Shared helpers for INFRA tests: one throw-away bundled PostgreSQL per pytest process, stub pipeline (fakes live ONLY in tests)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ["VERITY_NO_WORKER"] = "1"
os.environ["VERITY_KEEP_DB"] = "1"
_TMP = Path(tempfile.mkdtemp(prefix="verity_test_"))
os.environ["DATABASE_URL"] = ""  # force the bundled server even if backend/.env sets one

from app import config  # noqa: E402

config.DATABASE_URL = ""
config.STORAGE = _TMP / "storage"
PGDATA = _TMP / "pgdata"

from app import db, jobs  # noqa: E402
from app.repo import get_repo  # noqa: E402

_ready = False


def ensure_db():
    global _ready
    if not db.is_ready():
        db.init_db(pgdata=PGDATA, dbname="verity_test")
    _ready = True
    return get_repo()


# ---------------- stub pipeline -----------------
class Stub:
    settlement = "40000.00"
    calls: list = []
    before_commit = None  # callable(repo, case_id) run just before the stub commits (to simulate a concurrent writer)


def stub_extract(repo, evidence_id, providers):
    ev = repo.evidence(evidence_id)
    repo.save_extraction(evidence_id, {"text": f"stub extraction of {ev['filename']}", "items": [{"amount": "100"}]}, "stub", False)
    repo.save_passages(evidence_id, [{"page": 1, "text": f"passage for {ev['filename']}"}])
    repo.set_evidence_status(evidence_id, "extracted")
    Stub.calls.append(("extract", evidence_id))
    return {}


def stub_run_revision(repo, case_id, base_rev, trigger, job_id, providers, emit=None):
    Stub.calls.append(("run", case_id, base_rev, trigger))
    if emit:
        emit("analyze", "running")
    evs = repo.evidence_list(case_id)
    prev = repo.get_state(case_id) or {"findings": []}
    findings = [{"id": f"F-{i + 1:02d}", "type": "observation", "title": f"saw {e['filename']}", "body": "b", "epistemic": "observed", "status": "active",
                 "justification": {"evidence_ids": [e["id"]], "entity_keys": []}} for i, e in enumerate(evs)]
    state = {"rev": 0, "evidence_ids": [e["id"] for e in evs], "findings": findings, "facts": [], "hypotheses": [], "matrix": [],
             "requests": [{"id": "R-01", "key": "k", "text": "need more", "status": "open"}], "calc": {"proposed_settlement": Stub.settlement, "unresolved": []},
             "unresolved": [], "summary": f"stub summary {len(prev['findings'])}->{len(findings)}", "zones": {}, "injection_flags": []}
    if Stub.before_commit:
        Stub.before_commit(repo, case_id)
    if emit:
        emit("analyze", "done")
    return repo.commit_revision(case_id, base_rev, state, {"cause": "", "added": [], "stale": [], "lines": []}, trigger, state["summary"])


def install_stub():
    Stub.calls = []
    Stub.settlement = "40000.00"
    Stub.before_commit = None
    jobs.set_pipeline(run_revision=stub_run_revision, extract_evidence=stub_extract, providers=object())


def new_case(repo, title="t"):
    return repo.create_case(title)["id"]


def add_text_evidence(case_id, name, text):
    from app.api_evidence import ingest_bytes

    return ingest_bytes(case_id, name, text.encode(), None)
