import { useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'motion/react'
import { CheckCircle2, Crosshair, Lock, PackageOpen, Target, Ban, Sparkles } from 'lucide-react'
import type { EvidenceRequest } from '@/types'
import { ACCENT, Btn, DISCREPANCY, Empty, Pill, SectionHead, Tag } from './Primitives'
import { cmpDec, errorMessage, inr, post } from './net'

export function sortRequests(rs: EvidenceRequest[]): EvidenceRequest[] {
  const rank = (r: EvidenceRequest) => (r.status === 'open' ? 0 : r.status === 'received' ? 1 : 2)
  return [...rs].sort((a, b) => rank(a) - rank(b) || b.pairs_separated - a.pairs_separated || cmpDec(b.rupees_at_stake, a.rupees_at_stake) || a.id.localeCompare(b.id))
}

function Outcome({ r }: { r: EvidenceRequest }) {
  if (r.outcome === 'matched_prediction')
    return <Pill hue="#3FC1B0" icon={<Target size={11} />} title="The returned evidence matched the locked prediction. Model-assessed; the reviewer confirms.">Predicted: matched</Pill>
  if (r.outcome === 'unanticipated')
    return <Pill hue={DISCREPANCY} icon={<Sparkles size={11} />} title="The returned evidence did not match either locked branch. Model-assessed; the reviewer confirms.">Predicted vs actual: unanticipated</Pill>
  return <Pill hue="#8B93A1" icon={<Lock size={11} />} title="Prediction was locked before this evidence arrived; it is scored when the evidence lands.">Prediction locked</Pill>
}

export function Requests({ caseId, requests }: { caseId: string; requests: EvidenceRequest[] }) {
  const qc = useQueryClient()
  const sorted = useMemo(() => sortRequests(requests), [requests])
  const m = useMutation({
    mutationFn: (v: { rid: string; status: 'received' | 'dropped' | 'open' }) => post(`/cases/${caseId}/requests/${v.rid}/status`, { status: v.status }),
    onSuccess: () => qc.invalidateQueries(),
  })
  const open = requests.filter((r) => r.status === 'open').length
  const anyScored = requests.some((r) => r.outcome !== 'pending')

  return (
    <section>
      <SectionHead
        title="Evidence requests"
        kicker="next-best evidence first: hypothesis pairs separated, then rupees at stake"
        icon={<PackageOpen size={14} />}
        right={<span className="text-[11.5px] opacity-60">{open} open</span>}
      />
      {sorted.length === 0 ? (
        <Empty>No open requests. Nothing further would separate the current explanations.</Empty>
      ) : (
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          <AnimatePresence initial={false}>
            {sorted.map((r, i) => {
              const closed = r.status !== 'open'
              return (
                <motion.li
                  key={r.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: closed ? 0.6 : 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="v-panel p-3"
                  style={{ borderColor: r.outcome === 'unanticipated' ? DISCREPANCY : undefined }}
                >
                  <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                    <span className="v-mono grid size-5 place-items-center rounded-sm text-[11px] font-bold" style={{ background: `color-mix(in srgb, ${ACCENT} 18%, transparent)`, color: ACCENT }}>{i + 1}</span>
                    <Tag id={r.id} />
                    <Pill hue="#6AA3D9" icon={<Crosshair size={11} />} title="Hypothesis pairs whose assessment would differ depending on this evidence (computed in code)">
                      separates {r.pairs_separated} {r.pairs_separated === 1 ? 'pair' : 'pairs'}
                    </Pill>
                    <Pill hue="#ECE8DF" title="Difference between the highest and lowest conditional settlement (decimal arithmetic)">
                      {r.rupees_at_stake != null ? `${inr(r.rupees_at_stake)} at stake` : 'rupees at stake: not computable'}
                    </Pill>
                    <span className="text-[10.5px] uppercase tracking-wider opacity-45">{r.kind}</span>
                    <span className="ml-auto flex items-center gap-1.5">
                      {r.status !== 'open' && <Pill hue={r.status === 'received' ? '#3FC1B0' : '#8B93A1'} icon={r.status === 'received' ? <CheckCircle2 size={11} /> : <Ban size={11} />}>{r.status}</Pill>}
                      <Outcome r={r} />
                    </span>
                  </div>
                  <p className="mb-0 mt-2 text-[13px] leading-snug">{r.text}</p>
                  {r.resolves.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] opacity-70">
                      helps separate {r.resolves.map((h) => <Tag key={h} id={h} />)}
                    </div>
                  )}
                  {r.prediction && (
                    <div className="mt-2 grid gap-px overflow-hidden rounded border v-hair text-[12px] sm:grid-cols-2">
                      <div className="p-2" style={{ background: `color-mix(in srgb, #3FC1B0 6%, transparent)` }}>
                        <div className="mb-0.5 flex items-center gap-1 text-[10px] uppercase tracking-widest opacity-60"><Lock size={9} /> if it supports the leading hypothesis</div>
                        {r.prediction.if_supports}
                      </div>
                      <div className="p-2" style={{ background: `color-mix(in srgb, ${DISCREPANCY} 6%, transparent)` }}>
                        <div className="mb-0.5 flex items-center gap-1 text-[10px] uppercase tracking-widest opacity-60"><Lock size={9} /> if it contradicts it</div>
                        {r.prediction.if_contradicts}
                      </div>
                    </div>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {r.status === 'open' ? (
                      <>
                        <Btn busy={m.isPending && m.variables?.rid === r.id && m.variables.status === 'received'} onClick={() => m.mutate({ rid: r.id, status: 'received' })} title="Mark as received (the evidence itself still has to be uploaded)">
                          <CheckCircle2 size={12} /> Mark received
                        </Btn>
                        <Btn tone="quiet" busy={m.isPending && m.variables?.rid === r.id && m.variables.status === 'dropped'} onClick={() => m.mutate({ rid: r.id, status: 'dropped' })}>
                          <Ban size={12} /> Drop
                        </Btn>
                      </>
                    ) : (
                      <Btn tone="quiet" onClick={() => m.mutate({ rid: r.id, status: 'open' })}>Reopen</Btn>
                    )}
                    <span className="text-[10.5px] opacity-45">raised in r{r.created_rev}</span>
                  </div>
                </motion.li>
              )
            })}
          </AnimatePresence>
        </ol>
      )}
      {m.isError && <p className="mt-1.5 text-[12px]" style={{ color: DISCREPANCY }}>Could not update the request: {errorMessage(m.error).text}</p>}
      {anyScored && <p className="mt-1.5 text-[11px] opacity-50">Predicted-vs-actual is model-assessed; the human reviewer confirms. Predictions are locked before the evidence arrives.</p>}
    </section>
  )
}
