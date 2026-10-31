// DEV-ONLY fixture for building the Investigation / Changes views. Loaded via dynamic import behind import.meta.env.DEV
// and only when the URL has ?devmock. Never part of a production code path. Synthetic data.
import type { CaseDetail, CaseState, Delta, EvidenceOut, RevisionOut } from '@/types'

const ev = (id: string, kind: EvidenceOut['kind'], filename: string): EvidenceOut => ({
  id, case_id: 'dev', kind, filename, mime: 'application/octet-stream', size: 1000, sha256: id.padEnd(64, '0'), source_class: 'claimant',
  status: 'extracted', pages: 2, uploaded_at: '2026-10-31T10:00:00Z', extraction_version: 1, meta: {}, injection_flags: [],
})
const evidence = [ev('E-01', 'narrative', 'statement.txt'), ev('E-02', 'photo', 'damage_front.jpg'), ev('E-03', 'estimate', 'estimate.pdf'), ev('E-04', 'policy', 'policy.pdf')]
const evidence2 = [...evidence, ev('E-05', 'narrative', 'garage_report.txt')]

const rev1: CaseState = {
  rev: 1, evidence_ids: evidence.map((e) => e.id), facts: [],
  hypotheses: [
    { id: 'H-1', text: 'Rear strike, as the statement says', benign: false, kind: 'other', inconsistencies: 2, rank: 2 },
    { id: 'H-2', text: 'Chain collision: secondary impact moved the car forward into the front damage', benign: true, kind: 'benign', inconsistencies: 2, rank: 2 },
    { id: 'H-3', text: 'Statement or photo belongs to a different vehicle or event (record error)', benign: false, kind: 'data_error', inconsistencies: 1, rank: 1 },
  ],
  matrix: [
    { hypothesis_id: 'H-1', evidence_id: 'E-01', relation: 'consistent', why: 'Statement says "hit from behind".', receipt: 'matched' },
    { hypothesis_id: 'H-1', evidence_id: 'E-02', relation: 'inconsistent', why: 'Photo shows front bumper damage only.', receipt: 'n/a' },
    { hypothesis_id: 'H-1', evidence_id: 'E-03', relation: 'inconsistent', why: 'Estimate charges a front bumper.', receipt: 'matched' },
    { hypothesis_id: 'H-2', evidence_id: 'E-01', relation: 'inconsistent', why: 'Statement describes a single impact, not two.', receipt: 'partial' },
    { hypothesis_id: 'H-2', evidence_id: 'E-02', relation: 'inconsistent', why: 'Front damage has no documented cause yet.', receipt: 'n/a' },
    { hypothesis_id: 'H-2', evidence_id: 'E-03', relation: 'neutral', why: '', receipt: 'n/a' },
    { hypothesis_id: 'H-3', evidence_id: 'E-01', relation: 'neutral', why: '', receipt: 'n/a' },
    { hypothesis_id: 'H-3', evidence_id: 'E-02', relation: 'consistent', why: 'Plate is not legible; vehicle identity unconfirmed.', receipt: 'n/a' },
    { hypothesis_id: 'H-3', evidence_id: 'E-03', relation: 'inconsistent', why: 'Estimate vehicle number matches the policy.', receipt: 'partial' },
  ],
  findings: [
    { id: 'F-01', type: 'discrepancy', title: 'Impact zone differs between statement and photo', body: 'The statement places the impact at the rear; the photograph and the estimate both point to the front.', epistemic: 'inferred', status: 'active',
      supports: [{ evidence_id: 'E-01', page: 1, quote: 'hit from behind', receipt: 'matched' }], contradicts: [{ evidence_id: 'E-02', zone: 'front', receipt: 'n/a' }, { evidence_id: 'E-03', page: 1, quote: 'Front bumper', receipt: 'matched' }],
      alternatives: ['A second impact occurred after the first', 'The wrong photograph was attached'], uncertainty: 'No independent account of the event sequence.', action: 'Request any garage or third-party report.',
      justification: { evidence_ids: ['E-01', 'E-02', 'E-03'], entity_keys: ['zone:rear', 'zone:front'] }, since_rev: 1 },
    { id: 'F-02', type: 'calc', title: 'Estimate total reconciles', body: 'Line items sum to the quoted total.', epistemic: 'computed', status: 'active', supports: [{ evidence_id: 'E-03', page: 1, quote: '24,600', receipt: 'matched' }], contradicts: [], alternatives: [], uncertainty: '', action: '',
      justification: { evidence_ids: ['E-03'], entity_keys: ['amount:24600'] }, since_rev: 1 },
    { id: 'F-03', type: 'missing', title: 'Depreciation schedule not found', body: 'The policy pages supplied do not contain a depreciation schedule.', epistemic: 'observed', status: 'active', supports: [{ evidence_id: 'E-04', page: 1, receipt: 'n/a' }], contradicts: [], alternatives: [], uncertainty: 'A page may be missing.', action: 'Request the complete policy.',
      justification: { evidence_ids: ['E-04'], entity_keys: ['clause:depreciation'] }, since_rev: 1 },
  ],
  requests: [
    { id: 'R-01', key: 'k1', text: 'Provide the garage or tow report for this event.', kind: 'document', resolves: ['H-1', 'H-2'], pairs_separated: 2, rupees_at_stake: '18200', status: 'open', created_rev: 1, outcome: 'pending',
      prediction: { if_supports: 'A second vehicle struck first: chain collision (H-2) moves up.', if_contradicts: 'Single rear strike with front damage unexplained: record error (H-3) moves up.' } },
    { id: 'R-02', key: 'k2', text: 'Provide the full policy schedule including depreciation.', kind: 'document', resolves: ['H-1'], pairs_separated: 1, rupees_at_stake: '2450.50', status: 'open', created_rev: 1, outcome: 'pending', prediction: null },
  ],
  calc: null, timeline: [
    { order: 1, text: 'Vehicle is parked or stopped.', basis: 'reported', refs: [{ evidence_id: 'E-01', page: 1, quote: 'stopped at the signal', receipt: 'matched' }], hypothesis_ids: [] },
    { order: 2, text: 'Struck from behind.', basis: 'reported', refs: [{ evidence_id: 'E-01', page: 1, quote: 'hit from behind', receipt: 'matched' }], hypothesis_ids: ['H-1'] },
    { order: 3, text: 'A second vehicle strikes from behind, pushing the car forward.', basis: 'inferred', refs: [], hypothesis_ids: ['H-2'] },
    { order: 4, text: 'Front bumper contacts the vehicle ahead.', basis: 'observed', refs: [{ evidence_id: 'E-02', zone: 'front', receipt: 'n/a' }], hypothesis_ids: ['H-2'] },
    { order: 5, text: 'Photograph taken of the damaged front.', basis: 'observed', refs: [{ evidence_id: 'E-02', receipt: 'n/a' }], hypothesis_ids: [] },
  ],
  zones: { narrative: ['rear'], photo: ['front'], estimate: ['front'], mismatch: true, note: 'The statement cites the rear; the photo and estimate cite the front.' },
  unresolved: ['Depreciation schedule', 'Impact zone discrepancy'], summary: 'One open discrepancy between the statement and the photograph. Settlement cannot be proposed yet.', recommendation: 'Hold: discrepancy open; request R-01 first.', injection_flags: [],
}

