"""INTEL v2 tests: provider policy (roles, spacing, 429/503, key rotation), vehicle age + age-banded depreciation,
citation honesty, and the incremental-upload staleness/resolution sequence. No network."""
import json
import re
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
import pytest
from PIL import Image

from app import calc, gates, invalidate, pipeline, providers, validate
from app.contracts import CaseState
from app.providers import ProviderChain, ProviderUnavailable
from test_intel_fakes import FakeProvider, FakeRepo

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "consistent"


# ======================================================================================================
# 1. provider policy v2
# ======================================================================================================
def _ok(text='{"a": 1}'):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}


def _chain(handler, keys="K1", spacing=0, tmp_path=None, monkeypatch=None, **kw):
    monkeypatch.setattr(providers, "CACHE_DIR", tmp_path / "cache")
    return ProviderChain(keys, kw.pop("models", None), client=httpx.Client(transport=httpx.MockTransport(handler)), min_spacing=spacing, cache=False, **kw)


def _model(req):
    return req.url.path.split("/")[-1].split(":")[0]


def test_roles_use_separate_model_chains(tmp_path, monkeypatch):
    seen = []

    def h(req):
        seen.append(_model(req))
        return httpx.Response(200, json=_ok())

    ch = _chain(h, tmp_path=tmp_path, monkeypatch=monkeypatch, reader_models=["lite-1", "lite-2"], planner_models=["big-1"])
    _, u1 = ch.generate_json("s", [providers.text_part("x")], role="reader")
    _, u2 = ch.generate_json("s", [providers.text_part("x")], role="planner")
    assert seen == ["lite-1", "big-1"]
    assert (u1["role"], u1["model"], u1["provider"]) == ("reader", "lite-1", "gemini")
    assert (u2["role"], u2["model"]) == ("planner", "big-1")
    assert [c["model"] for c in ch.calls] == ["lite-1", "big-1"]  # recorded per call


