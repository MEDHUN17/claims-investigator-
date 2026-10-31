import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { CheckCircle2, ShieldCheck, XCircle } from 'lucide-react'
import { useCases } from '@/lib/api'
import type { GateResult } from '@/types'
import { Btn, DISCREPANCY, Empty, SectionHead } from '@/components/investigation/Primitives'
import { errorMessage, post } from '@/components/investigation/net'

const GATES: { name: string; title: string; what: string }[] = [
  { name: 'schema', title: 'Schema', what: 'Analysis output parses against the case-state schema; all ids are closed.' },
  { name: 'citations', title: 'Citations', what: 'Every cited evidence id, page and quote resolves to the source text.' },
  { name: 'language', title: 'Language', what: 'No accusation wording (fraud, fake, liar, ...) outside a quoted source span.' },
  { name: 'math', title: 'Math', what: 'The settlement waterfall recomputes to the same figure with decimal arithmetic.' },
  { name: 'unverified', title: 'Unverified', what: 'No unverified value entered the money math.' },
]

export function GatesPanel() {
  const cases = useCases()
  const [sp, setSp] = useSearchParams()
  const [caseId, setCaseId] = useState<string>(sp.get('case') ?? '')
  const [res, setRes] = useState<{ caseId: string; at: string; ms: number; gates: GateResult[] } | null>(null)

  useEffect(() => {
    if (!caseId && cases.data && cases.data.length > 0) setCaseId(cases.data[0].id)
  }, [cases.data, caseId])

  const run = useMutation({
    mutationFn: async (id: string) => {
      const t0 = performance.now()
      const gates = await post<GateResult[]>(`/cases/${id}/gates`)
      return { caseId: id, at: new Date().toLocaleTimeString(), ms: Math.round(performance.now() - t0), gates }
    },
    onSuccess: setRes,
  })

  const shown = res && res.caseId === caseId ? res : null
  const byName = new Map((shown?.gates ?? []).map((g) => [g.name, g]))
  const extra = (shown?.gates ?? []).filter((g) => !GATES.some((x) => x.name === g.name))
  const allPass = shown && shown.gates.length > 0 && shown.gates.every((g) => g.passed)

  return (
    <section>
      <SectionHead title="Universal gates" kicker="run on any analysis, including the case just uploaded" icon={<ShieldCheck size={14} />} />
      <div className="v-panel p-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-[12px] opacity-70" htmlFor="gate-case">Case</label>
          <select
            id="gate-case"
            value={caseId}
            onChange={(e) => { setCaseId(e.target.value); setSp((p) => { const n = new URLSearchParams(p); n.set('case', e.target.value); return n }, { replace: true }) }}
            className="min-w-[220px] rounded border v-hair bg-transparent px-2 py-1 text-[12.5px]"
            style={{ color: 'inherit' }}
          >
            {(cases.data ?? []).map((c) => <option key={c.id} value={c.id} style={{ color: '#111' }}>{c.case_no} · {c.title} · r{c.rev}</option>)}
            {(cases.data ?? []).length === 0 && <option value="">no cases</option>}
          </select>
          <Btn tone="accent" busy={run.isPending} disabled={!caseId} onClick={() => run.mutate(caseId)}>Run gates</Btn>
          {shown && <span className="v-mono text-[11px] opacity-55">ran {shown.at} · {shown.ms} ms</span>}
          {allPass && <span className="inline-flex items-center gap-1 text-[12px] font-semibold" style={{ color: '#3FC1B0' }}><CheckCircle2 size={13} /> all gates pass</span>}
        </div>
        {run.isError && <p className="mb-0 mt-2 text-[12.5px]" style={{ color: DISCREPANCY }}>Gates could not run: {errorMessage(run.error).text}</p>}
        {cases.isError && <p className="mb-0 mt-2 text-[12.5px]" style={{ color: DISCREPANCY }}>Could not list cases: {errorMessage(cases.error).text}</p>}
        {!shown && !run.isPending && <div className="mt-3"><Empty>Pick a case and run the five gates.</Empty></div>}
        {shown && (
          <ul className="m-0 mt-3 grid list-none gap-2 p-0 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
            {[...GATES.map((g) => ({ meta: g, r: byName.get(g.name) })), ...extra.map((r) => ({ meta: { name: r.name, title: r.name, what: '' }, r }))].map(({ meta, r }) => (
              <li key={meta.name} className="rounded border px-3 py-2" style={{ borderColor: r ? (r.passed ? 'color-mix(in srgb, #3FC1B0 55%, transparent)' : DISCREPANCY) : undefined }}>
                <div className="flex items-center gap-1.5 text-[12.5px] font-semibold">
                  {r ? (r.passed ? <CheckCircle2 size={14} style={{ color: '#3FC1B0' }} /> : <XCircle size={14} style={{ color: DISCREPANCY }} />) : <span className="inline-block size-3.5 rounded-full border border-dashed v-hair" />}
                  {meta.title}
                  <span className="ml-auto text-[10.5px] font-medium uppercase tracking-widest" style={{ color: r ? (r.passed ? '#3FC1B0' : DISCREPANCY) : undefined }}>{r ? (r.passed ? 'pass' : 'fail') : 'not returned'}</span>
                </div>
                {meta.what && <p className="mb-0 mt-0.5 text-[11.5px] opacity-55">{meta.what}</p>}
                {r?.detail && <p className="v-mono mb-0 mt-1 text-[11.5px] leading-snug opacity-85">{r.detail}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
