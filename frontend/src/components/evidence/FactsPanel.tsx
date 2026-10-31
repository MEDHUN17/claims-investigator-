import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Fingerprint, ShieldAlert, Pencil, Check, X, Loader2, Quote, Camera } from 'lucide-react'
import { api, useInvalidateCase } from '@/lib/api'
import type { CaseState, EvidenceOut, Fact } from '@/types'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Chip, EpistemicChip, EvidenceStatusChip, ReceiptChip } from '@/components/ui/Chip'
import { HatchedBadge } from '@/components/ui/HatchedBadge'
import { bytes, cn } from '@/lib/utils'
import { citationHref } from '@/lib/links'

/* ---------- Photo passport / file passport ---------- */
function exifTimes(meta: Record<string, any>): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = []
  for (const [k, v] of Object.entries(meta ?? {})) {
    if (v == null || typeof v === 'object') continue
    if (/(time|date|taken|captured|modified|created)/i.test(k)) out.push({ label: k.replace(/_/g, ' '), value: String(v) })
  }
  return out
}

export function Passport({ ev, tag }: { ev: EvidenceOut; tag: string }) {
  const times = exifTimes(ev.meta)
  const isPhoto = ev.kind === 'photo' || ev.mime.startsWith('image/')
  const captureKnown = times.some((t) => /capture|taken|exif|original/i.test(t.label) && t.value && !/unavailable|none|null/i.test(t.value))
  return (
    <Card>
      <CardHeader tag={tag} title={isPhoto ? 'Photo passport' : 'File passport'} right={<EvidenceStatusChip status={ev.status} />} />
      <dl className="grid gap-x-3 gap-y-1.5 p-3.5 text-xs" style={{ gridTemplateColumns: 'auto 1fr' }}>
        <dt className="text-ink-3">File</dt><dd className="mono break-all">{ev.filename}</dd>
        <dt className="text-ink-3">Kind</dt><dd className="mono">{ev.kind} · {ev.source_class.replace('_', ' ')} · {bytes(ev.size)}</dd>
        <dt className="text-ink-3 flex items-center gap-1"><Fingerprint size={11} />SHA-256</dt><dd className="mono break-all text-ink-2">{ev.sha256}</dd>
        <dt className="text-ink-3">Uploaded</dt><dd className="mono">{new Date(ev.uploaded_at).toLocaleString()}</dd>
        {isPhoto && (
          <>
            <dt className="text-ink-3 flex items-center gap-1"><Camera size={11} />Capture time</dt>
            <dd>{captureKnown ? <span className="mono">{times.filter((t) => /capture|taken|exif|original/i.test(t.label)).map((t) => t.value).join(' · ')}</span> : <HatchedBadge>unavailable</HatchedBadge>}
              {!captureKnown && <span className="ml-2 text-ink-3">Missing EXIF is common (messaging apps strip it) and is not treated as suspicious.</span>}</dd>
            {times.filter((t) => !/capture|taken|exif|original/i.test(t.label)).map((t) => (
              <Fragment key={t.label}><dt className="text-ink-3 capitalize">{t.label}</dt><dd className="mono">{t.value}</dd></Fragment>
            ))}
          </>
        )}
        {ev.error && <><dt className="text-ink-3">Error</dt><dd className="text-discrepancy">{ev.error}</dd></>}
      </dl>
    </Card>
  )
}

/* ---------- Injection flags ---------- */
export function InjectionPanel({ flags }: { flags: string[] }) {
  if (!flags.length) return null
  return (
    <Card className="border-dashed border-discrepancy/60">
      <CardHeader title={<span className="flex items-center gap-1.5 text-discrepancy"><ShieldAlert size={14} /> Embedded instruction found (ignored)</span>} />
      <div className="space-y-2 p-3.5 text-xs">
        <p className="text-ink-2">This document contains text that tries to instruct the system. It was recorded as data, never obeyed, and has no effect on the analysis, the settlement or the decision.</p>
        {flags.map((f, i) => <blockquote key={i} className="mono hatch rounded border border-dashed border-stale px-2 py-1.5 text-ink-2">"{f}"</blockquote>)}
      </div>
    </Card>
  )
}

/* ---------- Extracted facts with receipts ---------- */
export function FactsList({ caseId, facts, ev }: { caseId: string; facts: Fact[]; ev: EvidenceOut }) {
  if (!facts.length) {
    return <p className="p-3.5 text-xs text-ink-3">{ev.status === 'extracted' ? 'No cited facts were produced from this exhibit yet. The raw extraction is below.' : 'Facts appear here once the exhibit has been read.'}</p>
  }
  return (
    <ul className="divide-y divide-line-soft">
      {facts.map((f) => (
        <li key={f.id} className="space-y-1.5 px-3.5 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-ink-3">{f.label}</span>
            <EpistemicChip kind={f.epistemic} />
            {f.ref && <ReceiptChip state={f.ref.receipt} />}
            {f.ref?.receipt === 'unverified' && <HatchedBadge>excluded from money maths</HatchedBadge>}
          </div>
          <div className="mono break-words text-sm">{f.value}</div>
          {f.ref?.quote && (
            <Link to={citationHref(caseId, f.ref)} className="group flex items-start gap-1.5 rounded border border-line-soft px-2 py-1 text-xs text-ink-2 hover:border-accent hover:text-ink">
              <Quote size={12} className="mt-0.5 shrink-0 text-accent" />
              <span className="min-w-0">"{f.ref.quote}"{f.ref.page ? <span className="tag ml-1.5 text-ink-3">p.{f.ref.page}</span> : null}<span className="ml-1.5 text-accent opacity-0 group-hover:opacity-100">show in original</span></span>
            </Link>
          )}
        </li>
      ))}
    </ul>
  )
}

