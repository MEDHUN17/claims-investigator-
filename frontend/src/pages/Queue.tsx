import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { Plus, FlaskConical, ChevronDown, Loader2, Inbox } from 'lucide-react'
import { api, qk, useCases } from '@/lib/api'
import type { CaseSummary } from '@/types'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { CaseStatusChip } from '@/components/ui/Chip'
import { HatchedBadge } from '@/components/ui/HatchedBadge'
import { Dialog } from '@/components/ui/Dialog'
import { relTime } from '@/lib/utils'
import { QueueBackdrop } from '@/components/fx/QueueBackdrop'
import { VerityLogo } from '@/components/fx/VerityLogo'

interface Fixture { id: string; title: string; description: string; files?: number; twist?: boolean; available?: boolean }

function normaliseFixtures(raw: unknown): Fixture[] {
  const arr: any[] = Array.isArray(raw) ? raw : Array.isArray((raw as any)?.fixtures) ? (raw as any).fixtures : Array.isArray((raw as any)?.sets) ? (raw as any).sets : []
  return arr.map((f) => typeof f === 'string'
    ? { id: f, title: f.replace(/_/g, ' '), description: '' }
    : { files: typeof f.file_count === 'number' ? f.file_count : undefined, twist: !!f.apply_on, available: f.available !== false, id: String(f.id ?? f.fixture_set ?? f.name), title: String(f.title ?? f.name ?? f.id ?? f.fixture_set).replace(/_/g, ' '), description: String(f.description ?? '') })
}

