"""Five universal gates, run on EVERY analysis including the jury's upload."""
from __future__ import annotations

from decimal import Decimal

from pydantic import ValidationError

from .contracts import CaseState
from .validate import find_forbidden, parse_amount, receipt


def run_gates(state: dict, passages_by_evidence: dict[str, list[dict]]) -> list[dict]:
    res = []
    # 1 schema
    try:
        cs = CaseState.model_validate(state)
        detail = "CaseState validates"
        ok = True
        if cs.hypotheses:
            kinds = {h.kind for h in cs.hypotheses}
            if not any(h.benign for h in cs.hypotheses):
                ok, detail = False, "no benign hypothesis present"
            elif not (kinds & {"data_error", "misassociation"}):
                ok, detail = False, "no data-error hypothesis present"
            else:
                detail += "; benign and data-error hypotheses present"
        res.append({"name": "schema", "passed": ok, "detail": detail})
    except ValidationError as e:
        res.append({"name": "schema", "passed": False, "detail": f"{len(e.errors())} schema error(s): {e.errors()[0]['loc']}"})
        cs = None
    # 2 citations resolve
    bad, checked = [], 0
    ids = set(state.get("evidence_ids", []))
    refs = []
    for f in state.get("findings", []):
        refs += [(f["id"], r) for r in f.get("supports", []) + f.get("contradicts", [])]
    for t in state.get("timeline", []):
        refs += [(f"timeline {t.get('order')}", r) for r in t.get("refs", [])]
    rank_ = {"unverified": 0, "n/a": 0, "partial": 1, "matched": 2}
    for who, r in refs:
        checked += 1
        if r.get("evidence_id") not in ids:
            bad.append(f"{who}: unknown evidence {r.get('evidence_id')}")
        elif r.get("quote"):
            # the label on the citation must be TRUE: re-verify the quote against the stored source text.
            actual = receipt(r["quote"], passages_by_evidence.get(r["evidence_id"], []), r.get("page"))
            claimed = r.get("receipt", "n/a")
            if actual == "unverified" and claimed != "unverified":
                bad.append(f"{who}: quote not found in {r['evidence_id']} but marked {claimed}")
            elif claimed in ("matched", "partial") and rank_[actual] < rank_[claimed]:
                bad.append(f"{who}: quote only {actual} in {r['evidence_id']} but marked {claimed}")
    for c in state.get("matrix", []):
        if c["relation"] != "neutral" and c.get("receipt") not in ("matched", "partial"):
            bad.append(f"matrix {c['hypothesis_id']}x{c['evidence_id']}: non-neutral cell without receipt")
    res.append({"name": "citations", "passed": not bad, "detail": f"{checked} citation(s) checked" + ("" if not bad else "; " + "; ".join(bad[:4]))})
    # 3 language
    sources = [p.get("text", "") for ps in passages_by_evidence.values() for p in ps]
    texts = [state.get("summary", ""), state.get("recommendation", "")]
    for f in state.get("findings", []):
        texts += [f.get("title", ""), f.get("body", ""), f.get("uncertainty", ""), f.get("action", "")] + list(f.get("alternatives", []))
    texts += [h.get("text", "") for h in state.get("hypotheses", [])] + [r.get("text", "") for r in state.get("requests", [])]
    forb = [w for t in texts for w in find_forbidden(t, sources)]
    res.append({"name": "language", "passed": not forb, "detail": "no accusation language outside quoted source spans" if not forb else "found: " + ", ".join(sorted(set(forb)))})
    # 4 math recompute
    calc = state.get("calc")
    if not calc:
        res.append({"name": "math", "passed": True, "detail": "no calc block (nothing to recompute)"})
    else:
        probs = []
        lsum = sum((parse_amount(l["amount"]) or Decimal(0) for l in calc["lines"] if l["code"].startswith("L") and l["code"][1:].isdigit()), Decimal(0))
        if calc.get("recomputed_total") is not None and Decimal(calc["recomputed_total"]) != lsum.quantize(Decimal("0.01")):
            probs.append(f"recomputed_total {calc['recomputed_total']} != sum of lines {lsum}")
        if calc.get("proposed_settlement") is not None:
            if calc.get("unresolved"):
                probs.append("settlement present despite unresolved terms")
            cov, ded = parse_amount(calc.get("covered_loss")), parse_amount(calc.get("deductible"))
            idv = next((parse_amount(l["amount"]) for l in calc["lines"] if l["code"] == "IDV"), None)
            if cov is None or ded is None or idv is None:
                probs.append("settlement present but covered loss / deductible / IDV missing")
            else:
                exp = min(max(Decimal(0), cov - ded), idv)
                if exp.quantize(Decimal("0.01")) != Decimal(calc["proposed_settlement"]):
                    probs.append(f"settlement {calc['proposed_settlement']} != recomputed {exp}")
        elif not calc.get("unresolved"):
            probs.append("no settlement and no unresolved reason")
        res.append({"name": "math", "passed": not probs, "detail": "Decimal waterfall recomputes" if not probs else "; ".join(probs)})
    # 5 no unverified value in math
    if calc:
        leaked = [l["code"] for l in calc["lines"] if l.get("clause") and l["clause"].get("receipt") == "unverified"
                  and l.get("flag") is None and l["amount"] not in ("0.00", None) and "unverified" not in (l.get("basis") or "")]
        ok = not leaked
        res.append({"name": "unverified", "passed": ok, "detail": "no unverified amount enters the settlement" if ok else "unverified amounts in math: " + ", ".join(leaked)})
    else:
        res.append({"name": "unverified", "passed": True, "detail": "no calc block"})
    return res
