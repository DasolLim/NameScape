import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const sources = new Map<string, { setData: ReturnType<typeof vi.fn> }>()
const layers = new Map<string, Record<string, unknown>>()
const listeners = new Map<string, Set<() => void>>()
let styleLoaded = true

const mapInstance = {
  on: vi.fn((type: string, handler: () => void) => {
    const set = listeners.get(type) ?? new Set()
    set.add(handler)
    listeners.set(type, set)
  }),
  off: vi.fn(),
  emit(type: string) {
    for (const handler of [...(listeners.get(type) ?? [])]) handler()
  },
  remove: vi.fn(),
  setProjection: vi.fn(),
  setSky: vi.fn(),
  flyTo: vi.fn(),
  setCenter: vi.fn(),
  getCenter: vi.fn(() => ({ lng: 0, lat: 20 })),
  getZoom: vi.fn(() => 10),
  getContainer: vi.fn(() => document.createElement('div')),
  isStyleLoaded: vi.fn(() => styleLoaded),
  addSource: vi.fn((id: string) => {
    sources.set(id, { setData: vi.fn() })
  }),
  getSource: vi.fn((id: string) => sources.get(id)),
  addLayer: vi.fn((layer: Record<string, unknown>) => {
    layers.set(String(layer.id), layer)
  }),
  getLayer: vi.fn((id: string) => layers.get(id)),
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

beforeEach(() => {
  sources.clear()
  layers.clear()
  listeners.clear()
  styleLoaded = true
})

afterEach(() => vi.clearAllMocks())

const PINS = [
  { id: 1, lon: -53.5442, lat: 47.5766, name: 'Dildo' },
  { id: 2, lon: -122.3751, lat: 45.4265, name: 'Boring' },
]

test('setLayers adds a GeoJSON source and draws pins with a glow beneath', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ discoveries: { visible: true, features: PINS } })

  expect(sources.has('discoveries')).toBe(true)
  // Glow must be added before the pin so it renders underneath.
  const added = mapInstance.addLayer.mock.calls.map((call) => String(call[0].id))
  expect(added.indexOf('discoveries-glow')).toBeLessThan(added.indexOf('discoveries-pin'))
  globe.destroy()
})

test('pins are drawn by the GPU, never as DOM markers', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ discoveries: { visible: true, features: PINS } })

  for (const layer of layers.values()) {
    expect(['circle', 'symbol']).toContain(layer.type)
  }
  expect(document.querySelectorAll('.maplibregl-marker')).toHaveLength(0)
  globe.destroy()
})

test('a second call updates the data instead of re-adding the layers', () => {
  const globe = createGlobe(document.createElement('div'))
  globe.setLayers({ discoveries: { visible: true, features: PINS } })
  const addedFirst = mapInstance.addLayer.mock.calls.length

  globe.setLayers({ discoveries: { visible: true, features: [PINS[0]!] } })

  expect(mapInstance.addLayer.mock.calls.length).toBe(addedFirst)
  expect(sources.get('discoveries')?.setData).toHaveBeenCalled()
  globe.destroy()
})

test('hiding a layer sets its visibility rather than removing it', () => {
  const globe = createGlobe(document.createElement('div'))
  globe.setLayers({ discoveries: { visible: true, features: PINS } })

  globe.setLayers({ discoveries: { visible: false, features: PINS } })

  expect(mapInstance.setLayoutProperty).toHaveBeenCalledWith(
    'discoveries-pin',
    'visibility',
    'none',
  )
  globe.destroy()
})

test('bookmarks draw in their own layer', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ bookmarks: { visible: true, features: PINS } })

  expect(sources.has('bookmarks')).toBe(true)
  expect(layers.has('bookmarks-pin')).toBe(true)
  globe.destroy()
})

test('a bookmarked place shows its name, not just a dot', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ bookmarks: { visible: true, features: PINS } })

  const label = layers.get('bookmarks-label')
  expect(label?.type).toBe('symbol')
  const layout = label?.layout as Record<string, unknown>
  expect(JSON.stringify(layout['text-field'])).toContain('name')
  globe.destroy()
})

test('hiding bookmarks hides their labels too', () => {
  const globe = createGlobe(document.createElement('div'))
  globe.setLayers({ bookmarks: { visible: true, features: PINS } })

  globe.setLayers({ bookmarks: { visible: false, features: PINS } })

  expect(layers.get('bookmarks-label')?.visibility).toBe('none')
  expect(layers.get('bookmarks-pin')?.visibility).toBe('none')
  globe.destroy()
})

test('discovery pins stay unlabelled, so the map does not double up names', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ discoveries: { visible: true, features: PINS } })

  expect(layers.has('discoveries-label')).toBe(false)
  globe.destroy()
})

test('clusters carry their count for the label', () => {
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({
    clusters: { visible: true, features: [{ id: 1, lon: 0, lat: 0, count: 42 }] },
  })

  expect(layers.get('clusters-count')?.type).toBe('symbol')
  globe.destroy()
})

test('layers requested before the style loads are applied once it does', () => {
  styleLoaded = false
  const globe = createGlobe(document.createElement('div'))

  globe.setLayers({ discoveries: { visible: true, features: PINS } })
  expect(sources.has('discoveries')).toBe(false)

  styleLoaded = true
  mapInstance.emit('style.load')

  expect(sources.has('discoveries')).toBe(true)
  globe.destroy()
})
