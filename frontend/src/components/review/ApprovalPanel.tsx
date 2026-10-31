import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { BadgeCheck, CornerUpLeft, ArrowUpRight, Loader2, ShieldCheck, ShieldX, Info } from 'lucide-react'
import { api, useInvalidateCase } from '@/lib/api'
import type { ApprovalOut } from '@/types'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Seal } from '@/components/ui/Seal'
import { cn, inr } from '@/lib/utils'

const OPTS = [
  { v: 'approve', label: 'Approve', icon: BadgeCheck, hint: 'Accept this revision as the basis for payment.' },
  { v: 'return', label: 'Return', icon: CornerUpLeft, hint: 'Send back for more evidence or correction.' },
  { v: 'escalate', label: 'Escalate', icon: ArrowUpRight, hint: 'Refer to a higher authority.' },
] as const

/** Indicative only. The server computes and records the authoritative role. */
export function delegationRole(rupees?: string | null): string {
  if (rupees == null) return 'Not determinable while the settlement is unresolved'
  const n = Number(rupees)
  if (!Number.isFinite(n)) return 'Unknown'
  if (n <= 50000) return 'adjuster (up to ₹50,000)'
  if (n <= 200000) return 'senior_adjuster (up to ₹2,00,000)'
  return 'committee (above ₹2,00,000)'
}

function VerifyButton({ approval }: { approval: ApprovalOut }) {
  const m = useMutation({ mutationFn: () => api.get<{ valid: boolean; recomputed_hash: string; rev: number }>(`/approvals/${approval.id}/verify`) })
  return (
    <div className="space-y-1.5">
      <Button size="sm" onClick={() => m.mutate()} disabled={m.isPending}>{m.isPending ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />} Verify seal</Button>
      {m.data && (
        <div className={cn('flex items-start gap-1.5 rounded border px-2 py-1.5 text-xs', m.data.valid ? 'border-observed/60 text-observed' : 'border-discrepancy/60 text-discrepancy')}>
          {m.data.valid ? <ShieldCheck size={13} className="mt-px" /> : <ShieldX size={13} className="mt-px" />}
          <div>{m.data.valid ? 'Hash recomputed from the stored revision and it matches.' : 'Hash does NOT match the stored revision.'}<div className="mono mt-0.5 break-all text-ink-2">{m.data.recomputed_hash} · rev {m.data.rev}</div></div>
        </div>
      )}
      {m.isError && <p className="text-xs text-discrepancy">{(m.error as Error).message}</p>}
    </div>
  )
}

export function ApprovalPanel({ caseId, rev, rupees, busy, canDecide, current, history }: {
  caseId: string; rev: number; rupees?: string | null; busy: boolean; canDecide: boolean; current?: ApprovalOut | null; history: ApprovalOut[]
}) {
  const refresh = useInvalidateCase(caseId)
  const [decision, setDecision] = useState<'approve' | 'return' | 'escalate'>('return')
  const [reviewer, setReviewer] = useState(() => { try { return localStorage.getItem('verity-reviewer') ?? '' } catch { return '' } })
  const [note, setNote] = useState('')
  const m = useMutation({
    mutationFn: () => api.post<ApprovalOut>(`/cases/${caseId}/approve`, { decision, reviewer: reviewer.trim(), note }),
    onSuccess: () => { try { localStorage.setItem('verity-reviewer', reviewer.trim()) } catch { /* ignore */ } setNote(''); refresh() },
  })
  const active = current && current.status === 'active' ? current : null
  const voided = history.filter((a) => a.status === 'void')

  return (
    <Card>
      <CardHeader title="Human decision" tag={`rev ${rev}`} />
      <div className="space-y-4 p-3.5">
        {active && <Seal approval={active} />}
        {active && <VerifyButton approval={active} />}

        {!active && (
          <form onSubmit={(e) => { e.preventDefault(); if (reviewer.trim()) m.mutate() }} className="space-y-3">
            <fieldset>
              <legend className="label-caps mb-1.5">Decision</legend>
              <div className="grid grid-cols-3 gap-2">
                {OPTS.map((o) => (
                  <label key={o.v} title={o.hint} className={cn('flex cursor-pointer flex-col items-center gap-1 rounded-md border px-2 py-2 text-xs font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent', decision === o.v ? 'border-accent text-accent' : 'border-line text-ink-2 hover:bg-surface-2')} style={decision === o.v ? { background: 'color-mix(in srgb, var(--accent) 8%, transparent)' } : undefined}>
                    <input type="radio" name="decision" value={o.v} checked={decision === o.v} onChange={() => setDecision(o.v)} className="sr-only" />
                    <o.icon size={16} />{o.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="block text-xs font-medium text-ink-2">Reviewer name
              <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} required placeholder="e.g. A. Menon" className="mt-1 h-9 w-full rounded-md border border-line bg-bg px-2.5 text-sm text-ink outline-none focus:border-accent" />
              <span className="mt-1 flex items-start gap-1 text-[0.7rem] font-normal text-ink-3"><Info size={11} className="mt-px shrink-0" />A typed label recorded in the audit chain. This is not authentication.</span>
            </label>
            <label className="block text-xs font-medium text-ink-2">Note (optional)
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="mt-1 w-full rounded-md border border-line bg-bg px-2.5 py-1.5 text-sm text-ink outline-none focus:border-accent" />
            </label>
            <div className="text-xs text-ink-2">Delegation, indicative: <span className="mono text-ink">{delegationRole(rupees)}</span>{rupees != null && <> for <span className="mono text-ink">{inr(rupees)}</span></>}. The server records the authoritative role.</div>
            {busy && <p className="text-xs text-inferred">An analysis is still running. Decisions are blocked until it finishes, so the seal binds the final revision.</p>}
            {!canDecide && !busy && <p className="text-xs text-ink-3">No analysed revision yet.</p>}
            {m.isError && <p className="text-xs text-discrepancy">{(m.error as Error).message}</p>}
            <Button type="submit" variant="primary" disabled={!reviewer.trim() || busy || !canDecide || m.isPending}>
              {m.isPending && <Loader2 size={14} className="animate-spin" />} Record decision on rev {rev}
            </Button>
          </form>
        )}

        {voided.length > 0 && (
          <div className="space-y-2">
            <div className="label-caps">Voided approvals</div>
            {voided.map((a) => <Seal key={a.id} approval={a} animate={false} />)}
          </div>
        )}
      </div>
    </Card>
  )
}