/* ---------- Raw extraction tree with inline human correction ---------- */
function Leaf({ path, value, evidenceId, onSaved }: { path: string; value: unknown; evidenceId: string; onSaved: () => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(value ?? ''))
  const m = useMutation({
    mutationFn: (v: unknown) => api.patch(`/evidence/${evidenceId}/extraction`, { path, value: v }),
    onSuccess: () => { setEditing(false); onSaved() },
  })
  const commit = () => {
    let v: unknown = draft
    if (typeof value === 'number' && draft.trim() !== '' && !Number.isNaN(Number(draft))) v = Number(draft)
    else if (typeof value === 'boolean') v = draft === 'true'
    m.mutate(v)
  }
  if (!editing) {
    return (
      <span className="group inline-flex items-start gap-1.5">
        <span className="mono break-words text-ink">{value === null || value === '' ? <span className="text-ink-3">null</span> : String(value)}</span>
        <button aria-label={`Correct ${path}`} onClick={() => { setDraft(String(value ?? '')); setEditing(true) }} className="cursor-pointer text-ink-3 opacity-40 hover:text-accent hover:opacity-100 focus-visible:opacity-100 group-hover:opacity-100"><Pencil size={11} /></button>
      </span>
    )
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }} className="mono h-6 min-w-[140px] rounded border border-accent bg-bg px-1.5 text-xs outline-none" aria-label={`New value for ${path}`} />
      <Button size="sm" variant="primary" onClick={commit} disabled={m.isPending} aria-label="Save correction">{m.isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}</Button>
      <Button size="sm" variant="ghost" onClick={() => setEditing(false)} aria-label="Cancel"><X size={12} /></Button>
      {m.isError && <span className="text-xs text-discrepancy">{(m.error as Error).message}</span>}
    </span>
  )
}

function Tree({ node, path, evidenceId, onSaved, depth = 0 }: { node: unknown; path: string; evidenceId: string; onSaved: () => void; depth?: number }) {
  if (node !== null && typeof node === 'object') {
    const entries = Array.isArray(node) ? node.map((v, i) => [String(i), v] as const) : Object.entries(node as Record<string, unknown>)
    if (!entries.length) return <span className="text-ink-3">empty</span>
    return (
      <ul className={cn('space-y-1', depth > 0 && 'ml-3 border-l border-line-soft pl-3')}>
        {entries.map(([k, v]) => {
          const p = path ? `${path}.${k}` : k
          const nested = v !== null && typeof v === 'object'
          return (
            <li key={p} className="text-xs">
              <span className="mono mr-1.5 text-ink-3">{k}</span>
              {nested ? <Tree node={v} path={p} evidenceId={evidenceId} onSaved={onSaved} depth={depth + 1} /> : <Leaf path={p} value={v} evidenceId={evidenceId} onSaved={onSaved} />}
            </li>
          )
        })}
      </ul>
    )
  }
  return <Leaf path={path} value={node} evidenceId={evidenceId} onSaved={onSaved} />
}

export function ExtractionPanel({ ev, caseId }: { ev: EvidenceOut; caseId: string }) {
  const refresh = useInvalidateCase(caseId)
  return (
    <Card>
      <CardHeader
        title="Extraction"
        right={<>
          <span className="tag text-ink-3">v{ev.extraction_version}</span>
          {ev.extraction_version > 1 && <Chip tone="human" solid>Human-corrected</Chip>}
        </>}
      />
      <details className="group/ex p-3.5">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-ink-2 hover:text-ink"><Pencil size={12} className="text-accent" /> Open the raw extraction to correct a value <span className="tag ml-auto text-ink-3 group-open/ex:hidden">collapsed</span></summary>
        <p className="mb-2 mt-2 text-xs text-ink-3">Click a pencil to correct a value. A correction is saved as a new, human-labelled version and re-checks only the findings that depend on this exhibit.</p>
        {ev.extraction ? <Tree node={ev.extraction} path="" evidenceId={ev.id} onSaved={refresh} /> : <p className="text-xs text-ink-3">No extraction yet.</p>}
      </details>
    </Card>
  )
}

export function FactsPanel({ ev, tag, state, caseId }: { ev: EvidenceOut; tag: string; state?: CaseState | null; caseId: string }) {
  const facts = (state?.facts ?? []).filter((f) => f.evidence_id === ev.id)
  const stateFlags = (state?.injection_flags ?? []).filter((f) => f.evidence_id === ev.id).map((f) => f.text)
  const flags = Array.from(new Set([...(ev.injection_flags ?? []), ...stateFlags]))
  return (
    <div className="space-y-3 p-3">
      <Passport ev={ev} tag={tag} />
      <InjectionPanel flags={flags} />
      <Card>
        <CardHeader title="Facts read from this exhibit" tag={`${facts.length}`} />
        <FactsList caseId={caseId} facts={facts} ev={ev} />
      </Card>
      <ExtractionPanel ev={ev} caseId={caseId} />
    </div>
  )
}
