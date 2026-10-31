import type { SourceRef } from '@/types'

/** Deep link into the Evidence desk: opens the exhibit, jumps to the page and highlights the quoted text.
 *  The Evidence page accepts this query form and the path form (/evidence/:id?page=&quote=). */
export function citationHref(caseId: string, ref: Pick<SourceRef, 'evidence_id' | 'page' | 'quote'>): string {
  const p = new URLSearchParams({ ev: ref.evidence_id })
  if (ref.page != null) p.set('page', String(ref.page))
  if (ref.quote) p.set('q', ref.quote.slice(0, 160))
  return `/case/${caseId}/evidence?${p.toString()}`
}
