import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Neutral grey diagonal-hatch badge: STALE / UNKNOWN / UNRESOLVED / VOID. */
export function HatchedBadge({ children, icon, className, strong }: { children: ReactNode; icon?: ReactNode; className?: string; strong?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-[5px] border border-dashed border-stale px-1.5 py-[1px] text-[0.68rem] font-semibold uppercase tracking-wider text-stale',
        strong ? 'hatch-dense' : 'hatch',
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}
