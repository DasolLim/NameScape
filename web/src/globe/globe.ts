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
  let frame: number | null = null

  function cancelFrame(): void {
    if (frame !== null) {
      cancelAnimationFrame(frame)
      frame = null
    }
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
      cancelFrame()
      const step = (): void => {
        frame = requestAnimationFrame(step)
      }
      frame = requestAnimationFrame(step)
    },

    stopIdleSpin(): void {
      cancelFrame()
    },

    destroy(): void {
      cancelFrame()
      tapHandlers.clear()
      map.remove()
    },
  }
}