const rev2: CaseState = {
  ...rev1, rev: 2, evidence_ids: evidence2.map((e) => e.id),
  hypotheses: [
    { id: 'H-1', text: rev1.hypotheses[0].text, benign: false, kind: 'other', inconsistencies: 3, rank: 3 },
    { id: 'H-2', text: rev1.hypotheses[1].text, benign: true, kind: 'benign', inconsistencies: 0, rank: 1 },
    { id: 'H-3', text: rev1.hypotheses[2].text, benign: false, kind: 'data_error', inconsistencies: 2, rank: 2 },
  ],
  matrix: [
    ...rev1.matrix.map((c) => (c.hypothesis_id === 'H-2' && c.evidence_id === 'E-02' ? { ...c, relation: 'consistent' as const, why: 'Garage report describes a push into the vehicle ahead.', receipt: 'matched' as const } : c.hypothesis_id === 'H-2' && c.evidence_id === 'E-01' ? { ...c, relation: 'neutral' as const, why: 'Statement is silent on a second impact.', receipt: 'n/a' as const } : c)),
    { hypothesis_id: 'H-1', evidence_id: 'E-05', relation: 'inconsistent', why: 'Report records two impacts, not one.', receipt: 'matched' },
    { hypothesis_id: 'H-2', evidence_id: 'E-05', relation: 'consistent', why: 'Report: "second vehicle struck from behind".', receipt: 'matched' },
    { hypothesis_id: 'H-3', evidence_id: 'E-05', relation: 'inconsistent', why: 'Report lists the same registration.', receipt: 'matched' },
  ],
  findings: [
    { ...rev1.findings[0], status: 'resolved', revised_rev: 2, prior_body: rev1.findings[0].body, body: 'A garage report describes a chain collision: the rear strike pushed the car into the vehicle ahead, which explains the front damage.', stale_reason: undefined, epistemic: 'reported' },
    rev1.findings[1],
    { ...rev1.findings[2], status: 'stale', stale_reason: 'Policy page request R-02 is unchanged, but the garage report cites a clause number not in the supplied pages.' },
  ],
  requests: [
    { ...rev1.requests[0], status: 'received', outcome: 'matched_prediction' },
    rev1.requests[1],
  ],
  zones: { ...rev1.zones, mismatch: false, note: 'The garage report reconciles the two impact zones as one sequence.' },
  recommendation: 'Review: discrepancy explained by new evidence; depreciation still unresolved.',
}

