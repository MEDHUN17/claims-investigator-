import { motion } from 'motion/react'
import { CheckCircle2, CircleDashed, Loader2, MinusCircle, XCircle } from 'lucide-react'
import type { JobOut, PlanStep } from '@/types'
import { cn } from '@/lib/utils'

function StepIcon({ s }: { s: PlanStep['status'] }) {
  switch (s) {
    case 'done': return <CheckCircle2 size={12} className="text-observed" />
    case 'running': return <Loader2 size={12} className="animate-spin text-accent" />
    case 'failed': return <XCircle size={12} className="text-discrepancy" />
    case 'skipped': return <MinusCircle size={12} className="text-stale" />
    default: return <CircleDashed size={12} className="text-ink-3" />
  }
}
const WORD: Record<PlanStep['status'], string> = { pending: 'queued', running: 'running', done: 'done', skipped: 'skipped', failed: 'failed' }

/** Live plan strip built from the latest job's plan steps (no steps are invented here). */
export function PlanStrip({ job }: { job?: JobOut }) {
  if (!job) return null
  const active = job.status === 'queued' || job.status === 'running'
  return (
    <div aria-label="Investigation plan" className={cn('flex items-stretch gap-2 overflow-x-auto px-4 py-2', !active && 'opacity-75')}>
      <div className="flex shrink-0 flex-col justify-center pr-1">
        <span className="label-caps">Plan</span>
        <span className="tag text-ink-2">{active ? (job.status === 'queued' ? 'queued' : 'running') : job.status}</span>
      </div>
      {job.plan.length === 0 && <span className="self-center text-xs text-ink-3">Waiting for the planner to publish steps…</span>}
      {job.plan.map((s, i) => (
        <motion.div
          key={s.name + i}
          layout
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          title={s.reason}
          className={cn(
            'flex min-w-[130px] max-w-[240px] shrink-0 flex-col justify-center rounded-md border px-2.5 py-1.5',
            s.status === 'running' ? 'glow border-accent bg-accent/5' : 'border-line bg-surface/70',
            s.status === 'skipped' && 'hatch border-dashed',
          )}
        >
          <div className="flex items-center gap-1.5 text-xs font-medium"><StepIcon s={s.status} /><span className="mono truncate">{s.name}</span><span className="ml-auto text-[0.62rem] uppercase tracking-wider text-ink-3">{WORD[s.status]}</span></div>
          {s.reason && <div className="mt-0.5 truncate text-[0.7rem] text-ink-3">{s.reason}</div>}
        </motion.div>
      ))}
      {job.error && <span className="self-center text-xs text-discrepancy">{job.error}</span>}
    </div>
  )
}
