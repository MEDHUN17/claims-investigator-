export interface ContainerOptions { borderRadius?: number; type?: 'rounded' | 'circle' | 'pill'; tintOpacity?: number }
export class Container {
  static instances: Container[]
  static pageSnapshot: HTMLCanvasElement | null
  static isCapturing: boolean
  static waitingForSnapshot: Container[]
  constructor(options?: ContainerOptions)
  width: number
  height: number
  element: HTMLElement
  canvas: HTMLCanvasElement
  webglInitialized: boolean
  updateSizeFromDOM(): void
}
