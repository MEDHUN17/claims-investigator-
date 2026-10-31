"""Evidence intake and access routes."""
from __future__ import annotations

import copy
from typing import Any, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from . import config, jobs, storage
from .repo import Conflict, NotFound, get_repo

router = APIRouter(prefix="/api")


class DuplicateEvidence(Exception):
    def __init__(self, existing: dict):
        super().__init__("duplicate evidence")
        self.existing = existing


def ingest_bytes(case_id: str, filename: str, data: bytes, kind: Optional[str] = None, source_class: Optional[str] = None,
                 enqueue: bool = True) -> tuple[dict, Optional[dict]]:
    """Validate, store and register one file, then enqueue a job. Shared by the upload route, /demo and /lab (all use the REAL path)."""
    repo = get_repo()
    if not repo.case_exists(case_id):
        raise NotFound(f"case {case_id} not found")
    if len(data) == 0:
        raise storage.UploadError(422, "empty file")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise storage.UploadError(413, f"file exceeds the {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    sniffed = storage.sniff(data, filename)
    sha = storage.sha256_hex(data)
    existing = repo.find_by_sha(case_id, sha)
    if existing:
        raise DuplicateEvidence(existing)
    display = storage.safe_display_name(filename)
    k = storage.infer_kind(display, sniffed, data, kind)
    if source_class is not None and source_class not in ("third_party", "claimant", "system", "model", "human"):
        raise storage.UploadError(422, f"unknown source_class '{source_class}'")
    sc = source_class or storage.SOURCE_BY_KIND.get(k, "claimant")
    eid = repo.new_evidence_id()
    rel = storage.write_file(case_id, eid, sniffed.ext, data)
    status = "stored" if sniffed.supported else "unsupported"
    error = None if sniffed.supported else f"Unsupported file type: {sniffed.note}. Provide a transcript, stills or a text/PDF/image version."
    try:
        ev = repo.add_evidence(case_id, eid, display, sniffed.mime, len(data), sha, k, sc, status, error, rel,
                               meta={"sniffed_family": sniffed.family, "original_filename": display})
    except IntegrityError:
        try:
            storage.resolve_inside(rel).unlink(missing_ok=True)
        except Exception:
            pass
        existing = repo.find_by_sha(case_id, sha)
        if existing:
            raise DuplicateEvidence(existing)
        raise
    job = None
    if enqueue:
        job, _ = repo.enqueue_job(case_id, "process", eid, key=eid)
        jobs.worker.notify()
    return ev, job


@router.post("/cases/{case_id}/evidence")
async def upload_evidence(case_id: str, file: UploadFile = File(...), kind: Optional[str] = Form(None), source_class: Optional[str] = Form(None)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        ev, job = ingest_bytes(case_id, file.filename or "upload", data, kind or None, source_class or None)
    except DuplicateEvidence as d:
        return JSONResponse({"detail": "This file (same SHA-256) is already in the case.", "existing_id": d.existing["id"],
                             "existing": d.existing}, status_code=409)
    repo = get_repo()
    return {"evidence": repo.evidence_out(ev["id"]), "job": job}


@router.get("/evidence/{evidence_id}/file")
def evidence_file(evidence_id: str):
    repo = get_repo()
    ev = repo.evidence(evidence_id)
    path = repo.evidence_path(evidence_id)
    if not path.exists():
        raise NotFound("stored file is missing")
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"}
    inline = ev["status"] != "unsupported"
    disp = "inline" if inline else "attachment"
    safe = ev["filename"].encode("ascii", "ignore").decode() or "evidence"
    headers["Content-Disposition"] = f'{disp}; filename="{safe}"'
    return FileResponse(path, media_type=ev["mime"] if inline else "application/octet-stream", headers=headers)


@router.get("/evidence/{evidence_id}/passages")
def evidence_passages(evidence_id: str):
    repo = get_repo()
    repo.evidence(evidence_id)
    return repo.passages(evidence_id)


@router.get("/evidence/{evidence_id}")
def evidence_get(evidence_id: str):
    return get_repo().evidence_out(evidence_id)


class CorrectionBody(BaseModel):
    path: str
    value: Any


def set_path(obj: Any, path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p != ""]
    if not parts:
        raise Conflict("empty path", code="bad_path")
    cur = obj
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        if isinstance(cur, list):
            try:
                idx = int(p)
            except ValueError:
                raise Conflict(f"path segment '{p}' must be a list index", code="bad_path")
            if not (0 <= idx < len(cur)):
                raise Conflict(f"index {idx} out of range at '{'.'.join(parts[:i + 1])}'", code="bad_path")
            if last:
                cur[idx] = value
            else:
                cur = cur[idx]
        elif isinstance(cur, dict):
            if last:
                cur[p] = value
            else:
                if p not in cur:
                    raise Conflict(f"path '{'.'.join(parts[:i + 1])}' does not exist", code="bad_path")
                cur = cur[p]
        else:
            raise Conflict(f"cannot descend into a scalar at '{'.'.join(parts[:i])}'", code="bad_path")


@router.patch("/evidence/{evidence_id}/extraction")
def correct_extraction(evidence_id: str, body: CorrectionBody):
    repo = get_repo()
    ev = repo.evidence(evidence_id)
    latest = repo.latest_extraction(evidence_id)
    if not latest:
        raise Conflict("this evidence has no extraction to correct yet", code="no_extraction")
    payload = copy.deepcopy(latest["payload"])
    old = payload
    set_path(payload, body.path, body.value)
    ver = repo.save_extraction(evidence_id, payload, "human", False, human=True)
    repo.log_event(ev["case_id"], "stage", "human_correction", {"evidence_id": evidence_id, "path": body.path}, {"version": ver}, "ok", 0)
    job, _ = repo.enqueue_job(ev["case_id"], "process", evidence_id, key=f"correction-v{ver}")
    jobs.worker.notify()
    return {"extraction_version": ver, "job": job, "evidence": repo.evidence_out(evidence_id)}