const delta2: Delta = {
  cause: 'E-05 garage_report.txt added', added: [], revised: ['F-01'], resolved: ['F-01'], stale: ['F-03'], unchanged: 1, approval_voided: true,
  lines: [
    { finding_id: 'F-01', change: 'resolved', before: rev1.findings[0].body, after: rev2.findings[0].body, reason: 'The garage report separates two impacts, which accounts for the front damage.', refs: [{ evidence_id: 'E-05', page: 1, quote: 'second vehicle struck from behind', receipt: 'matched' }] },
    { finding_id: 'F-03', change: 'stale', before: rev1.findings[2].body, after: null, reason: 'Depends on the policy clause the new report cites.', refs: [{ evidence_id: 'E-05', page: 1, receipt: 'n/a' }] },
  ],
}

const revs: RevisionOut[] = [
  { rev: 1, created_at: '2026-10-31T10:02:00Z', trigger: 'E-01..E-04 uploaded', summary: rev1.summary, delta: { cause: 'initial analysis', added: ['F-01', 'F-02', 'F-03'], revised: [], resolved: [], stale: [], unchanged: 0, approval_voided: false, lines: rev1.findings.map((f) => ({ finding_id: f.id, change: 'added' as const, before: null, after: f.body, reason: 'First analysis', refs: f.supports.slice(0, 1) })) }, hash: 'a91f03c2e84b1d7a'.padEnd(64, '0'), prev_hash: '0'.repeat(64) },
  { rev: 2, created_at: '2026-10-31T10:20:00Z', trigger: 'E-05 garage_report.txt added', summary: rev2.summary, delta: delta2, hash: '5c70be19d3a4f862'.padEnd(64, '0'), prev_hash: 'a91f03c2e84b1d7a'.padEnd(64, '0') },
]

export function devDetail(rev: 1 | 2): CaseDetail {
  const state = rev === 1 ? rev1 : rev2
  return {
    case: { id: 'dev', case_no: 'CLM-2026-0001', title: 'DEV mock case', status: 'evidence_needed', unresolved: 2, open_requests: 2, evidence_count: rev === 1 ? 4 : 5, rev, synthetic: true, updated_at: '2026-10-31T10:20:00Z' },
    evidence: rev === 1 ? evidence : evidence2, state, revisions: revs.slice(0, rev), approvals: [], jobs: [], activity: [], approval_current: null,
  }
}
export const devRevisionStates: Record<number, CaseState> = { 1: rev1, 2: rev2 }
