import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-lg border border-line bg-surface/90', className)} {...rest} />
}

export function CardHeader({ title, tag, right, className }: { title: ReactNode; tag?: string; right?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-center gap-2 border-b border-line-soft px-3.5 py-2.5', className)}>
      {tag && <span className="tag rounded border border-line px-1.5 py-0.5 text-ink-2">{tag}</span>}
      <h3 className="text-sm font-semibold tracking-tight text-ink">{title}</h3>
      <div className="ml-auto flex items-center gap-2">{right}</div>
    </div>
  )
}

export function Section({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn('space-y-2', className)}>
      <div className="label-caps">{label}</div>
      {children}
    </section>
  )
}
