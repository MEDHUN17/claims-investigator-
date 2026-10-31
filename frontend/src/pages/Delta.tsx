import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, GitCompareArrows, Hash, History, Loader2 } from 'lucide-react'
import { useCaseDetail } from '@/lib/api'
import type { CaseDetail, CaseState, RevisionOut } from '@/types'
import { ACCENT, Empty, Pill, SectionHead, Tag } from '@/components/investigation/Primitives'
import { get } from '@/components/investigation/net'
import { DeltaView } from '@/components/delta/DeltaView'

interface RevDetail { revision: RevisionOut; state: CaseState }

function useRevisionState(caseId: string | undefined, rev: number | undefined, devStates: Record<number, CaseState> | null) {
  return useQuery({
    queryKey: ['revision', caseId, rev],
    enabled: !!caseId && !!rev && rev > 0 && !devStates,
    queryFn: () => get<RevDetail>(`/cases/${caseId}/revisions/${rev}`),
    staleTime: 60_000,
  })
}

export default function Delta() {
  const { id } = useParams<{ id: string }>()
  const live = useCaseDetail(id)
  const [sp, setSp] = useSearchParams()
  const [dev, setDev] = useState<{ detail: CaseDetail; states: Record<number, CaseState> } | null>(null)
  const wanted = import.meta.env.DEV && sp.has('devmock')
  useEffect(() => {
    if (wanted) import('@/components/investigation/_mock').then((m) => setDev({ detail: m.devDetail(2), states: m.devRevisionStates }))
  }, [wanted])

  const data = dev?.detail ?? live.data
  const caseId = id ?? data?.case.id ?? 'dev'
  const revisions = useMemo(() => [...(data?.revisions ?? [])].sort((a, b) => b.rev - a.rev), [data?.revisions])
  const wantedRev = Number(sp.get('rev')) || revisions[0]?.rev
  const selected = revisions.find((r) => r.rev === wantedRev) ?? revisions[0]

  const cur = useRevisionState(caseId, selected?.rev, dev?.states ?? null)
  const prevRev = selected && selected.rev > 1 ? selected.rev - 1 : undefined
  const prev = useRevisionState(caseId, prevRev, dev?.states ?? null)
  const curState = dev ? dev.states[selected?.rev ?? 0] : cur.data?.state
  const prevState = dev ? dev.states[prevRev ?? 0] : prev.data?.state
  const state = curState ?? data?.state ?? undefined

  const titles = useMemo(() => {
    const t: Record<string, string> = {}
    for (const f of data?.state?.findings ?? []) t[f.id] = f.title
    for (const f of curState?.findings ?? []) t[f.id] = f.title
    return t
  }, [data?.state, curState])

  const rankMoves = useMemo(() => {
    if (!curState || !prevState) return []
    const before = new Map(prevState.hypotheses.map((h) => [h.id, h]))
    return curState.hypotheses
      .map((h) => ({ h, from: before.get(h.id)?.rank }))
      .filter((x) => x.from !== undefined && x.from !== x.h.rank)
  }, [curState, prevState])

  if (!data) {
    if (live.isError) return <Empty>Could not load this case: {(live.error as Error)?.message}</Empty>
    return <div className="flex items-center gap-2 p-6 text-[13px] opacity-70"><Loader2 size={14} className="v-spin" /> Loading changes…</div>
  }
  if (revisions.length === 0) {
    return <div className="p-4"><Empty icon={<History size={14} />}>No revisions yet. The first analysis creates revision 1; each evidence drop after that creates a new one.</Empty></div>
  }

  return (
    <div className="grid gap-5 p-4 text-[13px] lg:grid-cols-[minmax(240px,320px)_1fr]">
      <aside>
        <SectionHead title="Revisions" icon={<History size={14} />} kicker="append-only, hash-chained" />
        <ol className="m-0 flex list-none flex-col gap-1.5 p-0">
          {revisions.map((r) => {
            const active = r.rev === selected?.rev
            return (
              <li key={r.rev}>
                <button
                  type="button"
                  onClick={() => setSp((p) => { const n = new URLSearchParams(p); n.set('rev', String(r.rev)); return n }, { replace: true })}
                  aria-current={active}
                  className={`v-panel w-full cursor-pointer p-2.5 text-left ${active ? '' : 'opacity-85'}`}
                  style={{ borderColor: active ? ACCENT : undefined, color: 'inherit' }}
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Tag id={`r${r.rev}`} />
                    <span className="v-mono inline-flex items-center gap-0.5 text-[10px] opacity-55" title={`Revision hash ${r.hash}`}><Hash size={9} />{r.hash.slice(0, 8)}</span>
                    {r.delta.approval_voided && <Pill hue="#C77DDB">approval voided</Pill>}
                    <span className="ml-auto text-[10.5px] opacity-45">{new Date(r.created_at).toLocaleTimeString()}</span>
                  </div>
                  <div className="mt-1 text-[12px] font-medium leading-snug">{r.trigger}</div>
                  <div className="mt-0.5 line-clamp-2 text-[11.5px] leading-snug opacity-60">{r.summary}</div>
                </button>
              </li>
            )
          })}
        </ol>
      </aside>

      <main className="flex min-w-0 flex-col gap-4">
        {selected && (
          <>
            <SectionHead
              title={`Evidence delta · r${selected.rev}`}
              icon={<GitCompareArrows size={14} />}
              kicker={`hash ${selected.hash.slice(0, 16)} ← ${selected.prev_hash.replace(/^0+$/, 'genesis').slice(0, 16)}`}
            />
            <DeltaView delta={selected.delta} caseId={caseId} evidence={data.evidence} titles={titles} />
            {rankMoves.length > 0 && (
              <section>
                <SectionHead title="Hypothesis ranks that moved" kicker={`r${prevRev} to r${selected.rev}, ordinal only`} />
                <ul className="m-0 flex list-none flex-col gap-1 p-0">
                  {rankMoves.map(({ h, from }) => (
                    <li key={h.id} className="v-panel flex flex-wrap items-center gap-2 px-3 py-1.5 text-[12.5px]">
                      <Tag id={h.id} />
                      <span className="v-mono text-[11.5px]">rank {from} <ArrowRight size={11} className="inline" /> rank {h.rank}</span>
                      <span className="min-w-0 flex-1 opacity-75">{h.text}</span>
                      {h.benign && <Pill hue="#3FC1B0">benign</Pill>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {(cur.isLoading && !dev) && <p className="m-0 flex items-center gap-1.5 text-[11.5px] opacity-60"><Loader2 size={11} className="v-spin" /> Loading revision snapshot…</p>}
            {state && selected.rev > 1 && !prevState && !prev.isLoading && !dev && (
              <p className="m-0 text-[11.5px] opacity-55">The previous revision snapshot is not available, so rank movement is not shown.</p>
            )}
          </>
        )}
      </main>
    </div>
  )
}
