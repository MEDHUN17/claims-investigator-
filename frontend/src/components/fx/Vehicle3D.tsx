import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { ZoneView } from '@/types'
import { useAppTheme, useInView, usePageVisible, usePrefersReducedMotion } from './env'

const HUE = { narrative: '#8C93F5', photo: '#3FC1B0', estimate: '#6AA3D9' } as const
const DISCREPANCY = '#C77DDB'
const RING_R = { narrative: [0.3, 0.37], photo: [0.2, 0.27], estimate: [0.1, 0.17] } as const

// Vehicle faces +Z. "left"/"right" are the driver's left/right when facing forward (left = +X).
const S = Math.SQRT1_2
const ZONE: Record<string, { p: [number, number, number]; n: [number, number, number] }> = {
  front: { p: [0, 0.55, 2.04], n: [0, 0, 1] },
  front_left: { p: [0.8, 0.58, 1.78], n: [S, 0, S] },
  left: { p: [0.93, 0.62, 0], n: [1, 0, 0] },
  rear_left: { p: [0.8, 0.62, -1.78], n: [S, 0, -S] },
  rear: { p: [0, 0.62, -2.04], n: [0, 0, -1] },
  rear_right: { p: [-0.8, 0.62, -1.78], n: [-S, 0, -S] },
  right: { p: [-0.93, 0.62, 0], n: [-1, 0, 0] },
  front_right: { p: [-0.8, 0.58, 1.78], n: [-S, 0, S] },
  roof: { p: [0, 1.45, -0.28], n: [0, 1, 0] },
  underbody: { p: [0, 0.1, 0], n: [0, -1, 0] },
}

/** Side profile (x = length, y = height) of a low-poly hatchback. */
function profile(points: [number, number][]) {
  const s = new THREE.Shape()
  points.forEach(([x, y], i) => (i ? s.lineTo(x, y) : s.moveTo(x, y)))
  s.closePath()
  return s
}
function extrude(shape: THREE.Shape, depth: number) {
  const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false })
  g.translate(0, 0, -depth / 2)
  g.rotateY(-Math.PI / 2) // length -> +Z
  return g
}

function Car({ dark }: { dark: boolean }) {
  const body = useMemo(() => extrude(profile([[2.0, 0.3], [2.0, 0.62], [1.55, 0.78], [-1.85, 0.8], [-2.0, 0.62], [-2.0, 0.3]]), 1.72), [])
  const cabin = useMemo(() => extrude(profile([[1.0, 0.78], [0.45, 1.36], [-1.0, 1.4], [-1.8, 0.8]]), 1.5), [])
  const glass = useMemo(() => extrude(profile([[0.93, 0.8], [0.42, 1.3], [-0.95, 1.34], [-1.7, 0.82]]), 1.56), [])
  const roof = useMemo(() => new THREE.BoxGeometry(1.5, 0.05, 1.5), [])
  const wheel = useMemo(() => new THREE.CylinderGeometry(0.33, 0.33, 0.24, 14), [])
  const graphite = dark ? '#2b3441' : '#9aa1ab'
  const ivory = dark ? '#ece8df' : '#f6f1e6'
  return (
    <group>
      <mesh geometry={body}><meshStandardMaterial color={graphite} roughness={0.7} metalness={0.15} flatShading /></mesh>
      <mesh geometry={cabin}><meshStandardMaterial color={dark ? "#3a4452" : "#c9c2b0"} roughness={0.8} metalness={0.05} flatShading /></mesh>
      <mesh geometry={glass}><meshStandardMaterial color={dark ? '#0e1116' : '#2a3140'} roughness={0.25} metalness={0.4} transparent opacity={0.82} flatShading /></mesh>
      <mesh geometry={roof} position={[0, 1.4, -0.28]}><meshStandardMaterial color={ivory} roughness={0.8} flatShading /></mesh>
      {[[0.9, 1.25], [-0.9, 1.25], [0.9, -1.25], [-0.9, -1.25]].map(([x, z]) => (
        <mesh key={`${x}${z}`} geometry={wheel} position={[x, 0.33, z]} rotation={[0, 0, Math.PI / 2]}>
          <meshStandardMaterial color="#12161c" roughness={0.9} flatShading />
        </mesh>
      ))}
      {/* bumpers / sills: ivory trim */}
      <mesh position={[0, 0.34, 2.0]}><boxGeometry args={[1.72, 0.1, 0.06]} /><meshStandardMaterial color={ivory} /></mesh>
      <mesh position={[0, 0.34, -2.0]}><boxGeometry args={[1.72, 0.1, 0.06]} /><meshStandardMaterial color={ivory} /></mesh>
    </group>
  )
}

function ZoneRings({ id, sets }: { id: string; sets: Record<'narrative' | 'photo' | 'estimate', Set<string>> }) {
  const z = ZONE[id]
  const q = useMemo(() => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(...z.n)), [z])
  const keys = (['narrative', 'photo', 'estimate'] as const).filter((k) => sets[k].has(id))
  if (!keys.length) return null
  const off = new THREE.Vector3(...z.n).multiplyScalar(0.03)
  return (
    <group position={[z.p[0] + off.x, z.p[1] + off.y, z.p[2] + off.z]} quaternion={q}>
      {keys.map((k) => (
        <mesh key={k}>
          <ringGeometry args={[RING_R[k][0], RING_R[k][1], 40]} />
          <meshBasicMaterial color={HUE[k]} side={THREE.DoubleSide} transparent opacity={0.95} depthWrite={false} />
        </mesh>
      ))}
      <Html center position={[0, 0, 0.45]} style={{ pointerEvents: 'none' }}>
        <span className="mono whitespace-nowrap rounded bg-black/55 px-1 text-[9px] text-white/80">{id}</span>
      </Html>
    </group>
  )
}

