import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { FileText, Image as ImageIcon, FileSpreadsheet, FileQuestion, ScrollText, Inbox } from 'lucide-react'
import { useCaseCtx } from '@/components/shell/ctx'
import { EvidenceViewer } from '@/components/evidence/Viewer'
import { FactsPanel } from '@/components/evidence/FactsPanel'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { EvidenceStatusChip } from '@/components/ui/Chip'
import type { EvidenceOut } from '@/types'
import { cn } from '@/lib/utils'

function useNarrow(): boolean {
  const [n, setN] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  useEffect(() => {
    const m = window.matchMedia('(max-width: 900px)')
    const f = () => setN(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return n
}

function KindIcon({ ev }: { ev: EvidenceOut }) {
  if (ev.mime.startsWith('image/')) return <ImageIcon size={14} />
  if (ev.kind === 'estimate' || ev.mime.includes('csv')) return <FileSpreadsheet size={14} />
  if (ev.kind === 'narrative' || ev.kind === 'policy' || ev.mime.includes('pdf') || ev.mime.startsWith('text/')) return <FileText size={14} />
  return <FileQuestion size={14} />
}

export default function Evidence() {
  const { detail } = useCaseCtx()
  const { evidenceId } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const narrow = useNarrow()
  const list = detail.evidence
  // Both deep-link shapes work: /evidence/:id?page=&quote= and /evidence?ev=&page=&q=
  const wanted = evidenceId ?? sp.get('ev') ?? undefined
  const selected = list.find((e) => e.id === wanted) ?? list[0]
  const page = Number(sp.get('page')) || undefined
  const quote = sp.get('quote') || sp.get('q') || undefined
  const unknownRef = !!wanted && !list.some((e) => e.id === wanted)
  // Exhibit tags are the real evidence ids (E-ADC1F3) everywhere, so tags match across tabs.
  const tagOf = (id: string) => id

  if (list.length === 0) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-2 p-12 text-center">
        <Inbox size={28} className="text-ink-3" />
        <h2 className="text-lg font-semibold">No evidence yet</h2>
        <p className="text-sm text-ink-2">Drop a photo, statement, policy PDF, estimate or any other file on this page, or type a statement in the bar above. Each file is stored, hashed and read; nothing leaves the case.</p>
      </div>
    )
  }

  const open = (id: string) => nav(`/case/${detail.case.id}/evidence?ev=${encodeURIComponent(id)}`)

  const rail = (
    <nav aria-label="Exhibits" className={cn('flex gap-1.5 overflow-auto', narrow ? 'flex-row border-b border-line p-2' : 'w-56 shrink-0 flex-col border-r border-line p-2')}>
      {!narrow && <div className="label-caps px-1 pb-1">Exhibits</div>}
      {list.map((e) => (
        <button
          key={e.id} onClick={() => open(e.id)} aria-current={e.id === selected.id}
          className={cn('shrink-0 cursor-pointer rounded-md border px-2.5 py-2 text-left transition-colors', narrow ? 'w-48' : 'w-full', e.id === selected.id ? 'border-accent bg-accent/8' : 'border-line bg-surface/70 hover:bg-surface-2')}
          style={e.id === selected.id ? { background: 'color-mix(in srgb, var(--accent) 8%, transparent)' } : undefined}
        >
          <div className="flex items-center gap-1.5"><span className="tag rounded border border-line px-1 text-ink-2">{tagOf(e.id)}</span><KindIcon ev={e} /><span className="tag ml-auto truncate text-ink-3">{e.kind}</span></div>
          <div className="mono mt-1 truncate text-xs" title={e.filename}>{e.filename}</div>
          <div className="mt-1"><EvidenceStatusChip status={e.status} /></div>
        </button>
      ))}
    </nav>
  )

  const viewer = <div className="h-full min-h-[320px] bg-surface/40"><ErrorBoundary label="The viewer"><EvidenceViewer key={selected.id} ev={selected} cite={{ page, quote }} /></ErrorBoundary></div>
  const facts = (
    <div className="h-full overflow-y-auto">
      {unknownRef && <p className="m-3 mb-0 rounded border border-dashed border-inferred px-2.5 py-1.5 text-xs text-inferred">The cited exhibit {wanted} is not in this case; showing {selected.id} instead.</p>}
      {quote && (
        <button onClick={() => setSp(wanted ? { ev: selected.id } : {}, { replace: true })} className="m-3 mb-0 flex cursor-pointer items-center gap-1.5 text-xs text-ink-3 hover:text-ink"><ScrollText size={12} /> Clear citation highlight</button>
      )}
      <FactsPanel ev={selected} tag={tagOf(selected.id)} state={detail.state} caseId={detail.case.id} />
    </div>
  )

  return (
    <div className={cn('flex', narrow ? 'flex-col' : 'h-[max(560px,calc(100dvh-15rem))]')}>
      {rail}
      {narrow ? (
        <div className="flex flex-col"><div className="h-[60vh]">{viewer}</div>{facts}</div>
      ) : (
        <Group orientation="horizontal" className="min-w-0 flex-1">
          <Panel defaultSize="55%" minSize="30%">{viewer}</Panel>
          <Separator className="w-1.5 bg-line-soft transition-colors hover:bg-accent data-[separator=active]:bg-accent" />
          <Panel defaultSize="45%" minSize="28%">{facts}</Panel>
        </Group>
      )}
    </div>
  )
}
