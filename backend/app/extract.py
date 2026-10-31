"""Step 1: per-evidence extraction (the Airlock reader). Deterministic parts first (hash, EXIF, PDF text, OCR, CSV math),
then ONE reader call (no tools, schema JSON only, document text spotlighted as untrusted data)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from . import prompts
from .calc import parse_date
from .contracts import ZONES
from .providers import ProviderUnavailable, inline_part, text_part
from .validate import parse_amount
from .zones import zone_for_part

IMAGE_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_TEXT_CHARS = 14000

INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions?|prompts?)|disregard\s+(the\s+|all\s+|any\s+)?(previous|prior|above|instructions?|rules?)|"
    r"system\s+prompt|you\s+are\s+now\b|new\s+instructions?\s*:|"
    r"\b(approve|release|pay)\b[^.\n]{0,40}\b(in\s+full|immediately|the\s+claim|full\s+amount|without\s+(review|checks?))|"
    r"do\s+not\s+(flag|mention|report)\b[^.\n]{0,40})", re.I)


def scan_injection(text: str) -> list[str]:
    """Return the sentence/line fragments containing instruction-like strings (recorded, never obeyed)."""
    found: list[str] = []
    for line in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if INJECTION_RE.search(line):
            s = line.strip()[:240]
            if s and s not in found:
                found.append(s)
    return found


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- text acquisition ----------
_OCR = None


def _ocr_image(pil_img) -> str:
    global _OCR
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    if _OCR is None:
        _OCR = RapidOCR()
    res, _ = _OCR(np.array(pil_img.convert("RGB")))
    return "\n".join(r[1] for r in (res or []))


def pdf_pages(path: Path) -> tuple[list[dict], list[str]]:
    """Per-page text via pypdf; pages with no text layer fall back to pypdfium2 + RapidOCR. Returns (passages, notes)."""
    from pypdf import PdfReader
    notes: list[str] = []
    reader = PdfReader(str(path))
    out = []
    for i, pg in enumerate(reader.pages, start=1):
        try:
            t = (pg.extract_text() or "").strip()
        except Exception:
            t = ""
        if len(t) < 15:
            try:
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(str(path))
                img = doc[i - 1].render(scale=2).to_pil()
                t = _ocr_image(img).strip()
                notes.append(f"page {i}: no text layer, OCR used")
            except Exception as e:
                notes.append(f"page {i}: no text layer and OCR failed ({type(e).__name__})")
        out.append({"page": i, "text": t})
    return out, notes


def read_passages(path: Path, mime: str, kind_hint: str) -> tuple[list[dict], list[str]]:
    ext = path.suffix.lower()
    if ext == ".pdf" or mime == "application/pdf":
        return pdf_pages(path)
    if ext in IMAGE_EXT:
        from PIL import Image
        try:
            return [{"page": 1, "text": _ocr_image(Image.open(path)).strip()}], ["OCR used"]
        except Exception as e:
            return [], [f"OCR failed ({type(e).__name__})"]
    if ext in (".txt", ".md", ".csv", ".json", ".log", ""):
        t = path.read_text(encoding="utf-8", errors="replace")
        return [{"page": 1, "text": t}], []
    return [], ["unsupported file type"]


# ---------- kind inference ----------
def infer_kind(filename: str, ext: str, text: str, declared: Optional[str]) -> str:
    if declared and declared not in ("other", ""):
        return declared
    fn = (filename or "").lower()
    if ext in IMAGE_EXT:
        return "photo"
    t = (text or "").lower()[:6000]
    if ext == ".csv":
        head = t.split("\n", 1)[0]
        if re.search(r"speed|lat|lon|accel|brake|gps|g_force", head):
            return "telematics"
        if re.search(r"part|description|amount|qty", head):
            return "estimate"
    if re.search(r"polic(y|ies)|schedule", fn):
        return "policy"
    if re.search(r"estimate|quot|invoice|repair", fn):
        return "estimate"
    if re.search(r"statement|narrative|fnol|report|account|witness|garage|notes?", fn):
        return "narrative"
    score = {
        "policy": len(re.findall(r"\b(idv|insured declared value|deductible|depreciation|exclusions?|policy no|premium)\b", t)),
        "estimate": len(re.findall(r"\b(estimate|labour|labor|qty|quantity|grand total|sub ?total|gst|spare)\b", t)),
        "narrative": len(re.findall(r"\b(i was|we were|the other (car|vehicle|driver)|collided|hit|struck|statement|witness|reported)\b", t)),
    }
    best = max(score, key=score.get)
    return best if score[best] >= 2 else ("narrative" if ext in (".txt", ".md") else "other")


# ---------- helpers ----------
def _zone(z) -> Optional[str]:
    if not z:
        return None
    s = re.sub(r"[\s\-]+", "_", str(z).strip().lower())
    return s if s in ZONES else "unknown"


def _akey(v) -> Optional[str]:
    d = parse_amount(v)
    if d is None:
        return None
    return "amount:" + (str(int(d)) if d == d.to_integral() else format(d.normalize(), "f"))


def _val(x):
    """Reader sub-objects are {value, quote, page}; tolerate bare values."""
    if isinstance(x, dict):
        return x.get("value"), x.get("quote"), x.get("page")
    return x, None, None


def exif_meta(path: Path, uploaded_at: Optional[str]) -> dict:
    from PIL import Image
    from PIL.ExifTags import TAGS
    meta: dict[str, Any] = {"sha256": sha256_file(path)}
    try:
        im = Image.open(path)
        meta.update({"width": im.width, "height": im.height, "format": im.format})
        raw = im.getexif()
        ex = {TAGS.get(k, str(k)): v for k, v in raw.items()}
        try:
            ex.update({TAGS.get(k, str(k)): v for k, v in raw.get_ifd(0x8769).items()})
        except Exception:
            pass
        cap = ex.get("DateTimeOriginal") or ex.get("DateTime")
        meta["exif_capture_time"] = str(cap) if cap else "unavailable"
        meta["exif_make_model"] = " ".join(str(ex[k]) for k in ("Make", "Model") if ex.get(k)) or "unavailable"
        meta["exif_software"] = str(ex["Software"]) if ex.get("Software") else "unavailable"
        meta["exif_gps"] = "present" if raw.get(0x8825) else "unavailable"
    except Exception as e:
        meta["exif_error"] = type(e).__name__
        meta["exif_capture_time"] = "unavailable"
    meta["file_modified_time"] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    meta["uploaded_at"] = uploaded_at or "unavailable"
    meta["exif_note"] = "Missing EXIF is common (messaging apps strip it) and is NOT treated as suspicious."
    return meta


# ---------- deterministic CSV estimate + telematics ----------
_ALIASES = {
    "part": ("part", "description", "item", "particulars", "part name", "item description"),
    "qty": ("qty", "quantity", "nos"),
    "unit": ("unit", "unit price", "rate", "unit_price", "price", "unit cost"),
    "amount": ("amount", "line total", "total", "line_total", "cost", "value"),
    "category": ("category", "type", "kind"),
    "zone": ("zone", "area", "location"),
    "material": ("material",),
}


def parse_estimate_csv(text: str) -> Optional[dict]:
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return None
    head = [h.strip().lower() for h in rows[0]]
    idx: dict[str, int] = {}
    for key, al in _ALIASES.items():
        for a in al:
            if a in head and key not in idx:
                idx[key] = head.index(a)
    if "part" not in idx or "amount" not in idx:
        return None
    raw_lines = text.splitlines()
    items, quoted_total = [], None
    for r, raw in zip(rows[1:], [l for l in raw_lines if l.strip()][1:]):
        get = lambda k: (r[idx[k]].strip() if k in idx and idx[k] < len(r) else "")
        part = get("part")
        if re.fullmatch(r"(grand\s+|sub\s*)?total", part.strip().lower()):
            if part.lower().startswith("sub"):
                continue
            quoted_total = {"value": get("amount"), "quote": raw.strip()}
            continue
        cat = (get("category") or "").lower() or ("labour" if re.search(r"labou?r|paint|denting|fitting", part.lower()) else "parts")
        if cat.startswith("lab"):
            cat = "labour"
        elif cat.startswith("pai"):
            cat = "paint"
        elif cat.startswith("tax") or cat.startswith("gst"):
            cat = "tax"
        elif cat not in ("parts", "labour", "paint", "tax"):
            cat = "parts"
        items.append({"part": part, "category": cat, "material": get("material") or None, "qty": get("qty") or "1",
                      "unit": get("unit") or None, "amount": get("amount"), "zone": _zone(get("zone")), "quote": raw.strip()})
    return {"line_items": items, "quoted_total": quoted_total, "currency": "INR", "injection_flags": []}


def telematics_summary(text: str, ext: str) -> dict:
    rows: list[dict] = []
    if ext == ".json":
        j = json.loads(text)
        rows = j if isinstance(j, list) else j.get("samples", [])
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    def col(*names):
        for n in names:
            for k in (rows[0].keys() if rows else []):
                if k.strip().lower() == n:
                    return k
        return None
    ks, ka, kt = col("speed", "speed_kmph", "speed_kph", "speed_kmh"), col("accel", "acceleration", "accel_g", "g_force", "decel"), col("time", "timestamp", "ts")
    def nums(k):
        out = []
        for r in rows:
            d = parse_amount(r.get(k)) if k else None
            if d is not None:
                out.append(float(d))
        return out
    sp, ac = nums(ks), nums(ka)
    s = {"rows": len(rows), "first_time": rows[0].get(kt) if rows and kt else None, "last_time": rows[-1].get(kt) if rows and kt else None,
         "max_speed": max(sp) if sp else None, "min_accel": min(ac) if ac else None, "max_accel": max(ac) if ac else None}
    return {"summary": s, "injection_flags": []}


# ---------- zone/facts derivation ----------
def facts_from_payload(ev: dict, p: dict) -> list[dict]:
    """Deterministic facts (no ids) from an extraction payload. Entity keys here drive staleness."""
    eid, kind = ev["id"], p.get("kind")
    facts: list[dict] = []

    def add(label, value, epistemic, key=None, quote=None, page=None, zone=None):
        if value in (None, "", []):
            return
        ref = {"evidence_id": eid, "page": page, "quote": quote, "zone": zone, "receipt": "n/a"} if (quote or zone or page) else None
        facts.append({"evidence_id": eid, "label": label, "value": str(value), "epistemic": epistemic, "entity_key": key, "ref": ref})

    plate = (p.get("vehicle") or {}).get("plate") or p.get("vehicle_plate")
    if plate:
        add("vehicle plate", plate, "reported" if kind != "photo" else "observed", "vehicle:" + re.sub(r"\W", "", str(plate)).upper())
    if kind == "photo":
        for d in p.get("damage", []):
            z = _zone(d.get("zone")) or "unknown"
            add(f"visible damage ({z})", f"{d.get('description', '')} [{d.get('severity', 'unclear')}]; uncertainty: {d.get('uncertainty', 'none stated')}",
                "observed", f"zone:{z}", zone=z)
        add("image quality", p.get("image_quality"), "observed")
        m = p.get("meta") or {}
        add("EXIF capture time", m.get("exif_capture_time"), "observed", "date:" + str(m["exif_capture_time"])[:10].replace(":", "-") if m.get("exif_capture_time") not in (None, "unavailable") else None)
    elif kind == "narrative":
        z = _zone(p.get("claimed_impact_zone"))
        add("claimed impact zone", z, "reported", f"zone:{z}" if z and z != "unknown" else None, quote=p.get("claimed_impact_quote"), zone=z)
        for sz in p.get("secondary_impact_zones") or []:
            add(f"reported secondary impact ({sz})", f"A second impact at the {sz} is reported", "reported", f"zone:{sz}", zone=sz)
        for e in p.get("reported_events", []):
            add(f"reported event {e.get('order', '')}", e.get("text"), "reported", None, quote=e.get("quote"))
        dol = p.get("date_of_loss") or p.get("date")
        if dol:
            iso = parse_date(dol)
            add("incident date", iso.isoformat() if iso else dol, "reported", f"date:{iso.isoformat() if iso else dol}", quote=p.get("date_of_loss_quote"))
        add("incident time", p.get("incident_time") or p.get("time"), "reported")
        add("place", p.get("place"), "reported")
    elif kind == "policy":
        t = p.get("terms") or {}
        for label, k, ck in (("IDV", "idv", "clause:idv"), ("compulsory deductible", "compulsory_deductible", "clause:deductible"), ("voluntary deductible", "voluntary_deductible", "clause:deductible")):
            v, q, pg = _val(t.get(k))
            if v is not None:
                add(label, v, "reported", ck, quote=q, page=pg)
        rv, rq, rp = _val(p.get("date_of_first_registration"))
        if rv:
            iso = parse_date(rv)
            add("date of first registration", iso.isoformat() if iso else rv, "reported", f"date:{iso.isoformat()}" if iso else None,
                quote=rq or p.get("date_of_first_registration_quote"), page=rp)
        for d in t.get("depreciation", []):
            add(f"depreciation: {d.get('category')}", d.get("rate"), "reported", "clause:depreciation", quote=d.get("quote"), page=d.get("page"))
        for x in t.get("exclusions", []):
            add("exclusion", x.get("text"), "reported", "clause:exclusions", quote=x.get("quote"), page=x.get("page"))
    elif kind == "estimate":
        for i, li in enumerate(p.get("line_items", []), start=1):
            z = li.get("zone") or "unmapped"
            k = [_akey(li.get("amount"))]
            add(f"estimate line {i}: {li.get('part')}", f"{li.get('amount')} ({li.get('category')}, zone {z})", "reported",
                (f"zone:{z}" if z != "unmapped" else None), quote=li.get("quote"), zone=li.get("zone"))
            if k[0]:
                facts.append({"evidence_id": eid, "label": f"estimate amount {i}", "value": str(li.get("amount")), "epistemic": "reported", "entity_key": k[0], "ref": None})
        qt, q, pg = _val(p.get("quoted_total"))
        if qt is not None:
            add("estimate quoted total", qt, "reported", _akey(qt), quote=q)
    elif kind == "telematics":
        for k, v in (p.get("summary") or {}).items():
            add(f"telematics {k}", v, "observed")
    else:
        for f in p.get("facts", []):
            add(f.get("label") or "fact", f.get("value"), "reported", None, quote=f.get("quote"))
    return facts


# ---------- orchestration ----------
def _reader_call(providers, kind: str, ev: dict, parts: list, max_tokens: int = 4096):
    system = prompts.AIRLOCK
    return providers.generate_json(system, parts, max_tokens=max_tokens, cache_key=f"extract:{kind}:{ev.get('sha256', '')}", role="reader")


def _clean_flags(obj: dict, text: str) -> list[str]:
    flags = list(scan_injection(text))
    for f in obj.get("injection_flags", []) or []:
        if isinstance(f, str) and f.strip() and f not in flags:
            flags.append(f.strip()[:240])
    return flags


def _text_for_model(passages: list[dict]) -> str:
    t = "\n".join(f"[PAGE {p['page']}]\n{p['text']}" for p in passages)
    return t[:MAX_TEXT_CHARS]


def extract_evidence(repo, evidence_id: str, providers, ev: Optional[dict] = None, emit=None) -> dict:
    """Extract one evidence item; saves passages + extraction via repo; returns the payload. Never raises for AI outages:
    the payload is then marked unavailable (and the evidence `failed`) so the pipeline degrades loudly and can retry."""
    t0 = time.time()
    if ev is None and hasattr(repo, "evidence"):
        ev = repo.evidence(evidence_id)
    path = Path(repo.evidence_path(evidence_id))
    ev = dict(ev or {"id": evidence_id, "filename": path.name, "mime": "", "kind": None, "uploaded_at": None})
    ev["id"] = evidence_id
    ext = path.suffix.lower()
    mime = ev.get("mime") or IMAGE_EXT.get(ext, "")
    ev.setdefault("sha256", sha256_file(path) if path.exists() else "")
    declared = ev.get("kind")
    repo.set_evidence_status(evidence_id, "processing")

    # audio / video / unknown binary: stored, unsupported + request
    if ext in (".mp3", ".wav", ".m4a", ".ogg", ".mp4", ".mov", ".avi", ".mkv", ".webm") or mime.startswith(("audio/", "video/")):
        payload = {"kind": "other", "unsupported": True, "reason": "audio/video analysis is not supported in this build",
                   "request": "Provide a transcript (for audio) or representative still frames (for video).", "facts": [], "injection_flags": []}
        repo.save_extraction(evidence_id, payload, "none", False)
        repo.set_evidence_status(evidence_id, "unsupported", error="audio/video not analysed; provide transcript or stills")
        return payload

    try:
        passages, notes = read_passages(path, mime, declared or "")
    except Exception as e:  # corrupt PDF etc.
        repo.save_extraction(evidence_id, {"kind": declared or "other", "unavailable": True, "reason": f"unreadable file: {type(e).__name__}", "facts": [], "injection_flags": []}, "none", False)
        repo.set_evidence_status(evidence_id, "failed", error=f"file could not be read ({type(e).__name__}); provide a legible copy")
        return {"kind": declared or "other", "unreadable": True}
    text_all = "\n".join(p["text"] for p in passages)
    kind = infer_kind(ev.get("filename", path.name), ext, text_all, declared)
    meta: dict[str, Any] = {"read_notes": notes}
    if ext in IMAGE_EXT:
        meta.update(exif_meta(path, ev.get("uploaded_at")))
    else:
        meta["sha256"] = ev["sha256"]
    if passages and kind != "photo":
        repo.save_passages(evidence_id, passages)

    payload: dict[str, Any] = {"kind": kind, "meta": meta, "injection_flags": scan_injection(text_all)}
    model, cached = "deterministic", False
    unavailable_reason = None
    try:
        if kind == "photo":
            img = path.read_bytes()
            parts = [text_part(prompts.READER_TASKS["photo"]), inline_part(img, mime or "image/jpeg")]
            obj, usage = _reader_call(providers, "photo", ev, parts)
            model, cached = usage.get("model", ""), bool(usage.get("cached"))
            dtype = obj.get("doc_type", "photo")
            if dtype != "photo" and obj.get("transcription"):
                passages = [{"page": 1, "text": str(obj["transcription"])}]
                repo.save_passages(evidence_id, passages)
                kind = payload["kind"] = infer_kind(ev.get("filename", ""), ext, passages[0]["text"], dtype if dtype in ("narrative", "estimate", "policy") else None)
                text_all = passages[0]["text"]
                payload["injection_flags"] = _clean_flags(obj, text_all)
                obj, payload = _extract_text_kind(providers, kind, ev, passages, ext, payload)
            else:
                z = [z for z in (_zone(x) for x in obj.get("zones", [])) if z]
                dm = obj.get("damage", []) or []
                for d in dm:
                    d["zone"] = _zone(d.get("zone")) or "unknown"
                payload.update({"zones": z, "damage": dm, "image_quality": obj.get("image_quality"), "quality_notes": obj.get("quality_notes"),
                                "vehicle": obj.get("vehicle") or {}, "scene_notes": obj.get("scene_notes", "")})
                payload["injection_flags"] = _clean_flags(obj, (obj.get("scene_notes") or "") + " " + str(obj.get("transcription") or ""))
                payload["usage"] = usage
        elif kind == "telematics":
            payload.update(telematics_summary(text_all, ext))
        elif kind == "estimate" and ext == ".csv" and (est := parse_estimate_csv(text_all)):
            payload.update({k: v for k, v in est.items() if k != "injection_flags"})
        elif kind in ("narrative", "policy", "estimate", "other", "history", "metadata", "weather"):
            if not any(p["text"].strip() for p in passages):
                raise ProviderUnavailable("no readable text in the file")
            k2 = kind if kind in prompts.READER_TASKS else "other"
            obj, payload = _extract_text_kind(providers, k2, ev, passages, ext, payload)
            model, cached = payload.pop("_model", ""), payload.pop("_cached", False)
    except ProviderUnavailable as e:
        unavailable_reason = str(e)[:300]

    # normalise per kind
    if payload["kind"] == "estimate":
        for li in payload.get("line_items", []):
            z = zone_for_part(li.get("part", "")) or (_zone(li.get("zone")) if li.get("zone") else None)
            li["zone"] = None if z == "unknown" else z
    if payload["kind"] == "policy" and "terms" not in payload:
        payload["terms"] = {k: payload.pop(k) for k in ("idv", "compulsory_deductible", "voluntary_deductible", "depreciation", "exclusions", "other_clauses") if k in payload}
    if unavailable_reason:
        payload["unavailable"] = True
        payload["reason"] = unavailable_reason
    payload["facts"] = facts_from_payload(ev, payload)
    ver = repo.save_extraction(evidence_id, payload, model, cached)
    if unavailable_reason:
        repo.set_evidence_status(evidence_id, "failed", error=f"AI unavailable: {unavailable_reason}", meta=meta, pages=len(passages), kind=payload["kind"])
    else:
        repo.set_evidence_status(evidence_id, "extracted", meta=meta, pages=len(passages), kind=payload["kind"])
    if emit:
        emit({"event": "extracted", "evidence_id": evidence_id, "kind": payload["kind"], "ms": int((time.time() - t0) * 1000), "version": ver})
    return payload


def _extract_text_kind(providers, kind: str, ev: dict, passages: list[dict], ext: str, payload: dict):
    text = _text_for_model(passages)
    task = prompts.READER_TASKS.get(kind, prompts.READER_TASKS["other"])
    parts = [text_part(task), text_part(prompts.untrusted(text, ev.get("filename", "document")))]
    obj, usage = _reader_call(providers, kind, ev, parts, max_tokens=12000 if kind in ("estimate", "policy") else 6000)
    flags = _clean_flags(obj, "\n".join(p["text"] for p in passages))
    payload["injection_flags"] = flags
    payload["_model"], payload["_cached"], payload["usage"] = usage.get("model", ""), bool(usage.get("cached")), usage
    if kind == "policy":
        payload["terms"] = {k: obj.get(k) for k in ("idv", "compulsory_deductible", "voluntary_deductible", "depreciation", "exclusions", "other_clauses")}
        payload["terms"]["depreciation"] = obj.get("depreciation") or []
        payload["terms"]["exclusions"] = obj.get("exclusions") or []
        for k in ("policy_number", "insured_vehicle", "vehicle_plate", "registration_year", "date_of_first_registration"):
            payload[k] = obj.get(k)
    elif kind == "estimate":
        payload.update({k: obj.get(k) for k in ("garage", "estimate_date", "date_of_loss", "date_of_loss_quote", "vehicle_plate", "line_items", "quoted_total", "currency")})
        payload["line_items"] = obj.get("line_items") or []
    elif kind == "narrative":
        payload.update({k: obj.get(k) for k in ("reported_events", "claimed_impact_zone", "claimed_impact_quote", "secondary_impact_zones", "date", "time", "place", "latitude", "longitude", "parties", "vehicle_plate", "author_role", "summary",
                                                 "date_of_loss", "date_of_loss_quote", "incident_time")})
        iso = parse_date(obj.get("date_of_loss") or obj.get("date"))
        payload["date_of_loss"] = iso.isoformat() if iso else (obj.get("date_of_loss") or obj.get("date"))
        payload["date"] = payload["date_of_loss"]  # legacy key used by facts / weather tool
        payload["incident_time"] = obj.get("incident_time") or obj.get("time")
        payload["time"] = payload["incident_time"]
        payload["reported_events"] = obj.get("reported_events") or []
        payload["claimed_impact_zone"] = _zone(obj.get("claimed_impact_zone"))
        payload["secondary_impact_zones"] = [z for z in (_zone(x) for x in (obj.get("secondary_impact_zones") or [])) if z and z != "unknown"]
    else:
        payload.update({"summary": obj.get("summary", ""), "facts_raw": obj.get("facts", [])})
        payload["facts"] = []
        payload["facts"] = [{"label": f.get("label"), "value": f.get("value"), "quote": f.get("quote")} for f in obj.get("facts", []) if isinstance(f, dict)]
    return obj, payload
