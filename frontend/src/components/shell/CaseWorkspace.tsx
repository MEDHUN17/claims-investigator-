import { Suspense, lazy, useMemo, useState } from 'react'
import { NavLink, Outlet, useParams, Link, useLocation } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { ArrowLeft, ScrollText, Upload, Files, Network, GitCompareArrows, Stamp, Loader2, TriangleAlert, RefreshCw } from 'lucide-react'
import { api, jobsActive, useCaseDetail, useInvalidateCase } from '@/lib/api'
import { useAiState } from './HealthChip'
import { CaseStatusChip } from '@/components/ui/Chip'
import { SealChip } from '@/components/ui/Seal'
import { Button } from '@/components/ui/Button'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { cn } from '@/lib/utils'
import { DropBar, useEvidenceUploader } from './DropBar'
import { PlanStrip } from './PlanStrip'
import { ToolTape } from './ToolTape'
import type { CaseCtx } from './ctx'

// FRONT-B owns the ribbon; it is shown under the drop bar after a revision lands.
const DeltaRibbon = lazy(() => import('@/components/delta/DeltaRibbon'))

const TABS = [
  { to: 'evidence', label: 'Evidence', icon: Files },
  { to: 'investigation', label: 'Investigation', icon: Network },
  { to: 'changes', label: 'Changes', icon: GitCompareArrows },
  { to: 'review', label: 'Review', icon: Stamp },
]

/** Shown when the committed revision was produced without the AI planner (provider failed). Offers an explicit re-run. */
function DegradedBanner({ caseId, busy }: { caseId: string; busy: boolean }) {
  const refresh = useInvalidateCase(caseId)
  const ai = useAiState()
  const [err, setErr] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const rerun = async () => {
    setPending(true); setErr(null)
    try { await api.post(`/cases/${caseId}/analyze`); refresh() } catch (e) { setErr(e instanceof Error ? e.message : 'Re-run failed') } finally { setPending(false) }
  }
  return (
    <div role="status" className="hatch mx-4 mb-2 mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-dashed border-inferred px-3.5 py-2.5">
      <TriangleAlert size={16} className="shrink-0 text-inferred" />
      <div className="min-w-[240px] flex-1 text-sm">
        <strong>This revision was built without the AI planner.</strong>{' '}
        <span className="text-ink-2">Facts, receipts and the arithmetic are real, but hypotheses, the evidence matrix and ranked requests are incomplete. Nothing was made up to fill the gap.</span>
        {ai.state !== 'ok' && <span className="ml-1 text-ink-3">Provider status right now: {ai.state}.</span>}
        {err && <div className="mt-1 text-xs text-discrepancy">{err}</div>}
      </div>
      <Button size="sm" variant="primary" onClick={() => void rerun()} disabled={busy || pending}>
        {pending || busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} {busy ? 'Analysis running' : 'Re-run analysis'}
      </Button>
    </div>
  )
}

export function CaseWorkspace() {
  const { id } = useParams()
  const { data: detail, isLoading, error } = useCaseDetail(id)
  const [tape, setTape] = useState(false)
  const onChangesTab = useLocation().pathname.endsWith('/changes')
  const caseId = id ?? ''
  const uploader = useEvidenceUploader(caseId, detail?.evidence.length ?? 0)
  const { getRootProps, getInputProps, open, isDragActive } = useDropzone({
    noClick: true, noKeyboard: true, multiple: true,
    onDrop: (files) => { void uploader.submitFiles(files) },
  })

  const latestJob = detail?.jobs?.length ? [...detail.jobs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] : undefined
  const latestRev = detail?.revisions?.length ? [...detail.revisions].sort((a, b) => b.rev - a.rev)[0] : undefined
  const ctx: CaseCtx | null = useMemo(() => (detail ? { detail } : null), [detail])
  const approval = detail?.approval_current ?? null

  if (isLoading) return <div className="flex items-center gap-2 p-8 text-sm text-ink-3"><Loader2 className="animate-spin" size={16} /> Loading case…</div>
  if (error || !detail || !ctx) {
    return (
      <div className="p-8">
        <p className="text-sm text-discrepancy">Could not load this case: {error instanceof Error ? error.message : 'not found'}</p>
        <Link to="/" className="mt-3 inline-block text-sm text-accent underline">Back to queue</Link>
      </div>
    )
  }
  const c = detail.case
  const degraded = !!detail.state?.unresolved?.some((u) => /AI analysis unavailable/i.test(u))
  const showRibbon = !onChangesTab && !!latestRev && latestRev.rev > 1 && latestRev.delta && latestRev.delta.lines?.length > 0 && !!detail.state

  return (
    <div {...getRootProps()} className="relative flex min-h-0 flex-1 flex-col">
      <input {...getInputProps()} />
      {isDragActive && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-bg/80">
          <div className="flex items-center gap-3 rounded-xl border-2 border-dashed border-accent bg-surface px-8 py-6 text-lg font-semibold text-accent"><Upload /> Drop to add as new evidence</div>
        </div>
      )}

      <div className="border-b border-line bg-surface/60">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 pt-3">
          <Link to="/" aria-label="Back to queue" className="rounded p-1 text-ink-3 hover:text-ink"><ArrowLeft size={16} /></Link>
          <span className="tag rounded border border-line px-1.5 py-0.5 text-ink-2">{c.case_no}</span>
          <h1 className="min-w-0 truncate text-base font-semibold tracking-tight">{c.title}</h1>
          <CaseStatusChip status={c.status} />
          {c.synthetic && <span className="tag rounded border border-dashed border-inferred px-1.5 py-0.5 text-inferred">SYNTHETIC</span>}
          <span className="tag text-ink-3">rev {c.rev}</span>
          <div className="ml-auto flex items-center gap-2">
            <SealChip approval={approval} />
            <Button size="sm" onClick={() => setTape((v) => !v)} aria-pressed={tape}><ScrollText size={13} /> Tool tape</Button>
          </div>
        </div>
        <nav className="mt-1 flex gap-1 overflow-x-auto px-3" aria-label="Case sections">
          {TABS.map((t) => (
            <NavLink
              key={t.to} to={t.to}
              className={({ isActive }) => cn('relative flex h-9 items-center gap-1.5 whitespace-nowrap border-b-2 px-3 text-sm font-medium', isActive ? 'border-accent text-ink' : 'border-transparent text-ink-3 hover:text-ink-2')}
            >
              <t.icon size={14} /> {t.label}
              {t.to === 'investigation' && c.open_requests > 0 && <span className="tag rounded bg-inferred/20 px-1 text-inferred">{c.open_requests} open</span>}
              {t.to === 'evidence' && <span className="tag text-ink-3">{c.evidence_count}</span>}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="border-b border-line-soft bg-bg/40">
        <DropBar onPickFiles={open} onText={uploader.submitText} notes={uploader.notes} busy={uploader.busy} dragging={isDragActive} />
        {degraded && <DegradedBanner caseId={caseId} busy={jobsActive(detail)} />}
        <PlanStrip job={latestJob} />
        {showRibbon && latestRev && detail.state && (
          <div className="px-4 pb-2">
            <Suspense fallback={null}><DeltaRibbon delta={latestRev.delta} state={detail.state} /></Suspense>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1"><ErrorBoundary label="This tab"><Outlet context={ctx} /></ErrorBoundary></div>
      <ToolTape open={tape} onClose={() => setTape(false)} activity={detail.activity ?? []} />
    </div>
  )
}
