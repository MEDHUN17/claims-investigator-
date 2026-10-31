import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, LayoutGroup } from 'motion/react'
import { ArrowRight, Equal, Layers, ShieldCheck, Wrench } from 'lucide-react'
import type { CaseState, Cell, EvidenceOut, Hypothesis } from '@/types'
import { ACCENT, DISCREPANCY, Empty, Pill, REL_META, ReceiptMark, SectionHead, Tag } from './Primitives'

type Moved = Record<string, { from: number; to: number }>

const KIND_LABEL: Record<Hypothesis['kind'], string> = {
  benign: 'benign explanation',
  data_error: 'record / data error',
  secondary_event: 'secondary event',
  misassociation: 'misassociation',
  other: 'other',
}

export function HypothesisBoard({ state, evidence }: { state: CaseState; evidence: EvidenceOut[] }) {
  const hyps = useMemo(() => [...state.hypotheses].sort((a, b) => a.rank - b.rank || a.id.localeCompare(b.id)), [state.hypotheses])
  const rankKey = hyps.map((h) => `${h.id}:${h.rank}`).join('|')
  const prev = useRef<Record<string, number> | null>(null)
  const [moved, setMoved] = useState<Moved>({})
  const [sel, setSel] = useState<{ h: string; e: string } | null>(null)

  useEffect(() => {
    const cur = Object.fromEntries(hyps.map((h) => [h.id, h.rank]))
    if (prev.current) {
      const m: Moved = {}
      for (const h of hyps) {
        const p = prev.current[h.id]
        if (p !== undefined && p !== h.rank) m[h.id] = { from: p, to: h.rank }
      }
      setMoved(m)
    }
    prev.current = cur
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankKey])

  const evById = useMemo(() => new Map(evidence.map((e) => [e.id, e])), [evidence])
  const evIds = useMemo(() => {
    const seen = new Set(state.matrix.map((c) => c.evidence_id))
    const ordered = evidence.map((e) => e.id).filter((id) => seen.has(id))
    for (const id of seen) if (!ordered.includes(id)) ordered.push(id)
    return ordered
  }, [state.matrix, evidence])
  const cell = useMemo(() => new Map<string, Cell>(state.matrix.map((c) => [`${c.hypothesis_id}|${c.evidence_id}`, c])), [state.matrix])
  const tieCount = useMemo(() => {
    const m = new Map<number, number>()
    hyps.forEach((h) => m.set(h.rank, (m.get(h.rank) ?? 0) + 1))
    return m
  }, [hyps])

  if (hyps.length === 0) {
    return (
      <section>
        <SectionHead title="Hypothesis board" icon={<Layers size={14} />} />
        <Empty>No competing explanations yet. They appear once the planner has read the evidence.</Empty>
      </section>
    )
  }

  const cols = `minmax(150px,190px) repeat(${hyps.length}, minmax(150px,1fr))`
  const selCell = sel ? cell.get(`${sel.h}|${sel.e}`) : null

  return (
    <section>
      <SectionHead
        title="Hypothesis board"
        kicker="competing explanations, ordered by fewest inconsistencies. Ordinal ranks only; there are no probabilities."
        icon={<Layers size={14} />}
        right={Object.keys(moved).length > 0 ? <Pill hue={ACCENT} icon={<ArrowRight size={11} />}>re-ranked this revision</Pill> : undefined}
      />
      <div className="v-panel overflow-x-auto">
        <LayoutGroup>
          <div style={{ minWidth: 150 * (hyps.length + 1) }}>
            {/* header row: rank ribbons */}
            <div className="grid border-b v-hair" style={{ gridTemplateColumns: cols }}>
              <div className="flex items-end p-2 text-[10.5px] uppercase tracking-widest opacity-55">Evidence \ Hypothesis</div>
              {hyps.map((h) => {
                const tied = (tieCount.get(h.rank) ?? 1) > 1
                const mv = moved[h.id]
                return (
                  <motion.div
                    key={h.id}
                    layout="position"
                    transition={{ type: 'spring', stiffness: 420, damping: 38, duration: 0.4 }}
                    className={`relative border-l v-hair p-2 ${mv ? 'v-flash' : ''}`}
                  >
                    <div className="mb-1.5 flex flex-wrap items-center gap-1">
                      <span
                        className="v-mono inline-flex items-center gap-1 rounded-sm px-1.5 py-px text-[10.5px] font-semibold"
                        style={{ background: `color-mix(in srgb, ${ACCENT} 16%, transparent)`, color: ACCENT }}
                        title={tied ? 'Tied: these hypotheses have the same number of inconsistencies' : 'Ordinal rank: fewest inconsistencies first'}
                      >
                        {tied && <Equal size={10} />}RANK {h.rank}{tied ? ' · tied' : ''}
                      </span>
                      {mv && (
                        <span className="v-mono text-[10px]" style={{ color: ACCENT }} title="Rank moved after the latest evidence">
                          r{mv.from} <ArrowRight size={9} className="inline" /> r{mv.to}
                        </span>
                      )}
                    </div>
                    <div className="mb-1 flex flex-wrap items-center gap-1.5">
                      <Tag id={h.id} />
                      <span className="text-[10.5px] opacity-60">{h.inconsistencies} inconsistent</span>
                    </div>
                    <div className="mb-1.5 text-[12px] leading-snug">{h.text}</div>
                    <div className="flex flex-wrap gap-1">
                      {h.benign ? (
                        <Pill hue="#3FC1B0" icon={<ShieldCheck size={10} />} title="A benign explanation is always kept on the board">benign explanation</Pill>
                      ) : h.kind === 'data_error' ? (
                        <Pill hue="#D8B26A" icon={<Wrench size={10} />}>{KIND_LABEL[h.kind]}</Pill>
                      ) : (
                        <Pill hue="#8B93A1">{KIND_LABEL[h.kind]}</Pill>
                      )}
                    </div>
                  </motion.div>
                )
              })}
            </div>
            {/* evidence rows */}
            {evIds.map((eid) => {
              const ev = evById.get(eid)
              return (
                <div key={eid} className="grid border-b v-hair last:border-b-0" style={{ gridTemplateColumns: cols }}>
                  <div className="p-2">
                    <Tag id={eid} />
                    <div className="mt-1 truncate text-[11.5px] opacity-70" title={ev?.filename}>{ev?.filename ?? 'evidence'}</div>
                    {ev && <div className="text-[10px] uppercase tracking-wider opacity-45">{ev.kind}</div>}
                  </div>
                  {hyps.map((h) => {
                    const c = cell.get(`${h.id}|${eid}`)
                    const active = sel?.h === h.id && sel.e === eid
                    return (
                      <motion.button
                        key={h.id}
                        layout="position"
                        transition={{ type: 'spring', stiffness: 420, damping: 38 }}
                        type="button"
                        onClick={() => setSel(active ? null : { h: h.id, e: eid })}
                        title={c?.why || undefined}
                        className={`flex cursor-pointer items-center gap-1.5 border-0 border-l v-hair bg-transparent p-2 text-left transition-colors hover:bg-current/5 ${active ? 'bg-current/8' : ''}`}
                        style={{ color: 'inherit' }}
                      >
                        {c ? (
                          <>
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium" style={{ color: REL_META[c.relation].hue }}>
                              {REL_META[c.relation].icon}
                              {REL_META[c.relation].label}
                            </span>
                            <ReceiptMark receipt={c.receipt} />
                          </>
                        ) : (
                          <span className="text-[11px] opacity-35">not assessed</span>
                        )}
                      </motion.button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </LayoutGroup>
      </div>
      {selCell && (
        <div className="v-panel mt-2 flex flex-wrap items-start gap-2 px-3 py-2 text-[12.5px]" style={{ borderColor: selCell.relation === 'inconsistent' ? DISCREPANCY : undefined }}>
          <Tag id={selCell.hypothesis_id} />
          <ArrowRight size={12} className="mt-0.5 opacity-50" />
          <Tag id={selCell.evidence_id} />
          <span className="min-w-0 flex-1">{selCell.why || 'No explanation recorded for this cell.'}</span>
          <ReceiptMark receipt={selCell.receipt} withLabel />
        </div>
      )}
      <p className="mt-1.5 text-[11px] opacity-50">
        A cell without a verifiable receipt is shown neutral. Receipts: matched = quote found in the source; partial = close match; unverified = not found.
      </p>
    </section>
  )
}
