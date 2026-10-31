"""File intake: magic-byte sniffing, size cap, safe generated names, path-traversal guard, kind inference."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config

TEXT_EXTS = {"txt", "md", "csv", "json"}
KINDS = {"photo", "narrative", "policy", "estimate", "history", "metadata", "weather", "telematics", "other"}
SOURCE_BY_KIND = {"policy": "third_party", "estimate": "third_party", "photo": "claimant", "narrative": "claimant",
                  "history": "system", "metadata": "system", "weather": "system", "telematics": "system", "other": "claimant"}
KEYWORDS = [
    ("policy", ("policy", "schedule", "wording", "idv")),
    ("estimate", ("estimate", "quotation", "quote", "invoice", "repair", "garage_bill", "bill")),
    ("telematics", ("telematic", "obd", "gps", "speed_log")),
    ("history", ("history", "prior_claims")),
    ("weather", ("weather",)),
    ("narrative", ("statement", "narrative", "fir", "report", "declaration", "account", "description", "claim_form", "witness", "mechanic")),
]


class UploadError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Sniffed:
    ext: str           # extension to store under
    mime: str
    family: str        # image | pdf | text | unsupported
    supported: bool
    note: str = ""


def sniff(data: bytes, filename: str = "") -> Sniffed:
    head = data[:16]
    name_ext = Path(filename).suffix.lower().lstrip(".")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Sniffed("png", "image/png", "image", True)
    if head.startswith(b"\xff\xd8\xff"):
        return Sniffed("jpg", "image/jpeg", "image", True)
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return Sniffed("webp", "image/webp", "image", True)
    if data[:1024].lstrip(b"\x00 \t\r\n").startswith(b"%PDF-") or head.startswith(b"%PDF-"):
        return Sniffed("pdf", "application/pdf", "pdf", True)
    # recognisable but unsupported media / containers
    if head[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return Sniffed("bin", "audio/wav", "unsupported", False, "audio (provide a transcript)")
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2") or head[:4] == b"OggS" or head[:4] == b"fLaC":
        return Sniffed("bin", "audio/" + ("ogg" if head[:4] == b"OggS" else "mpeg"), "unsupported", False, "audio (provide a transcript)")
    if data[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3":
        return Sniffed("bin", "video/mp4", "unsupported", False, "video (provide stills or a transcript)")
    if head[:2] == b"PK":
        return Sniffed("bin", "application/zip", "unsupported", False, "zip/office container (docx not supported)")
    if head[:4] in (b"GIF8",) or head[:2] == b"BM":
        return Sniffed("bin", "image/other", "unsupported", False, "image format not supported (use png/jpg/webp)")
    # text: no NUL bytes and decodes as UTF-8 (allow truncated multibyte tail)
    if b"\x00" not in data[:8192]:
        try:
            data[:65536].decode("utf-8")
            ok = True
        except UnicodeDecodeError as e:
            ok = e.start >= min(len(data), 65536) - 4
        if ok:
            ext = name_ext if name_ext in TEXT_EXTS else "txt"
            mime = {"txt": "text/plain", "md": "text/markdown", "csv": "text/csv", "json": "application/json"}[ext]
            return Sniffed(ext, mime, "text", True)
    return Sniffed("bin", "application/octet-stream", "unsupported", False, "unrecognised binary format")


def safe_display_name(filename: str) -> str:
    base = (filename or "upload").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    return (base or "upload")[:120]


def infer_kind(filename: str, sniffed: Sniffed, data: bytes, override: Optional[str] = None) -> str:
    if override:
        if override not in KINDS:
            raise UploadError(422, f"unknown kind '{override}'")
        return override
    if not sniffed.supported:
        return "other"
    stem = Path(filename).stem.lower()
    for kind, words in KEYWORDS:
        if any(w in stem for w in words):
            return kind
    if sniffed.family == "image":
        return "photo"
    if sniffed.family == "text":
        sample = data[:4000].decode("utf-8", "ignore").lower()
        for kind, words in KEYWORDS[:3]:
            if any(w in sample for w in words[:2]):
                return kind
        return "narrative" if sniffed.ext in ("txt", "md") else "other"
    return "other"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_root() -> Path:
    config.STORAGE.mkdir(parents=True, exist_ok=True)
    return config.STORAGE.resolve()


def resolve_inside(rel: str) -> Path:
    """Resolve a storage-relative path, refusing anything that escapes the storage root."""
    root = storage_root()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise UploadError(400, "path escapes storage root")
    return p


def write_file(case_id: str, evidence_id: str, ext: str, data: bytes) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", case_id) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", evidence_id):
        raise UploadError(400, "bad id")
    if not re.fullmatch(r"[a-z0-9]{1,5}", ext):
        raise UploadError(400, "bad extension")
    rel = f"{case_id}/{evidence_id}.{ext}"
    p = resolve_inside(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return rel
