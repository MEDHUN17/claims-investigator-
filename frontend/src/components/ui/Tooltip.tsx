import { useState, type ReactNode } from 'react'

/** Lightweight hover/focus tooltip (no portal; keep content short). */
export function Tooltip({ text, children }: { text: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
      {children}
      {open && (
        <span role="tooltip" className="pointer-events-none absolute left-1/2 top-full z-40 mt-1.5 w-max max-w-[260px] -translate-x-1/2 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs leading-snug text-ink shadow-[var(--shadow)]">
          {text}
        </span>
      )}
    </span>
  )
}
