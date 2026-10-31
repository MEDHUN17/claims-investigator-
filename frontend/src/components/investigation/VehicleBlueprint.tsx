import { useMemo, useState } from 'react'
import { Vehicle3DPanel } from '@/components/fx/Vehicle3DPanel'
import { webglAvailable } from '@/components/fx/env'
import { Car, TriangleAlert } from 'lucide-react'
import { ZONES } from '@/types'
import type { ZoneView } from '@/types'
import { DISCREPANCY, Pill, SectionHead } from './Primitives'

const RINGS = [
  { key: 'narrative', label: 'Narrative', hue: '#8C93F5', r: 17, note: 'where the statement says the impact was' },
  { key: 'photo', label: 'Photo', hue: '#3FC1B0', r: 11.5, note: 'where the photograph shows damage' },
  { key: 'estimate', label: 'Estimate', hue: '#6AA3D9', r: 6, note: 'where the repair estimate charges parts' },
] as const

// Anchor points on a 260x380 top-down schematic; front of the car is at the top.
const ANCHOR: Record<string, [number, number]> = {
  front: [130, 36],
  front_right: [196, 66],
  right: [208, 190],
  rear_right: [196, 314],
  rear: [130, 344],
  rear_left: [64, 314],
  left: [52, 190],
  front_left: [64, 66],
  roof: [130, 150],
  underbody: [130, 236],
}

