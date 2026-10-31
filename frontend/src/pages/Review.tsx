import { FileDown, Scale, ListChecks, GitFork, Ban } from 'lucide-react'
import { useCaseCtx } from '@/components/shell/ctx'
import { Waterfall } from '@/components/review/Waterfall'
import { ApprovalPanel } from '@/components/review/ApprovalPanel'
import { Card, CardHeader } from '@/components/ui/Card'
import { HatchedBadge } from '@/components/ui/HatchedBadge'
import { Button } from '@/components/ui/Button'
import { api, jobsActive } from '@/lib/api'
import { inr } from '@/lib/utils'

export default function Review() {
  const { detail } = useCaseCtx()
  const { state, case: c, approvals } = detail
  const active = approvals.find((a) => a.status === 'active' && a.rev === c.rev) ?? (detail.approval_current?.status === 'active' ? detail.approval_current : null)
  const latestVoid = !active ? [...approvals].filter((a) => a.status === 'void').sort((a, b) => b.rev - a.rev)[0] : undefined
  const calc = state?.calc ?? null
  const hyp = (id: string) => state?.hypotheses.find((h) => h.id === id)

  return (
    <div className="mx-auto grid max-w-6xl gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-4">
        {!active && (
          <div className="hatch flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-stale px-3.5 py-2.5">
            <HatchedBadge strong>Draft</HatchedBadge>
            <span className="text-sm text-ink-2">No active approval for revision {c.rev}. Everything below is a draft for a human to review; the exported PDF is watermarked DRAFT.</span>
          </div>
        )}
        {latestVoid && (
          <div role="alert" className="hatch-dense flex items-start gap-2 rounded-lg border border-dashed border-stale px-3.5 py-2.5 text-sm">
            <Ban size={16} className="mt-0.5 shrink-0 text-stale" />
            <div><strong>The earlier approval (rev {latestVoid.rev}) is VOID.</strong> <span className="text-ink-2">{latestVoid.void_reason ?? 'New evidence changed the case after it was sealed.'} Review the changes and decide again on rev {c.rev}.</span></div>
          </div>
        )}

        {!state ? (
          <Card><div className="p-6 text-sm text-ink-3">No analysis has been committed yet. Add evidence and wait for the plan to finish.</div></Card>
        ) : (
          <>
            <Card>
              <CardHeader title="Summary" tag={`rev ${state.rev}`} />
              <div className="space-y-2 p-3.5 text-sm">
                <p>{state.summary || 'No summary available.'}</p>
                {state.recommendation && <p className="text-ink-2"><span className="label-caps mr-2">Suggested next step</span>{state.recommendation}</p>}
                <p className="text-xs text-ink-3">The system only suggests. It never denies a claim, labels anyone as fraudulent, or releases payment.</p>
              </div>
            </Card>

            <Card>
              <CardHeader title={<span className="flex items-center gap-1.5"><Scale size={14} />Settlement waterfall</span>} right={calc && <span className="tag text-ink-3">{calc.currency} · computed in code</span>} />
              <div className="p-3.5">{calc ? <Waterfall calc={calc} /> : <p className="text-sm text-ink-3">Settlement cannot be computed yet: no estimate or policy terms were read.</p>}</div>
            </Card>

            {calc && (calc.unresolved.length > 0 || state.unresolved.length > 0) && (
              <Card className="border-dashed">
                <CardHeader title={<span className="flex items-center gap-1.5"><ListChecks size={14} />Unresolved</span>} tag={`${Math.max(calc.unresolved.length, state.unresolved.length)}`} />
                <ul className="divide-y divide-line-soft">
                  {calc.unresolved.map((u, i) => (
                    <li key={i} className="hatch space-y-0.5 px-3.5 py-2.5 text-sm">
                      <div className="flex items-center gap-2"><HatchedBadge>unresolved</HatchedBadge><span className="font-medium">{u.term}</span></div>
                      <div className="text-xs text-ink-2">{u.why}</div>
                      <div className="text-xs text-ink-3">Needs: <span className="text-ink-2">{u.needs}</span></div>
                    </li>
                  ))}
                  {calc.unresolved.length === 0 && state.unresolved.map((u, i) => <li key={i} className="px-3.5 py-2.5 text-sm">{u}</li>)}
                </ul>
              </Card>
            )}

            {calc && calc.conditional.length > 0 && (
              <Card>
                <CardHeader title={<span className="flex items-center gap-1.5"><GitFork size={14} />Conditional outcomes</span>} right={<span className="text-xs text-ink-3">what the settlement would be under each explanation</span>} />
                <ul className="divide-y divide-line-soft">
                  {calc.conditional.map((cd) => {
                    const h = hyp(cd.hypothesis_id)
                    return (
                      <li key={cd.hypothesis_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5 text-sm">
                        <span className="tag rounded border border-line px-1.5 py-0.5">{cd.hypothesis_id.toUpperCase()}</span>
                        <span className="min-w-0 flex-1">{h?.text ?? cd.hypothesis_id}{cd.note && <span className="ml-2 text-xs text-ink-3">{cd.note}</span>}</span>
                        {cd.settlement != null ? <span className="mono font-semibold">{inr(cd.settlement, calc.currency)}</span> : <HatchedBadge>unresolved</HatchedBadge>}
                      </li>
                    )
                  })}
                </ul>
              </Card>
            )}
          </>
        )}
      </div>

      <div className="space-y-4">
        <ApprovalPanel
          caseId={c.id} rev={c.rev} rupees={calc?.proposed_settlement}
          busy={jobsActive(detail)} canDecide={!!state} current={active} history={approvals}
        />
        <Card>
          <CardHeader title="Export" />
          <div className="space-y-2 p-3.5">
            <a href={api.reportUrl(c.id, c.rev)} target="_blank" rel="noreferrer">
              <Button className="w-full" variant="primary"><FileDown size={14} /> Export PDF for rev {c.rev}</Button>
            </a>
            <p className="text-xs text-ink-3">{active ? 'Sealed: the PDF prints the revision hash and the approval hash.' : 'No active approval: the PDF is watermarked DRAFT and prints the revision hash.'}</p>
          </div>
        </Card>
      </div>
    </div>
  )
}
