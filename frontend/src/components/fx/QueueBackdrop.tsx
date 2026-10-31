import { lazy, Suspense } from 'react'
import { FxBoundary } from './FxBoundary'
import { useAppTheme, usePageVisible, usePrefersReducedMotion, webglAvailable } from './env'

const GL = lazy(() => import('./QueueBackdropGL'))

const DARK_STATIC = 'radial-gradient(60% 90% at 12% 0%, rgba(63,193,176,0.14), transparent 70%), radial-gradient(55% 90% at 62% 0%, rgba(140,147,245,0.16), transparent 70%), radial-gradient(45% 80% at 100% 10%, rgba(199,125,219,0.12), transparent 70%)'
const LIGHT_STATIC = 'radial-gradient(60% 90% at 12% 0%, rgba(11,127,112,0.10), transparent 70%), radial-gradient(55% 90% at 62% 0%, rgba(74,82,196,0.10), transparent 70%), radial-gradient(45% 80% at 100% 10%, rgba(142,62,165,0.08), transparent 70%)'
const MASK = 'linear-gradient(to bottom, #000 0%, #000 35%, transparent 100%)'

/** Hero backdrop for the Queue page: top ~300 px only, dimmed so text stays readable. Dark theme animates; light theme is a pale static gradient. */
export function QueueBackdrop() {
  const theme = useAppTheme()
  const visible = usePageVisible()
  const reduced = usePrefersReducedMotion()
  const live = theme === 'dark' && visible && !reduced && webglAvailable()
  return (
    <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[300px] overflow-hidden" style={{ WebkitMaskImage: MASK, maskImage: MASK }}>
      <div className="absolute inset-0" style={{ background: theme === 'dark' ? DARK_STATIC : LIGHT_STATIC }} />
      {live && (
        <FxBoundary fallback={null} label="queue backdrop">
          <Suspense fallback={null}>
            <div className="absolute inset-0 opacity-90"><GL /></div>
          </Suspense>
        </FxBoundary>
      )}
      {/* dim scrim keeps text readable; hairline grid ties it to the light-table language */}
      <div className="absolute inset-0" style={{ background: theme === 'dark' ? 'linear-gradient(to bottom, rgba(14,17,22,0.35), rgba(14,17,22,0.82))' : 'transparent' }} />
      <div className="absolute inset-0" style={{ backgroundImage: 'linear-gradient(var(--grid) 1px, transparent 1px), linear-gradient(90deg, var(--grid) 1px, transparent 1px)', backgroundSize: '24px 24px' }} />
    </div>
  )
}
