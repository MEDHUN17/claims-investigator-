import { useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page } from 'react-pdf'
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus, Quote, Loader2, FileX2 } from 'lucide-react'
import '@/lib/pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import { api, usePassages } from '@/lib/api'
import type { EvidenceOut } from '@/types'
import { Button } from '@/components/ui/Button'
import { normalizeForMatch } from '@/lib/utils'

export interface Cite { page?: number; quote?: string }

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Case-insensitive, whitespace-tolerant regex for a quote. */
function quoteRegex(quote: string): RegExp | null {
  const words = quote.trim().split(/\s+/).filter(Boolean).map(esc)
  if (!words.length) return null
  try { return new RegExp(words.join('\\s+'), 'i') } catch { return null }
}

function CiteBanner({ quote, found }: { quote: string; found: boolean | null }) {
  return (
    <div className="flex items-start gap-2 border-b border-line bg-accent/8 px-3 py-1.5 text-xs" style={{ background: 'color-mix(in srgb, var(--accent) 8%, transparent)' }}>
      <Quote size={13} className="mt-0.5 shrink-0 text-accent" />
      <span className="min-w-0 flex-1"><span className="label-caps mr-1.5">Cited</span><mark className="cite">{quote}</mark></span>
      {found === false && <span className="tag shrink-0 text-inferred">not found in extracted text</span>}
    </div>
  )
}

function Empty({ msg }: { msg: string }) {
  return <div className="flex h-full items-center justify-center gap-2 p-6 text-sm text-ink-3"><FileX2 size={16} /> {msg}</div>
}

/* ---------------- Image with zoom ---------------- */
function ImageViewer({ ev }: { ev: EvidenceOut }) {
  const [scale, setScale] = useState(1)
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
        <Button size="sm" variant="ghost" onClick={() => setScale((s) => Math.max(0.25, +(s - 0.25).toFixed(2)))} aria-label="Zoom out"><Minus size={13} /></Button>
        <span className="tag w-12 text-center">{Math.round(scale * 100)}%</span>
        <Button size="sm" variant="ghost" onClick={() => setScale((s) => Math.min(6, +(s + 0.25).toFixed(2)))} aria-label="Zoom in"><Plus size={13} /></Button>
        <Button size="sm" variant="ghost" onClick={() => setScale(1)} aria-label="Fit"><Maximize2 size={13} /> Fit</Button>
        <span className="ml-auto tag text-ink-3">original, unmodified</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-[color-mix(in_srgb,var(--bg)_70%,black)] p-3" onWheel={(e) => { if (e.ctrlKey) { e.preventDefault(); setScale((s) => Math.min(6, Math.max(0.25, s - e.deltaY * 0.002))) } }}>
        <img src={api.fileUrl(ev.id)} alt={`Evidence ${ev.filename}`} style={{ width: `${scale * 100}%`, maxWidth: 'none' }} className="mx-auto block shadow-[var(--shadow)]" draggable={false} />
      </div>
    </div>
  )
}

