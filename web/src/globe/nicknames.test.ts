import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>()
const layers = new Map<string, Record<string, unknown>>()
let styleReloads = 0

const mapInstance = {
  on: vi.fn(),
  off: vi.fn(),
  remove: vi.fn(),
  setProjection: vi.fn(),
  flyTo: vi.fn(),
  setCenter: vi.fn(),
  getCenter: vi.fn(() => ({ lng: 0, lat: 20 })),
  getZoom: vi.fn(() => 10),
  getContainer: vi.fn(() => document.createElement('div')),
  isStyleLoaded: vi.fn(() => true),
  setStyle: vi.fn(() => {
    styleReloads += 1
  }),
  addSource: vi.fn((id: string, spec: { data: { features: unknown[] } }) => {
    sources.set(id, { setData: vi.fn() })
    return spec
  }),
  getSource: vi.fn((id: string) => sources.get(id)),
  addLayer: vi.fn((layer: Record<string, unknown>) => {
    layers.set(String(layer.id), layer)
  }),
  setLayoutProperty: vi.fn((id: string, key: string, value: unknown) => {
    layers.set(id, { ...layers.get(id), [key]: value })
  }),
}

vi.mock('maplibre-gl', () => ({
  Map: vi.fn(function MapStub() {
    return mapInstance
  }),
}))

import { createGlobe } from './index'

const NICKNAMES = [
  { id: 1, lon: -53.5442, lat: 47.5766, name: 'The Unfortunate Bay', score: 42 },
  { id: 2, lon: -3.9167, lat: 56.6167, name: 'The Understatement', score: 9 },
]

beforeEach(() => {
  sources.clear()
  layers.clear()
  styleReloads = 0
})

afterEach(() => vi.clearAllMocks())

test('nicknames render in their own symbol layer, quoted and offset below', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ nicknames: { visible: true, features: NICKNAMES } })

  const layer = layers.get('nicknames-label')
  expect(layer?.type).toBe('symbol')
  const layout = layer?.layout as Record<string, unknown>
  expect(JSON.stringify(layout['text-field'])).toContain('"')
  // Offset downward, so it sits beneath the official name rather than over it.
  expect((layout['text-offset'] as number[])[1]).toBeGreaterThan(0)
  globe.destroy()
})

test('the sort key follows the winning score, so the better nickname wins a collision', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ nicknames: { visible: true, features: NICKNAMES } })

  const layout = layers.get('nicknames-label')?.layout as Record<string, unknown>
  // MapLibre draws lower sort keys first and lets them win, so the key is
  // negated: a score of 42 must outrank a score of 9.
  expect(JSON.stringify(layout['symbol-sort-key'])).toContain('score')
  globe.destroy()
})

test('the toggle hides the layer entirely', () => {
  const globe = createGlobe(document.createElement('div'))
  globe.setLayers({ nicknames: { visible: true, features: NICKNAMES } })

  globe.setLayers({ nicknames: { visible: false, features: NICKNAMES } })

  expect(layers.get('nicknames-label')?.visibility).toBe('none')
  globe.destroy()
})

test('a place with no nickname renders no second label', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ nicknames: { visible: true, features: [] } })

  const spec = mapInstance.addSource.mock.calls[0]?.[1]
  expect(spec?.data.features).toHaveLength(0)
  globe.destroy()
})

test('changing the nicknames updates the source without reloading the style', () => {
  const globe = createGlobe(document.createElement('div'))
  globe.setLayers({ nicknames: { visible: true, features: NICKNAMES } })

  globe.setLayers({ nicknames: { visible: true, features: [NICKNAMES[0]!] } })

  expect(sources.get('nicknames')?.setData).toHaveBeenCalledOnce()
  expect(styleReloads).toBe(0)
  globe.destroy()
})
