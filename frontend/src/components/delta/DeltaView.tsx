import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import { Ban, CirclePlus, CircleDashed, CheckCircle2, Pencil, RotateCcw } from 'lucide-react'
import type { Delta, DeltaLine, EvidenceOut } from '@/types'
import { CitationLink, DISCREPANCY, Pill, Tag } from '@/components/investigation/Primitives'

export const CHANGE_META: Record<DeltaLine['change'], { hue: string; label: string; icon: ReactNode }> = {
  added: { hue: '#4DD8FF', label: 'added', icon: <CirclePlus size={12} /> },
  revised: { hue: '#D8B26A', label: 'revised', icon: <Pencil size={12} /> },
  resolved: { hue: '#3FC1B0', label: 'resolved', icon: <CheckCircle2 size={12} /> },
  stale: { hue: '#8B93A1', label: 'stale', icon: <CircleDashed size={12} /> },
  reopened: { hue: DISCREPANCY, label: 'reopened', icon: <RotateCcw size={12} /> },
}
const ORDER: DeltaLine['change'][] = ['stale', 'revised', 'resolved', 'reopened', 'added']

export function ApprovalVoidedBanner() {
  return (
    <div role="alert" className="flex items-start gap-2 rounded border px-3 py-2 text-[12.5px]" style={{ borderColor: DISCREPANCY, background: `color-mix(in srgb, ${DISCREPANCY} 10%, transparent)` }}>
      <Ban size={15} className="mt-0.5 shrink-0" style={{ color: DISCREPANCY }} />
      <div>
        <b className="font-semibold" style={{ color: DISCREPANCY }}>Approval voided.</b>{' '}
        New evidence changed the case after a reviewer decision, so that decision no longer applies. A reviewer must look at this revision again.
      </div>
    </div>
  )
}

export function CountChips({ delta }: { delta: Delta }) {
  const c: [DeltaLine['change'], number][] = [['added', delta.added.length], ['revised', delta.revised.length], ['resolved', delta.resolved.length], ['stale', delta.stale.length]]
  const reopened = delta.lines.filter((l) => l.change === 'reopened').length
  if (reopened) c.push(['reopened', reopened])
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {c.map(([k, n]) => (
        <Pill key={k} hue={CHANGE_META[k].hue} icon={CHANGE_META[k].icon} className={k === 'stale' ? 'v-hatch' : ''}>{n} {CHANGE_META[k].label}</Pill>
      ))}
      <span className="text-[11px] opacity-50">{delta.unchanged} unchanged</span>
    </span>
  )
}

export function DeltaLineRow({ line, caseId, title, evName }: { line: DeltaLine; caseId: string; title?: string; evName: Map<string, string> }) {
  const m = CHANGE_META[line.change]
  const hasBefore = !!line.before
  const hasAfter = !!line.after
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`v-panel list-none p-3 ${line.change === 'stale' ? 'v-hatch' : ''}`}
      style={{ borderLeft: `3px ${line.change === 'stale' ? 'dashed' : 'solid'} ${m.hue}` }}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill hue={m.hue} icon={m.icon}>{m.label}</Pill>
        <Tag id={line.finding_id} />
        {title && <span className="text-[13px] font-semibold">{title}</span>}
      </div>
      {(hasBefore || hasAfter) && (
        <div className="mt-2 grid gap-2 text-[12.5px] leading-snug md:grid-cols-2">
          {hasBefore && (
            <div>
              <div className="mb-0.5 text-[10px] uppercase tracking-widest opacity-50">{line.change === 'stale' ? 'held text (still on the file)' : 'before'}</div>
              <p className={`m-0 ${line.change === 'stale' ? 'opacity-70' : 'v-del'}`}>{line.before}</p>
            </div>
          )}
          {hasAfter && (
            <div className={hasBefore ? '' : 'md:col-span-2'}>
              <div className="mb-0.5 text-[10px] uppercase tracking-widest opacity-50">after</div>
              <p className="v-ins m-0 block">{line.after}</p>
            </div>
          )}
        </div>
      )}
      {line.change === 'stale' && !hasAfter && (
        <p className="v-hatch-strong mb-0 mt-2 rounded border border-dashed v-hair px-2 py-1 text-[12px] opacity-80">After: <i>awaiting re-resolution</i>. This finding cites the changed exhibit, so it is not trusted until it is re-checked.</p>
      )}
      {line.reason && (
        <p className="mb-0 mt-2 text-[12.5px] leading-snug"><b className="font-semibold opacity-70">Why: </b>{line.reason}</p>
      )}
      {line.refs.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {line.refs.map((r, i) => <CitationLink key={i} caseId={caseId} sref={r} evidenceName={evName.get(r.evidence_id)} />)}
        </div>
      )}
    </motion.li>
  )
}

export function DeltaView({ delta, caseId, evidence, titles }: { delta: Delta; caseId: string; evidence: EvidenceOut[]; titles?: Record<string, string> }) {
  const evName = new Map(evidence.map((e) => [e.id, e.filename]))
  const lines = [...delta.lines].sort((a, b) => ORDER.indexOf(a.change) - ORDER.indexOf(b.change))
  return (
    <div className="flex flex-col gap-3">
      {delta.approval_voided && <ApprovalVoidedBanner />}
      <div className="flex flex-wrap items-center gap-2">
        {delta.cause && <span className="text-[12.5px]"><span className="opacity-55">Cause: </span>{delta.cause}</span>}
        <CountChips delta={delta} />
      </div>
      {lines.length === 0 ? (
        <p className="m-0 text-[12.5px] opacity-65">No finding changed in this revision.</p>
      ) : (
        <ul className="m-0 flex flex-col gap-2 p-0">
          {lines.map((l, i) => <DeltaLineRow key={`${l.finding_id}-${l.change}-${i}`} line={l} caseId={caseId} title={titles?.[l.finding_id]} evName={evName} />)}
        </ul>
      )}
    </div>
  )
}
