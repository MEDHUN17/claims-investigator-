"""Validation of model output: receipts, closed ids, language guard, unreceipted cells -> neutral."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from rapidfuzz import fuzz

# ---------- normalisation ----------
_CUR = re.compile(r"(₹|rs\.?|inr|usd|\$)", re.I)


def normalise(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = s.replace("/-", " ")
    s = _CUR.sub(" ", s)
    s = re.sub(r"(?<=\d),(?=\d)", "", s)  # 1,23,456 and 123,456 -> 123456 (lakh grouping too)
    s = re.sub(r"\s+", "", s)
    return s


def parse_amount(x) -> Optional[Decimal]:
    """Parse '₹ 1,23,456.50', 'Rs. 48,250/-', '(500)' ... into Decimal; None if not a number."""
    if x is None:
        return None
    if isinstance(x, (int, Decimal)):
        return Decimal(x)
    if isinstance(x, float):
        return Decimal(str(x))
    s = str(x).strip()
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = _CUR.sub("", s).replace("/-", "")
    s = re.sub(r"[^\d.]", "", s.replace(",", ""))
    if not s or s == ".":
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if neg else d


def _amounts_in(text: str, csv_cells: bool = False) -> set[Decimal]:
    out = set()
    # a comma is a thousands/lakh separator only inside proper groups (6,800 | 1,23,456); in CSV rows "1,6800,6800" are three cells
    for m in re.finditer(r"\d{1,3}(?:,\d{2,3})+(?!\d)(?:\.\d+)?|\d+(?:\.\d+)?", text):
        d = parse_amount(m.group(0))
        if d is not None:
            out.add(d.normalize())
    if csv_cells and text.count(",") >= 2:  # a CSV row: every comma-separated cell is a candidate amount ("...,1,650,650" is qty 1, unit 650, amount 650)
        for cell in text.split(","):
            d = parse_amount(cell) if re.fullmatch(r"\s*[\d.]+\s*", cell) else None
            if d is not None:
                out.add(d.normalize())
    return out


def receipt(quote: Optional[str], passages: list[dict], page: Optional[int] = None) -> str:
    """matched | partial | unverified | n/a. `passages` = [{page, text}] of ONE evidence."""
    if quote is None or not str(quote).strip():
        return "n/a"
    nq = normalise(str(quote))
    if not nq:
        return "n/a"
    texts = [(p.get("page"), normalise(p.get("text", ""))) for p in passages]
    scoped = [t for pg, t in texts if page is None or pg == page] or [t for _, t in texts]
    for t in scoped + [t for _, t in texts]:
        if nq in t:
            return "matched"
    # a bare amount quote: compare as numbers (handles 48,250 vs 48250.00)
    qa = parse_amount(quote) if re.fullmatch(r"[\s₹rsRSinrINR.,/\-\d]+", str(quote)) else None
    if qa is not None:
        for p in passages:
            if qa.normalize() in _amounts_in(p.get("text", "")):
                return "matched"
    best = 0
    for _, t in texts:
        if len(nq) <= len(t):
            best = max(best, fuzz.partial_ratio(nq, t))
        else:
            best = max(best, fuzz.ratio(nq, t))
    return "partial" if best >= 90 else "unverified"


# ---------- language guard ----------
FORBIDDEN = {
    "fraudulent": "irregular", "fraudster": "party", "fraud": "irregularity", "fake": "unverified", "faked": "unverified",
    "lying": "giving an inconsistent account", "liar": "party with an inconsistent account", "lied": "gave an inconsistent account",
    "forged": "unverified", "forgery": "unverified document", "scam": "irregularity", "scammer": "party", "cheat": "irregularity",
    "cheating": "irregularity", "dishonest": "inconsistent", "dishonesty": "inconsistency",
}
_FORB_RE = re.compile(r"\b(" + "|".join(sorted(FORBIDDEN, key=len, reverse=True)) + r")\b", re.I)
_QUOTED = re.compile(r"[\"“‘']([^\"”’']{3,})[\"”’']")


def _quoted_spans(text: str, source_texts: list[str]) -> list[tuple[int, int]]:
    """Spans of `text` that sit inside quote marks AND whose content occurs in a source passage."""
    spans = []
    norm_sources = [normalise(s) for s in source_texts]
    for m in _QUOTED.finditer(text):
        inner = normalise(m.group(1))
        if inner and any(inner in s for s in norm_sources):
            spans.append((m.start(), m.end()))
    return spans


def guard_text(text: str, source_texts: list[str]) -> tuple[str, list[str]]:
    """Replace forbidden accusation words outside quoted source spans. Returns (clean_text, replaced_words)."""
    if not text or not _FORB_RE.search(text):
        return text, []
    spans = _quoted_spans(text, source_texts)
    replaced: list[str] = []

    def sub(m: re.Match) -> str:
        if any(a <= m.start() < b for a, b in spans):
            return m.group(0)
        w = m.group(0)
        replaced.append(w.lower())
        rep = FORBIDDEN[w.lower()]
        return rep.capitalize() if w[0].isupper() else rep

    return _FORB_RE.sub(sub, text), replaced


def find_forbidden(text: str, source_texts: list[str]) -> list[str]:
    """Forbidden words still present outside quoted source spans (used by the language gate)."""
    spans = _quoted_spans(text or "", source_texts)
    return [m.group(0).lower() for m in _FORB_RE.finditer(text or "") if not any(a <= m.start() < b for a, b in spans)]


def _walk_strings(obj, fn):
    """Apply fn(str)->str to every string in nested dict/list (in place for dicts/lists)."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = fn(v)
            else:
                _walk_strings(v, fn)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = fn(v)
            else:
                _walk_strings(v, fn)


