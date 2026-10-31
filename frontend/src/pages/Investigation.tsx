import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { AlertOctagon, Lightbulb, Loader2, ShieldAlert } from 'lucide-react'
import { useCaseDetail } from '@/lib/api'
import type { CaseDetail } from '@/types'
import { Empty, Pill, Tag } from '@/components/investigation/Primitives'
import { HypothesisBoard } from '@/components/investigation/HypothesisBoard'
import { Requests } from '@/components/investigation/Requests'
import { Findings } from '@/components/investigation/Findings'
import { VehicleBlueprint } from '@/components/investigation/VehicleBlueprint'
import { Sequence } from '@/components/investigation/Sequence'

/** DEV only: ?devmock renders the synthetic fixture so the revision moment can be previewed without a backend. */
function useDevMock(): { detail: CaseDetail | null; toggle: (() => void) | null; rev: number } {
  const [rev, setRev] = useState<1 | 2>(1)
  const [mod, setMod] = useState<typeof import('@/components/investigation/_mock') | null>(null)
  const wanted = import.meta.env.DEV && new URLSearchParams(window.location.search).has('devmock')
  useEffect(() => {
    if (wanted) import('@/components/investigation/_mock').then(setMod)
  }, [wanted])
  if (!wanted || !mod) return { detail: null, toggle: null, rev }
  return { detail: mod.devDetail(rev), toggle: () => setRev((r) => (r === 1 ? 2 : 1)), rev }
}

export default function Investigation() {
  const { id } = useParams<{ id: string }>()
  const live = useCaseDetail(id)
  const dev = useDevMock()
  const data = dev.detail ?? live.data
  const caseId = id ?? data?.case.id ?? 'dev'

  if (!data) {
    if (live.isError) return <Empty icon={<AlertOctagon size={14} />}>Could not load this case: {(live.error as Error)?.message}</Empty>
    return <div className="flex items-center gap-2 p-6 text-[13px] opacity-70"><Loader2 size={14} className="v-spin" /> Loading case…</div>
  }
  const state = data.state
  const running = data.jobs.some((j) => j.status === 'queued' || j.status === 'running')

  if (!state) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-3 p-10 text-center">
        <div className="v-panel v-hatch flex size-12 items-center justify-center rounded-full">{running ? <Loader2 size={20} className="v-spin" /> : <Lightbulb size={20} className="opacity-70" />}</div>
        <h2 className="m-0 text-base font-semibold">{running ? 'The first analysis is running' : 'The investigation starts with evidence'}</h2>
        <p className="m-0 text-[13px] leading-snug opacity-70">{running ? 'The hypothesis board, evidence requests and findings appear here as soon as the first revision is committed.' : 'Add a statement, photo, policy or estimate in the bar above. Verity then lays out competing explanations (always including a benign one), cites its sources, and asks for the single most useful next document.'}</p>
        <ol className="m-0 flex list-none flex-wrap justify-center gap-2 p-0 text-[11.5px] opacity-75">
          {['Read each exhibit', 'Propose explanations', 'Request next evidence'].map((t, i) => <li key={t} className="v-panel px-2 py-1"><span className="v-mono mr-1 opacity-60">{i + 1}</span>{t}</li>)}
        </ol>
      </div>
    )
  }

  const staleCount = state.findings.filter((f) => f.status === 'stale').length

  return (
    <div className="flex flex-col gap-6 p-4 text-[13px]">
      {dev.toggle && (
        <div className="flex items-center gap-2 rounded border border-dashed border-[#D8B26A] px-3 py-2 text-[12px]">
          <Pill hue="#D8B26A">DEV MOCK</Pill> synthetic fixture, revision {dev.rev}.
          <button className="cursor-pointer rounded border v-hair bg-transparent px-2 py-0.5 text-[12px]" style={{ color: 'inherit' }} onClick={dev.toggle}>{dev.rev === 1 ? 'Drop garage report (E-05)' : 'Back to revision 1'}</button>
        </div>
      )}

      {/* summary strip */}
      <header className="v-panel flex flex-col gap-1.5 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <Tag id={`r${state.rev}`} />
          <span className="text-[11px] uppercase tracking-widest opacity-50">Position</span>
          {running && <Pill hue="#4DD8FF" icon={<Loader2 size={11} className="v-spin" />}>re-resolving</Pill>}
          {staleCount > 0 && <Pill hue="#8B93A1" className="v-hatch">{staleCount} stale finding{staleCount > 1 ? 's' : ''} awaiting re-resolution</Pill>}
        </div>
        <p className="m-0 text-[13.5px] leading-snug">{state.summary || 'No summary yet.'}</p>
        {state.recommendation && (
          <p className="m-0 flex items-start gap-1.5 text-[12.5px] opacity-80"><Lightbulb size={13} className="mt-0.5 shrink-0" /> <span>{state.recommendation} <span className="opacity-60">(advisory; a human reviewer decides)</span></span></p>
        )}
        {state.unresolved.length > 0 && (
          <p className="m-0 text-[12px] opacity-75"><b className="font-semibold">Unresolved: </b>{state.unresolved.join(' · ')}</p>
        )}
        {state.injection_flags.length > 0 && (
          <p className="m-0 flex items-start gap-1.5 text-[12px]" style={{ color: '#C77DDB' }}>
            <ShieldAlert size={13} className="mt-0.5 shrink-0" />
            <span>{state.injection_flags.length} instruction-like string{state.injection_flags.length > 1 ? 's' : ''} found inside documents were treated as data and ignored ({[...new Set(state.injection_flags.map((f) => f.evidence_id))].join(', ')}).</span>
          </p>
        )}
      </header>

      <HypothesisBoard state={state} evidence={data.evidence} />

      <div className="grid gap-6 xl:grid-cols-2">
        <Requests caseId={caseId} requests={state.requests} />
        <Findings caseId={caseId} findings={state.findings} evidence={data.evidence} rev={state.rev} />
      </div>

      <VehicleBlueprint zones={state.zones} />
      <Sequence caseId={caseId} timeline={state.timeline} hypotheses={state.hypotheses} evidence={data.evidence} />
    </div>
  )
}