/** One soft expanding ring, played once per mismatch state. Keeps the demand loop alive only while it animates. */
function PulseRing({ id, play }: { id: string; play: boolean }) {
  const z = ZONE[id]
  const mesh = useRef<THREE.Mesh>(null)
  const t0 = useRef<number | null>(null)
  const invalidate = useThree((s) => s.invalidate)
  const q = useMemo(() => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(...z.n)), [z])
  useEffect(() => { t0.current = null; if (play) invalidate() }, [play, invalidate])
  useFrame(({ clock }) => {
    const m = mesh.current
    if (!m) return
    if (!play) { m.visible = false; return }
    if (t0.current === null) t0.current = clock.elapsedTime
    const k = (clock.elapsedTime - t0.current) / 1.6
    if (k >= 1) { m.visible = false; return }
    m.visible = true
    const e = 1 - Math.pow(1 - k, 3)
    m.scale.setScalar(0.6 + e * 1.5)
    ;(m.material as THREE.MeshBasicMaterial).opacity = 0.55 * (1 - k)
    invalidate()
  })
  const off = new THREE.Vector3(...z.n).multiplyScalar(0.05)
  return (
    <group position={[z.p[0] + off.x, z.p[1] + off.y, z.p[2] + off.z]} quaternion={q}>
      <mesh ref={mesh} visible={false}>
        <ringGeometry args={[0.34, 0.4, 48]} />
        <meshBasicMaterial color={DISCREPANCY} side={THREE.DoubleSide} transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  )
}

function Scene({ zones, dark }: { zones: ZoneView; dark: boolean }) {
  const sets = useMemo(() => ({ narrative: new Set(zones.narrative), photo: new Set(zones.photo), estimate: new Set(zones.estimate) }), [zones])
  const pulse = useMemo(() => {
    if (!zones.mismatch) return [] as string[]
    const all = new Set([...zones.narrative, ...zones.photo, ...zones.estimate])
    return [...all].filter((z) => ZONE[z] && !(sets.narrative.has(z) && sets.photo.has(z) && sets.estimate.has(z)))
  }, [zones, sets])
  const grid = useRef<THREE.GridHelper>(null)
  useEffect(() => {
    const m = grid.current?.material
    ;(Array.isArray(m) ? m : m ? [m] : []).forEach((x) => { x.transparent = true; x.opacity = dark ? 0.55 : 0.5 })
  }, [dark])
  return (
    <>
      <ambientLight intensity={dark ? 0.9 : 1.1} />
      <hemisphereLight args={[dark ? '#cfd8e6' : '#ffffff', '#1a1f27', 0.6]} />
      <directionalLight position={[4, 6, 3]} intensity={1.6} />
      <directionalLight position={[-4, 3, -4]} intensity={0.5} color="#8c93f5" />
      <gridHelper ref={grid} args={[12, 24, dark ? '#3a4452' : '#b9b09b', dark ? '#262e3a' : '#d8cfba']} />
      <Car dark={dark} />
      {Object.keys(ZONE).map((id) => <ZoneRings key={id} id={id} sets={sets} />)}
      {pulse.map((id) => <PulseRing key={`${id}-${zones.note}`} id={id} play />)}
      <OrbitControls makeDefault enablePan={false} enableDamping dampingFactor={0.12} minPolarAngle={Math.PI * 0.2} maxPolarAngle={Math.PI * 0.49} minDistance={5} maxDistance={9} />
    </>
  )
}

/** 3D low-poly hatchback with zone rings. Illustrative only. Default export for React.lazy. */
export default function Vehicle3D({ zones }: { zones: ZoneView }) {
  const wrap = useRef<HTMLDivElement>(null)
  const inView = useInView(wrap)
  const pageVisible = usePageVisible()
  const reduced = usePrefersReducedMotion()
  const theme = useAppTheme()
  const [ctxLost, setCtxLost] = useState(false)
  const mounted = inView && pageVisible && !ctxLost
  const unknown = [...zones.narrative, ...zones.photo, ...zones.estimate].includes('unknown')
  return (
    <div ref={wrap} className="relative mx-auto aspect-[10/9] w-full max-w-[420px] overflow-hidden rounded-md border border-line-soft" style={{ background: 'color-mix(in srgb, var(--bg) 70%, transparent)' }}>
      {mounted && (
        <Canvas
          frameloop="demand"
          dpr={[1, 1.5]}
          camera={{ position: [4.6, 3.1, 5.6], fov: 38 }}
          gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }}
          onCreated={({ gl }) => gl.domElement.addEventListener('webglcontextlost', (e) => { e.preventDefault(); setCtxLost(true) })}
          aria-label="Illustrative 3D vehicle with damage zone rings"
        >
          <Scene zones={reduced ? { ...zones, mismatch: false } : zones} dark={theme === 'dark'} />
        </Canvas>
      )}
      {ctxLost && <div className="absolute inset-0 grid place-items-center p-3 text-center text-xs text-ink-3">3D view paused (graphics context lost). Switch to the 2D blueprint.</div>}
      <div className="pointer-events-none absolute left-2 top-1.5 text-[10px] uppercase tracking-widest text-ink-3">drag to orbit</div>
      <div className="pointer-events-none absolute bottom-1.5 left-2 text-[10px] text-ink-3">Illustrative, not physics</div>
      {unknown && <div className="pointer-events-none absolute bottom-1.5 right-2 text-[10px] text-ink-3">zone &ldquo;unknown&rdquo; has no 3D location</div>}
    </div>
  )
}
