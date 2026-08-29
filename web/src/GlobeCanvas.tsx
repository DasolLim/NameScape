import { useEffect, useRef } from 'react'

import { createGlobe } from './globe'

export default function GlobeCanvas() {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = container.current
    if (!element) return

    const globe = createGlobe(element)
    return () => globe.destroy()
  }, [])

  // Inline, not a utility class: maplibre-gl.css sets `.maplibregl-map
  // { position: relative }` and loads after Tailwind, so it wins on classes.
  return (
    <div ref={container} data-testid="globe" style={{ position: 'absolute', inset: 0 }} />
  )
}
