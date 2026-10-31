import { useEffect, useState } from 'react'
import { BadgeCheck, CornerUpLeft, ArrowUpRight, Ban, FileClock } from 'lucide-react'
import type { ApprovalOut } from '@/types'
import { cn } from '@/lib/utils'
import { LiquidGlass } from '@/components/fx/LiquidGlass'

/** Types a string out character by character, finishing in about `ms` milliseconds. */
export function useTypewriter(text: string, ms = 400, enabled = true): string {
  const [n, setN] = useState(enabled ? 0 : text.length)
  useEffect(() => {
    if (!enabled) { setN(text.length); return }
    setN(0)
    const step = Math.max(8, ms / Math.max(1, text.length))
    const id = window.setInterval(() => setN((v) => { if (v >= text.length) { window.clearInterval(id); return v } return v + 1 }), step)
    return () => window.clearInterval(id)
  }, [text, ms, enabled])
  return text.slice(0, n)
}

const DEC = {
  approve: { label: 'Approved', icon: BadgeCheck },
  return: { label: 'Returned', icon: CornerUpLeft },
  escalate: { label: 'Escalated', icon: ArrowUpRight },
} as const

/** Compact chip for headers: DRAFT / SEALED / VOID. */
export function SealChip({ approval, className }: { approval?: ApprovalOut | null; className?: string }) {
  if (!approval) {
    return (
      <span className={cn('inline-flex items-center gap-1.5 rounded-md border border-dashed border-ink-3 px-2 py-1 text-[0.7rem] font-semibold uppercase tracking-wider text-ink-3', className)}>
        <FileClock size={12} /> Draft · no approval
      </span>
    )
  }
  if (approval.status === 'void') {
    return (
      <span title={approval.void_reason ?? 'Voided'} className={cn('hatch-dense crack inline-flex items-center gap-1.5 rounded-md border border-dashed border-stale px-2 py-1 text-[0.7rem] font-semibold uppercase tracking-wider text-stale', className)}>
        <Ban size={12} /> Void · rev {approval.rev}
      </span>
    )
  }
  const d = DEC[approval.decision]
  const I = d.icon
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-md border border-human bg-human/10 px-2 py-1 text-[0.7rem] font-semibold uppercase tracking-wider text-human', className)}>
      <I size={12} /> {d.label} · rev {approval.rev}
    </span>
  )
}

/** Large stamp: version hash types out; VOID state is hatched with the hash struck through. */
export function Seal({ approval, animate = true }: { approval: ApprovalOut; animate?: boolean }) {
  const isVoid = approval.status === 'void'
  const typed = useTypewriter(approval.hash, 420, animate && !isVoid)
  const d = DEC[approval.decision]
  const I = d.icon
  return (
    <LiquidGlass
      className={cn('relative overflow-hidden rounded-lg border-2 p-4', isVoid ? 'hatch-dense crack border-dashed border-stale text-stale' : 'border-human text-human')}
      style={{ background: isVoid ? undefined : 'color-mix(in srgb, var(--human) 6%, transparent)' }}
      strength={isVoid ? 0.5 : 0.9}
    >
      <div className="flex items-center gap-2">
        {isVoid ? <Ban size={20} /> : <I size={20} />}
        <div className="text-base font-bold uppercase tracking-[0.14em]">{isVoid ? 'VOID' : d.label}</div>
        <span className="tag ml-auto">rev {approval.rev}</span>
      </div>
      {isVoid && <p className="mt-1 text-xs">{approval.void_reason ?? 'New evidence changed the case after this approval. Review again.'}</p>}
      <dl className="mt-3 grid gap-x-3 gap-y-1 text-xs" style={{ gridTemplateColumns: 'auto 1fr' }}>
        <dt className="opacity-70">Decision by</dt>
        <dd className="font-medium">{approval.reviewer} <span className="opacity-60">(typed label, not authentication)</span></dd>
        <dt className="opacity-70">Authority</dt>
        <dd className="mono">{approval.authority_role}</dd>
        <dt className="opacity-70">Version hash</dt>
        <dd className={cn('mono break-all', isVoid && 'strike')}>{typed}<span className="opacity-40">{typed.length < approval.hash.length ? '▌' : ''}</span></dd>
      </dl>
    </LiquidGlass>
  )
}
