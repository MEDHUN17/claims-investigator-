import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { FileSearch, Flag, HelpCircle, Route, Swords } from 'lucide-react'
import type { EvidenceOut, Finding } from '@/types'
import { Btn, CitationLink, DISCREPANCY, Empty, EpiChip, Pill, SectionHead, StaleChip, Tag } from './Primitives'
import { errorMessage, post } from './net'

type Filter = 'all' | 'active' | 'stale' | 'resolved'

function FindingCard({ f, caseId, evName, curRev }: { f: Finding; caseId: string; evName: Map<string, string>; curRev: number }) {
  const qc = useQueryClient()
  const [asking, setAsking] = useState(false)
  const [note, setNote] = useState('')
  const challenge = useMutation({
    mutationFn: () => post(`/cases/${caseId}/findings/${f.id}/challenge`, { note: note.trim() }),
    onSuccess: () => { setAsking(false); setNote(''); qc.invalidateQueries() },
  })
  const stale = f.status === 'stale'
  const revised = f.revised_rev != null && f.prior_body
  const justNow = f.revised_rev === curRev || f.since_rev === curRev

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`v-panel relative p-3 ${stale ? 'v-hatch-strong' : ''}`}
      style={{ borderStyle: stale ? 'dashed' : 'solid', borderColor: f.type === 'discrepancy' && !stale ? DISCREPANCY : undefined, ...(stale ? { borderLeft: '4px solid #8B93A1' } : {}) }}
      aria-label={`Finding ${f.id}${stale ? ' (stale)' : ''}`}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Tag id={f.id} />
        <Pill hue={f.type === 'discrepancy' ? DISCREPANCY : '#8B93A1'}>{f.type}</Pill>
        <EpiChip kind={f.epistemic} />
        {stale && <StaleChip rev={f.revised_rev ?? undefined} />}
        {f.status === 'resolved' && <Pill hue="#3FC1B0">resolved</Pill>}
        {f.status === 'superseded' && <Pill hue="#8B93A1">superseded</Pill>}
        {justNow && f.status === 'active' && <Pill hue="#4DD8FF" title="Added or changed in the latest revision">new in r{curRev}</Pill>}
        <span className="ml-auto text-[10.5px] opacity-45">since r{f.since_rev}{f.revised_rev != null ? ` · revised r${f.revised_rev}` : ''}</span>
      </div>
      <h3 className={`mb-1 mt-2 text-[13.5px] font-semibold leading-snug ${stale ? 'opacity-70' : ''}`}>{f.title}</h3>
      {revised && <p className="v-del mb-1 mt-0 text-[12.5px] leading-snug">{f.prior_body}</p>}
      <p className={`m-0 text-[12.5px] leading-snug ${stale ? 'opacity-65' : ''} ${revised ? 'v-ins' : ''}`} style={revised ? { display: 'block' } : undefined}>{f.body}</p>

      {stale && f.stale_reason && (
        <div className="mt-2 flex items-start gap-1.5 rounded border border-dashed v-hair px-2 py-1.5 text-[12px]">
          <Flag size={12} className="mt-0.5 shrink-0 opacity-70" />
          <span><b className="font-semibold">Why stale: </b>{f.stale_reason}</span>
        </div>
      )}

      {(f.supports.length > 0 || f.contradicts.length > 0) && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {f.supports.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-widest opacity-50">supports</div>
              <div className="flex flex-col items-start gap-1">{f.supports.map((s, i) => <CitationLink key={i} caseId={caseId} sref={s} evidenceName={evName.get(s.evidence_id)} />)}</div>
            </div>
          )}
          {f.contradicts.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-widest" style={{ color: DISCREPANCY }}>contradicts</div>
              <div className="flex flex-col items-start gap-1">{f.contradicts.map((s, i) => <CitationLink key={i} caseId={caseId} sref={s} evidenceName={evName.get(s.evidence_id)} />)}</div>
            </div>
          )}
        </div>
      )}

      {(f.alternatives.length > 0 || f.uncertainty || f.action) && (
        <dl className="mb-0 mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
          {f.alternatives.length > 0 && (<><dt className="opacity-50">Alternatives</dt><dd className="m-0"><ul className="m-0 list-disc pl-4">{f.alternatives.map((a, i) => <li key={i}>{a}</li>)}</ul></dd></>)}
          {f.uncertainty && (<><dt className="opacity-50">Uncertainty</dt><dd className="m-0">{f.uncertainty}</dd></>)}
          {f.action && (<><dt className="opacity-50">Suggested step</dt><dd className="m-0">{f.action}</dd></>)}
        </dl>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t v-hair pt-2">
        <span className="text-[10px] uppercase tracking-widest opacity-45">depends on</span>
        {f.justification.evidence_ids.map((id) => <Tag key={id} id={id} />)}
        {f.justification.entity_keys.map((k) => <span key={k} className="v-mono rounded-sm bg-current/5 px-1 text-[10px] opacity-70">{k}</span>)}
        <span className="ml-auto">
          {asking ? null : (
            <Btn tone="quiet" onClick={() => setAsking(true)} title="Mark this finding stale and ask for it to be re-verified"><Swords size={12} /> Challenge</Btn>
          )}
        </span>
      </div>
      {asking && (
        <form className="mt-1.5 flex flex-wrap items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); challenge.mutate() }}>
          <input
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Why do you doubt this finding? (optional note)"
            className="min-w-[200px] flex-1 rounded border v-hair bg-transparent px-2 py-1 text-[12px] outline-none focus:border-[#4DD8FF]"
          />
          <Btn type="submit" tone="accent" busy={challenge.isPending}>Send challenge</Btn>
          <Btn tone="quiet" onClick={() => setAsking(false)}>Cancel</Btn>
        </form>
      )}
      {challenge.isError && <p className="mb-0 mt-1 text-[12px]" style={{ color: DISCREPANCY }}>Challenge failed: {errorMessage(challenge.error).text}</p>}
    </motion.article>
  )
}

