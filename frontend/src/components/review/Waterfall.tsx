import { motion } from 'motion/react'
import type { Calc, CalcLine } from '@/types'
import { inr } from '@/lib/utils'

/** Geometry only: money text is always printed from the original decimal strings. */
function num(s?: string | null): number { const n = Number(s); return Number.isFinite(n) ? n : 0 }
const fmt2 = (n: number) => n.toFixed(2)

type Kind = 'start' | 'minus' | 'plus' | 'flag' | 'total' | 'info'
interface Row { key: string; label: string; basis: string; amount: string; kind: Kind; from: number; to: number; flag?: CalcLine['flag']; note?: string }

/**
 * The API returns calc.lines as: estimate items L01.. (always positive, they ADD UP to the quoted total),
 * then summary lines whose sign is implied by the code, not by the number:
 *   QUOTED / RECOMPUTED = checkpoints (not additive), DEPR / DEDUCT = subtractions,
 *   COVERED = checkpoint, IDV = cap (informational, not a subtraction).
 * Items listed in calc.non_covered ("L07 label") are removed after the quoted total.
 * If COVERED is lower than the running total after depreciation, the gap is shown as "held out" (unresolved terms).
 */
function buildRows(calc: Calc): { rows: Row[]; running: number } {
  const rows: Row[] = []
  let run = 0
  const nonCov = new Set(calc.non_covered.map((s) => s.split(/\s+/)[0]))
  const isItem = (c: string) => /^L\d+$/i.test(c)
  const items = calc.lines.filter((l) => isItem(l.code))
  const other = calc.lines.filter((l) => !isItem(l.code))
  const push = (r: Omit<Row, 'from' | 'to'> & { to: number }, from = run) => { rows.push({ ...r, from }); }
  const meta = (l: CalcLine) => ({ key: l.code + rows.length, label: l.label, basis: l.basis, amount: l.amount, flag: l.flag })

  items.forEach((l, i) => {
    if (l.flag === 'duplicate_suspect') { push({ ...meta(l), kind: 'flag', to: run }); return }
    const a = Math.abs(num(l.amount))
    const to = run + a
    push({ ...meta(l), kind: i === 0 ? 'start' : 'plus', to })
    run = to
  })

  // Legacy / mock shaped payloads (no L## items): fall back to sign heuristics on the first line.
  const SUB = /ded|deprec|not_cov|non_cov|exclu|excess|duplicate/i
  const legacy = items.length === 0
  other.forEach((l) => {
    const a = Math.abs(num(l.amount))
    const code = l.code.toUpperCase()
    if (code === 'QUOTED' || code === 'RECOMPUTED') {
      if (legacy && rows.length === 0) { run = a; push({ ...meta(l), kind: 'start', to: run }, 0); return }
      push({ ...meta(l), kind: 'total', to: run, note: code === 'RECOMPUTED' ? 'checkpoint: sum of the lines above' : 'checkpoint: as printed on the estimate' }, 0)
      if (code === 'RECOMPUTED' || !other.some((x) => x.code.toUpperCase() === 'RECOMPUTED')) {
        // after the checkpoint, remove non-covered items
        const nc = items.filter((it) => nonCov.has(it.code))
        const ncSum = nc.reduce((t, it) => t + Math.abs(num(it.amount)), 0)
        if (nc.length) {
          const to = run - ncSum
          push({ key: 'NC' + rows.length, label: `Not covered (${nc.map((x) => x.code).join(', ')})`, basis: '', amount: fmt2(ncSum), kind: 'minus', flag: 'not_covered', to })
          run = to
        }
      }
      return
    }
    if (code === 'IDV') { push({ ...meta(l), kind: 'info', to: run, note: 'cap, applies only if the loss exceeds it' }, 0); return }
    if (code === 'COVERED') {
      const cov = num(l.amount)
      const gap = run - cov
      if (gap > 0.005) {
        const to = cov
        push({ key: 'HELD' + rows.length, label: 'Held out: unresolved terms', basis: '', amount: fmt2(gap), kind: 'minus', to })
        run = to
      }
      push({ ...meta(l), kind: 'total', to: run }, 0)
      return
    }
    const minus = l.flag === 'not_covered' || l.flag === 'depreciated' || SUB.test(code) || num(l.amount) < 0
    if (legacy && rows.length === 0) { run = a; push({ ...meta(l), kind: 'start', to: run }, 0); return }
    const to = minus ? run - a : run + a
    push({ ...meta(l), kind: minus ? 'minus' : 'plus', to })
    run = to
  })
  return { rows, running: run }
}

const W = 760, LABEL = 250, PAD = 96, ROW = 34

