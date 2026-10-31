import type { ReactNode } from 'react'
import { Eye, MessageSquareQuote, Calculator, Lightbulb, UserCheck, Layers, CircleHelp, CheckCircle2, CircleDashed, XCircle, Loader2, Ban, CircleDot, ShieldAlert, FileSearch, ListChecks } from 'lucide-react'
import type { Epistemic, Receipt, EvidenceStatus, CaseSummary, FindingStatus } from '@/types'
import { cn } from '@/lib/utils'

/** Base chip: icon + word + colour (never colour alone). `tone` is a CSS variable name (without --). */
export function Chip({ tone = 'ink-2', icon, children, dashed, solid, hatch, className, title }: {
  tone?: string; icon?: ReactNode; children: ReactNode; dashed?: boolean; solid?: boolean; hatch?: boolean; className?: string; title?: string
}) {
  return (
    <span
      title={title}
      style={{ color: `var(--${tone})`, borderColor: `color-mix(in srgb, var(--${tone}) 55%, transparent)`, background: solid ? `color-mix(in srgb, var(--${tone}) 14%, transparent)` : undefined }}
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-[5px] border px-1.5 py-[1px] text-[0.68rem] font-semibold uppercase tracking-wider',
        dashed ? 'border-dashed' : 'border-solid',
        hatch && 'hatch',
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}

const EPI: Record<Epistemic, { tone: string; label: string; icon: ReactNode; dashed?: boolean; solid?: boolean; hint: string }> = {
  observed: { tone: 'observed', label: 'Observed', icon: <Eye size={11} />, hint: 'Directly seen in the evidence (photo, document text).' },
  reported: { tone: 'reported', label: 'Reported', icon: <MessageSquareQuote size={11} />, hint: 'Stated by a person or document; not independently verified.' },
  computed: { tone: 'computed', label: 'Computed', icon: <Calculator size={11} />, hint: 'Calculated deterministically in code from cited inputs.' },
  inferred: { tone: 'inferred', label: 'Inferred', icon: <Lightbulb size={11} />, dashed: true, hint: 'Model inference. Treat as a lead, not a fact.' },
  human: { tone: 'human', label: 'Human', icon: <UserCheck size={11} />, solid: true, hint: 'Entered or corrected by a human reviewer.' },
}

export function EpistemicChip({ kind, className }: { kind: Epistemic; className?: string }) {
  const e = EPI[kind] ?? EPI.inferred
  return <Chip tone={e.tone} icon={e.icon} dashed={e.dashed} solid={e.solid} title={e.hint} className={className}>{e.label}</Chip>
}

export function ReceiptChip({ state, className }: { state: Receipt; className?: string }) {
  switch (state) {
    case 'matched': return <Chip tone="observed" icon={<CheckCircle2 size={11} />} className={className} title="Quote found verbatim in the source text.">Receipt matched</Chip>
    case 'partial': return <Chip tone="inferred" icon={<CircleDot size={11} />} dashed className={className} title="Quote found only approximately (fuzzy match).">Receipt partial</Chip>
    case 'unverified': return <Chip tone="discrepancy" icon={<CircleHelp size={11} />} className={className} title="Quote not found in the source. Excluded from the money maths until a human accepts it.">Unverified</Chip>
    default: return <Chip tone="stale" icon={<CircleDashed size={11} />} className={className}>No receipt</Chip>
  }
}

export function FindingStatusChip({ status }: { status: FindingStatus }) {
  switch (status) {
    case 'active': return <Chip tone="accent" icon={<CircleDot size={11} />}>Active</Chip>
    case 'stale': return <Chip tone="stale" icon={<Layers size={11} />} hatch>Stale</Chip>
    case 'resolved': return <Chip tone="observed" icon={<CheckCircle2 size={11} />}>Resolved</Chip>
    default: return <Chip tone="stale" icon={<Ban size={11} />}>Superseded</Chip>
  }
}

export function EvidenceStatusChip({ status }: { status: EvidenceStatus }) {
  switch (status) {
    case 'extracted': return <Chip tone="observed" icon={<CheckCircle2 size={11} />}>Extracted</Chip>
    case 'processing': return <Chip tone="accent" icon={<Loader2 size={11} className="animate-spin" />}>Reading</Chip>
    case 'failed': return <Chip tone="discrepancy" icon={<XCircle size={11} />}>Failed</Chip>
    case 'unsupported': return <Chip tone="stale" icon={<Ban size={11} />} hatch>Unsupported</Chip>
    default: return <Chip tone="ink-2" icon={<FileSearch size={11} />}>Stored</Chip>
  }
}

export function CaseStatusChip({ status }: { status: CaseSummary['status'] }) {
  switch (status) {
    case 'processing': return <Chip tone="accent" icon={<Loader2 size={11} className="animate-spin" />}>Processing</Chip>
    case 'evidence_needed': return <Chip tone="inferred" icon={<ListChecks size={11} />} dashed>Evidence needed</Chip>
    case 'ready_for_review': return <Chip tone="computed" icon={<FileSearch size={11} />} solid>Ready for review</Chip>
    case 'reviewed': return <Chip tone="human" icon={<UserCheck size={11} />} solid>Reviewed</Chip>
    case 'failed': return <Chip tone="discrepancy" icon={<ShieldAlert size={11} />}>Failed</Chip>
    default: return <Chip tone="ink-2" icon={<CircleDashed size={11} />}>Intake</Chip>
  }
}
