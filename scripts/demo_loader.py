"""Load a fixture set into a running Verity API (default http://127.0.0.1:8000/api).

Examples
  python scripts/demo_loader.py --list
  python scripts/demo_loader.py consistent
  python scripts/demo_loader.py twist_secondary_impact            # loads rear_vs_front first (apply_on), waits, then the twist
  python scripts/demo_loader.py twist_secondary_impact --case-id <id>   # apply on an existing case
  python scripts/demo_loader.py bad_estimate --no-wait --title "Bad estimate demo"

Standard library only. Waits for each upload's job to finish so a twist always lands on a settled case.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DEFAULT_BASE = "http://127.0.0.1:8000/api"
MIME_FALLBACK = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf", ".txt": "text/plain"}


def load_index() -> dict:
    return json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))


def find_set(index: dict, sid: str) -> dict:
    for s in index["sets"]:
        if s["id"] == sid:
            return s
    raise SystemExit(f"unknown set {sid!r}; available: {', '.join(s['id'] for s in index['sets'])}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("set", nargs="?", help="fixture set id (see --list)")
    ap.add_argument("--list", action="store_true", help="list sets and exit")
    ap.add_argument("--base", default=DEFAULT_BASE, help=f"API base url (default {DEFAULT_BASE})")
    ap.add_argument("--case-id", help="upload into this existing case instead of creating one")
    ap.add_argument("--title", help="title for a newly created case")
    ap.add_argument("--no-wait", action="store_true", help="do not wait for each processing job to finish")
    ap.add_argument("--no-base", action="store_true", help="for an apply_on set without --case-id: skip loading the base set (new empty case)")
    ap.add_argument("--timeout", type=float, default=240.0, help="seconds to wait per job (default 240)")
    return ap


def http_json(method: str, url: str, body: bytes | None = None, headers: dict | None = None, timeout: float = 60.0):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"detail": raw[:300].decode("utf-8", "replace")}


def multipart(fields: dict, filename: str, content: bytes, mime: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def create_case(base: str, title: str) -> str:
    code, js = http_json("POST", f"{base}/cases", json.dumps({"title": title}).encode(), {"Content-Type": "application/json"})
    if code >= 300:
        raise SystemExit(f"create case failed: HTTP {code} {js}")
    return js["id"]


def wait_job(base: str, job_id: str, timeout: float) -> str:
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, js = http_json("GET", f"{base}/jobs/{job_id}")
        if code == 200 and js["status"] in ("done", "failed", "interrupted"):
            return js["status"]
        time.sleep(1.5)
    return "timeout"


def upload_set(base: str, case_id: str, sset: dict, wait: bool, timeout: float) -> None:
    for f in sset["files"]:
        path = FIXTURES / f["path"]
        mime = mimetypes.guess_type(path.name)[0] or MIME_FALLBACK.get(path.suffix.lower(), "application/octet-stream")
        fields = {"kind": f["kind"]} if f.get("kind") else {}
        body, ctype = multipart(fields, path.name, path.read_bytes(), mime)
        code, js = http_json("POST", f"{base}/cases/{case_id}/evidence", body, {"Content-Type": ctype}, timeout=120)
        if code == 409:
            print(f"  {path.name}: already in this case (409, idempotent): {json.dumps(js)[:120]}")
            continue
        if code >= 300:
            print(f"  {path.name}: FAILED HTTP {code} {js}", file=sys.stderr)
            continue
        ev, job = js["evidence"], js["job"]
        status = "(not waiting)"
        if wait:
            status = f"job {wait_job(base, job['id'], timeout)}"
        print(f"  {path.name}: evidence {ev['id']} -> {status}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    index = load_index()
    if args.list or not args.set:
        for s in index["sets"]:
            print(f"{s['id']:<24} {len(s['files'])} files" + (f"  (apply_on {s['apply_on']})" if s.get("apply_on") else "") + f"  {s['title']}")
        return 0
    sset = find_set(index, args.set)
    wait = not args.no_wait
    case_id = args.case_id
    if not case_id:
        case_id = create_case(args.base, args.title or f"[SYNTHETIC demo] {sset['title']}")
        print(f"created case {case_id}")
        if sset.get("apply_on") and not args.no_base:
            base_set = find_set(index, sset["apply_on"])
            print(f"loading base set {base_set['id']} first")
            upload_set(args.base, case_id, base_set, wait=True, timeout=args.timeout)
            print(f"base set loaded; now applying {sset['id']}")
    print(f"uploading set {sset['id']} into case {case_id}")
    upload_set(args.base, case_id, sset, wait, args.timeout)
    print(f"case id: {case_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
