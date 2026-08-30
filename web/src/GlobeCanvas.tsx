import { useEffect, useRef } from 'react'

import { createGlobe, type GlobeHandle } from './globe'

interface GlobeCanvasProps {
  onReady?: (globe: GlobeHandle) => void
}

export default function GlobeCanvas({ onReady }: GlobeCanvasProps) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = container.current
    if (!element) return

    const globe = createGlobe(element)
    globe.startIdleSpin()
    onReady?.(globe)

    // Dev-only handle so end-to-end tests can drive the camera. Stripped from
    // production builds.
    if (import.meta.env.DEV) {
      ;(globalThis as unknown as { __globe?: GlobeHandle }).__globe = globe
    }

    return () => globe.destroy()
  }, [onReady])

  // Inline, not a utility class: maplibre-gl.css sets `.maplibregl-map
  // { position: relative }` and loads after Tailwind, so it wins on classes.
  return (
    <div
      ref={container}
      data-testid="globe"
      style={{ position: 'absolute', inset: 0, background: 'transparent' }}
    />
  )
}
