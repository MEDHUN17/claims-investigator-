"""Pipeline: extract -> deterministic checks -> planner -> validate -> rank/calc -> invalidate/delta -> commit.

`run_revision` is the single entry point INFRA's worker calls. It degrades loudly: if no provider works, the deterministic
parts still produce a state, LLM sections are marked unavailable, stale findings stay stale, and requests ask for what is needed.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from . import analyze, calc as calcmod, extract as extractmod, invalidate, rank, validate, zones as zonesmod
from .contracts import CaseState
from .providers import ProviderUnavailable
from .tools import ToolRegistry
from .validate import parse_amount, receipt, _amounts_in

DET_PREFIX = ("F-C", "F-Z", "F-I", "F-M")  # deterministic finding ids: recomputed every revision, never sent to the model
REQ_PREFIX = ("Needed to compute the settlement:", "Provide a legible", "AI analysis was unavailable", "Provide a transcript", "Provide the missing")


class Plan:
    def __init__(self, repo, job_id):
        self.repo, self.job_id, self.steps = repo, job_id, []

    def add(self, name: str, reason: str = ""):
        self.steps.append({"name": name, "status": "pending", "reason": reason})
        self._push()

    def set(self, name: str, status: str, reason: str = ""):
        for s in self.steps:
            if s["name"] == name:
                s["status"] = status
                if reason:
                    s["reason"] = reason
        self._push()

    def _push(self):
        if self.job_id is not None:
            try:
                self.repo.set_job_plan(self.job_id, [dict(s) for s in self.steps])
            except Exception:
                pass


def _needs_extract(repo, e: dict) -> bool:
    if e.get("status") == "unsupported":
        return False
    x = repo.latest_extraction(e["id"])
    if x is None:
        return True
    return bool(x["payload"].get("unavailable")) and not x.get("human_corrected")


def _stage(repo, case_id, name, args, result, status, t0):
    try:
        repo.log_event(case_id, "stage", name, args, result, status, int((time.time() - t0) * 1000))
    except Exception:
        pass


def _provider_event(repo, case_id, name, usage):
    try:
        repo.log_event(case_id, "provider", name, {"provider": usage.get("provider"), "model": usage.get("model"), "role": usage.get("role")},
                       {k: usage.get(k) for k in ("tokens_in", "tokens_out", "cached", "latency_ms", "fallbacks")}, "ok", int(usage.get("latency_ms") or 0))
    except Exception:
        pass


# ---------- facts ----------
def build_facts(evidence: list[dict], payloads: dict[str, dict], passages: dict[str, list[dict]]) -> list[dict]:
    facts: list[dict] = []
    n = 0
    for e in sorted(evidence, key=lambda x: (x.get("uploaded_at") or "", x["id"])):
        p = payloads.get(e["id"])
        if not p or p.get("unreadable"):
            continue
        ev = {"id": e["id"]}
        p = dict(p)
        p.setdefault("kind", e.get("kind"))
        for f in extractmod.facts_from_payload(ev, p):
            n += 1
            f["id"] = f"X-{n:03d}"
            ref = f.get("ref")
            if ref:
                if ref.get("quote"):
                    ref["receipt"] = receipt(ref["quote"], passages.get(e["id"], []), ref.get("page"))
                elif f["epistemic"] == "observed":
                    ref["receipt"] = "matched"
            facts.append(f)
    return facts


# ---------- calc inputs ----------
def calc_inputs(evidence, payloads, passages):
    lines, quoted, policy_present, problems = [], None, False, []
    terms: dict[str, Any] = {"depreciation": [], "exclusions": []}
    for e in evidence:
        p = payloads.get(e["id"]) or {}
        kind = p.get("kind") or e.get("kind")
        if kind == "estimate":
            for li in p.get("line_items", []):
                quote = li.get("quote")
                amt = parse_amount(li.get("amount"))
                pas = passages.get(e["id"], [])
                if amt is None:
                    rc = "unverified"
                elif quote:
                    rc = receipt(quote, pas)
                    if rc != "unverified" and amt.normalize() not in _amounts_in(quote, csv_cells=True):
                        rc = "unverified"  # the printed row does not contain the amount the reader reported
                else:
                    rc = "matched" if any(amt.normalize() in _amounts_in(x["text"]) for x in pas) else "unverified"
                lines.append({**li, "evidence_id": e["id"], "receipt": rc})
            q = p.get("quoted_total")
            qv = q.get("value") if isinstance(q, dict) else q
            if qv is not None and quoted is None:
                quoted = qv
        elif kind == "policy":
            policy_present = True
            t = p.get("terms") or {}
            pas = passages.get(e["id"], [])
            for k in ("idv", "compulsory_deductible", "voluntary_deductible"):
                v = t.get(k)
                val, quote = (v.get("value"), v.get("quote")) if isinstance(v, dict) else (v, None)
                if val is None or terms.get(k) is not None:
                    continue
                if quote and receipt(quote, pas) == "unverified":
                    problems.append(f"policy {k} could not be verified against the policy text and was not used")
                    continue
                terms[k] = val
            for d in t.get("depreciation") or []:
                if d.get("quote") and receipt(d["quote"], pas, d.get("page")) == "unverified":
                    problems.append(f"depreciation row {d.get('category')!r} could not be verified and was not used")
                    continue
                terms["depreciation"].append(d)
            for x in t.get("exclusions") or []:
                if x.get("quote") and receipt(x["quote"], pas, x.get("page")) == "unverified":
                    problems.append("an exclusion could not be verified against the policy text and was not used")
                    continue
                terms["exclusions"].append(x)
    return lines, quoted, policy_present, (terms if policy_present else None), problems


def zone_inputs(evidence, payloads):
    narr, photo, est, unmapped = [], [], [], 0
    for e in evidence:
        p = payloads.get(e["id"]) or {}
        k = p.get("kind") or e.get("kind")
        if k == "narrative":
            if p.get("claimed_impact_zone"):
                narr.append(p["claimed_impact_zone"])
            narr += list(p.get("secondary_impact_zones") or [])
        elif k == "photo":
            photo += [d.get("zone") for d in p.get("damage", [])] + list(p.get("zones", []))
        elif k == "estimate":
            for li in p.get("line_items", []):
                if li.get("zone"):
                    est.append(li["zone"])
                else:
                    unmapped += 1
    return zonesmod.build_zone_view(narr, photo, est, unmapped)


# ---------- deterministic findings ----------
def det_findings(calc: Optional[dict], zv: dict, inj: list[dict], fname: dict[str, str], est_ids: list[str], pol_ids: list[str],
                 payloads: dict[str, dict], extra_missing: list[tuple[str, str]], rev: int) -> list[dict]:
    out: list[dict] = []

    def F(id_, type_, title, body, ev_ids, keys, supports=None, action="", epi="computed"):
        out.append({"id": id_, "type": type_, "title": title, "body": body, "epistemic": epi, "status": "active", "supports": supports or [],
                    "contradicts": [], "alternatives": [], "uncertainty": "", "action": action,
                    "justification": {"evidence_ids": sorted(set(ev_ids)), "entity_keys": sorted(set(keys))}, "since_rev": rev,
                    "revised_rev": None, "prior_body": None, "stale_reason": None})

    if calc:
        akey = lambda s: "amount:" + (str(int(parse_amount(s))) if parse_amount(s) is not None and parse_amount(s) == parse_amount(s).to_integral() else str(parse_amount(s)))
        if calc["arithmetic_corrections"]:
            keys = [akey(calc["quoted_total"])] if calc.get("quoted_total") else []
            keys += [akey(l["amount"]) for l in calc["lines"] if l.get("flag") == "arithmetic_error"]
            F("F-C1", "calc", "Estimate arithmetic does not recompute", " ".join(calc["arithmetic_corrections"]) +
              f" Recomputed total {calc['recomputed_total']} (quoted {calc['quoted_total']}).", est_ids, keys,
              [l["clause"] for l in calc["lines"] if l.get("flag") == "arithmetic_error" and l.get("clause")][:4], "Confirm the correct figure with the garage.")
        if calc["duplicates"]:
            keys = [akey(l["amount"]) for l in calc["lines"] if l.get("flag") == "duplicate_suspect"]
            F("F-C2", "calc", "Possible duplicated estimate line", "Flagged (not deleted) and held out of the proposed settlement pending review: " + "; ".join(calc["duplicates"]) + ".",
              est_ids, keys, [l["clause"] for l in calc["lines"] if l.get("flag") == "duplicate_suspect" and l.get("clause")][:3], "Reviewer to confirm whether the line was charged twice.")
        if calc["unresolved"]:
            keymap = {"depreciation": "clause:depreciation", "exclusions": "clause:exclusions", "deductible": "clause:deductible",
                      "compulsory_deductible": "clause:deductible", "voluntary_deductible": "clause:deductible", "idv": "clause:idv", "policy": "clause:policy"}
            keys = [keymap.get(u["term"].split(":")[0], "") for u in calc["unresolved"]]
            F("F-C3", "calc", "Settlement cannot be computed: unresolved terms",
              "No settlement is proposed. Unresolved: " + "; ".join(f"{u['term']} ({u['why']})" for u in calc["unresolved"]) + ".", est_ids + pol_ids,
              [k for k in keys if k] + ["clause:policy"], action="Obtain: " + "; ".join(sorted({u["needs"] for u in calc["unresolved"]})))
        elif calc.get("proposed_settlement") is not None:
            F("F-C4", "calc", "Draft settlement computed from supplied terms", f"Draft settlement {calc['proposed_settlement']} {calc['currency']} (covered loss {calc['covered_loss']}, "
              f"deductibles {calc['deductible']}). A human reviewer decides; this is not an approval.", est_ids + pol_ids,
              ["clause:depreciation", "clause:exclusions", "clause:deductible", "clause:idv"] + [akey(l["amount"]) for l in calc["lines"] if l["code"].startswith("L") and l["code"][1:].isdigit()][:12])
    if zv.get("mismatch"):
        keys = [f"zone:{z}" for z in zv["narrative"] + zv["photo"] + zv["estimate"]]
        F("F-Z1", "discrepancy", "Damage zones differ between sources",
          f"Narrative zone(s): {', '.join(zv['narrative']) or 'none'}; photo zone(s): {', '.join(zv['photo']) or 'none'}; estimate zone(s): {', '.join(zv['estimate']) or 'none'}. {zv['note']}",
          est_ids + [e for e, p in payloads.items() if (p.get("kind") in ("narrative", "photo"))], keys, action="See the ranked evidence request.")
    for i, fl in enumerate(inj, start=1):
        F(f"F-I{i}", "anomaly", f"Instruction-like text found in {fname.get(fl['evidence_id'], fl['evidence_id'])}",
          f"The document contains text addressed to a reader/system: {fl['text']!r}. It was recorded and NOT followed; it does not affect the analysis.",
          [fl["evidence_id"]], [], [{"evidence_id": fl["evidence_id"], "quote": fl["text"][:200], "page": None, "zone": None, "receipt": "n/a"}], epi="observed")
    for i, (eid, why) in enumerate(extra_missing, start=1):
        F(f"F-M{i}", "missing", f"{fname.get(eid, eid)} could not be analysed", why, [eid], [], action="Provide what is described in the request.")
    return out


def _kind_matches(req_kind: str, ev_kind: str) -> bool:
    return {"photo": ev_kind == "photo", "statement": ev_kind == "narrative", "document": ev_kind in ("estimate", "policy", "history", "other", "narrative"),
            "inspection": ev_kind in ("other", "photo", "narrative"), "data": ev_kind in ("telematics", "history", "metadata", "other")}.get(req_kind, False)


# ---------- main ----------
def run_revision(repo, case_id: str, base_rev: int, trigger_evidence_id: Optional[str], job_id, providers, emit=None) -> int:
    t_all = time.time()
    plan = Plan(repo, job_id)
    evidence = repo.evidence_list(case_id)
    fname = {e["id"]: e.get("filename", e["id"]) for e in evidence}
    todo = [e for e in evidence if _needs_extract(repo, e)]
    plan.add("ingest")
    for e in todo:
        plan.add(f"extract:{e['id']}")
    for n in ("analyze", "validate", "invalidate", "persist"):
        plan.add(n)
    plan.set("ingest", "done", f"{len(evidence)} evidence item(s)")

    # 1. extract
    for e in todo:
        t0 = time.time()
        plan.set(f"extract:{e['id']}", "running")
        try:
            payload = extractmod.extract_evidence(repo, e["id"], providers, ev=e)
            if payload.get("usage"):
                _provider_event(repo, case_id, f"extract:{e['id']}", payload["usage"])
            st = "failed" if payload.get("unavailable") or payload.get("unreadable") else "done"
            plan.set(f"extract:{e['id']}", st, payload.get("reason", "") if st == "failed" else f"kind={payload.get('kind')}")
            _stage(repo, case_id, f"extract:{e['id']}", {"filename": fname[e["id"]]}, {"kind": payload.get("kind"), "unavailable": bool(payload.get("unavailable"))}, "ok" if st == "done" else "degraded", t0)
        except Exception as ex:  # one bad file must not kill the run, but it must be loud
            plan.set(f"extract:{e['id']}", "failed", f"{type(ex).__name__}: {str(ex)[:120]}")
            _stage(repo, case_id, f"extract:{e['id']}", {"filename": fname[e["id"]]}, {"error": f"{type(ex).__name__}: {str(ex)[:200]}"}, "error", t0)
    evidence = repo.evidence_list(case_id)  # statuses/kinds updated by extraction

    payloads, passages = {}, {}
    for e in evidence:
        x = repo.latest_extraction(e["id"])
        if x:
            payloads[e["id"]] = dict(x["payload"])
            payloads[e["id"]].setdefault("kind", e.get("kind"))
        passages[e["id"]] = repo.passages(e["id"])
    ev_ids = [e["id"] for e in evidence]
    kind_of = {e["id"]: (payloads.get(e["id"], {}).get("kind") or e.get("kind") or "other") for e in evidence}

    # 2. prior state + what changed
    prior = repo.get_state(case_id, base_rev) if base_rev else None
    prior_ids = set((prior or {}).get("evidence_ids", []))
    changed = {trigger_evidence_id} if trigger_evidence_id else set()
    new_ids = {i for i in ev_ids if i not in prior_ids} if prior else set(ev_ids)
    changed_or_new = (changed | new_ids) & set(ev_ids) if prior else set()
    new_keys, new_kinds, keys_ok = set(), set(), True
    for eid in changed_or_new:
        p = payloads.get(eid)
        new_kinds.add(kind_of.get(eid, "other"))
        if not p or p.get("unavailable") or p.get("unreadable"):
            keys_ok = False
            continue
        ks = invalidate.keys_from_extraction({"facts": extractmod.facts_from_payload({"id": eid}, p)})
        if not ks:
            keys_ok = False
        new_keys |= ks
    stale: dict[str, str] = {}
    if prior and changed_or_new:
        stale = invalidate.stale_set(prior, changed | new_ids, new_keys, new_kinds, keys_extractable=keys_ok and bool(new_keys))
    if prior:  # findings left stale by an earlier degraded run are re-checked now
        for f in prior.get("findings", []):
            if f.get("status") == "stale" and f["id"] not in stale:
                stale[f["id"]] = f.get("stale_reason") or "left stale by an earlier run"

    # 3. deterministic layer
    new_rev = base_rev + 1
    facts = build_facts(evidence, payloads, passages)
    facts_by_id = {f["id"]: f for f in facts}
    zv = zone_inputs(evidence, payloads)
    lines, quoted, policy_present, terms, term_problems = calc_inputs(evidence, payloads, passages)
    age = calcmod.vehicle_age_from_payloads(payloads, passages, kind_of) if policy_present else {"months": None, "basis": "", "problem": None}
    if policy_present:
        _stage(repo, case_id, "vehicle_age", {}, {k: age.get(k) for k in ("months", "registration", "loss", "problem")}, "ok" if age["months"] is not None else "unresolved", time.time())
    calc0 = (calcmod.compute(lines, terms, policy_present, hypotheses=None, quoted_total=quoted, vehicle_age_months=age["months"], age_problem=age["problem"], age_basis=age["basis"])
             if (lines or policy_present) else None)
    inj = [{"evidence_id": eid, "text": t} for eid, p in payloads.items() for t in (p.get("injection_flags") or [])]
    missing = []
    for e in evidence:
        p = payloads.get(e["id"], {})
        if p.get("unsupported"):
            missing.append((e["id"], p.get("reason", "unsupported file type")))
        elif p.get("unreadable") or e.get("status") == "failed" and not p.get("unavailable"):
            missing.append((e["id"], "The file could not be read: " + (e.get("error") or "unreadable") + "."))
    ai_down = [e["id"] for e in evidence if payloads.get(e["id"], {}).get("unavailable")]
    for eid in ai_down:
        missing.append((eid, "The AI reader was unavailable, so this file was stored and hashed but its content was not extracted: " + payloads[eid].get("reason", "")))
    est_ids = [e for e in ev_ids if kind_of[e] == "estimate"]
    pol_ids = [e for e in ev_ids if kind_of[e] == "policy"]

    # tools: weather (only when coordinates and date are known)
    tools = ToolRegistry(repo, case_id)
    for eid, p in payloads.items():
        if p.get("kind") == "narrative" and p.get("date") and p.get("latitude") is not None and p.get("longitude") is not None:
            try:
                tools.call("weather_lookup", {"date": str(p["date"]), "lat": float(p["latitude"]), "lon": float(p["longitude"])})
            except (TypeError, ValueError):
                pass

    # 4. planner (the only LLM reasoning step)
    plan.set("analyze", "running")
    planner_out, analysis_error = None, None
    prior_reqs = (prior or {}).get("requests", [])
    n_extracted_ok = sum(1 for e in ev_ids if payloads.get(e) and not payloads[e].get("unavailable") and not payloads[e].get("unreadable"))
    revision_mode = bool(prior and prior.get("hypotheses"))
    t0 = time.time()
    if n_extracted_ok == 0:
        analysis_error = "no evidence has been extracted yet"
    else:
        ctx = analyze.planner_context([{**e, "kind": kind_of[e["id"]]} for e in evidence], facts, calc0, zv, prior_reqs, tools.results,
                                      hypotheses=(prior or {}).get("hypotheses"))
        try:
            if revision_mode:
                re_resolve = {fid: r for fid, r in stale.items() if not fid.startswith(DET_PREFIX)}
                if re_resolve or changed_or_new:
                    planner_out, usage = analyze.call_revision(providers, ctx, prior["findings"], re_resolve, sorted(changed_or_new), prior_reqs, prior["hypotheses"])
                else:
                    planner_out, usage = {"hypotheses": [], "matrix": [], "findings": [], "requests": [], "request_outcomes": [], "timeline": [], "summary": "", "recommendation": ""}, None
            else:
                planner_out, usage = analyze.call_full(providers, ctx)
            if usage:
                _provider_event(repo, case_id, "planner", usage)
        except ProviderUnavailable as e:
            analysis_error = str(e)[:300]
    plan.set("analyze", "failed" if analysis_error else "done", ("AI unavailable: " + analysis_error) if analysis_error else "")
    _stage(repo, case_id, "analyze", {"mode": "revision" if revision_mode else "full", "stale": sorted(stale)}, {"error": analysis_error} if analysis_error else {"findings": len((planner_out or {}).get("findings", []))},
           "degraded" if analysis_error else "ok", t0)

    # 5. merge into a state
    state = _assemble(case_id, new_rev, prior, planner_out, analysis_error, stale, evidence, ev_ids, facts, facts_by_id,
                      zv, lines, quoted, policy_present, terms, inj, fname, est_ids, pol_ids, payloads, missing, ai_down, term_problems, kind_of,
                      changed_or_new, trigger_evidence_id, passages, age, prior_ids)

    # 6. validate (receipts, closed ids, language guard)
    plan.set("validate", "running")
    problems = validate.check_refs(state, passages, image_evidence={i for i, k in kind_of.items() if k == "photo"})
    cell_rc = state.pop("_cell_receipts", {})
    n_down = validate.downgrade_cells(state, cell_rc)
    replaced = validate.guard_state(state, passages)
    baseline = [] if analysis_error else validate.ensure_baseline_hypotheses(state["hypotheses"])
    rank.rank_hypotheses(state["hypotheses"], state["matrix"])
    plan.set("validate", "done", f"{len(problems)} dropped ref(s), {n_down} cell(s) neutralised, {len(replaced)} wording fix(es)" + (f", baseline hypothesis added: {', '.join(baseline)}" if baseline else ""))

    # 7. invalidate / delta
    plan.set("invalidate", "running")
    cause = (f"{trigger_evidence_id} {fname.get(trigger_evidence_id, '')} added".strip() if trigger_evidence_id else
             ("evidence added: " + ", ".join(fname[i] for i in sorted(new_ids)) if new_ids else "re-analysis"))
    resolutions = state.pop("_resolutions", {})
    dropped = state.pop("_dropped", [])
    delta = invalidate.build_delta(prior, state, stale, cause, resolutions, dropped)
    delta["approval_voided"] = False  # INFRA voids any active approval on commit and sets this
    plan.set("invalidate", "done", f"{len(stale)} finding(s) went stale: {', '.join(sorted(stale)) or 'none'}")

    # 8. persist
    plan.set("persist", "running")
    CaseState.model_validate(state)  # fail loudly if the assembled state breaks the contract
    summary = state["summary"][:240] or "analysis revision"
    new = repo.commit_revision(case_id, base_rev, state, delta, trigger_evidence_id, summary)  # StaleRun propagates to the worker
    plan.set("persist", "done", f"rev {new}")
    if emit:
        emit({"event": "revision", "rev": new, "ms": int((time.time() - t_all) * 1000), "stale": sorted(stale)})
    return new


def _cz_calc(cz):
    """Contract stores covered_zones as list[str] (["all"] = every line); calc wants 'all' or a list of zones. Unknown -> 'all' (as before)."""
    if cz in (None, "all", ["all"]):
        return "all"
    if isinstance(cz, str):
        return [cz]
    return list(cz) or "all"


def _assemble(case_id, rev, prior, out, ai_error, stale, evidence, ev_ids, facts, facts_by_id, zv, lines, quoted, policy_present, terms, inj, fname,
              est_ids, pol_ids, payloads, missing, ai_down, term_problems, kind_of, changed_or_new, trigger_id, passages,
              age=None, prior_ids=None) -> dict:
    out = out or {}
    # hypotheses: prior kept; model new/changed by id replace/add
    hyps: dict[str, dict] = {h["id"]: dict(h) for h in (prior or {}).get("hypotheses", [])}
    for h in out.get("hypotheses", []):
        hyps[h["id"]] = {**hyps.get(h["id"], {}), **h, "inconsistencies": 0, "rank": 0}
    dropped = []
    for d in out.get("dropped_hypotheses", []):  # only hypotheses that existed because evidence was absent; the Delta records each one
        h = hyps.pop(d["id"], None)
        if h is not None:
            dropped.append({"id": d["id"], "text": h.get("text"), "why": d.get("why") or ""})
    hypotheses = [{"id": h["id"], "text": h["text"], "benign": bool(h.get("benign")), "kind": h.get("kind", "other"), "inconsistencies": 0, "rank": 0,
                   "covered_zones": _cz_calc(h.get("covered_zones"))} for h in hyps.values()]
    age = age or {"months": None, "basis": "", "problem": None}
    # calc with conditionals per hypothesis
    calc = (calcmod.compute(lines, terms, policy_present, hypotheses=[{"id": h["id"], "covered_zones": h["covered_zones"]} for h in hypotheses], quoted_total=quoted,
                            vehicle_age_months=age["months"], age_problem=age["problem"], age_basis=age["basis"])
            if (lines or policy_present) else None)
    unresolved_text = []
    if calc:
        unresolved_text += [f"{u['term']}: {u['why']}" for u in calc["unresolved"]]
    unresolved_text += term_problems
    if ai_error or ai_down:
        unresolved_text.append("AI analysis unavailable: hypotheses/matrix/requests from the model could not be (re)computed" if ai_error else "AI reader unavailable for some evidence")

    # findings
    prior_f = {f["id"]: f for f in (prior or {}).get("findings", [])}
    resolutions: dict[str, str] = {}
    det = det_findings(calc, zv, inj, fname, est_ids, pol_ids, payloads, missing, rev)
    findings: list[dict] = []
    model_f = {f["id"]: f for f in out.get("findings", []) if f.get("id")}
    used_ids = set(prior_f) | {d["id"] for d in det}
    # model findings: re-resolved stale ones + new ones
    next_n = max([int(i.split("-")[1]) for i in used_ids if i.startswith("F-") and i[2:].isdigit()] + [0]) + 1 if used_ids else 1
    new_model: list[dict] = []
    for f in out.get("findings", []):
        fid = f.get("id")
        if fid in prior_f and fid in stale and not fid.startswith(DET_PREFIX):
            continue
        if not fid or fid in prior_f or fid in used_ids:
            fid = f"F-{next_n:02d}"
            next_n += 1
        used_ids.add(fid)
        new_model.append({**f, "id": fid})
    for pid, pf in prior_f.items():
        if pid.startswith(DET_PREFIX):
            continue  # regenerated deterministically below
        if pid in stale:
            mf = model_f.get(pid)
            if mf is None:
                nf = dict(pf)
                nf["status"] = "stale"
                nf["stale_reason"] = ("AI unavailable: not re-resolved; re-run analysis when a provider is available. " if ai_error else
                                      "re-check returned no result; re-run analysis. ") + stale[pid]
                findings.append(nf)
            else:
                res = mf.get("resolution") or "revised"
                resolutions[pid] = res
                nf = {**pf, **{k: mf[k] for k in ("type", "title", "body", "epistemic", "supports", "contradicts", "alternatives", "uncertainty", "action")},
                      "justification": mf["justification"] if (mf["justification"]["evidence_ids"] or mf["justification"]["entity_keys"]) else pf["justification"],
                      "status": "resolved" if res == "resolved" else "active", "revised_rev": rev, "prior_body": pf["body"],
                      "stale_reason": mf.get("stale_reason") or ("resolved by the new evidence" if res == "resolved" else None)}
                findings.append(nf)
        else:
            findings.append(dict(pf))
    for f in new_model:
        findings.append({**{k: f[k] for k in ("id", "type", "title", "body", "epistemic", "supports", "contradicts", "alternatives", "uncertainty", "action", "justification")},
                         "status": "active", "since_rev": rev, "revised_rev": None, "prior_body": None, "stale_reason": None})
    # deterministic: compare with prior
    det_ids = {d["id"] for d in det}
    for d in det:
        pf = prior_f.get(d["id"])
        if pf:
            d["since_rev"] = pf.get("since_rev", rev)
            if pf["body"] != d["body"]:
                d["prior_body"], d["revised_rev"] = pf["body"], rev
                if d["id"] in stale:
                    resolutions[d["id"]] = "revised"
            elif d["id"] in stale:
                resolutions[d["id"]] = "confirmed"
        findings.append(d)
    for pid, pf in prior_f.items():
        if pid.startswith(DET_PREFIX) and pid not in det_ids:
            nf = dict(pf)
            if nf["status"] != "resolved":
                nf.update({"status": "resolved", "prior_body": pf["body"], "revised_rev": rev, "body": "No longer applies after the latest evidence.",
                           "stale_reason": "the condition that raised this finding no longer holds"})
            findings.append(nf)
            if pid in stale:
                resolutions[pid] = "resolved"
    # model-resolved prior findings must also resolve deterministic stale ones that carried over
    state_ev = ev_ids

    # facts as contract Facts
    fact_list = [{"id": f["id"], "evidence_id": f["evidence_id"], "label": f["label"], "value": f["value"], "epistemic": f["epistemic"],
                  "entity_key": f.get("entity_key"), "ref": f.get("ref")} for f in facts]

    def refs(lst):
        return [analyze.resolve_ref(r, facts_by_id) for r in lst]

    for f in findings:
        f["supports"] = [analyze.resolve_ref(r, facts_by_id) if ("fact_id" in r) else r for r in f.get("supports", [])]
        f["contradicts"] = [analyze.resolve_ref(r, facts_by_id) if ("fact_id" in r) else r for r in f.get("contradicts", [])]

    # matrix: prior cells (minus cells for changed evidence the model re-judged) + new cells
    cells = [dict(c) for c in (prior or {}).get("matrix", [])]
    new_cells = out.get("matrix", [])
    rejudged = {c["evidence_id"] for c in new_cells}
    gone = {d["id"] for d in dropped}
    cells = [c for c in cells if c["evidence_id"] not in rejudged and c["hypothesis_id"] not in gone]
    new_cells = [c for c in new_cells if c["hypothesis_id"] not in gone]
    cell_rc: dict[tuple[str, str], str] = {}
    for c in new_cells:
        rc = "n/a"
        f = facts_by_id.get(c.get("fact_id") or "")
        if f and f.get("ref") and f["ref"].get("receipt") in ("matched", "partial") and f["evidence_id"] == c["evidence_id"]:
            rc = f["ref"]["receipt"]
        elif c.get("quote"):
            rc = receipt(c["quote"], passages.get(c["evidence_id"], []))
        cell_rc[(c["hypothesis_id"], c["evidence_id"])] = rc
        cells.append({"hypothesis_id": c["hypothesis_id"], "evidence_id": c["evidence_id"], "relation": c["relation"], "why": c["why"], "receipt": rc})
    for c in cells:  # carried-over cells keep their receipts
        cell_rc.setdefault((c["hypothesis_id"], c["evidence_id"]), c.get("receipt", "n/a"))

    # requests
    requests = _merge_requests(case_id, rev, prior_reqs=(prior or {}).get("requests", []), out=out, calc=calc, hypotheses=hypotheses, missing=missing,
                               ai_error=ai_error, changed_or_new=changed_or_new, kind_of=kind_of, trigger_id=trigger_id,
                               prior_kinds={kind_of.get(i, "other") for i in (prior_ids or set())})

    timeline = []
    for t in (out.get("timeline") or (prior or {}).get("timeline", [])):
        t = dict(t)
        t["refs"] = [analyze.resolve_ref(r, facts_by_id) if ("fact_id" in r) else r for r in t.get("refs", [])]
        timeline.append(t)

    summary = out.get("summary") or (prior or {}).get("summary") or ""
    reco = out.get("recommendation") or (prior or {}).get("recommendation") or ""
    if ai_error:
        summary = ("AI analysis unavailable (" + ai_error[:120] + "). Deterministic checks only: hashing, EXIF, text/OCR, arithmetic, receipts, zone comparison. " + summary).strip()
        reco = "Hold: AI analysis unavailable; deterministic findings below are valid. Re-run analysis when a provider is available."
    elif not reco:
        reco = "Hold for human review." if (calc is None or (calc and calc["unresolved"])) else "Draft settlement ready for human review."
    state_hyps = [{**h, "covered_zones": ["all"] if h["covered_zones"] == "all" else list(h["covered_zones"] or [])} for h in hypotheses]
    state = {"rev": rev, "evidence_ids": state_ev, "facts": fact_list, "findings": findings, "hypotheses": state_hyps, "matrix": cells, "requests": requests,
             "calc": calc, "timeline": timeline, "zones": zv, "unresolved": unresolved_text, "summary": summary, "recommendation": reco,
             "injection_flags": inj, "_cell_receipts": cell_rc, "_resolutions": resolutions, "_dropped": dropped}
    return state


_ASK_WORDS = {"narrative": r"narrative|statement|account|fnol|witness|incident|description of (the )?(accident|loss)|claim (form|description)",
              "estimate": r"estimate|quotation|quote|repair cost|invoice|garage",
              "photo": r"photo|picture|image",
              "policy": r"policy|schedule|clause|coverage|registration"}


def _first_supply(req: dict, changed_or_new, kind_of, prior_kinds: set) -> bool:
    """Backstop when the planner returned no outcome: a generic 'provide X' ask is satisfied by the first evidence of kind X to arrive
    (only when the case had NO evidence of that kind before, so a discriminating ask like 'garage statement on the secondary impact' is never closed this way)."""
    import re as _re
    now_kinds = set(kind_of.values())
    for e in changed_or_new:
        k = kind_of.get(e, "other")
        if k in _ASK_WORDS and k not in prior_kinds and _kind_matches(req["kind"], k) and _re.search(_ASK_WORDS[k], req["text"], _re.I):
            # a combined ask ("provide the narrative and the estimate") stays open until EVERY kind it names has arrived
            others = [o for o, rx in _ASK_WORDS.items() if o != k and o not in now_kinds and _re.search(rx, req["text"], _re.I)]
            if not others:
                return True
    return False


def _merge_requests(case_id, rev, prior_reqs, out, calc, hypotheses, missing, ai_error, changed_or_new, kind_of, trigger_id, prior_kinds=None) -> list[dict]:
    reqs = [dict(r) for r in prior_reqs]
    by_key = {r["key"]: r for r in reqs}
    n = max([int(r["id"].split("-")[1]) for r in reqs if r["id"].startswith("R-") and r["id"][2:].isdigit()] + [0])
    outcomes = {o["request_id"]: o for o in out.get("request_outcomes", [])}
    # outcomes scored against LOCKED predictions (the prediction text is never edited)
    for r in reqs:
        if r["status"] == "open":
            o = outcomes.get(r["id"])
            if o:
                r["status"], r["outcome"] = "received", o["outcome"]
            elif not r["text"].startswith(REQ_PREFIX) and _first_supply(r, changed_or_new, kind_of, prior_kinds or set()):
                r["status"] = "received"  # outcome vs the locked prediction stays 'pending' (the planner gave none)
            elif changed_or_new and any(_kind_matches(r["kind"], kind_of.get(e, "other")) for e in changed_or_new) and not r["text"].startswith(REQ_PREFIX) \
                    and ai_error:
                r["status"] = "received"  # evidence of the requested kind arrived; outcome is scored when the AI is back
    wanted_det: set[str] = set()

    def add(text, kind, resolves, expected=None, prediction=None, det=False):
        nonlocal n
        key = rank.request_key(case_id, text)
        if det:
            wanted_det.add(key)
        if key in by_key:
            r = by_key[key]
            if det and r["status"] == "received":
                r["status"] = "open"
            return
        n += 1
        r = {"id": f"R-{n:02d}", "key": key, "text": text, "kind": kind, "resolves": resolves, "pairs_separated": rank.pairs_separated(resolves, expected),
             "rupees_at_stake": None, "prediction": prediction, "status": "open", "created_rev": rev, "outcome": "pending"}
        reqs.append(r)
        by_key[key] = r

    hyp_ids = {h["id"] for h in hypotheses}
    for r in out.get("requests", []):
        res = [h for h in r["resolves"] if h in hyp_ids]
        add(r["text"], r["kind"], res, r.get("expected"), r.get("prediction"))
    if calc:
        for u in calc["unresolved"]:
            add(f"Needed to compute the settlement: {u['needs']} (term: {u['term']})", "document", [], det=True)
    for eid, why in missing:
        add(f"Provide a legible or typed copy of the content of {eid}: {why}", "document", [], det=True)
    if ai_error:
        add("AI analysis was unavailable: re-run the analysis when a model provider is reachable, or type the key facts as a statement.", "statement", [], det=True)
    for r in reqs:  # deterministic asks that no longer apply are closed (condition resolved), never deleted
        if r["text"].startswith(REQ_PREFIX) and r["key"] not in wanted_det and r["status"] == "open":
            r["status"] = "received"
    for r in reqs:
        if r["status"] == "open" and calc and r["resolves"]:
            r["rupees_at_stake"] = rank.rupees_at_stake(r["resolves"], calc["conditional"])
    return rank.order_requests(reqs)
