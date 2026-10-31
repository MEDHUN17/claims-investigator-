import { lazy, Suspense, useCallback, useState } from 'react'
import staticUrl from '@/assets/verity-mark-static.svg?url'
import { FxBoundary } from './FxBoundary'
import { usePageVisible, usePrefersReducedMotion, webglAvailable } from './env'

const GL = lazy(() => import('./VerityLogoGL'))

/** Verity mark. The static SVG always renders first; the liquid-metal shader takes over when WebGL is available and motion is allowed. */
export function VerityLogo({ size = 26, speed = 0.25, className }: { size?: number; speed?: number; className?: string }) {
  const reduced = usePrefersReducedMotion()
  const visible = usePageVisible()
  const [ready, setReady] = useState(false)
  const onReady = useCallback(() => setReady(true), [])
  const live = !reduced && visible && webglAvailable()
  return (
    <span className={className} style={{ position: 'relative', display: 'inline-block', width: size, height: size, flex: 'none' }} role="img" aria-label="Verity mark">
      <img src={staticUrl} alt="" width={size} height={size} draggable={false} style={{ width: '100%', height: '100%', opacity: live && ready ? 0 : 1, transition: 'opacity .3s' }} />
      {live && (
        <FxBoundary fallback={null} label="logo">
          <Suspense fallback={null}><GL speed={speed} onReady={onReady} /></Suspense>
        </FxBoundary>
      )}
    </span>
  )
}
