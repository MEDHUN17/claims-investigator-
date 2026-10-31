// Single place where FRONT-B touches the shared API client and route shapes.
// If FRONT-A's api client already prefixes /api, set API_PREFIX to ''.
import { api } from '@/lib/api'

export const API_PREFIX = ''
export const get = <T,>(path: string): Promise<T> => api.get<T>(API_PREFIX + path)
export const post = <T,>(path: string, body?: unknown): Promise<T> => api.post<T>(API_PREFIX + path, body)

/** Deep link into the Evidence tab (FRONT-A owns that page; it reads ?ev=&page=&q=). */
export function evidenceHref(caseId: string, ref: { evidence_id: string; page?: number | null; quote?: string | null }): string {
  const p = new URLSearchParams({ ev: ref.evidence_id })
  if (ref.page != null) p.set('page', String(ref.page))
  if (ref.quote) p.set('q', ref.quote.slice(0, 160))
  return `/case/${caseId}/evidence?${p.toString()}`
}
export const changesHref = (caseId: string, rev?: number) => `/case/${caseId}/changes${rev != null ? `?rev=${rev}` : ''}`

export function errorMessage(e: unknown): { text: string; rateLimited: boolean } {
  const any = e as { message?: string; status?: number } | null
  const msg = any?.message ?? String(e)
  const rl = any?.status === 429 || /\b429\b|rate.?limit|quota/i.test(msg)
  return { text: msg, rateLimited: rl }
}

// ---- decimal-string helpers (amounts are strings; never go through float) ----
export function cmpDec(a?: string | null, b?: string | null): number {
  const pa = a == null || a === '' ? null : a
  const pb = b == null || b === '' ? null : b
  if (pa == null && pb == null) return 0
  if (pa == null) return -1
  if (pb == null) return 1
  const [ai, af = ''] = pa.replace(/^-/, '').split('.')
  const [bi, bf = ''] = pb.replace(/^-/, '').split('.')
  const na = pa.startsWith('-') ? -1 : 1
  const nb = pb.startsWith('-') ? -1 : 1
  if (na !== nb) return na < nb ? -1 : 1
  const n = Math.max(af.length, bf.length)
  const ax = BigInt(ai + af.padEnd(n, '0'))
  const bx = BigInt(bi + bf.padEnd(n, '0'))
  const c = ax === bx ? 0 : ax < bx ? -1 : 1
  return c * na
}
/** Indian lakh grouping on a decimal string, e.g. "650000.50" -> "6,50,000.50". */
export function inr(v?: string | null): string {
  if (v == null || v === '') return '—'
  const neg = v.startsWith('-')
  const [i, f] = v.replace(/^-/, '').split('.')
  const last3 = i.slice(-3)
  const rest = i.slice(0, -3)
  const grouped = rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3 : last3
  return `${neg ? '-' : ''}\u20B9${grouped}${f ? '.' + f : ''}`
}