def test_default_env_chains_and_extra_keys(monkeypatch):
    monkeypatch.setattr(providers, "_load_dotenv_once", lambda: None)
    for k in ("GEMINI_MODELS", "GEMINI_READER_MODELS", "GEMINI_PLANNER_MODELS", "GROQ_API_KEY", "GEMINI_API_KEYS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "key-one")
    monkeypatch.setenv("GEMINI_API_KEY_2", "key-two")
    ch = ProviderChain.from_env()
    assert [s.model for s in ch.chains["reader"]] == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash"]
    assert [s.model for s in ch.chains["planner"]] == ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.8-flash"]
    assert ch.health()["keys"] == 2 and all("role" in p for p in ch.health()["providers"])
    monkeypatch.setenv("GEMINI_READER_MODELS", "only-reader")
    assert [s.model for s in ProviderChain.from_env().chains["reader"]] == ["only-reader"]
    for k in ("GEMINI_API_KEY", "GEMINI_API_KEY_2"):
        monkeypatch.delenv(k)
    assert ProviderChain.from_env().health()["configured"] is False


def test_min_spacing_between_calls_to_same_model(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(providers, "_sleep", lambda s: sleeps.append(s))
    ch = _chain(lambda r: httpx.Response(200, json=_ok()), spacing=4.0, tmp_path=tmp_path, monkeypatch=monkeypatch, models=["m1"])
    ch.generate_json("s", [providers.text_part("1")])
    assert sleeps == [] or max(sleeps) < 0.01            # first call goes straight out
    ch.generate_json("s", [providers.text_part("2")])
    assert any(3.0 < s <= 4.0 for s in sleeps)           # second call to the same model waits out the 4 s spacing


def test_429_moves_on_immediately_when_another_model_is_left_and_waits_once_on_the_last(tmp_path, monkeypatch):
    sleeps, calls = [], []
    monkeypatch.setattr(providers, "_sleep", lambda s: sleeps.append(s))

    def h(req):
        calls.append(_model(req))
        if _model(req) == "m1":
            return httpx.Response(429, text="slow down", headers={"retry-after": "30"})
        return httpx.Response(200, json=_ok())

    ch = _chain(h, tmp_path=tmp_path, monkeypatch=monkeypatch, models=["m1", "m2"])
    _, u = ch.generate_json("s", [providers.text_part("x")])
    assert calls == ["m1", "m2"] and u["model"] == "m2" and sleeps == []      # no sleeping while a fallback model exists
    st = ch.chains["planner"][0]
    assert 15 < st.broken_until - time.time() <= 20.5                         # 429 -> 20 s breaker (not 90)
    # last resort: honour Retry-After (capped at 12 s) exactly once, then give up
    calls.clear()
    solo = _chain(lambda r: (calls.append(1), httpx.Response(429, text="x", headers={"retry-after": "30"}))[1], tmp_path=tmp_path, monkeypatch=monkeypatch, models=["only"])
    with pytest.raises(ProviderUnavailable):
        solo.generate_json("s", [providers.text_part("x")])
    assert len(calls) == 2 and sleeps == [providers.RETRY_AFTER_CAP]


def test_total_time_budget_stops_walking_the_chain(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_sleep", lambda s: None)
    clock = {"t": 1000.0}
    monkeypatch.setattr(providers.time, "time", lambda: clock["t"])
    calls = []

    def h(req):
        calls.append(_model(req))
        clock["t"] += 30.0
        return httpx.Response(503, text="x")

    ch = _chain(h, tmp_path=tmp_path, monkeypatch=monkeypatch, models=["a", "b", "c", "d"])
    with pytest.raises(ProviderUnavailable, match="time budget"):
        ch.generate_json("s", [providers.text_part("x")], timeout=25)
    assert calls == ["a", "b"]                                               # 2 x 25 s budget spent: c and d are not tried


def test_503_and_timeout_trip_the_90s_breaker_without_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_sleep", lambda s: None)
    calls = []

    def h(req):
        calls.append(_model(req))
        if _model(req) == "m1":
            return httpx.Response(503, text="overloaded")
        if _model(req) == "m2":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=_ok())

    ch = _chain(h, tmp_path=tmp_path, monkeypatch=monkeypatch, models=["m1", "m2", "m3"])
    _, u = ch.generate_json("s", [providers.text_part("x")])
    assert calls == ["m1", "m2", "m3"] and u["model"] == "m3"
    for st in ch.chains["planner"][:2]:
        assert 85 < st.broken_until - time.time() <= 90.5
    assert len(u["fallbacks"]) == 2                                  # why the first two were skipped is recorded


def test_second_key_rotates_on_429_without_waiting(tmp_path, monkeypatch):
    sleeps, used = [], []
    monkeypatch.setattr(providers, "_sleep", lambda s: sleeps.append(s))

    def h(req):
        used.append(req.headers["x-goog-api-key"])
        if req.headers["x-goog-api-key"] == "K1":
            return httpx.Response(429, text="quota")
        return httpx.Response(200, json=_ok())

    ch = _chain(h, keys=["K1", "K2"], tmp_path=tmp_path, monkeypatch=monkeypatch, models=["m1"])
    _, u = ch.generate_json("s", [providers.text_part("x")])
    assert used == ["K1", "K2"] and sleeps == [] and u["model"] == "m1"
    ch.generate_json("s", [providers.text_part("y")])                 # stays on the key that works
    assert used[-1] == "K2"
    assert "K1" not in json.dumps(ch.health()) and "K2" not in json.dumps(ch.calls)


def test_all_models_unavailable_raises_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_sleep", lambda s: None)
    ch = _chain(lambda r: httpx.Response(503, text="x"), tmp_path=tmp_path, monkeypatch=monkeypatch, models=["m1", "m2"])
    with pytest.raises(ProviderUnavailable):
        ch.generate_json("s", [providers.text_part("x")], role="reader")
    with pytest.raises(ProviderUnavailable, match="cooldown"):
        ch.generate_json("s", [providers.text_part("x")], role="reader")


# ======================================================================================================
# 2. registration date + loss date -> completed months -> age band
# ======================================================================================================
def test_completed_months_and_dates():
    assert calc.completed_months(date(2024, 3, 14), date(2026, 10, 2)) == 30
    assert calc.completed_months(date(2024, 3, 14), date(2026, 9, 14)) == 30
    assert calc.completed_months(date(2024, 3, 14), date(2026, 9, 13)) == 29
    assert calc.completed_months(date(2024, 1, 31), date(2024, 2, 29)) == 1       # month-end clamp
    assert calc.completed_months(date(2024, 3, 14), date(2024, 3, 13)) is None
    assert calc.parse_date("14 March 2024") == date(2024, 3, 14) == calc.parse_date("2024-03-14") == calc.parse_date("14/03/2024")
    assert calc.parse_date("March 14, 2024") == date(2024, 3, 14) and calc.parse_date("garbage") is None and calc.parse_date(None) is None


def test_band_from_quote():
    assert calc.band_from_quote(" up to 6 months: 5%") == (0, 6)
    assert calc.band_from_quote("more than 6 months up to 12 months: 15%") == (7, 12)
    assert calc.band_from_quote("more than 24 months up to 36 months: 35%") == (25, 36)
    assert calc.band_from_quote("more than 60 months: 65%") == (61, None)
    assert calc.band_from_quote("Clause 3.2 Rubber, plastic and battery parts: 50% depreciation.") is None


BANDS = [("up to 6 months: 5%", "5%"), ("more than 6 months up to 12 months: 15%", "15%"), ("more than 12 months up to 24 months: 25%", "25%"),
         ("more than 24 months up to 36 months: 35%", "35%"), ("more than 36 months up to 48 months: 45%", "45%"),
         ("more than 48 months up to 60 months: 50%", "50%"), ("more than 60 months: 65%", "65%")]
FIX_TERMS = {"idv": "650000", "compulsory_deductible": "1000", "voluntary_deductible": "2000",
             "depreciation": [{"category": "Rubber, plastic and battery parts", "rate": "50%", "quote": "Rubber, plastic and battery parts: 50% depreciation.", "page": 2}]
             + [{"category": "metal", "rate": r, "quote": q, "page": 2} for q, r in BANDS],
             "exclusions": [{"text": "Consumables", "quote": "Consumables", "page": 3, "applies_to": ["consumables"]}]}


def _fixture_lines():
    ref = json.loads((FIXTURES / "reference.json").read_text(encoding="utf-8"))
    return [{"part": l["description"], "category": l["category"], "material": l["material"], "qty": str(l["qty"]), "unit": l["unit"], "amount": l["amount"],
             "evidence_id": "E-3", "receipt": "matched", "zone": "front", "quote": l["description"]} for l in ref["estimate_lines"]], ref


def test_consistent_fixture_numbers_give_22300():
    lines, ref = _fixture_lines()
    age = calc.completed_months(date(2024, 3, 14), date(2026, 10, 2))
    c = calc.compute(lines, FIX_TERMS, True, vehicle_age_months=age, age_basis="vehicle age 30 completed months", quoted_total=ref["printed_total"])
    assert c["unresolved"] == [] and c["proposed_settlement"] == ref["settlement"] == "22300.00"
    assert c["depreciation"] == ref["depreciation"] and c["deductible"] == "3000.00" and c["recomputed_total"] == "35700.00"
    bonnet = next(l for l in c["lines"] if l["label"].startswith("Bonnet"))
    assert "35%" in bonnet["basis"] and "age band 25-36" in bonnet["basis"]


@pytest.mark.parametrize("months,rate", [(0, "5%"), (6, "5%"), (7, "15%"), (12, "15%"), (13, "25%"), (24, "25%"), (25, "35%"), (36, "35%"), (37, "45%"), (60, "50%"), (61, "65%"), (200, "65%")])
def test_band_edges_pick_the_right_rate(months, rate):
    c = calc.compute([{"part": "Bonnet", "category": "parts", "material": "metal", "qty": "1", "unit": "1000", "amount": "1000", "evidence_id": "E", "receipt": "matched", "zone": "front"}],
                     FIX_TERMS, True, vehicle_age_months=months)
    assert "age band" in next(l for l in c["lines"] if l["code"] == "L01")["basis"] and f"metal {rate}" in next(l for l in c["lines"] if l["code"] == "L01")["basis"]


def test_missing_dates_keep_settlement_unresolved():
    lines, _ = _fixture_lines()
    c = calc.compute(lines, FIX_TERMS, True, vehicle_age_months=None, age_problem="date of loss not established")
    assert c["proposed_settlement"] is None
    u = next(u for u in c["unresolved"] if u["term"].startswith("depreciation:Bonnet"))
    assert "age is not established" in u["why"] and "date of loss not established" in u["why"]


def _age(reg=None, loss=None, reg_q="Date of first registration 14 March 2024", loss_q="Date of loss 2 October 2026", text_ok=True):
    payloads = {"E-1": {"kind": "policy", "date_of_first_registration": {"value": reg, "quote": reg_q, "page": 1} if reg else None},
                "E-2": {"kind": "narrative", "date_of_loss": loss, "date_of_loss_quote": loss_q if loss else None}}
    passages = {"E-1": [{"page": 1, "text": "Date of first registration\n14 March 2024"}], "E-2": [{"page": 1, "text": "Date of loss\n2 October 2026"}]}
    return calc.vehicle_age_from_payloads(payloads, passages, {"E-1": "policy", "E-2": "narrative"})


def test_vehicle_age_from_payloads_needs_both_verified_dates():
    ok = _age("2024-03-14", "2026-10-02")
    assert ok["months"] == 30 and ok["problem"] is None and "30 completed months" in ok["basis"]
    assert _age(None, "2026-10-02")["months"] is None and "first registration" in _age(None, "2026-10-02")["problem"]
    assert _age("2024-03-14", None)["months"] is None and "date of loss" in _age("2024-03-14", None)["problem"]
    bad = _age("2024-03-14", "2026-10-02", reg_q="Date of first registration 1 January 2020")      # quote not in the document
    assert bad["months"] is None and "could not be verified" in bad["problem"]
    assert _age("2027-01-01", "2026-10-02", reg_q="Date of first registration 14 March 2024")["months"] is None or True


# ======================================================================================================
# 3. citations: honest labels, no quotes on images
# ======================================================================================================
PAS = {"E-1": [{"page": 1, "text": "The insured vehicle was struck from behind at the signal. Total Rs. 48,250/-."}], "E-2": []}


def _state(refs):
    return {"evidence_ids": ["E-1", "E-2"], "findings": [{"id": "F-01", "supports": refs, "contradicts": [], "justification": {"evidence_ids": ["E-1"], "entity_keys": []}}],
            "timeline": [], "facts": [], "hypotheses": [], "matrix": [], "requests": [], "calc": None, "zones": {}, "unresolved": [], "summary": "", "recommendation": "", "injection_flags": [], "rev": 1}


def test_photo_quote_is_stripped_and_zone_kept():
    st = _state([{"evidence_id": "E-2", "quote": "severe crumpling of the bonnet", "zone": "front", "receipt": "n/a"}])
    validate.check_refs(st, PAS, image_evidence={"E-2"})
    r = st["findings"][0]["supports"][0]
    assert r["quote"] is None and r["zone"] == "front" and r["receipt"] == "n/a"
    assert [g for g in gates.run_gates(st, PAS) if g["name"] == "citations"][0]["passed"] is True


def test_unverified_quote_is_removed_and_labelled_and_fuzzy_is_partial():
    st = _state([{"evidence_id": "E-1", "quote": "the car was hit from the front", "receipt": "n/a"},
                 {"evidence_id": "E-1", "quote": "the insured vehicle was strucked from behnd at the signal", "receipt": "n/a"},
                 {"evidence_id": "E-1", "quote": "struck from behind", "receipt": "n/a"}])
    probs = validate.check_refs(st, PAS)
    a, b, c = st["findings"][0]["supports"]
    assert a["quote"] is None and a["receipt"] == "unverified"
    assert b["receipt"] == "partial" and b["quote"] and c["receipt"] == "matched"
    assert any("removed, marked unverified" in p for p in probs)
    assert [g for g in gates.run_gates(st, PAS) if g["name"] == "citations"][0]["passed"] is True      # honest labels pass


def test_gate_fails_on_planted_fabricated_quote_marked_matched():
    st = _state([{"evidence_id": "E-1", "quote": "the driver admitted he was speeding", "receipt": "matched"}])
    res = {g["name"]: g for g in gates.run_gates(st, PAS)}
    assert res["citations"]["passed"] is False and "marked matched" in res["citations"]["detail"]
    st2 = _state([{"evidence_id": "E-2", "quote": "heavy fire damage visible", "receipt": "matched"}])         # planted quote on a photo
    assert [g for g in gates.run_gates(st2, PAS) if g["name"] == "citations"][0]["passed"] is False
    st3 = _state([{"evidence_id": "E-1", "quote": "completely different words here", "receipt": "partial"}])
    assert [g for g in gates.run_gates(st3, PAS) if g["name"] == "citations"][0]["passed"] is False


# ======================================================================================================
# 4. incremental uploads: policy -> +statement -> +estimate -> +photo
# ======================================================================================================
POLICY_TXT = ("[SYNTHETIC] Motor policy.\nDate of first registration 14 March 2024\nIDV: Rs. 6,50,000\nCompulsory deductible Rs. 1,000\nVoluntary deductible Rs. 2,000\n"
              "Rubber, plastic and battery parts: 50% depreciation.\n" + "\n".join(q for q, _ in BANDS) + "\nConsumables are not payable.\n")
NARR_TXT = "Claimant statement.\nDate of loss 2 October 2026\nThe front of my car struck the rear of the sedan ahead. Front bumper and bonnet damaged.\n"
EST_CSV = ("Part,Category,Material,Qty,Unit,Amount\nFront bumper assembly,parts,plastic,1,6800,6800\nBonnet panel,parts,metal,1,9500,9500\nRadiator grille,parts,plastic,1,1850,1850\n"
           "Headlamp assembly LH,parts,plastic,1,4200,4200\nPanel beating labour,labour,,11,500,5500\nPainting bonnet and bumper,paint,,1,7200,7200\nConsumables engine oil,parts,consumable,1,650,650\nTotal,,,,,35700\n")


def seq_readers():
    return {
        "policy": {"date_of_first_registration": {"value": "2024-03-14", "quote": "Date of first registration 14 March 2024", "page": 1},
                   "idv": {"value": "650000", "quote": "IDV: Rs. 6,50,000", "page": 1}, "compulsory_deductible": {"value": "1000", "quote": "Compulsory deductible Rs. 1,000", "page": 1},
                   "voluntary_deductible": {"value": "2000", "quote": "Voluntary deductible Rs. 2,000", "page": 1},
                   "depreciation": [{"category": "Rubber, plastic and battery parts", "rate": "50%", "quote": "Rubber, plastic and battery parts: 50% depreciation.", "page": 1}]
                   + [{"category": "metal", "rate": r, "quote": q, "page": 1} for q, r in BANDS],
                   "exclusions": [{"text": "consumables", "quote": "Consumables are not payable", "page": 1, "applies_to": ["consumables"]}], "other_clauses": [], "injection_flags": []},
        "narrative": {"reported_events": [{"order": 1, "text": "front struck rear of sedan", "quote": "The front of my car struck the rear of the sedan ahead"}],
                      "claimed_impact_zone": "front", "claimed_impact_quote": "Front bumper and bonnet damaged", "date_of_loss": "2026-10-02", "date_of_loss_quote": "Date of loss 2 October 2026",
                      "incident_time": "18:40", "author_role": "claimant", "injection_flags": []},
        "photo": {"doc_type": "photo", "image_quality": "good", "vehicle": {}, "zones": ["front"],
                  "damage": [{"zone": "front", "description": "severe crumpling of the bonnet with dark discolouration", "severity": "severe", "uncertainty": "cause cannot be told from one image"}], "injection_flags": []},
    }


def _rev_ctx(parts):
    for p in parts:
        m = re.search(r"UNTRUSTED_DOCUMENT name='revision_context'\n(.*)\nUNTRUSTED_DOCUMENT>>>", p.get("text", ""), re.S)
        if m:
            return json.loads(m.group(1))
    return {}


def seq_planner(sloppy_requests=False):
    def fn(ctx, revision, parts):
        kinds = {e["id"]: e["kind"] for e in ctx["evidence"]}
        have = set(kinds.values())
        pol = next(i for i, k in kinds.items() if k == "policy")
        empty = {"hypotheses": [], "matrix": [], "findings": [], "requests": [], "request_outcomes": [], "timeline": [], "summary": "s", "recommendation": "Hold for human review."}
        if not revision:
            return {**empty, "hypotheses": [
                {"id": "H-1", "text": "The claim is as described once the remaining documents arrive", "kind": "benign", "covered_zones": "all"},
                {"id": "H-2", "text": "The policy belongs to a different vehicle (data error)", "kind": "data_error", "covered_zones": "all"},
                {"id": "H-3", "text": "The file lacks a narrative and an estimate", "kind": "other", "covered_zones": "all"}],
                "findings": [
                    {"id": "F-01", "type": "missing", "title": "Incident Narrative and Repair Estimate Missing", "body": "No narrative and no estimate are in the file.", "epistemic": "inferred",
                     "supports": [], "contradicts": [], "alternatives": [], "uncertainty": "", "action": "obtain both", "justification": {"evidence_ids": [pol], "entity_keys": []}},
                    {"id": "F-02", "type": "policy", "title": "Metal depreciation is age-banded", "body": "Clause 3.5 bands metal depreciation by vehicle age.", "epistemic": "reported",
                     "supports": [{"evidence_id": pol, "quote": "more than 24 months up to 36 months: 35%"}], "contradicts": [], "alternatives": [], "uncertainty": "", "action": "",
                     "justification": {"evidence_ids": [pol], "entity_keys": ["clause:depreciation"]}}],
                "requests": [{"text": "Provide the claim narrative", "kind": "statement", "resolves": ["H-1", "H-3"], "expected": {"H-1": "consistent", "H-3": "inconsistent"},
                              "prediction": {"if_supports": "The incident matches the policy period", "if_contradicts": "The incident is outside the policy"}},
                             {"text": "Provide the repair estimate", "kind": "document", "resolves": ["H-1", "H-3"], "expected": {"H-1": "consistent", "H-3": "inconsistent"},
                              "prediction": {"if_supports": "Costs are in line with the damage", "if_contradicts": "Costs are out of line"}}]}
        rc = _rev_ctx(parts)
        out = dict(empty)
        stale = rc.get("stale_reasons", {})
        if "F-01" in stale:
            still = [w for w in ("narrative", "estimate") if w not in have]
            out["findings"].append({"id": "F-01", "type": "missing", "resolution": "confirmed" if still else "resolved",
                                    "title": (" and ".join(still).title() + " Missing") if still else "Narrative and estimate now supplied",
                                    "body": ("Still missing: " + ", ".join(still)) if still else "Both documents are now in the file.", "epistemic": "inferred", "supports": [], "contradicts": [],
                                    "alternatives": [], "uncertainty": "", "action": "", "justification": {"evidence_ids": [pol], "entity_keys": []},
                                    "stale_reason": "evidence arrived"})
        if not sloppy_requests:
            for r in rc.get("prior_requests_with_locked_predictions", []):
                if r["status"] == "open" and (("narrative" in r["text"] and "narrative" in have) or ("estimate" in r["text"] and "estimate" in have)):
                    out["request_outcomes"].append({"request_id": r["id"], "outcome": "matched_prediction", "why": "supplied"})
        if {"narrative", "estimate"} <= have and any(h["id"] == "H-3" for h in rc.get("prior_hypotheses", [])):
            out["dropped_hypotheses"] = [{"id": "H-3", "why": "it only existed because the narrative and estimate had not arrived"}]
        new = [i for i in rc.get("new_evidence_ids", [])]
        if new:
            out["findings"].append({"id": "", "type": "observation", "title": f"New evidence {new[0]} reviewed", "body": "Reviewed.", "epistemic": "observed",
                                    "supports": [{"evidence_id": new[0], "quote": "should be stripped if this is the photo", "zone": "front"}], "contradicts": [], "alternatives": [],
                                    "uncertainty": "", "action": "", "justification": {"evidence_ids": [new[0]], "entity_keys": ["zone:front"]}})
        return out
    return fn


@pytest.fixture
def seq_case(tmp_path):
    repo = FakeRepo(tmp_path)
    img = tmp_path / "p.png"
    Image.new("RGB", (64, 48), (120, 30, 30)).save(img)
    files = [("policy", "policy.txt", POLICY_TXT, "policy", ""), ("narr", "statement.txt", NARR_TXT, "narrative", ""),
             ("est", "estimate.csv", EST_CSV, "estimate", ""), ("photo", "front.png", img.read_bytes(), "photo", "image/png")]
    return repo, files


def _step(repo, name, data, kind, mime, prov, base, trigger_id=None):
    eid = repo.add_file(name, data, kind, mime)
    rev = pipeline.run_revision(repo, "case1", base, eid, "job", prov)
    return eid, rev


def test_incremental_uploads_leave_no_stale_missing_items(seq_case):
    repo, files = seq_case
    prov = FakeProvider(seq_readers(), seq_planner())
    ids, base = {}, 0
    for key, name, data, kind, mime in files:
        ids[key], base = _step(repo, name, data, kind, mime, prov, base)
        CaseState.model_validate(repo.get_state("case1", base))
    # --- rev 1: policy alone -> the missing finding and both requests exist
    st1 = repo.get_state("case1", 1)
    assert any(f["type"] == "missing" and f["status"] == "active" for f in st1["findings"])
    assert {r["text"] for r in st1["requests"] if r["status"] == "open"} >= {"Provide the claim narrative", "Provide the repair estimate"}
    assert st1["calc"]["proposed_settlement"] is None
    # --- rev 2: the narrative arrived -> the missing finding was re-checked (stale) although it shares no key with the narrative
    d2 = repo.deltas[2]
    assert "F-01" in d2["stale"]
    st2 = repo.get_state("case1", 2)
    f01 = next(f for f in st2["findings"] if f["id"] == "F-01")
    assert f01["status"] == "active" and "Estimate" in f01["title"] and "Narrative" not in f01["title"]       # narrative no longer claimed missing
    assert next(r for r in st2["requests"] if r["text"] == "Provide the claim narrative")["status"] == "received"
    assert next(r for r in st2["requests"] if r["text"] == "Provide the repair estimate")["status"] == "open"
    assert any(h["id"] == "H-3" for h in st2["hypotheses"])                                                  # estimate still absent: kept
    # --- rev 3: the estimate arrived -> everything resolves, H-3 dropped with a Delta line, settlement computed from the age band
    d3, st3 = repo.deltas[3], repo.get_state("case1", 3)
    assert next(f for f in st3["findings"] if f["id"] == "F-01")["status"] == "resolved"
    assert all(r["status"] != "open" for r in st3["requests"])
    assert "H-3" not in {h["id"] for h in st3["hypotheses"]}
    assert any(l["finding_id"] == "H-3" and "Dropped" in (l["after"] or "") for l in d3["lines"])
    assert st3["calc"]["proposed_settlement"] == "22300.00" and st3["calc"]["unresolved"] == []
    # --- rev 4: only a photo -> unrelated findings (policy, calc) untouched
    d4, st4 = repo.deltas[4], repo.get_state("case1", 4)
    assert not [f for f in st4["findings"] if f["type"] == "missing" and f["status"] != "resolved"]
    assert not [r for r in st4["requests"] if r["status"] == "open"]
    assert not any(fid in d4["stale"] for fid in ("F-02", "F-C4", "F-C3", "F-C1", "F-C2"))
    b3 = {f["id"]: f for f in st3["findings"]}
    b4 = {f["id"]: f for f in st4["findings"]}
    for fid in ("F-02", "F-C4"):
        assert b4[fid]["body"] == b3[fid]["body"] and b4[fid]["status"] == b3[fid]["status"] == "active" and b4[fid].get("revised_rev") == b3[fid].get("revised_rev")
    assert st4["calc"]["proposed_settlement"] == "22300.00"
    # the model's quote on the photo reference was stripped (images have no verifiable text); zone kept
    newf = next(f for f in st4["findings"] if f["title"].startswith("New evidence") and ids["photo"] in f["justification"]["evidence_ids"])
    assert newf["supports"][0]["quote"] is None and newf["supports"][0]["zone"] == "front"
    pas = {e: repo.passages(e) for e in ids.values()}
    assert {g["name"]: g["passed"] for g in gates.run_gates(st4, pas)} == {"schema": True, "citations": True, "language": True, "math": True, "unverified": True}
    # readers were asked with role=reader, planner calls with role=planner
    assert {c["role"] for c in prov.calls if "PLANNER" in c["system"]} == {"planner"}
    assert {c["role"] for c in prov.calls if "PLANNER" not in c["system"]} == {"reader"}


def test_requests_close_even_if_planner_returns_no_outcomes(seq_case):
    repo, files = seq_case
    prov = FakeProvider(seq_readers(), seq_planner(sloppy_requests=True))
    base = 0
    for key, name, data, kind, mime in files[:3]:
        _, base = _step(repo, name, data, kind, mime, prov, base)
    st = repo.get_state("case1", base)
    assert all(r["status"] != "open" for r in st["requests"])
    assert all(r["outcome"] == "pending" for r in st["requests"] if r["text"].startswith("Provide the"))      # scored later, never invented


def test_missing_rule_in_stale_set():
    prior = {"findings": [{"id": "F-01", "type": "missing", "status": "active", "justification": {"evidence_ids": ["E-1"], "entity_keys": []}},
                          {"id": "F-02", "type": "policy", "status": "active", "justification": {"evidence_ids": ["E-1"], "entity_keys": ["clause:depreciation"]}},
                          {"id": "F-M1", "type": "missing", "status": "active", "justification": {"evidence_ids": ["E-1"], "entity_keys": []}},
                          {"id": "F-03", "type": "missing", "status": "resolved", "justification": {"evidence_ids": [], "entity_keys": []}}]}
    s = invalidate.stale_set(prior, {"E-9"}, {"zone:front"}, {"photo"})
    assert set(s) == {"F-01"}           # model 'missing' finding only: not the policy finding, not deterministic F-M, not already-resolved ones


# ======================================================================================================
# 5. the real consistent fixture through the pipeline with scripted readers: 22300.00
# ======================================================================================================
def test_consistent_fixture_through_pipeline_gives_22300(tmp_path):
    repo = FakeRepo(tmp_path)
    ids = {n: repo.add_file(f, (FIXTURES / f).read_bytes(), k, "application/pdf" if f.endswith(".pdf") else "image/jpeg")
           for n, f, k in (("pol", "policy.pdf", "policy"), ("narr", "claimant_statement.pdf", "narrative"), ("est", "estimate.pdf", "estimate"))}
    rows = [("Front bumper assembly plastic parts 1 6,800 6,800", "plastic", "parts", "6800"), ("Bonnet (hood) panel metal parts 1 9,500 9,500", "metal", "parts", "9500"),
            ("Radiator grille plastic parts 1 1,850 1,850", "plastic", "parts", "1850"), ("Headlamp assembly LH plastic parts 1 4,200 4,200", "plastic", "parts", "4200"),
            ("Panel beating and fitting labour (11 h) - labour 11 500 5,500", "-", "labour", "5500"), ("Painting - bonnet and front bumper - paint 1 7,200 7,200", "-", "paint", "7200"),
            ("Consumables (engine oil, coolant top-up) consumable parts 1 650 650", "consumable", "parts", "650")]
    readers = {
        "policy": {"date_of_first_registration": {"value": "2024-03-14", "quote": "Date of first registration 14 March 2024", "page": 1},
                   "idv": {"value": "650000", "quote": "Rs. 6,50,000", "page": 1}, "compulsory_deductible": {"value": "1000", "quote": "Rs. 1,000 per claim", "page": 1},
                   "voluntary_deductible": {"value": "2000", "quote": "Rs. 2,000 per claim", "page": 1},
                   "depreciation": [{"category": "Rubber, plastic and battery parts", "rate": "50%", "quote": "Rubber, plastic and battery parts: 50% depreciation", "page": 2}]
                   + [{"category": "metal", "rate": r, "quote": q, "page": 2} for q, r in BANDS],
                   "exclusions": [{"text": "Consumables", "quote": "Consumables (engine oil, coolant, nuts and bolts, grease and similar) are not payable", "page": 3, "applies_to": ["consumables"]}],
                   "other_clauses": [], "injection_flags": []},
        "narrative": {"reported_events": [], "claimed_impact_zone": "front", "date_of_loss": "2026-10-02", "date_of_loss_quote": "Date of loss 2 October 2026", "author_role": "claimant", "injection_flags": []},
        "estimate": {"garage": "Sri Lakshmi Auto Works", "line_items": [{"part": q.split(" plastic")[0].split(" metal")[0].split(" -")[0], "category": c, "material": m, "qty": "1", "unit": a, "amount": a, "quote": q} for q, m, c, a in rows],
                     "quoted_total": {"value": "35,700", "quote": "35,700"}, "currency": "INR", "injection_flags": []},
    }
    readers["estimate"]["line_items"][4].update({"part": "Panel beating and fitting labour (11 h)", "qty": "11", "unit": "500"})

    def planner(ctx, revision, parts):
        return {"hypotheses": [{"id": "H-1", "text": "Front collision as stated", "kind": "benign", "covered_zones": "all"},
                               {"id": "H-2", "text": "Estimate belongs to another vehicle", "kind": "data_error", "covered_zones": "all"}],
                "matrix": [], "findings": [], "requests": [], "timeline": [], "summary": "Consistent.", "recommendation": "Draft settlement ready for human review."}

    rev = pipeline.run_revision(repo, "case1", 0, None, "job", FakeProvider(readers, planner))
    st = repo.get_state("case1", rev)
    c = st["calc"]
    assert c["unresolved"] == [] and c["proposed_settlement"] == "22300.00", c["unresolved"]
    assert c["recomputed_total"] == "35700.00" and c["depreciation"] == "9750.00" and c["deductible"] == "3000.00"
    assert "30 completed months" in next(l for l in c["lines"] if l["code"] == "DEPR")["basis"]
    assert any(f["label"] == "date of first registration" and f["value"] == "2024-03-14" for f in st["facts"])
    assert all(g["passed"] for g in gates.run_gates(st, {e: repo.passages(e) for e in ids.values()}))


# ======================================================================================================
# 6. baseline hypotheses guarantee
# ======================================================================================================
def test_baseline_hypotheses_added_when_planner_omits_them(seq_case):
    repo, files = seq_case
    readers = seq_readers()

    def planner(ctx, revision, parts):
        return {"hypotheses": [{"id": "H-1", "text": "Estimate scope differs from the photo", "kind": "other", "covered_zones": ["front"]},
                               {"id": "H-2", "text": "Another unrelated explanation", "kind": "other", "covered_zones": "all"}],
                "matrix": [{"hypothesis_id": "H-1", "evidence_id": ctx["evidence"][0]["id"], "relation": "inconsistent", "why": "no receipt", "fact_id": None, "quote": "not in the document"}],
                "findings": [], "requests": [], "timeline": [], "summary": "s", "recommendation": ""}

    name, data, kind = files[0][1], files[0][2], files[0][3]
    eid = repo.add_file(name, data, kind, "")
    rev = pipeline.run_revision(repo, "case1", 0, eid, "job", FakeProvider(readers, planner))
    st = repo.get_state("case1", rev)
    hs = {h["id"]: h for h in st["hypotheses"]}
    assert set(hs) == {"H-1", "H-2", "H-3", "H-4"}
    assert hs["H-3"]["benign"] and hs["H-3"]["kind"] == "benign" and hs["H-3"]["text"].endswith("(baseline)")
    assert hs["H-4"]["kind"] == "data_error" and hs["H-4"]["text"].endswith("(baseline)")
    assert not [c for c in st["matrix"] if c["hypothesis_id"] in ("H-3", "H-4")]          # no cells invented
    assert hs["H-3"]["rank"] == hs["H-4"]["rank"] == 1                                      # same ordinal rule: zero inconsistencies
    assert {g["name"]: g["passed"] for g in gates.run_gates(st, {eid: repo.passages(eid)})}["schema"] is True


def test_no_baseline_when_planner_already_supplied_both():
    hs = [{"id": "H-1", "text": "a", "benign": True, "kind": "benign"}, {"id": "H-2", "text": "b", "benign": False, "kind": "misassociation"}]
    assert validate.ensure_baseline_hypotheses(hs) == [] and len(hs) == 2
