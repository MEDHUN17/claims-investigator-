import { Fragment, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, FlaskConical, Play, PlayCircle, XCircle } from 'lucide-react'
import type { LabRow, LabScenario } from '@/types'
import { Btn, DISCREPANCY, Empty, Pill, SectionHead, Tag } from '@/components/investigation/Primitives'
import { errorMessage, get, post } from '@/components/investigation/net'
import { GatesPanel } from '@/components/lab/GatesPanel'

function median(xs: number[]): number | null {
  if (xs.length === 0) return null
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2)
}
const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`)

export default function Lab() {
  const qc = useQueryClient()
  const scenarios = useQuery({ queryKey: ['lab', 'scenarios'], queryFn: () => get<LabScenario[]>('/lab/scenarios') })
  const results = useQuery({ queryKey: ['lab', 'results'], queryFn: () => get<LabRow[]>('/lab/results') })
  const [fresh, setFresh] = useState<Record<string, LabRow>>({})
  const [errors, setErrors] = useState<Record<string, { text: string; rateLimited: boolean }>>({})
  const [queued, setQueued] = useState<string[]>([])
  const [running, setRunning] = useState<string | null>(null)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [halt, setHalt] = useState<string | null>(null)
  const [calls, setCalls] = useState(0)
  const busy = useRef(false)

  const latest = useMemo(() => {
    const m = new Map<string, LabRow>()
    for (const r of results.data ?? []) {
      const p = m.get(r.scenario_id)
      if (!p || r.ran_at > p.ran_at) m.set(r.scenario_id, r)
    }
    for (const [k, r] of Object.entries(fresh)) {
      const p = m.get(k)
      if (!p || r.ran_at >= p.ran_at) m.set(k, r)
    }
    return m
  }, [results.data, fresh])

  /** Sequential queue: one scenario at a time so the shared model quota is never hit in parallel. */
  async function runIds(ids: string[]) {
    if (busy.current || ids.length === 0) return
    busy.current = true
    setHalt(null)
    setQueued(ids)
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i]
      setRunning(id)
      setQueued(ids.slice(i + 1))
      setErrors((e) => { const n = { ...e }; delete n[id]; return n })
      try {
        setCalls((c) => c + 1)
        const rows = await post<LabRow[]>('/lab/run', { scenario_id: id })
        const row = rows.find((r) => r.scenario_id === id) ?? rows[0]
        if (row) setFresh((f) => ({ ...f, [id]: row }))
      } catch (e) {
        const er = errorMessage(e)
        setErrors((x) => ({ ...x, [id]: er }))
        if (er.rateLimited) {
          setHalt(`Provider rate limit (429) on ${id}. The remaining ${ids.length - i - 1} scenario(s) were not started; wait a minute and re-run.`)
          break
        }
      }
    }
    setRunning(null)
    setQueued([])
    busy.current = false
    qc.invalidateQueries({ queryKey: ['lab', 'results'] })
  }

  const list = scenarios.data ?? []
  const rows = list.map((s) => latest.get(s.id))
  const done = rows.filter((r): r is LabRow => !!r)
  const passCount = done.filter((r) => r.passed).length
  const assertTotal = done.reduce((n, r) => n + r.assertions.length, 0)
  const assertPass = done.reduce((n, r) => n + r.assertions.filter((a) => a.passed).length, 0)
  const med = median(done.map((r) => r.latency_ms))
  const liveCount = done.filter((r) => r.source === 'live').length

  const toggle = (id: string) => setOpen((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n })

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6 p-4 text-[13px]">
      <header>
        <h1 className="m-0 flex items-center gap-2 text-[18px] font-semibold"><FlaskConical size={18} /> Proof Lab</h1>
        <p className="mb-0 mt-1 max-w-[80ch] text-[12.5px] leading-snug opacity-70">
          Labelled scenarios run through the real pipeline, plus five universal gates that run on any analysis. Expected outcomes were written before any model run.
          Evaluation fixtures are team-written synthetic data: a pass shows behaviour on these cases, not accuracy on real claims.
        </p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section>
          <SectionHead
            title="Scenarios"
            icon={<PlayCircle size={14} />}
            right={<Btn tone="accent" busy={!!running} disabled={list.length === 0} onClick={() => runIds(list.map((s) => s.id))}><Play size={12} /> Run all</Btn>}
          />
          {halt && (
            <div role="alert" className="mb-2 flex items-start gap-2 rounded border px-3 py-2 text-[12.5px]" style={{ borderColor: DISCREPANCY, background: `color-mix(in srgb, ${DISCREPANCY} 8%, transparent)` }}>
              <AlertTriangle size={14} className="mt-0.5 shrink-0" style={{ color: DISCREPANCY }} /> {halt}
            </div>
          )}
          {scenarios.isError ? (
            <Empty icon={<AlertTriangle size={14} />}>Could not load scenarios: {errorMessage(scenarios.error).text}</Empty>
          ) : scenarios.isLoading ? (
            <Empty>Loading scenarios…</Empty>
          ) : list.length === 0 ? (
            <Empty>No scenarios are registered.</Empty>
          ) : (
            <div className="v-panel overflow-x-auto">
              <table className="w-full border-collapse text-left text-[12.5px]">
                <thead>
                  <tr className="border-b v-hair text-[10.5px] uppercase tracking-widest opacity-55">
                    <th className="w-6 p-2" />
                    <th className="p-2 font-medium">Scenario</th>
                    <th className="p-2 font-medium">Result</th>
                    <th className="p-2 text-right font-medium">Latency</th>
                    <th className="p-2 font-medium">Source</th>
                    <th className="p-2" />
                  </tr>
                </thead>
                <tbody>
                  {list.map((s) => {
                    const r = latest.get(s.id)
                    const err = errors[s.id]
                    const isRun = running === s.id
                    const isQ = queued.includes(s.id)
                    const isOpen = open.has(s.id)
                    return (
                      <Fragment key={s.id}>
                        <tr className="border-b v-hair align-top last:border-b-0">
                          <td className="p-2">
                            <button type="button" aria-label={isOpen ? 'Collapse' : 'Expand'} onClick={() => toggle(s.id)} className="cursor-pointer border-0 bg-transparent p-0" style={{ color: 'inherit' }}>
                              {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </button>
                          </td>
                          <td className="p-2">
                            <div className="flex flex-wrap items-center gap-1.5"><Tag id={s.id} /><span className="font-semibold">{s.title}</span></div>
                            <div className="mt-0.5 max-w-[60ch] text-[11.5px] leading-snug opacity-60">{s.description}</div>
                            <div className="v-mono mt-0.5 text-[10.5px] opacity-45">fixture: {s.fixture_set}</div>
                            {err && <div className="mt-1 text-[12px]" style={{ color: DISCREPANCY }}>{err.rateLimited ? 'Rate limited (429): ' : 'Run failed: '}{err.text}</div>}
                          </td>
                          <td className="p-2 whitespace-nowrap">
                            {isRun ? <Pill hue="#4DD8FF" icon={<span className="v-spin inline-block size-2.5 rounded-full border-2 border-current border-t-transparent" />}>running</Pill>
                              : isQ ? <Pill hue="#8B93A1">queued</Pill>
                              : r ? (
                                <span className="inline-flex flex-col gap-0.5">
                                  {r.passed ? <Pill hue="#3FC1B0" icon={<CheckCircle2 size={11} />}>pass</Pill> : <Pill hue={DISCREPANCY} icon={<XCircle size={11} />}>fail</Pill>}
                                  <span className="text-[10.5px] opacity-55">{r.assertions.filter((a) => a.passed).length}/{r.assertions.length} assertions</span>
                                </span>
                              ) : <span className="text-[11.5px] opacity-45">not run</span>}
                          </td>
                          <td className="v-mono p-2 text-right text-[12px] whitespace-nowrap">{r ? fmtMs(r.latency_ms) : '—'}</td>
                          <td className="p-2">
                            {r ? <Pill hue={r.source === 'live' ? '#4DD8FF' : '#8B93A1'} title={r.source === 'live' ? 'Ran just now against the live provider' : 'Stored result from an earlier run'}>{r.source}</Pill> : null}
                            {r && <div className="v-mono mt-0.5 text-[10px] opacity-45">{new Date(r.ran_at).toLocaleString()}</div>}
                          </td>
                          <td className="p-2 text-right">
                            <Btn busy={isRun} disabled={!!running && !isRun} onClick={() => runIds([s.id])} title="Re-run this scenario"><Play size={11} /> Re-run</Btn>
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="border-b v-hair last:border-b-0">
                            <td />
                            <td colSpan={5} className="px-2 pb-3">
                              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                                {(r?.assertions ?? s.assertions.map((text) => ({ text, passed: undefined as boolean | undefined, detail: undefined as string | undefined }))).map((a, i) => (
                                  <li key={i} className="flex items-start gap-1.5 text-[12px] leading-snug">
                                    {a.passed === undefined ? <span className="mt-0.5 inline-block size-3 shrink-0 rounded-full border border-dashed v-hair" />
                                      : a.passed ? <CheckCircle2 size={13} className="mt-px shrink-0" style={{ color: '#3FC1B0' }} /> : <XCircle size={13} className="mt-px shrink-0" style={{ color: DISCREPANCY }} />}
                                    <span>
                                      {a.text}
                                      {a.detail && <span className="v-mono block text-[11px] opacity-65">{a.detail}</span>}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="v-panel mt-3 grid grid-cols-2 gap-px overflow-hidden text-[12px] sm:grid-cols-4">
            {[
              ['Scenarios passing', done.length ? `${passCount} of ${done.length} run (${list.length} defined)` : `none run (${list.length} defined)`],
              ['Assertions passing', assertTotal ? `${assertPass} of ${assertTotal}` : '—'],
              ['Median latency', med != null ? fmtMs(med) : '—'],
              ['Source mix', done.length ? `${liveCount} live, ${done.length - liveCount} stored` : '—'],
            ].map(([k, v]) => (
              <div key={k} className="p-2.5">
                <div className="text-[10px] uppercase tracking-widest opacity-50">{k}</div>
                <div className="v-mono mt-0.5 text-[12.5px]">{v}</div>
              </div>
            ))}
          </div>
          <p className="mb-0 mt-1.5 text-[11px] opacity-50">
            Figures are measured from the stored and live rows above. Run requests sent from this page this session: {calls}. A scenario may make more than one model call; the per-call count is in the activity tape, not estimated here.
          </p>
        </section>

        <GatesPanel />
      </div>
    </div>
  )
}
