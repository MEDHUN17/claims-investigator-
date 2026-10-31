from __future__ import annotations

import pytest
from sqlalchemy import text

from test_infra_common import Stub, add_text_evidence, ensure_db, install_stub, new_case  # noqa: E402

from app import audit, db, jobs, storage  # noqa: E402
from app.repo import Conflict, StaleRun  # noqa: E402


@pytest.fixture(autouse=True)
def _env():
    ensure_db()
    install_stub()
    yield
    jobs.set_pipeline()


def test_cross_case_isolation():
    repo = ensure_db()
    a, b = new_case(repo, "A"), new_case(repo, "B")
    ea, _ = add_text_evidence(a, "statement.txt", "same bytes")
    eb, _ = add_text_evidence(b, "statement.txt", "same bytes")  # same sha in another case is NOT a duplicate
    assert ea["id"] != eb["id"] and ea["sha256"] == eb["sha256"]
    jobs.drain()
    assert [e["id"] for e in repo.evidence_list(a)] == [ea["id"]]
    assert [e["id"] for e in repo.evidence_list(b)] == [eb["id"]]
    assert repo.current_rev(a) == 1 and repo.current_rev(b) == 1
    sa, sb = repo.get_state(a), repo.get_state(b)
    assert sa["evidence_ids"] == [ea["id"]] and sb["evidence_ids"] == [eb["id"]]
    # a revision in A leaves B untouched; commit with B's rev number against A is stale
    add_text_evidence(a, "more.txt", "extra")
    jobs.drain()
    assert repo.current_rev(a) == 2 and repo.current_rev(b) == 1
    assert all(j["case_id"] == b for j in repo.jobs_for_case(b))
    assert repo.get_state(b, 2) is None  # revision numbers are per case


def test_stale_run_rejected_and_newer_rev_kept():
    repo = ensure_db()
    c = new_case(repo)
    add_text_evidence(c, "a.txt", "one")
    jobs.drain()
    assert repo.current_rev(c) == 1
    with pytest.raises(StaleRun):
        repo.commit_revision(c, 0, {"findings": []}, {}, None, "late")
    assert repo.current_rev(c) == 1

    # concurrent writer commits while the worker's run is in flight -> that run is rejected, the newer rev survives
    def concurrent(r, case_id):
        r.commit_revision(case_id, r.current_rev(case_id), {"findings": [], "summary": "concurrent"}, {}, None, "concurrent writer")

    Stub.before_commit = concurrent
    _, job = add_text_evidence(c, "b.txt", "two")
    jobs.drain()
    j = repo.job(job["id"])
    assert j["status"] == "failed" and j["error"].startswith("stale")
    assert repo.current_rev(c) == 2
    assert repo.get_state(c)["summary"] == "concurrent"


def test_approval_bound_to_rev_voided_by_new_evidence_and_delegation():
    repo = ensure_db()
    c = new_case(repo)
    add_text_evidence(c, "a.txt", "one")
    # refused while a job is queued
    with pytest.raises(Conflict):
        repo.approve(c, "approve", "Asha Rao")
    jobs.drain()
    with pytest.raises(Conflict):
        repo.approve(c, "approve", "system")
    ap = repo.approve(c, "approve", "Asha Rao", "looks fine")
    assert ap["rev"] == 1 and ap["authority_role"] == "adjuster" and ap["rupees"] == "40000.00" and ap["status"] == "active"
    assert repo.current_approval(c)["id"] == ap["id"]
    assert repo.verify_approval(ap["id"])["valid"] is True

    ev, _ = add_text_evidence(c, "twist.txt", "new evidence")
    jobs.drain()
    after = repo.approval(ap["id"])
    assert after["status"] == "void" and "revision 2" in after["void_reason"] and ev["id"] in after["void_reason"] + repo.revisions(c)[-1]["trigger"]
    assert repo.current_approval(c) is None
    assert repo.revisions(c)[-1]["delta"]["approval_voided"] is True
    assert repo.verify_approval(ap["id"])["valid"] is True  # hash of the voided record still verifies; status says void

    Stub.settlement = "150000.00"
    repo.enqueue_job(c, "analyze", None, key="x")
    jobs.drain()
    assert repo.approve(c, "approve", "Ravi")["authority_role"] == "senior_adjuster"
    Stub.settlement = "250000.00"
    repo.enqueue_job(c, "analyze", None, key="y")
    jobs.drain()
    assert repo.approve(c, "approve", "Ravi")["authority_role"] == "committee"

    # tampering with an approval row is detected by verify
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE approvals SET note = 'edited' WHERE id = :i"), {"i": ap["id"]})
    v = repo.verify_approval(ap["id"])
    assert v["valid"] is False and v["recomputed_hash"] != ap["hash"]


def test_duplicate_upload_is_409_via_http():
    from fastapi.testclient import TestClient

    from app.main import app

    repo = ensure_db()
    c = new_case(repo)
    cl = TestClient(app)
    r1 = cl.post(f"/api/cases/{c}/evidence", files={"file": ("statement.txt", b"hello claim", "text/plain")})
    assert r1.status_code == 200, r1.text
    r2 = cl.post(f"/api/cases/{c}/evidence", files={"file": ("renamed.txt", b"hello claim", "text/plain")})
    assert r2.status_code == 409 and r2.json()["existing_id"] == r1.json()["evidence"]["id"]
    assert len(repo.evidence_list(c)) == 1
    assert len([j for j in repo.jobs_for_case(c)]) == 1


