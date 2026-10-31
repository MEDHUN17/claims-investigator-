import { useEffect, useState } from 'react'

let glCache: boolean | null = null
/** True when a WebGL context can be created. Cached; failures never throw. */
export function webglAvailable(): boolean {
  if (glCache !== null) return glCache
  try {
    const c = document.createElement('canvas')
    glCache = !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch { glCache = false }
  return glCache
}

export function usePrefersReducedMotion(): boolean {
  const [v, setV] = useState(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const mq = matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setV(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return v
}

/** Follows the app's data-theme attribute ('dark' default). */
export function useAppTheme(): 'dark' | 'light' {
  const read = () => (document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
  const [t, setT] = useState<'dark' | 'light'>(read)
  useEffect(() => {
    const mo = new MutationObserver(() => setT(read()))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return t
}

/** False while the browser tab is hidden. */
export function usePageVisible(): boolean {
  const [v, setV] = useState(() => !document.hidden)
  useEffect(() => {
    const on = () => setV(!document.hidden)
    document.addEventListener('visibilitychange', on)
    return () => document.removeEventListener('visibilitychange', on)
  }, [])
  return v
}

/** Tracks whether the element is currently on screen. */
export function useInView(ref: React.RefObject<Element | null>): boolean {
  const [v, setV] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') { setV(true); return }
    const io = new IntersectionObserver(([e]) => setV(e.isIntersecting), { threshold: 0.05 })
    io.observe(el)
    return () => io.disconnect()
  }, [ref])
  return v
}
