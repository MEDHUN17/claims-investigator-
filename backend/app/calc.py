"""Deterministic settlement waterfall (Decimal). The model never touches money.

quoted -> arithmetic-corrected -> duplicates flagged (never deleted; held out of the settlement) -> non-covered removed
(per supplied exclusions) -> depreciation per supplied schedule -> deductibles -> cap (IDV) -> proposed settlement.
ANY missing/ambiguous term, or any unverified amount, => proposed_settlement = None + `unresolved` entries.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .validate import parse_amount, normalise, receipt as _receipt

TWO = Decimal("0.01")


def q2(d: Decimal) -> Decimal:
    return d.quantize(TWO, rounding=ROUND_HALF_UP)


def s2(d: Optional[Decimal]) -> Optional[str]:
    return None if d is None else format(q2(d), "f")


def _norm_part(p: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (p or "").lower()).strip()


def _rate(x) -> Optional[Decimal]:
    """'50%' / 50 / 0.5 -> Decimal fraction 0..1."""
    if x is None:
        return None
    if isinstance(x, str):
        t = x.strip().rstrip("%")
        try:
            v = Decimal(t)
        except Exception:
            return None
        return v / 100 if (x.strip().endswith("%") or v > 1) else v
    v = Decimal(str(x))
    return v / 100 if v > 1 else v


def _material_tokens(s: str) -> set[str]:
    s = (s or "").lower()
    toks = set(re.findall(r"[a-z]+", s))
    if "fibre" in toks or "fiber" in toks:
        toks |= {"fibreglass"}
    return toks


# ---------- vehicle age (deterministic) ----------
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def parse_date(x) -> Optional[date]:
    """ISO 'YYYY-MM-DD', '14 March 2024', 'March 14, 2024', '14/03/2024' (day first, as in India) -> date; None if unparseable."""
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    t = str(x).strip()
    try:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?", t)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", t)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))
        m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{4})", t)
        if m and m[2].lower() in _MONTHS:
            return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        m = re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", t)
        if m and m[1].lower() in _MONTHS:
            return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
    except ValueError:
        return None
    return None


def _add_months(d: date, n: int) -> date:
    y, mo = divmod(d.month - 1 + n, 12)
    y, mo = d.year + y, mo + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def completed_months(registered: date, loss: date) -> Optional[int]:
    """Whole calendar months from first registration to the date of loss (None if the loss precedes registration)."""
    if loss < registered:
        return None
    m = (loss.year - registered.year) * 12 + loss.month - registered.month
    if _add_months(registered, m) > loss:
        m -= 1
    return m


def band_from_quote(quote: Optional[str]) -> Optional[tuple]:
    """Age band (min, max) in completed months, inclusive, parsed from the printed row text:
    'up to 6 months' -> (0, 6); 'more than 6 months up to 12 months' -> (7, 12); 'more than 60 months' -> (61, None)."""
    t = re.sub(r"\s+", " ", (quote or "").lower())
    m = re.search(r"(?:more than|over|above|exceeding)\s+(\d+)\s*(?:months?)?\s*(?:,|and)?\s*(?:up to|upto|to|not exceeding)\s+(\d+)\s*months?", t)
    if m:
        return int(m[1]) + 1, int(m[2])
    m = re.search(r"(?:more than|over|above|exceeding)\s+(\d+)\s*months?", t)
    if m:
        return int(m[1]) + 1, None
    m = re.search(r"(?:up to|upto|not exceeding|within)\s+(\d+)\s*months?", t)
    if m:
        return 0, int(m[1])
    return None


def vehicle_age_from_payloads(payloads: dict, passages: dict, kind_of: dict) -> dict:
    """Completed months between the policy's date of first registration and the date of loss.
    Each date must be backed by a quote found in its source (receipt); conflicting dates => not established.
    Returns {months: int|None, basis: str, problem: str|None, registration: iso|None, loss: iso|None}."""
    def collect(kind_names, getter):
        found, probs = {}, []
        for eid, p in payloads.items():
            if kind_of.get(eid, p.get("kind")) not in kind_names:
                continue
            val, quote = getter(p)
            if val in (None, ""):
                continue
            d = parse_date(val)
            if d is None:
                probs.append(f"{eid}: date {val!r} not understood")
                continue
            if quote and _receipt(quote, passages.get(eid, [])) == "unverified":
                probs.append(f"{eid}: date {val!r} could not be verified against the document text")
                continue
            if not quote and not any(str(d.year) in x.get("text", "") for x in passages.get(eid, [])):
                probs.append(f"{eid}: date {val!r} has no supporting text")
                continue
            found[d] = eid
        return found, probs

    def reg_get(p):
        v = p.get("date_of_first_registration")
        return (v.get("value"), v.get("quote")) if isinstance(v, dict) else (v, p.get("date_of_first_registration_quote"))

    def loss_get(p):
        v = p.get("date_of_loss") or p.get("date")
        if isinstance(v, dict):
            return v.get("value"), v.get("quote")
        return v, p.get("date_of_loss_quote")

    regs, p1 = collect({"policy"}, reg_get)
    losses, p2 = collect({"narrative", "estimate", "other"}, loss_get)
    out = {"months": None, "basis": "", "problem": None, "registration": None, "loss": None}
    if len(regs) > 1:
        out["problem"] = "the documents give different dates of first registration: " + ", ".join(sorted(d.isoformat() for d in regs))
    elif len(losses) > 1:
        out["problem"] = "the documents give different dates of loss: " + ", ".join(sorted(d.isoformat() for d in losses))
    elif not regs:
        out["problem"] = "date of first registration not established" + (" (" + "; ".join(p1) + ")" if p1 else " (not found in a policy page)")
    elif not losses:
        out["problem"] = "date of loss not established" + (" (" + "; ".join(p2) + ")" if p2 else " (not found in a statement or estimate)")
    else:
        reg, loss = next(iter(regs)), next(iter(losses))
        m = completed_months(reg, loss)
        out["registration"], out["loss"] = reg.isoformat(), loss.isoformat()
        if m is None:
            out["problem"] = f"date of loss {loss.isoformat()} precedes the date of first registration {reg.isoformat()}"
        else:
            out["months"] = m
            out["basis"] = f"vehicle age {m} completed months (registered {reg.isoformat()}, loss {loss.isoformat()})"
    return out


def _bands(schedule: list) -> list:
    """Copy schedule rows; an age band printed in a row's own quote (deterministic) overrides the reader's numbers."""
    out = []
    for r in schedule:
        r = dict(r)
        b = band_from_quote(r.get("quote"))
        if b is not None:
            r["age_min_months"], r["age_max_months"] = b
        out.append(r)
    return out


def _match_dep_row(line: dict, schedule: list, vehicle_age_months: Optional[int], age_problem: Optional[str] = None):
    """Find the schedule row for a PARTS line. Returns (row, problem). problem set => ambiguous/missing."""
    hay = _material_tokens(f"{line.get('material', '')} {line.get('part', '')}")
    cands = []
    for row in schedule:
        cat = _material_tokens(row.get("category", ""))
        if cat & (hay - {"and", "or", "of", "the", "part", "parts", "front", "rear", "left", "right"}):
            cands.append(row)
    if not cands:
        return None, "no depreciation row in the supplied schedule matches this part/material"
    aged = [r for r in cands if r.get("age_min_months") is not None or r.get("age_max_months") is not None]
    if aged:
        if vehicle_age_months is None:
            return None, "depreciation depends on vehicle age and the age is not established" + (f": {age_problem}" if age_problem else "")
        hits = [r for r in aged if vehicle_age_months >= (r.get("age_min_months") or 0)
                and (r.get("age_max_months") is None or vehicle_age_months <= r["age_max_months"])]
        if hits:
            return min(hits, key=lambda r: r.get("age_min_months") or 0), None
        return None, "vehicle age falls outside every age band in the schedule"
    rates = {_rate(r.get("rate")) for r in cands}
    if len(rates) > 1:
        return None, "several schedule rows match with different rates"
    return cands[0], None


def _excluded_by(line: dict, exclusions: list[dict]) -> Optional[dict]:
    pn = _norm_part(line.get("part", ""))
    for ex in exclusions:
        kws = [k.lower() for k in (ex.get("applies_to") or []) if k]
        if any(k and (k in pn) for k in kws):
            return ex
    return None


def detect_duplicates(lines: list[dict]) -> set[int]:
    """Indices of later duplicate lines: same evidence, normalised part, zone, qty and amount as an earlier line."""
    seen: dict[tuple, int] = {}
    dups: set[int] = set()
    for i, ln in enumerate(lines):
        key = (ln.get("evidence_id"), _norm_part(ln.get("part", "")), ln.get("zone") or "", str(ln.get("qty", "1")), str(parse_amount(ln.get("amount"))))
        if key in seen:
            dups.add(i)
        else:
            seen[key] = i
    return dups


def _waterfall(lines: list[dict], terms: Optional[dict], vehicle_age_months: Optional[int], dup_idx: set[int],
               zone_filter: Optional[set[str]] = None, collect: Optional[list] = None, unresolved: Optional[list] = None,
               accepted_ids: Optional[set[str]] = None, age_problem: Optional[str] = None) -> dict:
    """Core arithmetic. Returns totals; appends CalcLine dicts to `collect` and unresolved dicts to `unresolved`."""
    unresolved = unresolved if unresolved is not None else []
    terms = terms or {}
    exclusions = terms.get("exclusions") or []
    schedule = _bands(terms.get("depreciation") or [])
    idv = parse_amount(terms.get("idv"))
    ded_c, ded_v = parse_amount(terms.get("compulsory_deductible")), parse_amount(terms.get("voluntary_deductible"))
    accepted_ids = accepted_ids or set()
    covered = Decimal(0)
    dep_total = Decimal(0)
    noncov: list[str] = []
    seen_unres: set[str] = set()

    def unres(term, why, needs):
        if term not in seen_unres:
            seen_unres.add(term)
            unresolved.append({"term": term, "why": why, "needs": needs})

    for i, ln in enumerate(lines):
        if zone_filter is not None and ln.get("zone") and ln["zone"] not in zone_filter:
            continue
        amt = ln["_corrected"]
        if amt is None:
            continue
        code = f"L{i + 1:02d}"
        flag = ln.get("_flag")
        if i in dup_idx:
            continue  # held out, flagged on the base waterfall
        if exclusions or terms.get("exclusions_checked"):
            ex = _excluded_by(ln, exclusions)
            if ex:
                noncov.append(f"{code} {ln.get('part')}")
                continue
        cat = (ln.get("category") or "parts").lower()
        rate = Decimal(0)
        basis = "labour/paint/tax: not depreciated (no schedule row applies)" if cat != "parts" else ""
        if cat == "parts":
            row, problem = _match_dep_row(ln, schedule, vehicle_age_months, age_problem) if schedule else (None, "no depreciation schedule supplied")
            if problem:
                unres(f"depreciation:{ln.get('part')}", problem, "the policy page carrying the depreciation schedule; for age-banded rows also the date of first registration (policy) and the date of loss (statement)")
                continue
            rate = _rate(row.get("rate")) or Decimal(0)
            basis = f"{row.get('category')} {rate * 100:.0f}%"
            if row.get("age_min_months") is not None or row.get("age_max_months") is not None:
                lo, hi = row.get("age_min_months") or 0, row.get("age_max_months")
                basis += f" (age band {lo}-{hi if hi is not None else 'more'} months, vehicle age {vehicle_age_months})"
        ln["_dep_basis"] = basis if cat == "parts" else ""
        d = q2(amt * rate)
        dep_total += d
        covered += amt - d
    base = covered
    ded = None
    if ded_c is None and ded_v is None:
        unres("deductible", "no deductible found in the supplied policy text", "policy page with compulsory/voluntary deductible")
    else:
        ded = (ded_c or Decimal(0)) + (ded_v or Decimal(0))
        if ded_c is None:
            unres("compulsory_deductible", "compulsory deductible not found", "policy schedule page")
        if ded_v is None:
            unres("voluntary_deductible", "voluntary deductible not found (state 0 if none)", "policy schedule page")
    if idv is None:
        unres("idv", "insured declared value not found; cannot apply the cap", "policy schedule page with IDV")
    after_ded = max(Decimal(0), base - (ded or Decimal(0)))
    settle = min(after_ded, idv) if idv is not None else after_ded
    return {"covered": base, "dep": dep_total, "ded": ded, "idv": idv, "settle": settle, "noncov": noncov}


def compute(lines_in: list[dict], terms: Optional[dict], policy_present: bool, hypotheses: Optional[list[dict]] = None,
            vehicle_age_months: Optional[int] = None, quoted_total=None, accepted_line_ids: Optional[set[str]] = None,
            age_problem: Optional[str] = None, age_basis: str = "") -> dict:
    """Build a Calc dict.

    lines_in: [{part, zone, category, qty, unit, amount, evidence_id, receipt, material?, quote?, page?, id?}]
    terms: policy terms or None. hypotheses: [{id, covered_zones}] ('all' or list) for conditional settlements.
    """
    accepted = accepted_line_ids or set()
    lines = [dict(l) for l in lines_in]
    unresolved: list[dict] = []
    calc_lines: list[dict] = []
    corrections: list[str] = []

    # 1. per-line arithmetic + receipts
    for i, ln in enumerate(lines):
        code = f"L{i + 1:02d}"
        stated = parse_amount(ln.get("amount"))
        qty, unit = parse_amount(ln.get("qty")), parse_amount(ln.get("unit"))
        ln["_corrected"], ln["_flag"] = stated, None
        if ln.get("receipt") == "unverified" and str(ln.get("id", code)) not in accepted:
            ln["_corrected"] = None
            unresolved.append({"term": f"amount:{ln.get('part')}", "why": "amount could not be found in the source document (unverified receipt); excluded from the math",
                               "needs": "reviewer acceptance of this amount, or a legible copy of the estimate"})
            continue
        if stated is None:
            ln["_corrected"] = None
            unresolved.append({"term": f"amount:{ln.get('part')}", "why": "amount is missing or unreadable", "needs": "legible estimate line"})
            continue
        if qty is not None and unit is not None and q2(qty * unit) != q2(stated):
            corrected = q2(qty * unit)
            corrections.append(f"{code} {ln.get('part')}: stated {s2(stated)} but qty {qty.normalize():f} x unit {s2(unit)} = {s2(corrected)}")
            ln["_corrected"], ln["_flag"] = corrected, "arithmetic_error"
    dup_idx = detect_duplicates([{**l, "amount": l.get("amount")} for l in lines])
    duplicates = []
    for i in sorted(dup_idx):
        lines[i]["_flag"] = "duplicate_suspect"
        duplicates.append(f"L{i + 1:02d} {lines[i].get('part')}")

    recomputed = sum((l["_corrected"] for l in lines if l["_corrected"] is not None), Decimal(0))
    q_total = parse_amount(quoted_total)
    if q_total is not None and q2(q_total) != q2(recomputed) and not [u for u in unresolved if u["term"].startswith("amount:")]:
        corrections.append(f"quoted total {s2(q_total)} differs from the sum of the lines {s2(recomputed)} (difference {s2(q_total - recomputed)})")

    if not lines:
        unresolved.append({"term": "estimate", "why": "no repair estimate lines are available, so there is nothing to settle", "needs": "repair estimate"})

    # 2. policy presence
    if not policy_present or not terms:
        unresolved.append({"term": "policy", "why": "no policy terms are available; deductible, depreciation, exclusions and IDV cannot be applied",
                           "needs": "policy schedule and conditions"})
        terms = {}
    else:
        if not terms.get("exclusions"):
            unresolved.append({"term": "exclusions", "why": "no exclusions clause was found in the supplied policy pages; coverage of each line cannot be confirmed",
                               "needs": "policy page with exclusions"})
        if not terms.get("depreciation"):
            unresolved.append({"term": "depreciation", "why": "no depreciation schedule found in the supplied policy pages", "needs": "policy page with the depreciation schedule"})

    # 3. base waterfall
    res = _waterfall(lines, terms, vehicle_age_months, dup_idx, collect=calc_lines, unresolved=unresolved, accepted_ids=accepted, age_problem=age_problem)

    for i, ln in enumerate(lines):
        code = f"L{i + 1:02d}"
        calc_lines.append({"code": code, "label": str(ln.get("part") or "line"), "amount": s2(ln["_corrected"]) if ln["_corrected"] is not None else "0.00",
                           "basis": ("excluded from settlement pending review" if ln["_flag"] == "duplicate_suspect" else
                                     "arithmetic corrected" if ln["_flag"] == "arithmetic_error" else
                                     "unverified: excluded from the math" if ln["_corrected"] is None else ln.get("_dep_basis", "")),
                           "clause": ({"evidence_id": ln["evidence_id"], "page": ln.get("page"), "quote": ln.get("quote"), "zone": ln.get("zone"),
                                       "receipt": ln.get("receipt", "n/a")} if ln.get("evidence_id") else None),
                           "flag": ln["_flag"]})
    for code, label, val, flag in (("QUOTED", "Quoted total", q_total, None), ("RECOMPUTED", "Recomputed total (sum of lines)", recomputed, None)):
        if val is not None:
            calc_lines.append({"code": code, "label": label, "amount": s2(val), "basis": "", "clause": None, "flag": flag})
    if res["noncov"]:
        pass
    calc_lines.append({"code": "DEPR", "label": "Depreciation (supplied schedule)", "amount": s2(res["dep"]), "basis": age_basis if vehicle_age_months is not None else "", "clause": None, "flag": "depreciated" if res["dep"] else None})
    calc_lines.append({"code": "COVERED", "label": "Covered loss after depreciation", "amount": s2(res["covered"]), "basis": "", "clause": None, "flag": None})
    if res["ded"] is not None:
        calc_lines.append({"code": "DEDUCT", "label": "Deductibles (compulsory + voluntary)", "amount": s2(res["ded"]), "basis": "", "clause": None, "flag": None})
    if res["idv"] is not None:
        calc_lines.append({"code": "IDV", "label": "Insured declared value (cap)", "amount": s2(res["idv"]), "basis": "", "clause": None, "flag": None})

    blocked = bool(unresolved)
    settlement = None if blocked else res["settle"]
    if settlement is not None:
        calc_lines.append({"code": "SETTLE", "label": "Proposed settlement (draft for reviewer)", "amount": s2(settlement), "basis": "", "clause": None, "flag": None})

    # 4. conditionals per hypothesis (same terms, only the lines attributable under that hypothesis)
    conditional = []
    for h in hypotheses or []:
        cz = h.get("covered_zones", "all")
        if blocked:
            conditional.append({"hypothesis_id": h["id"], "settlement": None, "note": "cannot be computed: the unresolved terms above block the waterfall"})
            continue
        if cz in (None, [], "unknown"):
            conditional.append({"hypothesis_id": h["id"], "settlement": None, "note": "the zones attributable under this hypothesis were not stated"})
            continue
        zset = None if cz == "all" else set(cz)
        sub = _waterfall(lines, terms, vehicle_age_months, dup_idx, zone_filter=zset, unresolved=[], accepted_ids=accepted, age_problem=age_problem)
        unm = sum(1 for l in lines if not l.get("zone"))
        note = "all estimate lines attributable" if zset is None else "only lines in zones " + ", ".join(sorted(zset)) + " attributable"
        if unm and zset is not None:
            note += f"; {unm} unmapped line(s) counted in every case"
        conditional.append({"hypothesis_id": h["id"], "settlement": s2(sub["settle"]), "note": note})

    return {"currency": "INR", "lines": calc_lines, "quoted_total": s2(q_total), "recomputed_total": s2(recomputed),
            "arithmetic_corrections": corrections, "duplicates": duplicates, "non_covered": res["noncov"],
            "depreciation": s2(res["dep"]), "deductible": s2(res["ded"]), "covered_loss": s2(res["covered"]),
            "proposed_settlement": s2(settlement) if settlement is not None else None, "unresolved": unresolved, "conditional": conditional}