/* ---------------- PDF with page navigation + citation highlight ---------------- */
function PdfViewer({ ev, cite }: { ev: EvidenceOut; cite: Cite }) {
  const [numPages, setNumPages] = useState(ev.pages || 0)
  const [page, setPage] = useState(cite.page ?? 1)
  const [width, setWidth] = useState(600)
  const [err, setErr] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const passages = usePassages(ev.id)

  // Jump to the cited page; if the quote is actually on another page, jump there.
  const foundPage = useMemo(() => {
    if (!cite.quote || !passages.data) return null
    const re = quoteRegex(cite.quote)
    if (!re) return null
    if (cite.page && re.test(passages.data.find((p) => p.page === cite.page)?.text ?? '')) return cite.page
    return passages.data.find((p) => re.test(p.text))?.page ?? null
  }, [cite.quote, cite.page, passages.data])

  useEffect(() => {
    if (foundPage) setPage(foundPage)
    else if (cite.page) setPage(cite.page)
  }, [foundPage, cite.page, cite.quote])

  useEffect(() => {
    if (!box.current) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, Math.floor(e.contentRect.width - 24))))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])

  const nq = cite.quote ? normalizeForMatch(cite.quote) : ''
  const render = useMemo(() => {
    if (!nq) return undefined
    return ({ str }: { str: string }) => {
      const n = normalizeForMatch(str)
      const hit = n.length >= 3 && (nq.includes(n) || n.includes(nq))
      return hit ? `<mark class="cite">${str.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</mark>` : str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    }
  }, [nq])

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
        <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Previous page"><ChevronLeft size={14} /></Button>
        <span className="tag w-20 text-center">page {page} / {numPages || '…'}</span>
        <Button size="sm" variant="ghost" disabled={!numPages || page >= numPages} onClick={() => setPage((p) => p + 1)} aria-label="Next page"><ChevronRight size={14} /></Button>
        <span className="ml-auto tag text-ink-3">PDF.js, local worker</span>
      </div>
      {cite.quote && <CiteBanner quote={cite.quote} found={passages.data ? foundPage != null : null} />}
      <div ref={box} className="min-h-0 flex-1 overflow-auto bg-[color-mix(in_srgb,var(--bg)_70%,black)] p-3">
        {err ? <Empty msg={err} /> : (
          <Document
            file={api.fileUrl(ev.id)}
            onLoadSuccess={(d) => { setNumPages(d.numPages); setPage((p) => Math.min(Math.max(1, p), d.numPages)) }}
            onLoadError={(e) => setErr(`Could not render this PDF: ${e.message}`)}
            loading={<div className="flex items-center justify-center gap-2 p-6 text-sm text-ink-3"><Loader2 size={15} className="animate-spin" /> Loading PDF…</div>}
          >
            <Page pageNumber={page} width={width} renderAnnotationLayer={false} customTextRenderer={render} />
          </Document>
        )}
      </div>
    </div>
  )
}

/* ---------------- Text passages (txt / md / csv / json / unknown) ---------------- */
function Highlighted({ text, quote }: { text: string; quote?: string }) {
  const re = quote ? quoteRegex(quote) : null
  const m = re ? re.exec(text) : null
  const ref = useRef<HTMLElement>(null)
  useEffect(() => { ref.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }) }, [quote, text])
  if (!m) return <>{text}</>
  return <>{text.slice(0, m.index)}<mark ref={ref} className="cite">{m[0]}</mark>{text.slice(m.index + m[0].length)}</>
}

function TextViewer({ ev, cite }: { ev: EvidenceOut; cite: Cite }) {
  const passages = usePassages(ev.id)
  const found = useMemo(() => {
    if (!cite.quote || !passages.data) return null
    const re = quoteRegex(cite.quote)
    return re ? passages.data.some((p) => re.test(p.text)) : null
  }, [cite.quote, passages.data])
  return (
    <div className="flex h-full flex-col">
      {cite.quote && <CiteBanner quote={cite.quote} found={found} />}
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {passages.isLoading && <div className="text-sm text-ink-3"><Loader2 size={14} className="mr-2 inline animate-spin" />Loading text…</div>}
        {passages.data?.length === 0 && <Empty msg="No readable text was extracted from this file." />}
        {passages.data?.map((p) => (
          <div key={p.page} className="mb-4 rounded-md border border-line bg-surface p-3">
            {passages.data!.length > 1 && <div className="label-caps mb-1.5">page {p.page}</div>}
            <pre className="mono whitespace-pre-wrap break-words text-[0.8rem] leading-relaxed text-ink"><Highlighted text={p.text} quote={cite.page && cite.page !== p.page ? undefined : cite.quote} /></pre>
          </div>
        ))}
      </div>
    </div>
  )
}

export function EvidenceViewer({ ev, cite }: { ev: EvidenceOut; cite: Cite }) {
  if (ev.status === 'unsupported') return <Empty msg={`${ev.filename} is stored but not analysable (${ev.mime}). Provide a transcript or stills.`} />
  if (ev.mime.startsWith('image/')) return <ImageViewer ev={ev} />
  if (ev.mime === 'application/pdf' || ev.filename.toLowerCase().endsWith('.pdf')) return <PdfViewer ev={ev} cite={cite} />
  return <TextViewer ev={ev} cite={cite} />
}