_FREE_TEXT_KEYS = ("title", "body", "uncertainty", "action", "text", "why", "summary", "recommendation", "note",
                   "if_supports", "if_contradicts", "stale_reason", "reason", "alternatives", "prior_body")


def guard_state(state: dict, passages_by_evidence: dict[str, list[dict]]) -> list[str]:
    """Apply the language guard to every model-authored free-text field of a CaseState dict (in place)."""
    sources = [p.get("text", "") for ps in passages_by_evidence.values() for p in ps]
    replaced: list[str] = []

    def g(s: str) -> str:
        out, r = guard_text(s, sources)
        replaced.extend(r)
        return out

    def visit(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k in _FREE_TEXT_KEYS and isinstance(v, str):
                    node[k] = g(v)
                elif k in _FREE_TEXT_KEYS and isinstance(v, list) and all(isinstance(x, str) for x in v):
                    node[k] = [g(x) for x in v]
                elif k == "quote":
                    continue  # quotes are source text, never rewritten
                else:
                    visit(v)
        elif isinstance(node, list):
            for x in node:
                visit(x)

    visit(state)
    return replaced


# ---------- closed ids + receipts ----------
def _fix_ref(ref: dict, passages_by_evidence: dict[str, list[dict]], valid_ids: set[str], problems: list[str],
             image_ids: Optional[set[str]] = None, strip_unverified: bool = False) -> Optional[dict]:
    """Closed-id + receipt pass for ONE reference.

    * Image evidence (photos) carries no text layer: a quote on such a ref cannot be verified, so it is stripped (the zone stays).
    * A model-authored quote that is not found even fuzzily (`strip_unverified`) is REMOVED and the ref is labelled receipt='unverified',
      so nothing unverifiable is displayed as if it were a source quote.
    """
    from .contracts import ZONES
    if ref.get("evidence_id") not in valid_ids:
        problems.append(f"dropped reference to unknown evidence id {ref.get('evidence_id')!r}")
        return None
    if ref.get("zone") and ref["zone"] not in ZONES:
        ref["zone"] = "unknown"
    q = ref.get("quote")
    if q and ref["evidence_id"] in (image_ids or set()):
        ref["quote"] = None
        ref["page"] = None
        if ref.get("receipt") not in ("matched", "partial"):
            ref["receipt"] = "n/a"
        problems.append(f"quote on image evidence {ref['evidence_id']} stripped (images have no verifiable text)")
    elif q:
        ref["receipt"] = receipt(q, passages_by_evidence.get(ref["evidence_id"], []), ref.get("page"))
        if ref["receipt"] == "unverified" and strip_unverified:
            ref["quote"] = None
            problems.append(f"quote not found in {ref['evidence_id']}: removed, marked unverified")
    elif ref.get("receipt") not in ("matched", "partial", "unverified"):
        ref["receipt"] = "n/a"
    return ref


def check_refs(state: dict, passages_by_evidence: dict[str, list[dict]], image_evidence: Optional[set[str]] = None) -> list[str]:
    """Closed-id + receipt pass over findings, timeline and facts. Mutates state; returns problems found."""
    valid = set(state.get("evidence_ids", []))
    problems: list[str] = []
    imgs = set(image_evidence or ())

    def fix(r, strip):
        return _fix_ref(dict(r), passages_by_evidence, valid, problems, imgs, strip)

    for f in state.get("findings", []):
        for key in ("supports", "contradicts"):
            f[key] = [r for r in (fix(r, True) for r in f.get(key, [])) if r]
        j = f.setdefault("justification", {"evidence_ids": [], "entity_keys": []})
        j["evidence_ids"] = [e for e in j.get("evidence_ids", []) if e in valid]
    for t in state.get("timeline", []):
        t["refs"] = [r for r in (fix(r, True) for r in t.get("refs", [])) if r]
    for fact in state.get("facts", []):
        if fact.get("ref"):
            fact["ref"] = fix(fact["ref"], False)
    return problems


def downgrade_cells(state: dict, cell_receipts: dict[tuple[str, str], str]) -> int:
    """Unreceipted matrix cells become neutral. `cell_receipts[(hyp, evidence)]` is the receipt computed from the cited
    quote/fact. A cell with receipt not in (matched, partial) is downgraded. Returns number downgraded."""
    valid_h = {h["id"] for h in state.get("hypotheses", [])}
    valid_e = set(state.get("evidence_ids", []))
    keep, n = [], 0
    for c in state.get("matrix", []):
        if c["hypothesis_id"] not in valid_h or c["evidence_id"] not in valid_e:
            continue  # closed ids: drop the cell
        rc = cell_receipts.get((c["hypothesis_id"], c["evidence_id"]), c.get("receipt", "n/a"))
        c["receipt"] = rc
        if c["relation"] != "neutral" and rc not in ("matched", "partial"):
            c["why"] = ("(no verifiable receipt; treated as neutral) " + c.get("why", "")).strip()
            c["relation"] = "neutral"
            n += 1
        keep.append(c)
    state["matrix"] = keep
    return n


# ---------- baseline hypotheses ----------
BASELINE_BENIGN = "The documents are consistent and the account is accurate as reported (baseline)"
BASELINE_DATA_ERROR = "A record or data-entry error explains any mismatch between the documents (baseline)"


def ensure_baseline_hypotheses(hypotheses: list[dict]) -> list[str]:
    """Guarantee >=1 benign and >=1 data-error hypothesis. If the planner omitted one, add a clearly labelled neutral baseline
    (no matrix cells are invented for it; ranking treats it like any other hypothesis). Returns the ids added."""
    def nid() -> str:
        n = max([int(h["id"].split("-")[1]) for h in hypotheses if str(h.get("id", "")).startswith("H-") and str(h["id"])[2:].isdigit()] + [0]) + 1
        return f"H-{n}"

    added: list[str] = []
    if not any(h.get("benign") for h in hypotheses):
        hypotheses.append({"id": nid(), "text": BASELINE_BENIGN, "benign": True, "kind": "benign", "inconsistencies": 0, "rank": 0, "covered_zones": ["all"]})
        added.append(hypotheses[-1]["id"])
    if not any(h.get("kind") in ("data_error", "misassociation") for h in hypotheses):
        hypotheses.append({"id": nid(), "text": BASELINE_DATA_ERROR, "benign": False, "kind": "data_error", "inconsistencies": 0, "rank": 0, "covered_zones": ["all"]})
        added.append(hypotheses[-1]["id"])
    return added
