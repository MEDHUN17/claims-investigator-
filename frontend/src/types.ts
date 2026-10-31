// Hand-mirrored from backend/app/contracts.py — keep in sync. Amounts are decimal strings.
export type Epistemic = 'observed' | 'reported' | 'computed' | 'inferred' | 'human'
export type Relation = 'consistent' | 'inconsistent' | 'neutral'
export type Receipt = 'matched' | 'partial' | 'unverified' | 'n/a'
export type FindingType = 'observation' | 'discrepancy' | 'policy' | 'calc' | 'anomaly' | 'missing'
export type FindingStatus = 'active' | 'stale' | 'resolved' | 'superseded'
export type EvidenceKind = 'photo' | 'narrative' | 'policy' | 'estimate' | 'history' | 'metadata' | 'weather' | 'telematics' | 'other'
export type SourceClass = 'third_party' | 'claimant' | 'system' | 'model' | 'human'
export type EvidenceStatus = 'stored' | 'processing' | 'extracted' | 'failed' | 'unsupported'
export type StepStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'
export const ZONES = ['front', 'front_left', 'left', 'rear_left', 'rear', 'rear_right', 'right', 'front_right', 'roof', 'underbody', 'unknown'] as const

export interface SourceRef { evidence_id: string; page?: number | null; quote?: string | null; zone?: string | null; receipt: Receipt }
export interface Justification { evidence_ids: string[]; entity_keys: string[] }
export interface Fact { id: string; evidence_id: string; label: string; value: string; epistemic: Epistemic; entity_key?: string | null; ref?: SourceRef | null }
export interface Finding {
  id: string; type: FindingType; title: string; body: string; epistemic: Epistemic; status: FindingStatus
  supports: SourceRef[]; contradicts: SourceRef[]; alternatives: string[]; uncertainty: string; action: string
  justification: Justification; since_rev: number; revised_rev?: number | null; prior_body?: string | null; stale_reason?: string | null
}
export interface Hypothesis { id: string; text: string; benign: boolean; kind: 'benign' | 'data_error' | 'secondary_event' | 'misassociation' | 'other'; inconsistencies: number; rank: number; covered_zones?: string[] | 'all' }
export interface Cell { hypothesis_id: string; evidence_id: string; relation: Relation; why: string; receipt: Receipt }
export interface Prediction { if_supports: string; if_contradicts: string }
export interface EvidenceRequest {
  id: string; key: string; text: string; kind: string; resolves: string[]; pairs_separated: number
  rupees_at_stake?: string | null; prediction?: Prediction | null; status: 'open' | 'received' | 'dropped'
  created_rev: number; outcome: 'pending' | 'matched_prediction' | 'unanticipated'
}
export interface Unresolved { term: string; why: string; needs: string }
export interface CalcLine { code: string; label: string; amount: string; basis: string; clause?: SourceRef | null; flag?: 'duplicate_suspect' | 'arithmetic_error' | 'not_covered' | 'depreciated' | null }
export interface Conditional { hypothesis_id: string; settlement?: string | null; note: string }
export interface Calc {
  currency: string; lines: CalcLine[]; quoted_total?: string | null; recomputed_total?: string | null
  arithmetic_corrections: string[]; duplicates: string[]; non_covered: string[]; depreciation?: string | null
  deductible?: string | null; covered_loss?: string | null; proposed_settlement?: string | null
  unresolved: Unresolved[]; conditional: Conditional[]
}
export interface TimelineStep { order: number; text: string; basis: 'reported' | 'observed' | 'inferred'; refs: SourceRef[]; hypothesis_ids: string[] }
export interface ZoneView { narrative: string[]; photo: string[]; estimate: string[]; mismatch: boolean; note: string }
export interface DeltaLine { finding_id: string; change: 'added' | 'revised' | 'resolved' | 'stale' | 'reopened'; before?: string | null; after?: string | null; reason: string; refs: SourceRef[] }
export interface Delta { cause: string; added: string[]; revised: string[]; resolved: string[]; stale: string[]; unchanged: number; lines: DeltaLine[]; approval_voided: boolean }
export interface PlanStep { name: string; status: StepStatus; reason: string }
export interface CaseState {
  rev: number; evidence_ids: string[]; facts: Fact[]; findings: Finding[]; hypotheses: Hypothesis[]; matrix: Cell[]
  requests: EvidenceRequest[]; calc?: Calc | null; timeline: TimelineStep[]; zones: ZoneView; unresolved: string[]
  summary: string; recommendation: string; injection_flags: { evidence_id: string; text: string }[]
}
export interface GateResult { name: string; passed: boolean; detail: string }

export interface EvidenceOut {
  id: string; case_id: string; kind: EvidenceKind; filename: string; mime: string; size: number; sha256: string
  source_class: SourceClass; status: EvidenceStatus; error?: string | null; pages: number; uploaded_at: string
  extraction?: Record<string, any> | null; extraction_version: number; meta: Record<string, any>; injection_flags: string[]
}
export interface RevisionOut { rev: number; created_at: string; trigger: string; summary: string; delta: Delta; hash: string; prev_hash: string }
export interface ApprovalOut {
  id: string; rev: number; decision: 'approve' | 'return' | 'escalate'; reviewer: string; authority_role: string; note: string
  rupees?: string | null; hash: string; status: 'active' | 'void'; void_reason?: string | null; created_at: string
}
export interface JobOut { id: string; case_id: string; status: 'queued' | 'running' | 'done' | 'failed' | 'interrupted'; base_rev: number; plan: PlanStep[]; error?: string | null; created_at: string }
export interface ActivityOut { ts: string; kind: 'stage' | 'tool' | 'provider' | 'audit'; name: string; args: Record<string, any>; result: Record<string, any>; status: string; duration_ms: number }
export interface CaseSummary {
  id: string; case_no: string; title: string; status: 'intake' | 'processing' | 'evidence_needed' | 'ready_for_review' | 'reviewed' | 'failed'
  unresolved: number; open_requests: number; evidence_count: number; rev: number; synthetic: boolean; updated_at: string
}
export interface CaseDetail {
  case: CaseSummary; evidence: EvidenceOut[]; state?: CaseState | null; revisions: RevisionOut[]; approvals: ApprovalOut[]
  jobs: JobOut[]; activity: ActivityOut[]; approval_current?: ApprovalOut | null
}
export interface AiHealth { configured: boolean; providers: { name: string; model: string; healthy: boolean; last_error?: string; last_latency_ms?: number }[]; message: string }
export interface Health { ok: boolean; db: string; ai: AiHealth; version: string }
export interface LabScenario { id: string; title: string; description: string; fixture_set: string; assertions: string[] }
export interface LabRow { scenario_id: string; passed: boolean; assertions: { text: string; passed: boolean; detail?: string }[]; latency_ms: number; ran_at: string; source: 'live' | 'stored' }
