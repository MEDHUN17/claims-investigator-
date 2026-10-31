"""Persisted job queue with ONE worker thread. Pipeline hooks are resolved lazily and are injectable for tests."""
from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any, Callable, Optional

from .repo import StaleRun, get_repo

log = logging.getLogger("verity.jobs")

_hooks: dict[str, Any] = {"run_revision": None, "extract_evidence": None, "providers": None}


def set_pipeline(run_revision: Optional[Callable] = None, extract_evidence: Optional[Callable] = None, providers: Any = None) -> None:
    """Inject pipeline hooks (tests). Passing nothing for a hook restores the lazy default for it."""
    _hooks["run_revision"] = run_revision
    _hooks["extract_evidence"] = extract_evidence
    _hooks["providers"] = providers


def _run_revision_fn() -> Callable:
    if _hooks["run_revision"]:
        return _hooks["run_revision"]
    from . import pipeline  # imported at call time: INTEL writes it concurrently

    return pipeline.run_revision


def _extract_fn() -> Callable:
    if _hooks["extract_evidence"]:
        return _hooks["extract_evidence"]
    from . import extract

    return extract.extract_evidence


def _providers() -> Any:
    p = _hooks["providers"]
    if p is not None:
        return p() if callable(p) and not hasattr(p, "generate_json") else p
    from . import providers as prov

    chain = prov.ProviderChain.from_env()
    _hooks["providers"] = chain  # one chain per process so the circuit breaker / cache persist
    return chain


def _is_stale(e: BaseException) -> bool:
    return isinstance(e, StaleRun) or type(e).__name__ == "StaleRun"


def _make_emit(repo, job_id: str) -> Callable:
    """emit(name, status='running', reason='') or emit({'name':..,'status':..,'reason':..}) updates the persisted plan."""
    def emit(*args, **kw):
        try:
            if args and isinstance(args[0], dict):
                d = args[0]
                name, status, reason = d.get("name", ""), d.get("status", "running"), d.get("reason", "")
            else:
                name = args[0] if args else kw.get("name", "")
                status = args[1] if len(args) > 1 else kw.get("status", "running")
                reason = args[2] if len(args) > 2 else kw.get("reason", "")
            if name:
                repo.update_plan_step(job_id, str(name), str(status), str(reason or ""))
        except Exception:  # progress reporting must never kill the job
            log.exception("emit failed")
    return emit


def process_job(job: dict, merged: list[dict]) -> None:
    repo = get_repo()
    job_id, case_id = job["id"], job["case_id"]
    all_jobs = [job] + merged
    final_status, final_error = "done", None
    t0 = time.time()
    try:
        evs = repo.evidence_list(case_id)
        retry_failed = job.get("kind") == "analyze" or any(j.get("kind") == "analyze" for j in merged)
        todo = [e for e in evs if e["status"] in ("stored", "processing") or (retry_failed and e["status"] == "failed")]
        plan = [{"name": "ingest", "status": "done", "reason": ""}]
        plan += [{"name": f"extract:{e['id']}", "status": "pending", "reason": e["filename"]} for e in todo]
        plan += [{"name": n, "status": "pending", "reason": ""} for n in ("analyze", "validate", "invalidate", "persist")]
        repo.set_job_plan(job_id, plan)
        providers = _providers()
        extract_fn = _extract_fn()
        for e in todo:
            step = f"extract:{e['id']}"
            repo.update_plan_step(job_id, step, "running")
            repo.set_evidence_status(e["id"], "processing")
            ts = time.time()
            try:
                extract_fn(repo, e["id"], providers)
                cur = repo.evidence(e["id"])
                if cur["status"] in ("processing", "stored"):
                    repo.set_evidence_status(e["id"], "extracted")
                repo.update_plan_step(job_id, step, "done")
                repo.log_event(case_id, "stage", step, {"evidence_id": e["id"]}, {}, "ok", int((time.time() - ts) * 1000))
            except Exception as ex:  # one bad file must not stop the case; the failure is stored and visible
                repo.set_evidence_status(e["id"], "failed", error=f"{type(ex).__name__}: {ex}"[:500])
                repo.update_plan_step(job_id, step, "failed", str(ex)[:200])
                repo.log_event(case_id, "stage", step, {"evidence_id": e["id"]}, {"error": str(ex)[:500]}, "failed", int((time.time() - ts) * 1000))
        trigger = None
        for j in reversed(all_jobs):
            if j.get("trigger_evidence_id"):
                trigger = j["trigger_evidence_id"]
                break
        base_rev = repo.current_rev(case_id)  # rev at the moment analysis starts; a commit by anyone else meanwhile makes this run stale
        rev = _run_revision_fn()(repo, case_id, base_rev, trigger, job_id, providers, _make_emit(repo, job_id))
        repo.log_event(case_id, "stage", "job", {"job_id": job_id, "base_rev": base_rev}, {"rev": rev}, "ok", int((time.time() - t0) * 1000))
    except BaseException as e:  # noqa: BLE001
        if _is_stale(e):
            cur = repo.current_rev(case_id)
            final_status = "failed"
            final_error = f"stale: the case moved to rev {cur} while this run was in progress; the newer revision was kept and this run's result was discarded"
            repo.log_event(case_id, "stage", "job", {"job_id": job_id}, {"error": final_error}, "stale", int((time.time() - t0) * 1000))
        else:
            final_status = "failed"
            final_error = f"{type(e).__name__}: {e}"[:1000]
            log.error("job %s failed: %s\n%s", job_id, final_error, traceback.format_exc())
            try:
                repo.log_event(case_id, "stage", "job", {"job_id": job_id}, {"error": final_error}, "failed", int((time.time() - t0) * 1000))
            except Exception:
                pass
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            repo.finish_job(job_id, final_status, final_error)
            raise
    for j in all_jobs:
        repo.finish_job(j["id"], final_status, final_error)


class Worker:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._wake = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="verity-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def notify(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        repo = get_repo()
        debounce_s = 2.5  # let a burst of uploads queue up so they coalesce into ONE revision (one planner call)
        while not self._stop.is_set():
            if self._wake.is_set():
                self._wake.clear()
                self._stop.wait(debounce_s)
            try:
                claimed = repo.claim_next_job()
            except Exception:
                log.exception("claim failed")
                claimed = None
            if not claimed:
                self._wake.wait(1.0)
                continue
            try:
                process_job(*claimed)
            except Exception:
                log.exception("worker crashed on job")


def run_once() -> bool:
    """Process a single queued job synchronously (used by tests and tooling). Returns True if a job ran."""
    claimed = get_repo().claim_next_job()
    if not claimed:
        return False
    process_job(*claimed)
    return True


def drain() -> int:
    n = 0
    while run_once():
        n += 1
    return n


worker = Worker()


def start_worker() -> None:
    """Recover interrupted work, then start the single worker thread."""
    recovered = get_repo().recover_jobs()
    if recovered:
        log.warning("re-queued %d interrupted job(s): %s", len(recovered), recovered)
    worker.start()


def wait_idle(case_id: str, timeout: float = 300.0) -> bool:
    """Block until the case has no queued/running job. Drives the queue itself when no worker thread is running."""
    repo = get_repo()
    end = time.time() + timeout
    while time.time() < end:
        if not repo.has_active_job(case_id):
            return True
        if worker._thread is None or not worker._thread.is_alive():
            if not run_once():
                time.sleep(0.2)
        else:
            worker.notify()
            time.sleep(0.3)
    return not repo.has_active_job(case_id)
