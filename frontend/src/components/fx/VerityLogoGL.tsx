import { useEffect } from 'react'
import { LiquidMetal } from '@paper-design/shaders-react'
import markUrl from '@/assets/verity-mark.svg?url'

/** Liquid-metal rendering of the Verity mark (Paper Shaders, the engine behind liquid-logo). Default export for React.lazy. */
export default function VerityLogoGL({ speed, onReady }: { speed: number; onReady: () => void }) {
  useEffect(() => { const id = window.setTimeout(onReady, 350); return () => window.clearTimeout(id) }, [onReady])
  return (
    <LiquidMetal
      image={markUrl}
      colorBack="#00000000"
      colorTint="#ffffff"
      repetition={2}
      softness={0.5}
      shiftRed={0.25}
      shiftBlue={0.25}
      distortion={0.1}
      contour={0.45}
      angle={70}
      speed={speed}
      scale={0.92}
      fit="contain"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
    />
  )
}