export default function Queue() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: cases, isLoading, error } = useCases()
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [menu, setMenu] = useState(false)
  const fixtures = useQuery({ queryKey: qk.fixtures, queryFn: async () => normaliseFixtures(await api.get('/demo/fixtures')), retry: 0 })

  useEffect(() => {
    if (!menu) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false) }
    const onDown = (e: MouseEvent) => { if (!(e.target as HTMLElement).closest('[data-demo-menu]')) setMenu(false) }
    window.addEventListener('keydown', onKey); window.addEventListener('mousedown', onDown)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onDown) }
  }, [menu])

  const create = useMutation({
    mutationFn: (t: string) => api.post<CaseSummary>('/cases', { title: t }),
    onSuccess: (c) => { qc.invalidateQueries({ queryKey: qk.cases }); setCreating(false); setTitle(''); nav(`/case/${c.id}/evidence`) },
  })
  const load = useMutation({
    mutationFn: (fixture_set: string) => api.post<any>('/demo/load', { fixture_set }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: qk.cases })
      const id = r?.id ?? r?.case?.id ?? r?.case_id
      if (id) nav(`/case/${id}/evidence`)
    },
  })

  return (
    <div className="relative w-full"><QueueBackdrop />
    <div className="relative mx-auto w-full max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-end gap-3">
        <VerityLogo size={84} speed={0.3} className="hidden sm:inline-block" />
        <div>
          <div className="label-caps">Case queue</div>
          <h1 className="text-xl font-semibold tracking-tight">Claims under investigation</h1>
          <p className="mt-1 max-w-xl text-sm text-ink-2">Drop evidence, see competing explanations, and re-check only what new evidence touches. A human decides; the system never denies a claim or releases payment.</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative" data-demo-menu>
            <Button onClick={() => setMenu((v) => !v)} aria-haspopup="menu" aria-expanded={menu} disabled={load.isPending}>
              {load.isPending ? <Loader2 size={14} className="animate-spin" /> : <FlaskConical size={14} />} Load demo case <ChevronDown size={13} />
            </Button>
            {menu && (
              <div role="menu" className="absolute right-0 z-20 mt-1 max-h-[70vh] w-[min(24rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-line bg-surface shadow-[var(--shadow)]">
                <div className="border-b border-line-soft px-3 py-2 text-xs text-ink-3">Synthetic evidence runs through the real pipeline, including the AI planner.</div>
                {fixtures.isLoading && <div className="p-3 text-xs text-ink-3">Loading…</div>}
                {fixtures.isError && <div className="p-3 text-xs text-ink-3">Demo fixtures unavailable.</div>}
                {fixtures.data?.map((f) => (
                  <button key={f.id} role="menuitem" disabled={f.available === false} onClick={() => { setMenu(false); load.mutate(f.id) }} className="block w-full cursor-pointer px-3 py-2 text-left hover:bg-surface-2 focus-visible:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50">
                    <div className="flex items-center gap-2"><span className="mono min-w-0 text-sm capitalize">{f.title}</span>{f.files != null && <span className="tag ml-auto shrink-0 whitespace-nowrap text-ink-3">{f.files} files</span>}{f.twist && <span className="tag shrink-0 rounded border border-dashed border-inferred px-1 text-inferred">twist</span>}</div>
                    {f.description && <div className="line-clamp-2 text-xs text-ink-3">{f.description}</div>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <Button variant="primary" onClick={() => setCreating(true)}><Plus size={14} /> New case</Button>
        </div>
      </div>
      {load.isError && <p className="mt-3 text-sm text-discrepancy">Demo load failed: {(load.error as Error).message}</p>}

      <Card className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              {['Case', 'Title', 'Status', 'Unresolved', 'Open requests', 'Evidence', 'Updated'].map((h) => <th key={h} className="label-caps px-3 py-2.5 font-semibold">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={7} className="p-6 text-center text-ink-3"><Loader2 size={16} className="mr-2 inline animate-spin" />Loading cases…</td></tr>}
            {error && <tr><td colSpan={7} className="p-6 text-center text-discrepancy">{(error as Error).message}</td></tr>}
            {cases && cases.length === 0 && (
              <tr><td colSpan={7} className="p-10 text-center text-ink-3"><Inbox className="mx-auto mb-2" size={22} />No cases yet. Create one or load a synthetic demo case.</td></tr>
            )}
            {cases?.map((c, i) => (
              <motion.tr
                key={c.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, delay: Math.min(i, 8) * 0.02 }}
                tabIndex={0} role="link" aria-label={`Open ${c.case_no}`}
                onClick={() => nav(`/case/${c.id}/evidence`)} onKeyDown={(e) => { if (e.key === 'Enter') nav(`/case/${c.id}/evidence`) }}
                className="cursor-pointer border-b border-line-soft last:border-0 hover:bg-surface-2/70"
              >
                <td className="px-3 py-2.5"><span className="tag rounded border border-line px-1.5 py-0.5">{c.case_no}</span></td>
                <td className="max-w-[360px] px-3 py-2.5 font-medium" title={c.title}><span className="line-clamp-2">{c.title}</span> {c.synthetic && <span className="tag ml-1 text-inferred">SYNTHETIC</span>}</td>
                <td className="px-3 py-2.5"><CaseStatusChip status={c.status} /></td>
                <td className="px-3 py-2.5">{c.unresolved > 0 ? <HatchedBadge>{c.unresolved} unresolved</HatchedBadge> : <span className="tag text-ink-3">none</span>}</td>
                <td className="mono px-3 py-2.5">{c.open_requests}</td>
                <td className="mono px-3 py-2.5">{c.evidence_count}</td>
                <td className="px-3 py-2.5 text-xs text-ink-3">{relTime(c.updated_at)} · <span className="mono">rev {c.rev}</span></td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Dialog open={creating} onClose={() => setCreating(false)} title="New case">
        <form onSubmit={(e) => { e.preventDefault(); if (title.trim()) create.mutate(title.trim()) }} className="space-y-3">
          <label className="block text-xs font-medium text-ink-2">Case title
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Hatchback collision, Anna Salai" className="mt-1 h-9 w-full rounded-md border border-line bg-bg px-2.5 text-sm text-ink outline-none focus:border-accent" />
          </label>
          {create.isError && <p className="text-xs text-discrepancy">{(create.error as Error).message}</p>}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setCreating(false)}>Cancel</Button>
            <Button variant="primary" type="submit" disabled={!title.trim() || create.isPending}>{create.isPending && <Loader2 size={14} className="animate-spin" />} Create</Button>
          </div>
        </form>
      </Dialog>
    </div>
    </div>
  )
}
