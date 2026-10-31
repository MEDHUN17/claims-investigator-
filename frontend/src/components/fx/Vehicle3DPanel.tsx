import { lazy, Suspense } from 'react'
import { Loader2 } from 'lucide-react'
import type { ZoneView } from '@/types'
import { FxBoundary } from './FxBoundary'

const Vehicle3D = lazy(() => import('./Vehicle3D'))

const Placeholder = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-auto grid aspect-[10/9] w-full max-w-[420px] place-items-center rounded-md border border-dashed border-line p-3 text-center text-xs text-ink-3">{children}</div>
)

/** Lazy, error-bounded 3D vehicle. The three.js chunk only loads when the user picks the 3D view. */
export function Vehicle3DPanel({ zones }: { zones: ZoneView }) {
  return (
    <FxBoundary label="3D vehicle" fallback={<Placeholder>3D view unavailable on this device. The 2D blueprint shows the same zones.</Placeholder>}>
      <Suspense fallback={<Placeholder><Loader2 size={16} className="animate-spin" /></Placeholder>}>
        <Vehicle3D zones={zones} />
      </Suspense>
    </FxBoundary>
  )
}
