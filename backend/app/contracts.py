"""Shared data contract for Verity. THE source of truth: frontend/src/types.ts mirrors it by hand.

Every case revision stores one `CaseState` document (JSONB). Findings carry a justification set so new
evidence can mark exactly the dependent findings stale. Amounts are decimal STRINGS (never floats).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Epistemic = Literal["observed", "reported", "computed", "inferred", "human"]
Relation = Literal["consistent", "inconsistent", "neutral"]
Receipt = Literal["matched", "partial", "unverified", "n/a"]
FindingType = Literal["observation", "discrepancy", "policy", "calc", "anomaly", "missing"]
FindingStatus = Literal["active", "stale", "resolved", "superseded"]
EvidenceKind = Literal["photo", "narrative", "policy", "estimate", "history", "metadata", "weather", "telematics", "other"]
SourceClass = Literal["third_party", "claimant", "system", "model", "human"]
EvidenceStatus = Literal["stored", "processing", "extracted", "failed", "unsupported"]
StepStatus = Literal["pending", "running", "done", "skipped", "failed"]

# Simplified clock-style damage zones (inspired by SAE J224 clock directions; NOT the full CDC code).
ZONES = ["front", "front_left", "left", "rear_left", "rear", "rear_right", "right", "front_right", "roof", "underbody", "unknown"]


class SourceRef(BaseModel):
    evidence_id: str
    page: Optional[int] = None
    quote: Optional[str] = None  # must be found in the source text for receipt == matched
    zone: Optional[str] = None  # one of ZONES, for photo / estimate refs
    receipt: Receipt = "n/a"


class Justification(BaseModel):
    evidence_ids: list[str] = []
    entity_keys: list[str] = []  # e.g. "zone:rear", "amount:48250", "clause:7", "date:2026-10-02", "vehicle:KA01AB1234"


class Fact(BaseModel):
    id: str  # "X-001"
    evidence_id: str
    label: str
    value: str
    epistemic: Epistemic
    entity_key: Optional[str] = None
    ref: Optional[SourceRef] = None


class Finding(BaseModel):
    id: str  # "F-01"
    type: FindingType
    title: str
    body: str
    epistemic: Epistemic
    status: FindingStatus = "active"
    supports: list[SourceRef] = []
    contradicts: list[SourceRef] = []
    alternatives: list[str] = []
    uncertainty: str = ""
    action: str = ""
    justification: Justification = Field(default_factory=Justification)
    since_rev: int = 1
    revised_rev: Optional[int] = None
    prior_body: Optional[str] = None  # text before the latest revision, for diff display
    stale_reason: Optional[str] = None


class Hypothesis(BaseModel):
    id: str  # "H-1"
    text: str
    benign: bool = False  # at least one hypothesis must be benign, one a data/record error
    kind: Literal["benign", "data_error", "secondary_event", "misassociation", "other"] = "other"
    inconsistencies: int = 0
    rank: int = 0  # ordinal by FEWEST inconsistencies; ties share a rank. No probabilities anywhere.
    covered_zones: list[str] = []  # zones whose repair lines belong to the insured event if this hypothesis holds; ["all"] = every line

    @field_validator("covered_zones", mode="before")
    @classmethod
    def _coerce_zones(cls, v):  # older stored revisions kept "all" / None here
        if v is None:
            return []
        return [v] if isinstance(v, str) else v


class Cell(BaseModel):
    hypothesis_id: str
    evidence_id: str
    relation: Relation
    why: str = ""
    receipt: Receipt = "n/a"  # a cell without a valid receipt is downgraded to neutral by validate.py


class Prediction(BaseModel):
    if_supports: str  # what we would conclude if the requested evidence supports the leading hypothesis
    if_contradicts: str


class EvidenceRequest(BaseModel):
    id: str  # "R-01"
    key: str  # idempotency key: stable hash of (case, text-normalised); retries never duplicate
    text: str
    kind: str = "document"  # photo | document | statement | inspection | data
    resolves: list[str] = []  # hypothesis ids it helps separate
    pairs_separated: int = 0  # computed in code from the matrix, never by the model
    rupees_at_stake: Optional[str] = None  # decimal string; None = not computable
    prediction: Optional[Prediction] = None
    status: Literal["open", "received", "dropped"] = "open"
    created_rev: int = 1
    outcome: Literal["pending", "matched_prediction", "unanticipated"] = "pending"


class Unresolved(BaseModel):
    term: str
    why: str
    needs: str


class CalcLine(BaseModel):
    code: str
    label: str
    amount: str
    basis: str = ""
    clause: Optional[SourceRef] = None
    flag: Optional[Literal["duplicate_suspect", "arithmetic_error", "not_covered", "depreciated"]] = None


class Conditional(BaseModel):
    hypothesis_id: str
    settlement: Optional[str] = None  # None = cannot be computed under this hypothesis
    note: str = ""


class Calc(BaseModel):
    currency: str = "INR"
    lines: list[CalcLine] = []
    quoted_total: Optional[str] = None
    recomputed_total: Optional[str] = None
    arithmetic_corrections: list[str] = []
    duplicates: list[str] = []
    non_covered: list[str] = []
    depreciation: Optional[str] = None
    deductible: Optional[str] = None
    covered_loss: Optional[str] = None
    proposed_settlement: Optional[str] = None  # None whenever `unresolved` is non-empty
    unresolved: list[Unresolved] = []
    conditional: list[Conditional] = []


class TimelineStep(BaseModel):
    order: int
    text: str
    basis: Literal["reported", "observed", "inferred"]
    refs: list[SourceRef] = []
    hypothesis_ids: list[str] = []  # which hypotheses assert this step; empty = common to all


class ZoneView(BaseModel):
    narrative: list[str] = []
    photo: list[str] = []
    estimate: list[str] = []
    mismatch: bool = False
    note: str = ""


class DeltaLine(BaseModel):
    finding_id: str
    change: Literal["added", "revised", "resolved", "stale", "reopened"]
    before: Optional[str] = None
    after: Optional[str] = None
    reason: str = ""
    refs: list[SourceRef] = []


class Delta(BaseModel):
    cause: str = ""  # e.g. "E-07 statement.pdf added"
    added: list[str] = []
    revised: list[str] = []
    resolved: list[str] = []
    stale: list[str] = []
    unchanged: int = 0
    lines: list[DeltaLine] = []
    approval_voided: bool = False


class PlanStep(BaseModel):
    name: str  # ingest | extract:E-03 | analyze | validate | invalidate | persist
    status: StepStatus = "pending"
    reason: str = ""


class CaseState(BaseModel):
    rev: int
    evidence_ids: list[str] = []
    facts: list[Fact] = []
    findings: list[Finding] = []
    hypotheses: list[Hypothesis] = []
    matrix: list[Cell] = []
    requests: list[EvidenceRequest] = []
    calc: Optional[Calc] = None
    timeline: list[TimelineStep] = []
    zones: ZoneView = Field(default_factory=ZoneView)
    unresolved: list[str] = []
    summary: str = ""
    recommendation: str = ""  # neutral wording, e.g. "Hold: discrepancy open; request R-01 first"
    injection_flags: list[dict] = []  # {evidence_id, text}: embedded instruction-like strings, ignored


class GateResult(BaseModel):
    name: str  # schema | citations | language | math | unverified
    passed: bool
    detail: str = ""


# ---------- API shapes ----------
class EvidenceOut(BaseModel):
    id: str
    case_id: str
    kind: EvidenceKind
    filename: str
    mime: str
    size: int
    sha256: str
    source_class: SourceClass
    status: EvidenceStatus
    error: Optional[str] = None
    pages: int = 0
    uploaded_at: str
    extraction: Optional[dict] = None  # latest payload
    extraction_version: int = 0
    meta: dict = {}  # EXIF / file properties / passport
    injection_flags: list[str] = []


class RevisionOut(BaseModel):
    rev: int
    created_at: str
    trigger: str
    summary: str
    delta: Delta
    hash: str
    prev_hash: str


class ApprovalOut(BaseModel):
    id: str
    rev: int
    decision: Literal["approve", "return", "escalate"]
    reviewer: str
    authority_role: str
    note: str
    rupees: Optional[str] = None
    hash: str
    status: Literal["active", "void"]
    void_reason: Optional[str] = None
    created_at: str


class JobOut(BaseModel):
    id: str
    case_id: str
    status: Literal["queued", "running", "done", "failed", "interrupted"]
    base_rev: int
    plan: list[PlanStep] = []
    error: Optional[str] = None
    created_at: str


class ActivityOut(BaseModel):
    ts: str
    kind: Literal["stage", "tool", "provider", "audit"]
    name: str
    args: dict = {}
    result: dict = {}
    status: str = "ok"
    duration_ms: int = 0


class CaseSummary(BaseModel):
    id: str
    case_no: str  # "CLM-2026-0001"
    title: str
    status: Literal["intake", "processing", "evidence_needed", "ready_for_review", "reviewed", "failed"]
    unresolved: int = 0
    open_requests: int = 0
    evidence_count: int = 0
    rev: int = 0
    synthetic: bool = True
    updated_at: str


class CaseDetail(BaseModel):
    case: CaseSummary
    evidence: list[EvidenceOut]
    state: Optional[CaseState] = None
    revisions: list[RevisionOut] = []
    approvals: list[ApprovalOut] = []
    jobs: list[JobOut] = []
    activity: list[ActivityOut] = []
    approval_current: Optional[ApprovalOut] = None  # active approval bound to the CURRENT rev, else None


class AiHealth(BaseModel):
    configured: bool
    providers: list[dict] = []  # {name, model, healthy, last_error, last_latency_ms}
    message: str = ""


class Health(BaseModel):
    ok: bool
    db: str  # "postgresql 16.x" or error
    ai: AiHealth
    version: str = "0.1.0"
