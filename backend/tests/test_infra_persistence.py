from __future__ import annotations

import psycopg
import pytest

from test_infra_common import PGDATA, Stub, add_text_evidence, ensure_db, install_stub, new_case  # noqa: E402

from app import db, jobs  # noqa: E402
from app.repo import get_repo  # noqa: E402


def test_server_restart_keeps_data_and_recovers_interrupted_job():
    repo = ensure_db()
    install_stub()
    c = new_case(repo, "restart case")
    ev, job = add_text_evidence(c, "statement.txt", "persist me")
    jobs.drain()
    assert repo.current_rev(c) == 1
    ap = repo.approve(c, "approve", "Asha Rao")
    ev2, job2 = add_text_evidence(c, "second.txt", "in flight")
    claimed = repo.claim_next_job()  # worker had picked it up ...
    assert claimed and claimed[0]["id"] == job2["id"] and repo.job(job2["id"])["status"] == "running"
    old_uri = db._server.get_uri()

    db.shutdown(stop_server=True)  # ... and the process/server dies
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(old_uri, connect_timeout=3)

    db.init_db(pgdata=PGDATA, dbname="verity_test")  # fresh start on the same data dir
    repo = get_repo()
    assert repo.evidence(ev["id"])["filename"] == "statement.txt"
    assert repo.current_rev(c) == 1 and repo.get_state(c)["evidence_ids"] == [ev["id"]]
    assert repo.approval(ap["id"])["status"] == "active"
    assert repo.job(job2["id"])["status"] == "running"  # stuck exactly as the crash left it

    install_stub()
    assert repo.recover_jobs() == [job2["id"]]
    assert repo.recover_jobs() == []  # a second restart before it ran changes nothing (already queued once)
    assert repo.job(job2["id"])["status"] == "queued"
    jobs.drain()
    assert repo.job(job2["id"])["status"] == "done"
    assert len(repo.jobs_for_case(c)) == 2  # no duplicate job rows
    assert repo.current_rev(c) == 2  # exactly one new revision for the interrupted run
    assert len(repo.evidence_list(c)) == 2
    assert sum(1 for x in Stub.calls if x == ("extract", ev2["id"])) == 1
    assert repo.approval(ap["id"])["status"] == "void"
    assert repo.audit_verify(c)["valid"] is True
    actions = [a["action"] for a in repo.audit_tail(c, 100)]
    assert "job.interrupted" in actions and "job.requeued" in actions
