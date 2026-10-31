import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Brain, Calculator, Check, CircleDashed, Eye, HelpCircle, Minus, Quote, UserCheck, X, AlertTriangle, MessageSquareQuote } from 'lucide-react'
import type { Epistemic, Receipt, Relation, SourceRef } from '@/types'
import { evidenceHref } from './net'
import './investigation.css'

export const EPI: Record<Epistemic, { hue: string; label: string; icon: ReactNode; dashed?: boolean }> = {
  observed: { hue: '#3FC1B0', label: 'observed', icon: <Eye size={11} /> },
  reported: { hue: '#8C93F5', label: 'reported', icon: <MessageSquareQuote size={11} /> },
  computed: { hue: '#6AA3D9', label: 'computed', icon: <Calculator size={11} /> },
  inferred: { hue: '#D8B26A', label: 'inferred', icon: <Brain size={11} />, dashed: true },
  human: { hue: '#ECE8DF', label: 'human', icon: <UserCheck size={11} /> },
}
export const DISCREPANCY = '#C77DDB'
export const ACCENT = '#4DD8FF'
export const NEUTRAL = '#8B93A1'

export function Tag({ id, className = '' }: { id: string; className?: string }) {
  return (
    <span className={`v-mono inline-block rounded-[3px] border v-hair px-1.5 py-px text-[10.5px] leading-4 tracking-tight opacity-90 ${className}`}>
      {id}
    </span>
  )
}

function tint(hue: string, pct = 14) {
  return `color-mix(in srgb, ${hue} ${pct}%, transparent)`
}

export function Pill({ hue, icon, children, dashed, title, className = '' }: { hue: string; icon?: ReactNode; children: ReactNode; dashed?: boolean; title?: string; className?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-px text-[10.5px] font-medium leading-4 whitespace-nowrap ${className}`}
      style={{ color: hue, background: tint(hue), border: `1px ${dashed ? 'dashed' : 'solid'} ${tint(hue, 55)}` }}
    >
      {icon}
      {children}
    </span>
  )
}

export function EpiChip({ kind }: { kind: Epistemic }) {
  const e = EPI[kind]
  return <Pill hue={e.hue} icon={e.icon} dashed={e.dashed}>{e.label}</Pill>
}

const REC: Record<Receipt, { hue: string; icon: ReactNode; label: string; hint: string }> = {
  matched: { hue: '#3FC1B0', icon: <Check size={10} strokeWidth={3} />, label: 'matched', hint: 'Quote found in the source text' },
  partial: { hue: '#D8B26A', icon: <Quote size={10} />, label: 'partial', hint: 'Close match (fuzzy), not exact' },
  unverified: { hue: DISCREPANCY, icon: <AlertTriangle size={10} />, label: 'unverified', hint: 'Could not be found in the source text' },
  'n/a': { hue: NEUTRAL, icon: <Minus size={10} />, label: 'no quote', hint: 'No quotation to check' },
}
export function ReceiptMark({ receipt, withLabel = false }: { receipt: Receipt; withLabel?: boolean }) {
  const r = REC[receipt]
  return (
    <span title={`Receipt: ${r.label}. ${r.hint}`} className="inline-flex items-center gap-0.5 rounded px-1 text-[10px] leading-4" style={{ color: r.hue, background: tint(r.hue, 12) }}>
      {r.icon}
      {withLabel && r.label}
    </span>
  )
}

const REL: Record<Relation, { hue: string; icon: ReactNode; label: string }> = {
  consistent: { hue: '#6AA3D9', icon: <Check size={12} strokeWidth={2.5} />, label: 'consistent' },
  inconsistent: { hue: DISCREPANCY, icon: <X size={12} strokeWidth={2.5} />, label: 'inconsistent' },
  neutral: { hue: NEUTRAL, icon: <Minus size={12} />, label: 'neutral' },
}
export const REL_META = REL

export function RelationChip({ relation, receipt, compact }: { relation: Relation; receipt?: Receipt; compact?: boolean }) {
  const r = REL[relation]
  return (
    <span className="inline-flex items-center gap-1">
      <Pill hue={r.hue} icon={r.icon} className={compact ? 'px-1.5' : ''}>{r.label}</Pill>
      {receipt && <ReceiptMark receipt={receipt} />}
    </span>
  )
}

export function StaleChip({ rev }: { rev?: number | null }) {
  return <Pill hue={NEUTRAL} icon={<CircleDashed size={11} />} className="v-hatch" title="Depends on evidence that changed; awaiting re-resolution">stale{rev != null ? ` since r${rev}` : ''}</Pill>
}

export function CitationLink({ caseId, sref, evidenceName }: { caseId: string; sref: SourceRef; evidenceName?: string }) {
  return (
    <Link
      to={evidenceHref(caseId, sref)}
      title={sref.quote ? `Open source: "${sref.quote}"` : 'Open source evidence'}
      className="group inline-flex max-w-full items-center gap-1 rounded border v-hair px-1.5 py-0.5 text-[11px] leading-4 no-underline transition-colors hover:border-[#4DD8FF] hover:text-[#4DD8FF]"
    >
      <span className="v-mono shrink-0">{sref.evidence_id}</span>
      {sref.page != null && <span className="v-mono shrink-0 opacity-60">p{sref.page}</span>}
      {sref.zone && <span className="v-mono shrink-0 opacity-60">[{sref.zone}]</span>}
      {sref.quote ? <span className="truncate italic opacity-80">“{sref.quote}”</span> : evidenceName ? <span className="truncate opacity-60">{evidenceName}</span> : null}
      <ReceiptMark receipt={sref.receipt} />
    </Link>
  )
}

export function SectionHead({ title, kicker, right, icon }: { title: string; kicker?: string; right?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-2 flex items-end justify-between gap-3 border-b v-hair pb-1.5">
      <div className="flex items-center gap-2">
        {icon}
        <h2 className="m-0 text-[13px] font-semibold uppercase tracking-[0.12em]">{title}</h2>
        {kicker && <span className="text-[11.5px] opacity-55">{kicker}</span>}
      </div>
      {right}
    </div>
  )
}

export function Empty({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="v-panel flex items-center gap-2 px-3 py-4 text-[12.5px] opacity-70">
      {icon ?? <HelpCircle size={14} />}
      <span>{children}</span>
    </div>
  )
}

export function Btn({ children, onClick, disabled, busy, tone = 'default', title, type = 'button' }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; busy?: boolean; tone?: 'default' | 'accent' | 'quiet'; title?: string; type?: 'button' | 'submit'
}) {
  const base = 'inline-flex whitespace-nowrap items-center gap-1.5 rounded border px-2.5 py-1 text-[12px] font-medium leading-4 transition-colors disabled:cursor-not-allowed disabled:opacity-45 cursor-pointer'
  const tones = {
    default: 'v-hair hover:border-[#4DD8FF] hover:text-[#4DD8FF] bg-transparent',
    quiet: 'border-transparent hover:bg-current/5 bg-transparent',
    accent: 'border-[#4DD8FF] text-[#4DD8FF] bg-[#4DD8FF]/10 hover:bg-[#4DD8FF]/20',
  }
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled || busy} className={`${base} ${tones[tone]}`} style={{ color: tone === 'accent' ? undefined : undefined }}>
      {busy && <span className="v-spin inline-block size-3 rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  )
}

export const WATERMARK = 'Illustrative reconstruction, not physics'
