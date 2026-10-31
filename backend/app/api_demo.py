"""Demo fixtures: list, load through the REAL pipeline, reset (only cases flagged demo)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from . import config
from .api_evidence import DuplicateEvidence, ingest_bytes
from .repo import Conflict, NotFound, get_repo

router = APIRouter(prefix="/api")


def load_index() -> dict:
    p = config.FIXTURES_DIR / "index.json"
    if not p.exists():
        return {"sets": []}
    return json.loads(p.read_text(encoding="utf-8"))


def find_set(set_id: str) -> dict:
    for s in load_index().get("sets", []):
        if s.get("id") == set_id:
            return s
    raise NotFound(f"fixture set '{set_id}' not found")


def _safe_fixture_path(set_id: str, rel: str) -> Path:
    root = config.FIXTURES_DIR.resolve()
    for cand in (root / rel, root / set_id / rel):
        p = cand.resolve()
        if (p == root or root in p.parents) and p.is_file():
            return p
    raise NotFound(f"fixture file '{rel}' not found for set '{set_id}'")


def set_file_paths(fset: dict) -> list[tuple[Path, Optional[str]]]:
    out = []
    for f in fset.get("files", []):
        rel = f if isinstance(f, str) else f.get("path", "")
        kind = None if isinstance(f, str) else f.get("kind")
        out.append((_safe_fixture_path(fset["id"], rel), kind))
    return out


def upload_set(case_id: str, fset: dict) -> list[dict]:
    """Upload every file of a fixture set via the same ingest path as a user upload. Returns per-file results."""
    results = []
    for path, kind in set_file_paths(fset):
        try:
            ev, job = ingest_bytes(case_id, path.name, path.read_bytes(), kind)
            results.append({"file": path.name, "evidence_id": ev["id"], "job_id": (job or {}).get("id"), "status": "uploaded"})
        except DuplicateEvidence as d:
            results.append({"file": path.name, "evidence_id": d.existing["id"], "job_id": None, "status": "duplicate"})
    return results


class LoadBody(BaseModel):
    fixture_set: str
    apply_to_case: Optional[str] = None


@router.get("/demo/fixtures")
def demo_fixtures():
    idx = load_index()
    out = []
    for s in idx.get("sets", []):
        try:
            n = len(set_file_paths(s))
            ok = True
        except NotFound:
            n, ok = 0, False
        out.append({**s, "available": ok, "file_count": n})
    return {"sets": out, "available": bool(out)}


@router.post("/demo/load")
def demo_load(body: LoadBody):
    repo = get_repo()
    fset = find_set(body.fixture_set)
    if body.apply_to_case:
        cid = body.apply_to_case
        repo.case(cid)  # 404 if missing
        uploaded = upload_set(cid, fset)
        return {"case": repo.case_summary(cid), "uploaded": uploaded, "note": f"'{fset['id']}' applied to the existing case"}
    case = repo.create_case(f"Demo: {fset.get('title', fset['id'])}", synthetic=True, demo=True)
    note = ""
    base_id = fset.get("apply_on")
    uploaded = []
    if base_id:
        # a twist set only makes sense on top of its base: load the base now, drop the twist later with apply_to_case
        uploaded = upload_set(case["id"], find_set(base_id))
        note = (f"'{fset['id']}' is a twist that applies on '{base_id}': the base files were loaded; "
                f"drop the twist with POST /api/demo/load {{fixture_set: '{fset['id']}', apply_to_case: '{case['id']}'}}")
    else:
        uploaded = upload_set(case["id"], fset)
    return {"case": repo.case_summary(case["id"]), "uploaded": uploaded, "note": note,
            "next": {"fixture_set": fset["id"], "apply_to_case": case["id"]} if base_id else None}


@router.post("/demo/reset")
def demo_reset():
    return {"deleted": get_repo().delete_demo_cases()}