export function Waterfall({ calc }: { calc: Calc }) {
  const { rows, running } = buildRows(calc)
  const resolved = calc.proposed_settlement != null
  const finalVal = resolved ? num(calc.proposed_settlement) : running
  const max = Math.max(1, ...rows.map((r) => Math.max(r.from, r.to)), finalVal)
  const track = W - LABEL - PAD
  const x = (v: number) => LABEL + (Math.max(0, v) / max) * track
  const total = rows.length + 1
  const H = total * ROW + 12

  if (calc.lines.length === 0) {
    return <p className="text-sm text-ink-3">No calculation lines yet. The waterfall appears when an estimate and policy terms have been read.</p>
  }

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Settlement waterfall" className="w-full min-w-[560px]">
        <defs>
          <pattern id="wf-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="none" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--stale)" strokeWidth="1.6" />
          </pattern>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((g) => <line key={g} x1={LABEL + g * track} x2={LABEL + g * track} y1={0} y2={H - 6} stroke="var(--line-soft)" strokeWidth="1" />)}
        {rows.map((r, i) => {
          const y = i * ROW + 6
          const x1 = x(Math.min(r.from, r.to)), x2 = x(Math.max(r.from, r.to))
          const color = r.kind === 'total' ? 'var(--ink-2)' : r.kind === 'minus' ? 'var(--inferred)' : r.kind === 'flag' ? 'var(--stale)' : 'var(--computed)'
          return (
            <g key={r.key}>
              <text x={LABEL - 10} y={y + 14} textAnchor="end" fontSize="11.5" fill="var(--ink)">{r.label.length > 40 ? r.label.slice(0, 39) + '…' : r.label}<title>{r.label}</title></text>
              {(r.flag || r.note) && <text x={LABEL - 10} y={y + 26} textAnchor="end" fontSize="9" fill={r.flag ? 'var(--stale)' : 'var(--ink-3)'} style={{ textTransform: 'uppercase', letterSpacing: '0.08em' }}>{r.flag ? r.flag.replace('_', ' ') : r.note}</text>}
              {r.kind === 'info' ? (
                <text x={LABEL + 6} y={y + 17} fontSize="10.5" fill="var(--ink-3)" fontStyle="italic">cap, not reached</text>
              ) : r.kind === 'flag' ? (
                <motion.rect initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.07, duration: 0.25 }} x={x(r.from) - 3} y={y + 4} width={6} height={18} fill="url(#wf-hatch)" stroke="var(--stale)" />
              ) : (
                <motion.rect
                  initial={{ width: 0, opacity: 0 }} animate={{ width: Math.max(2, x2 - x1), opacity: 1 }} transition={{ delay: i * 0.07, duration: 0.3 }}
                  x={x1} y={y + 4} height={18} rx={2}
                  fill={r.kind === 'minus' ? 'color-mix(in srgb, var(--inferred) 30%, transparent)' : r.kind === 'total' ? 'color-mix(in srgb, var(--ink) 14%, transparent)' : 'color-mix(in srgb, var(--computed) 32%, transparent)'}
                  stroke={color} strokeWidth="1.2" strokeDasharray={r.kind === 'minus' ? '4 3' : undefined}
                />
              )}
              {i > 0 && r.kind !== 'info' && r.kind !== 'total' && <line x1={x(r.from)} x2={x(r.from)} y1={y - ROW + 22} y2={y + 4} stroke="var(--ink-3)" strokeWidth="0.8" strokeDasharray="2 2" />}
              <text x={W - 6} y={y + 17} textAnchor="end" fontSize="11.5" fontFamily="var(--font-mono)" fontWeight={r.kind === 'total' ? 700 : 400} fill={r.kind === 'info' ? 'var(--ink-3)' : 'var(--ink)'}>{r.kind === 'minus' ? '− ' : r.kind === 'plus' ? '+ ' : ''}{inr(r.amount.replace('-', ''), calc.currency)}</text>
            </g>
          )
        })}
        {/* Final figure or UNRESOLVED */}
        {(() => {
          const i = rows.length
          const y = i * ROW + 6
          return (
            <g>
              <line x1={LABEL} x2={W - 6} y1={y - 1} y2={y - 1} stroke="var(--ink-3)" strokeWidth="1" />
              <text x={LABEL - 10} y={y + 17} textAnchor="end" fontSize="12.5" fontWeight="700" fill="var(--ink)">{resolved ? 'Proposed settlement' : 'UNRESOLVED'}</text>
              <motion.rect
                initial={{ width: 0 }} animate={{ width: Math.max(4, x(finalVal) - LABEL) }} transition={{ delay: rows.length * 0.07 + 0.1, duration: 0.4 }}
                x={LABEL} y={y + 4} height={20} rx={2}
                fill={resolved ? 'color-mix(in srgb, var(--human) 22%, transparent)' : 'url(#wf-hatch)'} stroke={resolved ? 'var(--human)' : 'var(--stale)'} strokeWidth="1.6" strokeDasharray={resolved ? undefined : '5 3'}
              />
              {resolved
                ? <text x={W - 6} y={y + 19} textAnchor="end" fontSize="13" fontWeight="700" fontFamily="var(--font-mono)" fill="var(--ink)">{inr(calc.proposed_settlement, calc.currency)}</text>
                : <text x={LABEL + 10} y={y + 19} fontSize="12" fontWeight="700" fontFamily="var(--font-mono)" fill="var(--ink)" stroke="var(--surface)" strokeWidth="5" paintOrder="stroke">no figure: see unresolved list</text>}
            </g>
          )
        })()}
      </svg>
    </div>
  )
}
