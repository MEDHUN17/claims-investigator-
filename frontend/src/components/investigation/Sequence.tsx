import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { ListOrdered } from 'lucide-react'
import type { EvidenceOut, Hypothesis, TimelineStep } from '@/types'
import { ACCENT, CitationLink, Empty, EpiChip, Pill, SectionHead, Tag, WATERMARK } from './Primitives'

export function Sequence({ caseId, timeline, hypotheses, evidence }: { caseId: string; timeline: TimelineStep[]; hypotheses: Hypothesis[]; evidence: EvidenceOut[] }) {
  const hyps = useMemo(() => [...hypotheses].sort((a, b) => a.rank - b.rank || a.id.localeCompare(b.id)), [hypotheses])
  const [hid, setHid] = useState<string | undefined>(hyps[0]?.id)
  useEffect(() => {
    if (!hid || !hyps.some((h) => h.id === hid)) setHid(hyps[0]?.id)
  }, [hyps, hid])
  const evName = useMemo(() => new Map(evidence.map((e) => [e.id, e.filename])), [evidence])

  const steps = useMemo(() => {
    const sel = timeline.filter((s) => s.hypothesis_ids.length === 0 || (hid != null && s.hypothesis_ids.includes(hid)))
    return [...sel].sort((a, b) => a.order - b.order)
  }, [timeline, hid])

  return (
    <section>
      <SectionHead title="Sequence of events" kicker="one reconstruction per hypothesis" icon={<ListOrdered size={14} />} />
      {timeline.length === 0 ? (
        <Empty>No sequence could be reconstructed from the current evidence.</Empty>
      ) : (
        <div className="v-panel relative overflow-hidden">
          <div role="tablist" className="flex flex-wrap gap-1 border-b v-hair p-2">
            {hyps.map((h) => (
              <button
                key={h.id}
                role="tab"
                aria-selected={hid === h.id}
                onClick={() => setHid(h.id)}
                className={`cursor-pointer rounded border px-2 py-1 text-left text-[11.5px] ${hid === h.id ? 'border-[#4DD8FF] text-[#4DD8FF]' : 'v-hair opacity-75'}`}
                style={{ background: 'transparent' }}
              >
                <span className="v-mono mr-1.5">{h.id}</span>
                {h.benign ? 'benign' : h.kind.replace('_', ' ')}
              </button>
            ))}
          </div>
          <div className="pointer-events-none absolute inset-0 grid select-none place-items-center overflow-hidden" aria-hidden>
            <span className="-rotate-12 whitespace-nowrap text-[26px] font-bold uppercase tracking-[0.18em] opacity-[0.045]">{WATERMARK}</span>
          </div>
          <ol className="relative m-0 list-none p-3">
            <AnimatePresence mode="popLayout" initial={false}>
              {steps.map((s) => (
                <motion.li
                  key={`${hid}-${s.order}`}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="relative flex gap-3 pb-3 last:pb-0"
                >
                  <span className="absolute bottom-0 left-[11px] top-6 w-px bg-current/15 last:hidden" />
                  <span className="v-mono relative z-10 grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold" style={{ borderColor: ACCENT, color: ACCENT, background: 'color-mix(in srgb, #4DD8FF 10%, transparent)' }}>{s.order}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <EpiChip kind={s.basis === 'inferred' ? 'inferred' : s.basis === 'observed' ? 'observed' : 'reported'} />
                      {s.hypothesis_ids.length === 0 ? <Pill hue="#8B93A1">common to all</Pill> : s.hypothesis_ids.map((h) => <Tag key={h} id={h} />)}
                    </div>
                    <p className="mb-0 mt-1 text-[12.5px] leading-snug">{s.text}</p>
                    {s.refs.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{s.refs.map((r, i) => <CitationLink key={i} caseId={caseId} sref={r} evidenceName={evName.get(r.evidence_id)} />)}</div>}
                  </div>
                </motion.li>
              ))}
            </AnimatePresence>
            {steps.length === 0 && <li className="text-[12px] opacity-60">This hypothesis has no distinct steps.</li>}
          </ol>
          <div className="relative border-t v-hair px-3 py-1.5 text-[10.5px] uppercase tracking-[0.14em] opacity-55">{WATERMARK}</div>
        </div>
      )}
    </section>
  )
}
