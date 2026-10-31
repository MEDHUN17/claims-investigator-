"""Ordinal hypothesis ranks, pairs_separated, rupees_at_stake, idempotent request keys. No probabilities anywhere."""
from __future__ import annotations

import hashlib
import itertools
import re
from decimal import Decimal
from typing import Optional

from .validate import parse_amount


def request_key(case_id: str, text: str) -> str:
    """Stable idempotency key: retries / re-analysis of the same ask never create a duplicate request."""
    norm = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    return hashlib.sha256(f"{case_id}|{norm}".encode()).hexdigest()[:16]


def rank_hypotheses(hypotheses: list[dict], matrix: list[dict]) -> list[dict]:
    """Set `inconsistencies` (cells with relation=inconsistent) and ordinal `rank` (1 = fewest; ties share a rank)."""
    counts = {h["id"]: 0 for h in hypotheses}
    for c in matrix:
        if c["relation"] == "inconsistent" and c["hypothesis_id"] in counts:
            counts[c["hypothesis_id"]] += 1
    distinct = sorted(set(counts.values()))
    for h in hypotheses:
        h["inconsistencies"] = counts[h["id"]]
        h["rank"] = distinct.index(counts[h["id"]]) + 1
    return hypotheses


def pairs_separated(resolves: list[str], expected: Optional[dict]) -> int:
    """Number of hypothesis pairs within `resolves` that the requested evidence would tell apart: pairs whose
    EXPECTED relation to that evidence differs (consistent vs inconsistent). Computed here, never by the model.
    `expected` maps hypothesis id -> 'consistent'|'inconsistent'|'neutral'."""
    if not expected:
        return 0
    n = 0
    for a, b in itertools.combinations(sorted(set(resolves)), 2):
        ra, rb = expected.get(a), expected.get(b)
        if ra and rb and ra != rb and "neutral" not in (ra, rb):
            n += 1
    return n


def rupees_at_stake(resolves: list[str], conditional: list[dict]) -> Optional[str]:
    """max - min of the conditional settlements over the hypotheses this request resolves; None if not computable."""
    vals = []
    for c in conditional:
        if c["hypothesis_id"] in resolves:
            d = parse_amount(c.get("settlement"))
            if d is None:
                return None
            vals.append(d)
    if len(vals) < 2:
        return None
    return format((max(vals) - min(vals)).quantize(Decimal("0.01")), "f")


def order_requests(requests: list[dict]) -> list[dict]:
    """Open first; then pairs_separated desc, rupees_at_stake desc (None last), then id. Stable, deterministic."""
    def k(r):
        d = parse_amount(r.get("rupees_at_stake"))
        return (0 if r.get("status") == "open" else 1, -int(r.get("pairs_separated", 0)), -(d if d is not None else Decimal(-1)), r["id"])
    return sorted(requests, key=k)
