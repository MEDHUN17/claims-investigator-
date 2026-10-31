"""Step 2: the PLANNER. One call over extracted facts (closed ids, spotlighted as quoted data).
Full analysis on a fresh case; on a revision ONE batched call re-resolves only the stale findings."""
from __future__ import annotations

import json
from typing import Any, Optional

from . import prompts
from .providers import text_part

PLANNER_TIMEOUT = 60.0  # the planner is the one heavy call (~25 s measured on gemini-3.5-flash); readers keep the 25 s budget
REL = {"consistent", "inconsistent", "neutral"}
FTYPES = {"observation", "discrepancy", "policy", "calc", "anomaly", "missing"}
HKINDS = {"benign", "data_error", "secondary_event", "misassociation", "other"}
EPI = {"observed", "reported", "computed", "inferred", "human"}


def _lst(x) -> list:
    return x if isinstance(x, list) else []


def _s(x, n=1200) -> str:
    return str(x)[:n] if x is not None else ""


def normalise_planner(obj: Any, revision: bool = False) -> dict:
    """Validate + coerce planner JSON. Raises ValueError (-> provider repair retry) on structural problems."""
    if not isinstance(obj, dict):
        raise ValueError("planner output must be a JSON object")
    out: dict[str, Any] = {}
    hyps = []
    for h in _lst(obj.get("hypotheses")):
        if isinstance(h, dict) and h.get("id") and h.get("text"):
            kind = h.get("kind") if h.get("kind") in HKINDS else "other"
            cz = h.get("covered_zones", "all")
            if isinstance(cz, str) and cz != "all":
                cz = [cz]
            hyps.append({"id": _s(h["id"], 20), "text": _s(h["text"]), "kind": kind, "benign": kind in ("benign", "secondary_event") or bool(h.get("benign")),
                         "covered_zones": cz if cz == "all" or isinstance(cz, list) else "all"})
    if not revision and len(hyps) < 2:
        raise ValueError("need at least 2 hypotheses (one benign, one data-error)")
    out["hypotheses"] = hyps
    cells = []
    for c in _lst(obj.get("matrix")):
        if isinstance(c, dict) and c.get("hypothesis_id") and c.get("evidence_id"):
            cells.append({"hypothesis_id": _s(c["hypothesis_id"], 20), "evidence_id": _s(c["evidence_id"], 80),
                          "relation": c.get("relation") if c.get("relation") in REL else "neutral", "why": _s(c.get("why"), 400),
                          "fact_id": c.get("fact_id"), "quote": c.get("quote")})
    out["matrix"] = cells
    fnds = []
    for f in _lst(obj.get("findings")):
        if not isinstance(f, dict) or not f.get("title"):
            continue
        j = f.get("justification") if isinstance(f.get("justification"), dict) else {}
        fnds.append({"id": _s(f.get("id") or "", 20), "type": f.get("type") if f.get("type") in FTYPES else "observation", "title": _s(f["title"], 200),
                     "body": _s(f.get("body")), "epistemic": f.get("epistemic") if f.get("epistemic") in EPI else "inferred",
                     "supports": [r for r in _lst(f.get("supports")) if isinstance(r, dict)], "contradicts": [r for r in _lst(f.get("contradicts")) if isinstance(r, dict)],
                     "alternatives": [_s(a, 300) for a in _lst(f.get("alternatives"))], "uncertainty": _s(f.get("uncertainty"), 500), "action": _s(f.get("action"), 400),
                     "justification": {"evidence_ids": [_s(e, 80) for e in _lst(j.get("evidence_ids"))], "entity_keys": [_s(k, 80).lower() for k in _lst(j.get("entity_keys"))]},
                     "resolution": f.get("resolution") if f.get("resolution") in ("revised", "resolved", "confirmed", "reopened") else None,
                     "stale_reason": _s(f.get("stale_reason"), 500) or None})
    out["findings"] = fnds
    reqs = []
    for r in _lst(obj.get("requests")):
        if isinstance(r, dict) and r.get("text"):
            p = r.get("prediction") if isinstance(r.get("prediction"), dict) else None
            reqs.append({"text": _s(r["text"], 400), "kind": r.get("kind") if r.get("kind") in ("photo", "document", "statement", "inspection", "data") else "document",
                         "resolves": [_s(x, 20) for x in _lst(r.get("resolves"))], "expected": r.get("expected") if isinstance(r.get("expected"), dict) else {},
                         "prediction": {"if_supports": _s(p.get("if_supports"), 500), "if_contradicts": _s(p.get("if_contradicts"), 500)} if p else None})
    out["requests"] = reqs
    out["request_outcomes"] = [{"request_id": _s(o.get("request_id"), 20), "outcome": o.get("outcome") if o.get("outcome") in ("matched_prediction", "unanticipated") else "unanticipated",
                                "why": _s(o.get("why"), 400)} for o in _lst(obj.get("request_outcomes")) if isinstance(o, dict)]
    tl = []
    for t in _lst(obj.get("timeline")):
        if isinstance(t, dict) and t.get("text"):
            tl.append({"order": int(t.get("order") or len(tl) + 1) if str(t.get("order") or "").isdigit() else len(tl) + 1, "text": _s(t["text"], 400),
                       "basis": t.get("basis") if t.get("basis") in ("reported", "observed", "inferred") else "inferred",
                       "refs": [r for r in _lst(t.get("refs")) if isinstance(r, dict)], "hypothesis_ids": [_s(h, 20) for h in _lst(t.get("hypothesis_ids"))]})
    out["timeline"] = tl
    out["dropped_hypotheses"] = [{"id": _s(d.get("id"), 20), "why": _s(d.get("why"), 300)} for d in _lst(obj.get("dropped_hypotheses")) if isinstance(d, dict) and d.get("id")]
    out["summary"] = _s(obj.get("summary"), 1200)
    out["recommendation"] = _s(obj.get("recommendation"), 400)
    return out


