import 'maplibre-gl/dist/maplibre-gl.css'

import { Map as MapLibreMap } from 'maplibre-gl'

import { applyLayer } from './layers'
import { BASEMAP_STYLE_URL } from './style'
import type {
  FocusOptions,
  GlobeHandle,
  GlobeOptions,
  LayerName,
  LayerState,
  PlaceRef,
  Unsubscribe,
  Viewport,
} from './types'

const SPIN_DEGREES_PER_SECOND = 4
const IDLE_RESUME_MS = 5_000
const INTERACTION_EVENTS = ['pointerdown', 'touchstart', 'wheel', 'keydown'] as const

const ZOOM_BY_FEATURE_CLASS: Record<'P' | 'H' | 'T', number> = {
  P: 11, // a town frames tight
  H: 9, // lakes and rivers need room around them
  T: 10,
}
const DEFAULT_FOCUS_ZOOM = 10

/**
 * Under globe projection the relationship between zoom and apparent planet
 * size is not the Mercator one, so adding a delta to the current zoom
 * overshoots when flying in from planet view. The target is always absolute
 * and never reads the current zoom.
 */
function resolveZoom(place: PlaceRef, options: FocusOptions): number {
  const byClass = place.featureClass
    ? ZOOM_BY_FEATURE_CLASS[place.featureClass]
    : DEFAULT_FOCUS_ZOOM
  return Math.min(Math.max(options.zoom ?? byClass, 0), 22)
}

function prefersReducedMotion(): boolean {
  return globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export function createGlobe(container: HTMLElement, options: GlobeOptions = {}): GlobeHandle {
  const map = new MapLibreMap({
    container,
    style: options.styleUrl ?? BASEMAP_STYLE_URL,
    center: options.center ?? [0, 20],
    zoom: options.zoom ?? 1.5,
    // Keeping the drawing buffer lets tests read the rendered frame back with
    // readPixels; without it the buffer is cleared after compositing. It costs
    // frame time, so production keeps the default.
    canvasContextAttributes: { preserveDrawingBuffer: import.meta.env.DEV },
  })

  // setProjection throws if called before the style loads, and a style served
  // from a URL cannot carry the projection, so it is set as soon as it is safe.
  let pendingLayers: LayerState | null = null

  map.on('style.load', () => {
    map.setProjection({ type: 'globe' })
    if (pendingLayers) {
      applyLayers(pendingLayers)
      pendingLayers = null
    }
  })

  function applyLayers(layers: LayerState): void {
    for (const [name, spec] of Object.entries(layers)) {
      if (spec) applyLayer(map, name as LayerName, spec)
    }
  }

  const tapHandlers = new Set<(placeId: string) => void>()
  const viewportHandlers = new Set<(viewport: Viewport) => void>()
  const element = map.getContainer()

  let frame: number | null = null
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  let lastFrameTime: number | null = null
  let spinRequested = false
  let destroyed = false
  let releaseActiveFocus: (() => void) | null = null

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

  map.on('moveend', () => {
    if (viewportHandlers.size === 0) return
    const bounds = map.getBounds()
    const viewport: Viewport = {
      west: bounds.getWest(),
      south: bounds.getSouth(),
      east: bounds.getEast(),
      north: bounds.getNorth(),
      zoom: Math.round(map.getZoom()),
    }
    for (const handler of [...viewportHandlers]) handler(viewport)
  })

  return {
    async focusOn(place: PlaceRef, focus: FocusOptions = {}): Promise<void> {
      if (destroyed) throw new Error('focusOn called on a destroyed globe')

      // A flight always wins over the drift; the user asked to go somewhere.
      spinRequested = false
      clearIdleTimer()
      cancelFrame()

      releaseActiveFocus?.()

      map.flyTo({
        center: [place.lon, place.lat],
        zoom: resolveZoom(place, focus),
        curve: 1.6,
        speed: 0.8,
        essential: true,
      })

      return new Promise<void>((resolve) => {
        const finish = (): void => {
          map.off('moveend', finish)
          if (releaseActiveFocus === finish) releaseActiveFocus = null
          resolve()
        }
        releaseActiveFocus = finish
        map.on('moveend', finish)
      })
    },

    setLayers(layers: LayerState): void {
      // Before style load there is nothing to add layers to; hold them.
      if (!map.isStyleLoaded()) {
        pendingLayers = { ...pendingLayers, ...layers }
        return
      }
      applyLayers(layers)
    },

    onPlaceTap(handler: (placeId: string) => void): Unsubscribe {
      tapHandlers.add(handler)
      return () => {
        tapHandlers.delete(handler)
      }
    },

    onViewportChange(handler: (viewport: Viewport) => void): Unsubscribe {
      viewportHandlers.add(handler)
      return () => {
        viewportHandlers.delete(handler)
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
      destroyed = true
      releaseActiveFocus?.()
      spinRequested = false
      clearIdleTimer()
      cancelFrame()
      for (const type of INTERACTION_EVENTS) {
        element.removeEventListener(type, onInteraction)
      }
      tapHandlers.clear()
      viewportHandlers.clear()
      map.remove()
    },
  }
}