export function VehicleBlueprint({ zones }: { zones: ZoneView }) {
  const [mode, setMode] = useState<'2d' | '3d'>('2d')
  const can3d = useMemo(() => webglAvailable(), [])
  const sets = useMemo(() => ({ narrative: new Set(zones.narrative), photo: new Set(zones.photo), estimate: new Set(zones.estimate) }), [zones])
  const pulseZones = useMemo(() => {
    if (!zones.mismatch) return [] as string[]
    const all = new Set([...zones.narrative, ...zones.photo, ...zones.estimate])
    return [...all].filter((z) => !(sets.narrative.has(z) && sets.photo.has(z) && sets.estimate.has(z)) && ANCHOR[z])
  }, [zones, sets])
  const unknown = ZONES.includes('unknown') && (sets.narrative.has('unknown') || sets.photo.has('unknown') || sets.estimate.has('unknown'))
  const none = zones.narrative.length + zones.photo.length + zones.estimate.length === 0

  return (
    <section>
      <SectionHead
        title="Vehicle blueprint"
        kicker="schematic, not a measurement"
        icon={<Car size={14} />}
        right={<span className="inline-flex items-center gap-2">
          {zones.mismatch ? <Pill hue={DISCREPANCY} icon={<TriangleAlert size={11} />}>zones disagree</Pill> : null}
          <span role="group" aria-label="Blueprint view" className="inline-flex overflow-hidden rounded border border-line text-[11px]">
            {(['2d', '3d'] as const).map((m) => (
              <button key={m} type="button" aria-pressed={mode === m} disabled={m === '3d' && !can3d} title={m === '3d' && !can3d ? 'WebGL unavailable' : undefined}
                onClick={() => setMode(m)} className={`cursor-pointer px-2 py-0.5 font-medium disabled:cursor-not-allowed disabled:opacity-40 ${mode === m ? 'bg-surface-3 text-ink' : 'text-ink-3 hover:text-ink'}`}>
                {m === '2d' ? '2D blueprint' : '3D'}
              </button>
            ))}
          </span>
        </span>}
      />
      <div className="v-panel grid gap-3 p-3 md:grid-cols-[minmax(0,300px)_1fr]">
        {mode === '3d' ? <Vehicle3DPanel zones={zones} /> : <svg viewBox="0 0 260 380" role="img" aria-label={`Damage zones. Narrative: ${zones.narrative.join(', ') || 'none'}. Photo: ${zones.photo.join(', ') || 'none'}. Estimate: ${zones.estimate.join(', ') || 'none'}.`} className="mx-auto h-auto w-full max-w-[300px]">
          <defs>
            <pattern id="vb-grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M20 0H0V20" fill="none" stroke="currentColor" strokeOpacity="0.07" />
            </pattern>
          </defs>
          <rect x="0" y="0" width="260" height="380" fill="url(#vb-grid)" />
          {/* body */}
          <g fill="none" stroke="currentColor" strokeOpacity="0.5" strokeWidth="1.4">
            <path d="M92 58 C92 38 104 30 130 30 C156 30 168 38 168 58 L174 118 L174 262 L168 322 C168 342 156 350 130 350 C104 350 92 342 92 322 L86 262 L86 118 Z" />
            <path d="M104 96 L156 96 L162 140 L98 140 Z" strokeOpacity="0.35" />
            <path d="M104 262 L156 262 L160 300 L100 300 Z" strokeOpacity="0.35" />
            <rect x="98" y="148" width="64" height="104" rx="6" strokeOpacity="0.35" />
            <rect x="70" y="92" width="14" height="26" rx="4" strokeOpacity="0.4" />
            <rect x="176" y="92" width="14" height="26" rx="4" strokeOpacity="0.4" />
            <rect x="70" y="262" width="14" height="26" rx="4" strokeOpacity="0.4" />
            <rect x="176" y="262" width="14" height="26" rx="4" strokeOpacity="0.4" />
          </g>
          <text x="8" y="16" fontSize="9" fill="currentColor" opacity="0.5" letterSpacing="1.5">↑ FRONT OF VEHICLE</text>
          {/* underbody marker */}
          <rect x="108" y="222" width="44" height="28" rx="4" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeDasharray="3 3" />
          {/* mismatch pulse, played once per mismatch state */}
          {pulseZones.map((z) => (
            <circle key={`${z}-${zones.note}`} className="v-pulse-once" cx={ANCHOR[z][0]} cy={ANCHOR[z][1]} r="24" fill={`color-mix(in srgb, ${DISCREPANCY} 22%, transparent)`} stroke={DISCREPANCY} strokeWidth="1.5" />
          ))}
          {/* rings */}
          {Object.entries(ANCHOR).map(([z, [x, y]]) => (
            <g key={z}>
              {RINGS.map((rg) => {
                const on = sets[rg.key].has(z)
                return (
                  <circle
                    key={rg.key}
                    cx={x}
                    cy={y}
                    r={rg.r}
                    fill={on ? `color-mix(in srgb, ${rg.hue} 20%, transparent)` : 'none'}
                    stroke={on ? rg.hue : 'currentColor'}
                    strokeOpacity={on ? 1 : 0.14}
                    strokeWidth={on ? 2.2 : 0.8}
                    strokeDasharray={on ? undefined : '2 3'}
                  />
                )
              })}
              <text x={x} y={y + (y < 100 ? -27 : 31)} textAnchor="middle" fontSize="7.5" fill="currentColor" opacity="0.55" fontFamily="JetBrains Mono Variable, monospace">{z}</text>
            </g>
          ))}
        </svg>}
        <div className="flex min-w-0 flex-col gap-3">
          <div>
            <div className="mb-1.5 text-[10px] uppercase tracking-widest opacity-50">Legend (outer to inner ring)</div>
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[12px]">
              {RINGS.map((rg) => (
                <li key={rg.key} className="flex flex-wrap items-center gap-2">
                  <span className="inline-block size-3 rounded-full" style={{ border: `2px solid ${rg.hue}`, background: `color-mix(in srgb, ${rg.hue} 20%, transparent)` }} />
                  <b className="font-semibold" style={{ color: rg.hue }}>{rg.label}</b>
                  <span className="opacity-60">{rg.note}</span>
                  <span className="v-mono ml-auto text-[11px] opacity-80">{zones[rg.key].length ? zones[rg.key].join(', ') : 'none cited'}</span>
                </li>
              ))}
              {unknown && <li className="text-[11.5px] opacity-60">Some evidence cites zone “unknown”: location could not be resolved.</li>}
            </ul>
          </div>
          {zones.mismatch && (
            <div className="rounded border px-2.5 py-2 text-[12.5px]" style={{ borderColor: DISCREPANCY, background: `color-mix(in srgb, ${DISCREPANCY} 8%, transparent)` }}>
              <div className="mb-0.5 flex items-center gap-1 font-semibold" style={{ color: DISCREPANCY }}><TriangleAlert size={12} /> Discrepancy between sources</div>
              {zones.note || 'The narrative, photo and estimate do not point at the same zones.'}
            </div>
          )}
          {!zones.mismatch && zones.note && <p className="m-0 text-[12.5px] opacity-80">{zones.note}</p>}
          {none && <p className="m-0 text-[12px] opacity-60">No zone has been cited yet.</p>}
          <p className="m-0 text-[11px] opacity-45">Clock-style zones simplified from SAE J224 direction coding; not the full CDC code.</p>
        </div>
      </div>
    </section>
  )
}
