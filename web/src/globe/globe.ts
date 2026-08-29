import 'maplibre-gl/dist/maplibre-gl.css'

import { Map as MapLibreMap } from 'maplibre-gl'

import { BASEMAP_STYLE_URL } from './style'
import type {
  FocusOptions,
  GlobeHandle,
  GlobeOptions,
  LayerState,
  PlaceRef,
  Unsubscribe,
} from './types'

const SPIN_DEGREES_PER_SECOND = 4
const IDLE_RESUME_MS = 5_000
const INTERACTION_EVENTS = ['mousedown', 'touchstart', 'wheel', 'keydown'] as const

function prefersReducedMotion(): boolean {
  return globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export function createGlobe(container: HTMLElement, options: GlobeOptions = {}): GlobeHandle {
  const map = new MapLibreMap({
    container,
    style: options.styleUrl ?? BASEMAP_STYLE_URL,
    center: options.center ?? [0, 20],
    zoom: options.zoom ?? 1.5,
  })

  // setProjection throws if called before the style loads, and a style served
  // from a URL cannot carry the projection, so it is set as soon as it is safe.
  map.on('style.load', () => {
    map.setProjection({ type: 'globe' })
  })

  const tapHandlers = new Set<(placeId: string) => void>()
  const element = map.getContainer()

  let frame: number | null = null
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  let lastFrameTime: number | null = null
  let spinRequested = false

  function cancelFrame(): void {
    if (frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
    lastFrameTime = null
  }

  function clearIdleTimer(): void {
    if (idleTimer !== null) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  function tick(now: number): void {
    if (lastFrameTime !== null) {
      const seconds = (now - lastFrameTime) / 1000
      const { lng, lat } = map.getCenter()
      map.setCenter([lng + SPIN_DEGREES_PER_SECOND * seconds, lat])
    }
    lastFrameTime = now
    frame = requestAnimationFrame(tick)
  }

  function runSpin(): void {
    cancelFrame()
    frame = requestAnimationFrame(tick)
  }

  // Panning under globe projection is rotation, so dragging needs no code of
  // its own; it only has to stop the drift from fighting the user.
  function onInteraction(): void {
    cancelFrame()
    clearIdleTimer()
    if (spinRequested) idleTimer = setTimeout(runSpin, IDLE_RESUME_MS)
  }

  for (const type of INTERACTION_EVENTS) {
    element.addEventListener(type, onInteraction, { passive: true })
  }

  return {
    async focusOn(place: PlaceRef, focus: FocusOptions = {}): Promise<void> {
      map.flyTo({ center: [place.lon, place.lat], zoom: focus.zoom ?? 6 })
    },

    setLayers(_layers: LayerState): void {
      // Sources and layers arrive with the viewport module in step 15.
    },

    onPlaceTap(handler: (placeId: string) => void): Unsubscribe {
      tapHandlers.add(handler)
      return () => {
        tapHandlers.delete(handler)
      }
    },

    startIdleSpin(): void {
      if (prefersReducedMotion()) return
      spinRequested = true
      runSpin()
    },

    stopIdleSpin(): void {
      spinRequested = false
      clearIdleTimer()
      cancelFrame()
    },

    destroy(): void {
      spinRequested = false
      clearIdleTimer()
      cancelFrame()
      for (const type of INTERACTION_EVENTS) {
        element.removeEventListener(type, onInteraction)
      }
      tapHandlers.clear()
      map.remove()
    },
  }
}
