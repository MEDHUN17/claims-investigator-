import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import { cn } from '@/lib/utils'

export interface TabDef { id: string; label: ReactNode; badge?: ReactNode; icon?: ReactNode }

export function Tabs({ tabs, value, onChange, layoutId = 'tabs', className }: {
  tabs: TabDef[]; value: string; onChange: (id: string) => void; layoutId?: string; className?: string
}) {
  return (
    <div role="tablist" className={cn('flex items-center gap-1 overflow-x-auto', className)}>
      {tabs.map((t) => {
        const active = t.id === value
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={cn(
              'relative flex h-9 cursor-pointer items-center gap-2 whitespace-nowrap px-3 text-sm font-medium transition-colors',
              active ? 'text-ink' : 'text-ink-3 hover:text-ink-2',
            )}
          >
            {t.icon}
            {t.label}
            {t.badge}
            {active && (
              <motion.span layoutId={layoutId} transition={{ duration: 0.25 }} className="absolute inset-x-1 -bottom-px h-[2px] bg-accent" />
            )}
          </button>
        )
      })}
    </div>
  )
}
