"""Deterministic zone logic: estimate part-name -> zone lookup, zone adjacency, mismatch flag.

Unmapped parts are returned as None and shown as "unmapped" by callers; nothing is guessed.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from .contracts import ZONES

_REAR = r"\b(rear|tail|boot|trunk|dickey|dicky|back)\b"
_FRONT = r"\b(front|head\s*lamp|headlamp|headlight|head\s*light|bonnet|hood|grille|grill|radiator|condenser|fog|wind\s*shield|windshield|windscreen|apron|bumper|fender|wing|lower\s*arm|intercooler)\b"
_SIDE_PART = r"\b(door|quarter|sill|rocker|orvm|mirror|side|b\s*pillar|a\s*pillar|c\s*pillar|running\s*board|footstep)\b"
_ROOF = r"\b(roof|sunroof)\b"
_UNDER = r"\b(underbody|under\s*body|sump|axle|subframe|chassis|exhaust|floor|undertray)\b"
_LEFT = r"\b(left|lh|lhs|l/h|nearside)\b"
_RIGHT = r"\b(right|rh|rhs|r/h|offside)\b"


def zone_for_part(part: str) -> Optional[str]:
    """Map an estimate part description to a zone in ZONES, or None when it cannot be mapped."""
    s = (part or "").lower()
    if not s.strip():
        return None
    rear = re.search(_REAR, s) is not None
    front = re.search(_FRONT, s) is not None
    left = re.search(_LEFT, s) is not None
    right = re.search(_RIGHT, s) is not None
    side_part = re.search(_SIDE_PART, s) is not None
    if re.search(_ROOF, s):
        return "roof"
    if re.search(_UNDER, s) and not (rear or front):
        return "underbody"
    # explicit front/rear words win over generic ones ("rear bumper" has both bumper and rear)
    if rear and not re.search(r"\bfront\b", s):
        return "rear_left" if left else "rear_right" if right else "rear"
    if re.search(r"\bfront\b", s) and not rear:
        if side_part and re.search(r"door", s):
            return "left" if left else "right" if right else None
        return "front_left" if left else "front_right" if right else "front"
    if rear and re.search(r"\bfront\b", s):  # e.g. "front and rear bumper": ambiguous
        return None
    if front:
        return "front_left" if left else "front_right" if right else "front"
    if side_part:
        return "left" if left else "right" if right else None
    return None


# Zones that count as "the same or adjacent area" so a front-left photo does not contradict a front narrative.
_ADJ = {
    "front": {"front_left", "front_right"}, "front_left": {"front", "left"}, "left": {"front_left", "rear_left"},
    "rear_left": {"left", "rear"}, "rear": {"rear_left", "rear_right"}, "rear_right": {"rear", "right"},
    "right": {"rear_right", "front_right"}, "front_right": {"right", "front"},
    "roof": set(), "underbody": set(), "unknown": set(),
}


def compatible(a: Iterable[str], b: Iterable[str]) -> bool:
    """True if two zone sets overlap or touch (adjacent). Empty/unknown on either side = cannot say = True."""
    a = {z for z in a if z in ZONES and z != "unknown"}
    b = {z for z in b if z in ZONES and z != "unknown"}
    if not a or not b:
        return True
    if a & b:
        return True
    return any(_ADJ.get(x, set()) & b for x in a)


def clean(zs: Iterable[Optional[str]]) -> list[str]:
    out: list[str] = []
    for z in zs:
        if z and z in ZONES and z != "unknown" and z not in out:
            out.append(z)
    return out


def build_zone_view(narrative: Iterable[str], photo: Iterable[str], estimate: Iterable[str], unmapped_parts: int = 0) -> dict:
    n, p, e = clean(narrative), clean(photo), clean(estimate)
    pairs = {"narrative vs photo": (n, p), "narrative vs estimate": (n, e), "photo vs estimate": (p, e)}
    bad = [name for name, (x, y) in pairs.items() if x and y and not compatible(x, y)]
    note_bits = []
    if bad:
        note_bits.append("Zone sets do not overlap or touch: " + ", ".join(bad) + ".")
    if not (n and p and e):
        missing = [k for k, v in (("narrative", n), ("photo", p), ("estimate", e)) if not v]
        note_bits.append("Zone not available from: " + ", ".join(missing) + " (not a finding by itself).")
    if unmapped_parts:
        note_bits.append(f"{unmapped_parts} estimate part(s) could not be mapped to a zone and are shown as unmapped.")
    return {"narrative": n, "photo": p, "estimate": e, "mismatch": bool(bad), "note": " ".join(note_bits)}
