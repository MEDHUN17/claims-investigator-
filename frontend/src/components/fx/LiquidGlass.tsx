import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { usePrefersReducedMotion, webglAvailable } from './env'

let loading: Promise<typeof import('@/vendor/liquid-glass/container.js')> | null = null
let lastSnapshotAt = 0

/** Loads the vendored liquid-glass-js Container (dashersw, MIT) and html2canvas-pro on demand. */
function loadGlass() {
  loading ??= (async () => {
    const [{ default: h2c }, mod] = await Promise.all([import('html2canvas-pro'), import('@/vendor/liquid-glass/container.js')])
    ;(window as unknown as { html2canvas: unknown }).html2canvas = h2c
    return mod
  })()
  return loading
}

/**
 * Wraps a surface with the liquid-glass refraction canvas from liquid-glass-js.
 * The host keeps its own layout, border and background (the CSS fallback); the canvas sits between
 * the background and the content, so text is never rendered through the shader.
 * Disabled for prefers-reduced-motion, without WebGL, or when `off` is set.
 */
export function LiquidGlass({ children, className, style, off = false, strength = 1, tint = 0.1 }: {
  children: ReactNode; className?: string; style?: CSSProperties; off?: boolean
  /** 0..1 canvas opacity over the CSS fallback (lower lets hatches / tints show through). */
  strength?: number; tint?: number
}) {
  const host = useRef<HTMLDivElement>(null)
  const reduced = usePrefersReducedMotion()
  const enabled = !off && !reduced && webglAvailable()

  useEffect(() => {
    if (!enabled) return
    const el = host.current
    if (!el) return
    let cancelled = false
    let canvas: HTMLCanvasElement | null = null
    const idle = (window as unknown as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback
    const start = async () => {
      try {
        const { Container } = await loadGlass()
        if (cancelled) return
        // Reuse a recent page snapshot; otherwise capture a fresh one so the refraction matches the current route.
        if (Date.now() - lastSnapshotAt > 4000) { Container.pageSnapshot = null; lastSnapshotAt = Date.now() }
        const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 12
        const c = new Container({ borderRadius: radius, type: 'rounded', tintOpacity: tint })
        // Adopt our host as the container element so React keeps owning the layout.
        c.element = el
        c.canvas.style.boxShadow = 'none'
        c.canvas.style.opacity = String(strength)
        c.canvas.style.pointerEvents = 'none'
        // Only the rim refracts: the interior stays the plain CSS surface so text contrast never depends on the page snapshot.
        const ring = 9
        const cs = c.canvas.style as CSSStyleDeclaration & Record<string, string>
        const m = { maskImage: 'linear-gradient(#000,#000),linear-gradient(#000,#000)', maskSize: `100% 100%,calc(100% - ${ring * 2}px) calc(100% - ${ring * 2}px)`, maskPosition: '0 0,center', maskRepeat: 'no-repeat', maskComposite: 'exclude' }
        for (const [k, v] of Object.entries(m)) { cs[k] = v; cs['Webkit' + k[0].toUpperCase() + k.slice(1)] = v }
        cs.WebkitMaskComposite = 'xor'
        canvas = c.canvas
        el.prepend(c.canvas)
        c.updateSizeFromDOM()
        const ro = new ResizeObserver(() => c.updateSizeFromDOM())
        ro.observe(el)
        const prevCleanup = cleanup
        cleanup = () => {
          prevCleanup(); ro.disconnect()
          const i = Container.instances.indexOf(c)
          if (i > -1) Container.instances.splice(i, 1)
        }
      } catch (e) {
        console.warn('[fx] liquid glass disabled:', (e as Error).message)
      }
    }
    let cleanup = () => {}
    // Let the route settle (and PDFs / images paint) before the one-off page snapshot.
    const t = window.setTimeout(() => { if (idle) idle(() => void start(), { timeout: 1500 }); else void start() }, 2000)
    return () => {
      cancelled = true
      window.clearTimeout(t)
      cleanup()
      canvas?.remove()
    }
  }, [enabled, strength, tint])

  return (
    // `glass-container` marks the host so the library excludes it from its page snapshot.
    <div ref={host} className={`glass-container ${className ?? ''}`} style={{ position: 'relative', isolation: 'isolate', ...style }}>
      {children}
    </div>
  )
}
