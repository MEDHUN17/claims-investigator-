import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format a decimal-string amount with Indian digit grouping. Never does float math on money. */
export function inr(amount?: string | null, currency = 'INR'): string {
  if (amount == null || amount === '') return '—'
  const neg = amount.startsWith('-')
  const [int, frac] = amount.replace('-', '').split('.')
  const last3 = int.slice(-3)
  const rest = int.slice(0, -3)
  const grouped = rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3 : last3
  const sym = currency === 'INR' ? '₹' : currency + ' '
  const f = frac && /[1-9]/.test(frac) ? '.' + frac.padEnd(2, '0').slice(0, 2) : ''
  return `${neg ? '-' : ''}${sym}${grouped}${f}`
}

export function relTime(iso?: string | null): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const s = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return new Date(iso).toLocaleDateString()
}

export function shortHash(h?: string | null, n = 10): string {
  return h ? h.slice(0, n) : '—'
}

/** Exhibit tag helpers (E-01, F-03...). Falls back to a short id slice. */
export function tagFor(prefix: string, ids: string[], id: string): string {
  const i = ids.indexOf(id)
  return i >= 0 ? `${prefix}-${String(i + 1).padStart(2, '0')}` : `${prefix}-${id.slice(0, 4)}`
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function normalizeForMatch(s: string): string {
  return s.toLowerCase().replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/\s+/g, ' ').trim()
}
