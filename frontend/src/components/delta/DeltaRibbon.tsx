import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowRight, Ban, GitCompareArrows } from 'lucide-react'
import type { CaseState, Delta } from '@/types'
import { ACCENT, DISCREPANCY, Tag } from '@/components/investigation/Primitives'
import { changesHref } from '@/components/investigation/net'
import { CHANGE_META, CountChips } from './DeltaView'

/** Compact ribbon for FRONT-A to show right after an upload: counts, the first lines, and a View changes link. */
export function DeltaRibbon({ delta, state, caseId: caseIdProp, rev: revProp, titles: titlesProp, className = '' }: { delta: Delta; state?: CaseState | null; caseId?: string; rev?: number; titles?: Record<string, string>; className?: string }) {
  const params = useParams<{ id: string }>()
  const caseId = caseIdProp ?? params.id ?? ''
  const rev = revProp ?? state?.rev
  const titles = useMemo(() => titlesProp ?? Object.fromEntries((state?.findings ?? []).map((f) => [f.id, f.title])), [titlesProp, state])
  const first = delta.lines.slice(0, 2)
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className={`rounded border px-3 py-2 text-[12.5px] ${className}`}
      style={{ borderColor: ACCENT, background: `color-mix(in srgb, ${ACCENT} 7%, transparent)` }}
    >
      <div className="flex flex-wrap items-center gap-2">
        <GitCompareArrows size={14} style={{ color: ACCENT }} />
        <b className="font-semibold">Evidence delta{rev != null ? ` · r${rev}` : ''}</b>
        {delta.cause && <span className="opacity-70">{delta.cause}</span>}
        <CountChips delta={delta} />
        {delta.approval_voided && (
          <span className="inline-flex items-center gap-1 text-[11.5px] font-semibold" style={{ color: DISCREPANCY }}><Ban size={12} /> approval voided</span>
        )}
        <Link to={changesHref(caseId, rev)} className="ml-auto inline-flex items-center gap-1 whitespace-nowrap no-underline" style={{ color: ACCENT }}>
          View changes <ArrowRight size={12} />
        </Link>
      </div>
      {first.length > 0 && (
        <ul className="m-0 mt-1.5 flex list-none flex-col gap-0.5 p-0">
          {first.map((l, i) => (
            <li key={i} className="flex items-baseline gap-1.5 leading-snug">
              <span style={{ color: CHANGE_META[l.change].hue }} className="shrink-0">{CHANGE_META[l.change].icon}</span>
              <Tag id={l.finding_id} />
              <span className="min-w-0 truncate opacity-85">{titles?.[l.finding_id] ?? l.reason}</span>
            </li>
          ))}
          {delta.lines.length > first.length && <li className="text-[11px] opacity-55">+{delta.lines.length - first.length} more</li>}
        </ul>
      )}
    </motion.div>
  )
}

export default DeltaRibbon
