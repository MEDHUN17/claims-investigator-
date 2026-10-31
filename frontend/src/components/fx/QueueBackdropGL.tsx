import { ShaderGradient, ShaderGradientCanvas } from '@shadergradient/react'

/** Quiet animated gradient in the graphite / teal / indigo / orchid palette. Default export for React.lazy. */
export default function QueueBackdropGL() {
  return (
    <ShaderGradientCanvas pixelDensity={1} fov={45} pointerEvents="none" lazyLoad={false} powerPreference="low-power" style={{ position: 'absolute', inset: 0 }}>
      <ShaderGradient
        control="props"
        type="waterPlane"
        animate="on"
        uTime={0}
        uSpeed={0.08}
        uStrength={1.6}
        uDensity={1.1}
        uFrequency={5.5}
        uAmplitude={0}
        color1="#1d3a44"
        color2="#2f3470"
        color3="#4b2f5c"
        lightType="3d"
        brightness={0.9}
        reflection={0.05}
        grain="off"
        cAzimuthAngle={170}
        cPolarAngle={90}
        cDistance={2.8}
        cameraZoom={9}
        positionX={0}
        positionY={0}
        positionZ={0}
        rotationX={50}
        rotationY={0}
        rotationZ={-60}
        enableTransition={false}
      />
    </ShaderGradientCanvas>
  )
}