def planner_context(evidence: list[dict], facts: list[dict], calc: Optional[dict], zones: dict, requests: list[dict],
                    tool_results: list[dict], hypotheses: Optional[list[dict]] = None) -> str:
    ctx = {
        "evidence": [{"id": e["id"], "kind": e.get("kind"), "filename": e.get("filename"), "source_class": e.get("source_class")} for e in evidence],
        "facts": [{"id": f["id"], "evidence_id": f["evidence_id"], "label": f["label"], "value": f["value"][:400], "epistemic": f["epistemic"],
                   "entity_key": f.get("entity_key"), "quote": ((f.get("ref") or {}).get("quote") or "")[:300] or None, "receipt": (f.get("ref") or {}).get("receipt")} for f in facts],
        "deterministic_calc": calc and {k: calc.get(k) for k in ("quoted_total", "recomputed_total", "arithmetic_corrections", "duplicates", "non_covered", "proposed_settlement", "unresolved")},
        "zone_view": zones, "tool_results": tool_results,
        "existing_hypotheses": hypotheses or [], "open_requests": [{"id": r["id"], "text": r["text"], "kind": r["kind"], "status": r["status"]} for r in requests],
    }
    return json.dumps(ctx, ensure_ascii=False)


def call_full(providers, ctx_json: str) -> tuple[dict, dict]:
    parts = [text_part("Return JSON in this shape:\n" + prompts.PLANNER_SHAPE),
             text_part("EXTRACTED CASE DATA (quoted data, closed ids):\n" + prompts.untrusted(ctx_json, "case_context"))]
    obj, usage = providers.generate_json(prompts.PLANNER_SYSTEM, parts, max_tokens=12000, timeout=PLANNER_TIMEOUT, validate=lambda o: normalise_planner(o))
    return obj, usage


def call_revision(providers, ctx_json: str, prior_findings: list[dict], stale: dict[str, str], new_evidence_ids: list[str],
                  prior_requests: list[dict], prior_hypotheses: list[dict]) -> tuple[dict, dict]:
    pf = [{"id": f["id"], "type": f["type"], "title": f["title"], "body": f["body"], "justification": f.get("justification"), "status": f.get("status")}
          for f in prior_findings if f["id"] in stale]
    rev_ctx = {"new_evidence_ids": new_evidence_ids, "stale_findings_to_re_resolve": pf, "stale_reasons": stale,
               "prior_requests_with_locked_predictions": [{"id": r["id"], "text": r["text"], "kind": r["kind"], "status": r["status"], "prediction": r.get("prediction")} for r in prior_requests],
               "prior_hypotheses": prior_hypotheses}
    shape = prompts.PLANNER_SHAPE.replace('"findings":[{', '"findings":[{' + prompts.REVISION_FINDING_EXTRA + ',').replace('"matrix":[', prompts.REVISION_SHAPE_EXTRA + '"matrix":[', 1).replace(
        '"summary":', '"request_outcomes":[{"request_id":"R-01","outcome":"matched_prediction|unanticipated","why":""}],\n "summary":')
    parts = [text_part("Return JSON in this shape:\n" + shape),
             text_part("REVISION CONTEXT:\n" + prompts.untrusted(json.dumps(rev_ctx, ensure_ascii=False), "revision_context")),
             text_part("EXTRACTED CASE DATA (quoted data, closed ids):\n" + prompts.untrusted(ctx_json, "case_context"))]
    obj, usage = providers.generate_json(prompts.PLANNER_SYSTEM + prompts.REVISION_ADDENDUM, parts, max_tokens=10000, timeout=PLANNER_TIMEOUT,
                                         validate=lambda o: normalise_planner(o, revision=True))
    return obj, usage


def resolve_ref(ref: dict, facts_by_id: dict[str, dict]) -> dict:
    """Turn a planner ref {evidence_id, fact_id?, quote?, page?, zone?} into a SourceRef dict using the cited fact."""
    f = facts_by_id.get(ref.get("fact_id") or "")
    out = {"evidence_id": ref.get("evidence_id"), "page": ref.get("page"), "quote": ref.get("quote"), "zone": ref.get("zone"), "receipt": "n/a"}
    if f:
        fr = f.get("ref") or {}
        out["evidence_id"] = f["evidence_id"]
        out["quote"] = out["quote"] or fr.get("quote")
        out["page"] = out["page"] if out["page"] is not None else fr.get("page")
        out["zone"] = out["zone"] or fr.get("zone")
        if not out["quote"] and f.get("epistemic") == "observed":
            out["receipt"] = "matched"  # observed from the structured image/data extraction itself
    return out