export function Findings({ caseId, findings, evidence, rev }: { caseId: string; findings: Finding[]; evidence: EvidenceOut[]; rev: number }) {
  const [filter, setFilter] = useState<Filter>('all')
  const evName = useMemo(() => new Map(evidence.map((e) => [e.id, e.filename])), [evidence])
  const counts = useMemo(() => ({
    all: findings.length,
    active: findings.filter((f) => f.status === 'active').length,
    stale: findings.filter((f) => f.status === 'stale').length,
    resolved: findings.filter((f) => f.status === 'resolved' || f.status === 'superseded').length,
  }), [findings])
  const shown = useMemo(() => {
    const list = findings.filter((f) => filter === 'all' || (filter === 'resolved' ? f.status === 'resolved' || f.status === 'superseded' : f.status === filter))
    const order = { stale: 0, active: 1, resolved: 2, superseded: 3 } as const
    return [...list].sort((a, b) => order[a.status] - order[b.status] || a.id.localeCompare(b.id))
  }, [findings, filter])

  return (
    <section>
      <SectionHead
        title="Findings"
        kicker="every claim cites its source; stale ones wait for re-resolution"
        icon={<FileSearch size={14} />}
        right={
          <div role="tablist" className="flex items-center gap-1">
            {(['all', 'active', 'stale', 'resolved'] as Filter[]).map((k) => (
              <button
                key={k}
                role="tab"
                aria-selected={filter === k}
                onClick={() => setFilter(k)}
                className={`cursor-pointer rounded border px-2 py-0.5 text-[11px] ${filter === k ? 'border-[#4DD8FF] text-[#4DD8FF]' : 'v-hair bg-transparent opacity-70'}`}
                style={{ background: 'transparent' }}
              >
                {k} <span className="v-mono opacity-60">{counts[k]}</span>
              </button>
            ))}
          </div>
        }
      />
      {shown.length === 0 ? (
        <Empty icon={<HelpCircle size={14} />}>{findings.length === 0 ? 'No findings yet.' : `No ${filter} findings.`}</Empty>
      ) : (
        <div className="flex flex-col gap-2">{shown.map((f) => <FindingCard key={f.id} f={f} caseId={caseId} evName={evName} curRev={rev} />)}</div>
      )}
      <p className="mt-1.5 flex items-center gap-1 text-[11px] opacity-50"><Route size={11} /> Citations open the exact page and quotation in the Evidence tab.</p>
    </section>
  )
}
