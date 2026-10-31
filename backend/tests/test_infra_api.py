from __future__ import annotations

from fastapi.testclient import TestClient

from test_infra_common import add_text_evidence, ensure_db, install_stub, new_case  # noqa: E402

from app import jobs  # noqa: E402
from app.api_lab import evaluate  # noqa: E402
from app.main import app  # noqa: E402


def test_pdf_draft_then_approved_and_voided():
    repo = ensure_db()
    install_stub()
    c = new_case(repo, "pdf case")
    add_text_evidence(c, "statement.txt", "x")
    jobs.drain()
    cl = TestClient(app)
    r = cl.get(f"/api/cases/{c}/report.pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    draft_size = len(r.content)
    ap = cl.post(f"/api/cases/{c}/approve", json={"decision": "approve", "reviewer": "Asha Rao", "note": "ok"})
    assert ap.status_code == 200 and ap.json()["authority_role"] == "adjuster"
    approved = cl.get(f"/api/cases/{c}/report.pdf")
    assert approved.status_code == 200 and approved.content != r.content
    assert cl.get(f"/api/approvals/{ap.json()['id']}/verify").json()["valid"] is True
    detail = cl.get(f"/api/cases/{c}").json()
    assert detail["approval_current"]["id"] == ap.json()["id"] and detail["case"]["status"] == "reviewed"
    add_text_evidence(c, "twist.txt", "new")
    # approving while the job is queued is refused with 409
    assert cl.post(f"/api/cases/{c}/approve", json={"decision": "approve", "reviewer": "Asha Rao"}).status_code == 409
    jobs.drain()
    detail = cl.get(f"/api/cases/{c}").json()
    assert detail["approval_current"] is None and detail["approvals"][0]["status"] == "void"
    assert cl.get(f"/api/cases/{c}/report.pdf?rev=1").status_code == 200  # old revision still reproducible


def test_health_and_demo_endpoints():
    ensure_db()
    cl = TestClient(app)
    h = cl.get("/api/health").json()
    assert h["ok"] is True and h["db"].startswith("postgresql 16")
    assert "configured" in h["ai"]
    assert cl.get("/api/demo/fixtures").status_code == 200
    assert cl.post("/api/demo/reset").status_code == 200


def test_demo_reset_only_deletes_flagged_cases():
    repo = ensure_db()
    keep = repo.create_case("real-ish case")["id"]
    gone = repo.create_case("demo case", demo=True)["id"]
    cl = TestClient(app)
    assert cl.post("/api/demo/reset").json()["deleted"] >= 1
    assert repo.case_exists(keep) and not repo.case_exists(gone)


def test_lab_evaluator_vocabulary():
    repo = ensure_db()
    install_stub()
    c = new_case(repo)
    add_text_evidence(c, "a.txt", "one")
    jobs.drain()
    rows = evaluate(c, {"calc.proposed_settlement": "40000.00", "requests.min_open": 1, "revision.count": 1, "findings.types_include": ["observation"],
                        "language.forbidden_absent": True, "evidence.status": {"a.txt": "extracted"}, "zones.mismatch": False,
                        "unresolved.contains_term": "nothing-here", "not.a_key": 1}, {})
    by = {r["text"]: r for r in rows}
    assert sum(r["passed"] for r in rows) == 7
    failing = [r for r in rows if not r["passed"]]
    assert {r["detail"] for r in failing} >= {"unknown check key (not in the lab vocabulary)"}
