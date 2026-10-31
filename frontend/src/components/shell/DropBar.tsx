import { useCallback, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Paperclip, SendHorizonal, Loader2, CopyCheck, TriangleAlert, FilePlus2 } from 'lucide-react'
import { ApiError, useUploadEvidence } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { LiquidGlass } from '@/components/fx/LiquidGlass'

export interface UploadNote { key: string; name: string; tag?: string; state: 'sent' | 'duplicate' | 'error'; msg: string }

/** Upload logic shared by the drop bar and the workspace-wide drag overlay. */
export function useEvidenceUploader(caseId: string, existingCount: number) {
  const mut = useUploadEvidence(caseId)
  const [notes, setNotes] = useState<UploadNote[]>([])
  const [busy, setBusy] = useState(0)

  const push = (n: UploadNote) => setNotes((cur) => [n, ...cur].slice(0, 4))

  const sendOne = useCallback(async (file: File | Blob, filename: string) => {
    setBusy((b) => b + 1)
    try {
      const out = await mut.mutateAsync({ file, filename })
      push({ key: out.evidence.id, name: filename, state: 'sent', tag: out.evidence.id, msg: 'Stored, hashed, queued for reading' })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) push({ key: filename + Date.now(), name: filename, state: 'duplicate', msg: 'Already in this case (same SHA-256). Nothing changed.' })
      else push({ key: filename + Date.now(), name: filename, state: 'error', msg: e instanceof Error ? e.message : 'Upload failed' })
    } finally {
      setBusy((b) => b - 1)
    }
  }, [mut, existingCount])

  const submitFiles = useCallback(async (files: File[]) => { for (const f of files) await sendOne(f, f.name) }, [sendOne])
  const submitText = useCallback(async (text: string) => {
    const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15)
    await sendOne(new Blob([text], { type: 'text/plain' }), `statement-${stamp}.txt`)
  }, [sendOne])

  return { submitFiles, submitText, notes, busy: busy > 0 }
}

export function DropBar({ onPickFiles, onText, notes, busy, dragging }: {
  onPickFiles: () => void; onText: (t: string) => void | Promise<void>; notes: UploadNote[]; busy: boolean; dragging: boolean
}) {
  const [text, setText] = useState('')
  const send = async () => {
    const t = text.trim()
    if (!t) return
    setText('')
    await onText(t)
  }
  return (
    <div className="px-4 py-2.5">
      <LiquidGlass off={dragging} strength={0.8} className={cn('flex items-center gap-2 rounded-lg border border-dashed bg-surface/80 px-2.5 py-1.5 transition-colors', dragging ? 'border-accent bg-accent/10' : 'border-line')}>
        <FilePlus2 size={16} className="shrink-0 text-accent" aria-hidden />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
          placeholder="Add evidence or type a statement  (drop any file anywhere on this page)"
          aria-label="Add evidence or type a statement"
          className="h-8 min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-3"
        />
        <Button size="sm" variant="ghost" onClick={onPickFiles} aria-label="Attach files"><Paperclip size={14} /> <span className="hidden sm:inline">Attach</span></Button>
        <Button size="sm" variant="primary" onClick={() => void send()} disabled={!text.trim() || busy} aria-label="Submit statement">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <SendHorizonal size={14} />} <span className="hidden sm:inline">Add</span>
        </Button>
      </LiquidGlass>
      <div className="mt-1.5 flex flex-wrap gap-2" aria-live="polite">
        <AnimatePresence initial={false}>
          {notes.map((n) => (
            <motion.div
              key={n.key}
              layout
              initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}
              className={cn('flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs', n.state === 'error' ? 'border-discrepancy/60 text-discrepancy' : n.state === 'duplicate' ? 'hatch border-dashed border-stale text-ink-2' : 'border-line bg-surface text-ink-2')}
            >
              {n.state === 'sent' ? <span className="tag rounded border border-accent px-1 text-accent">{n.tag}</span> : n.state === 'duplicate' ? <CopyCheck size={12} /> : <TriangleAlert size={12} />}
              <span className="mono max-w-[180px] truncate">{n.name}</span>
              <span className="text-ink-3">{n.msg}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
