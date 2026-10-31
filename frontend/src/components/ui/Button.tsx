import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger-neutral'
type Size = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-accent-ink hover:brightness-110 border-transparent font-semibold',
  secondary: 'bg-surface-2 text-ink hover:bg-surface-3 border-line',
  ghost: 'bg-transparent text-ink-2 hover:text-ink hover:bg-surface-2 border-transparent',
  'danger-neutral': 'bg-transparent text-discrepancy border-discrepancy/50 hover:bg-discrepancy/10',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', className, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md border transition-colors select-none',
        'disabled:opacity-45 disabled:cursor-not-allowed cursor-pointer',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-9 px-3.5 text-sm',
        variants[variant],
        className,
      )}
      {...rest}
    />
  )
})