def test_upload_limits_and_unsupported_http():
    from fastapi.testclient import TestClient

    from app.main import app

    repo = ensure_db()
    c = new_case(repo)
    cl = TestClient(app)
    big = b"a" * (25 * 1024 * 1024 + 10)
    assert cl.post(f"/api/cases/{c}/evidence", files={"file": ("big.txt", big, "text/plain")}).status_code == 413
    r = cl.post(f"/api/cases/{c}/evidence", files={"file": ("../../evil.mp3", b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 50, "audio/mpeg")})
    assert r.status_code == 200
    ev = r.json()["evidence"]
    assert ev["status"] == "unsupported" and ev["filename"] == "evil.mp3" and ev["kind"] == "other"
    assert ".." not in str(repo.evidence_path(ev["id"]).relative_to(storage.storage_root()))
    f = cl.get(f"/api/evidence/{ev['id']}/file")
    assert f.status_code == 200 and "attachment" in f.headers["content-disposition"]


def test_storage_sniffing_and_traversal_guard():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    assert storage.sniff(png, "x.txt").family == "image"  # magic bytes win over the extension
    assert storage.sniff(b"%PDF-1.7\n...", "x.bin").ext == "pdf"
    assert storage.sniff(b"PK\x03\x04....", "claim.docx").supported is False
    assert storage.sniff(b"\x00\x01\x02binary", "x.txt").supported is False
    assert storage.sniff(b"a,b\n1,2\n", "t.csv").ext == "csv"
    with pytest.raises(storage.UploadError):
        storage.resolve_inside("../outside.txt")
    with pytest.raises(storage.UploadError):
        storage.write_file("../x", "E-1", "txt", b"x")
    assert storage.infer_kind("garage_estimate.pdf", storage.sniff(b"%PDF-1", "a.pdf"), b"%PDF-1") == "estimate"
    assert storage.infer_kind("photo.jpg", storage.sniff(b"\xff\xd8\xff\xe0" + b"0" * 10, "p.jpg"), b"") == "photo"
    assert storage.infer_kind("x.txt", storage.sniff(b"hi", "x.txt"), b"hi", override="policy") == "policy"


def test_audit_hash_chain_tamper_detection():
    repo = ensure_db()
    c = new_case(repo)
    add_text_evidence(c, "a.txt", "one")
    jobs.drain()
    assert repo.audit_verify(c)["valid"] is True and repo.audit_verify(c)["count"] >= 4
    assert repo.verify_revisions(c)["valid"] is True
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE audit_events SET payload = jsonb_set(payload, '{filename}', '\"tampered.txt\"') "
                          "WHERE chain = :c AND action = 'evidence.added'"), {"c": c})
    res = repo.audit_verify(c)
    assert res["valid"] is False and res["broken_at_seq"] is not None
    # revision tamper
    with db.engine().begin() as conn:
        conn.execute(text("UPDATE revisions SET state = jsonb_set(state, '{summary}', '\"edited\"') WHERE case_id = :c AND rev = 1"), {"c": c})
    assert repo.verify_revisions(c)["valid"] is False


def test_idempotent_retry_and_coalescing():
    repo = ensure_db()
    c = new_case(repo)
    for n in ("a.txt", "b.txt", "c.txt"):
        add_text_evidence(c, n, n * 5)
    j1, created1 = repo.enqueue_job(c, "analyze", None, key="rev0")
    j2, created2 = repo.enqueue_job(c, "analyze", None, key="rev0")
    assert created1 and not created2 and j1["id"] == j2["id"]
    assert len(repo.jobs_for_case(c)) == 4
    jobs.drain()
    # one coalesced analysis = ONE revision, every job finished
    assert repo.current_rev(c) == 1
    assert [j["status"] for j in repo.jobs_for_case(c)] == ["done"] * 4
    assert sum(1 for x in Stub.calls if x[0] == "extract") == 3  # each file extracted once
    # re-running analyze after completion is allowed and makes a new revision, not a duplicate of the old job
    j3, created3 = repo.enqueue_job(c, "analyze", None, key="rev1")
    assert created3 and j3["id"] != j1["id"]
    jobs.drain()
    assert repo.current_rev(c) == 2


def test_request_status_and_challenge_create_revisions_and_void_approval():
    from fastapi.testclient import TestClient

    from app.main import app

    repo = ensure_db()
    c = new_case(repo)
    add_text_evidence(c, "a.txt", "one")
    jobs.drain()
    ap = repo.approve(c, "approve", "Asha Rao")
    cl = TestClient(app)
    r = cl.post(f"/api/cases/{c}/requests/R-01/status", json={"status": "received"})
    assert r.status_code == 200 and r.json()["rev"] == 2
    assert repo.get_state(c)["requests"][0]["status"] == "received"
    assert repo.approval(ap["id"])["status"] == "void"
    r = cl.post(f"/api/cases/{c}/findings/F-01/challenge", json={"note": "check the photo"})
    assert r.status_code == 200
    st = repo.get_state(c, 3)
    assert st["findings"][0]["status"] == "stale" and "check the photo" in st["findings"][0]["stale_reason"]
    assert repo.job(r.json()["job"]["id"])["status"] == "queued"
    assert cl.post(f"/api/cases/{c}/requests/R-99/status", json={"status": "dropped"}).status_code in (404, 409)
