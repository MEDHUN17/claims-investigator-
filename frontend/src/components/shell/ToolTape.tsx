import { AnimatePresence, motion } from 'motion/react'
import { ScrollText, X } from 'lucide-react'
import type { ActivityOut } from '@/types'
import { cn } from '@/lib/utils'

const KIND_TONE: Record<string, string> = { stage: 'text-accent', tool: 'text-computed', provider: 'text-reported', audit: 'text-human' }

function brief(o: Record<string, any>): string {
  const s = JSON.stringify(o ?? {})
  return s.length > 140 ? s.slice(0, 140) + '…' : s
}

/** Drawer listing every tool / stage / provider call the system made (case.activity), newest first. */
export function ToolTape({ open, onClose, activity }: { open: boolean; onClose: () => void; activity: ActivityOut[] }) {
  const rows = [...activity].reverse()
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          aria-label="Tool tape"
          initial={{ x: 420, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 420, opacity: 0 }} transition={{ duration: 0.25 }}
          className="fixed bottom-0 right-0 top-12 z-40 flex w-[min(420px,100vw)] flex-col border-l border-line bg-surface shadow-[var(--shadow)]"
        >
          <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
            <ScrollText size={15} className="text-accent" />
            <h2 className="text-sm font-semibold">Tool tape</h2>
            <span className="tag text-ink-3">{rows.length} calls</span>
            <button onClick={onClose} aria-label="Close tool tape" className="ml-auto cursor-pointer rounded p-1 text-ink-3 hover:text-ink"><X size={16} /></button>
          </div>
          <p className="border-b border-line-soft px-3 py-2 text-xs text-ink-3">Every stage, tool and model call, as logged. Model-proposed tool calls outside the closed registry appear here as rejected.</p>
          <ol className="min-h-0 flex-1 overflow-y-auto">
            {rows.length === 0 && <li className="p-4 text-xs text-ink-3">No activity yet.</li>}
            {rows.map((a, i) => (
              <li key={i} className="border-b border-line-soft px-3 py-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className={cn('tag font-bold uppercase', KIND_TONE[a.kind])}>{a.kind}</span>
                  <span className="mono font-medium">{a.name}</span>
                  <span className={cn('tag ml-auto', a.status === 'ok' || a.status === 'done' ? 'text-observed' : 'text-inferred')}>{a.status}</span>
                  <span className="tag text-ink-3">{a.duration_ms} ms</span>
                </div>
                <div className="tag mt-0.5 text-ink-3">{new Date(a.ts).toLocaleTimeString()}</div>
                {Object.keys(a.args ?? {}).length > 0 && <div className="tag mt-1 break-all text-ink-2">in  {brief(a.args)}</div>}
                {Object.keys(a.result ?? {}).length > 0 && <div className="tag break-all text-ink-2">out {brief(a.result)}</div>}
              </li>
            ))}
          </ol>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
