import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const container = document.createElement('div')
let center = { lng: 0, lat: 20 }
let currentZoom = 1.5

const listeners = new Map<string, Set<(...args: unknown[]) => void>>()

const mapInstance = {
  on: vi.fn((type: string, handler: (...args: unknown[]) => void) => {
    const set = listeners.get(type) ?? new Set()
    set.add(handler)
    listeners.set(type, set)
  }),
  off: vi.fn((type: string, handler: (...args: unknown[]) => void) => {
    listeners.get(type)?.delete(handler)
  }),
  emit(type: string) {
    for (const handler of [...(listeners.get(type) ?? [])]) handler()
  },
  remove: vi.fn(),
  flyTo: vi.fn(),
  getContainer: vi.fn(() => container),
  getCenter: vi.fn(() => center),
  getZoom: vi.fn(() => currentZoom),
  setCenter: vi.fn(([lng, lat]: [number, number]) => {
    center = { lng, lat }
  }),
}

vi.mock('maplibre-gl', () => ({
  // An arrow function cannot be used with `new`, so the stub is a plain function.
  Map: vi.fn(function MapStub() {
    return mapInstance
  }),
}))

import * as globeModule from './index'
import { createGlobe } from './index'

beforeEach(() => {
  center = { lng: 0, lat: 20 }
  currentZoom = 1.5
  listeners.clear()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

function newGlobe() {
  return createGlobe(document.createElement('div'))
}

test('the handle exposes exactly the seven documented methods', () => {
  expect(Object.keys(newGlobe()).sort()).toEqual([
    'destroy',
    'focusOn',
    'onPlaceTap',
    'onViewportChange',
    'setLayers',
    'startIdleSpin',
    'stopIdleSpin',
  ])
})

test('the module exports exactly one runtime value', () => {
  expect(Object.keys(globeModule)).toEqual(['createGlobe'])
})

test('idle spin advances the centre longitude at roughly 4 degrees a second', () => {
  const globe = newGlobe()

  globe.startIdleSpin()
  vi.advanceTimersByTime(1000)

  expect(center.lng).toBeGreaterThan(3.5)
  expect(center.lng).toBeLessThan(4.5)
  globe.destroy()
})

test('interaction cancels the spin immediately', () => {
  const globe = newGlobe()
  globe.startIdleSpin()
  vi.advanceTimersByTime(500)

  container.dispatchEvent(new Event('pointerdown'))
  const frozen = center.lng
  vi.advanceTimersByTime(1000)

  expect(center.lng).toBe(frozen)
  globe.destroy()
})

test('the spin resumes after five seconds of idle', () => {
  const globe = newGlobe()
  globe.startIdleSpin()
  container.dispatchEvent(new Event('wheel'))
  const frozen = center.lng

  vi.advanceTimersByTime(4000)
  expect(center.lng).toBe(frozen)

  vi.advanceTimersByTime(1500)
  expect(center.lng).toBeGreaterThan(frozen)
  globe.destroy()
})

test('stopIdleSpin halts the spin and does not resume it', () => {
  const globe = newGlobe()
  globe.startIdleSpin()
  vi.advanceTimersByTime(200)

  globe.stopIdleSpin()
  const frozen = center.lng
  vi.advanceTimersByTime(10_000)

  expect(center.lng).toBe(frozen)
  globe.destroy()
})

test('prefers-reduced-motion disables the spin entirely', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn() }))
  const globe = newGlobe()

  globe.startIdleSpin()
  vi.advanceTimersByTime(2000)

  expect(center.lng).toBe(0)
  globe.destroy()
  vi.unstubAllGlobals()
})

test('mounting and destroying twenty times leaves no spin loop running', () => {
  for (let i = 0; i < 20; i += 1) {
    const globe = newGlobe()
    globe.startIdleSpin()
    vi.advanceTimersByTime(100)
    globe.destroy()
  }

  expect(mapInstance.remove).toHaveBeenCalledTimes(20)

  const settled = mapInstance.setCenter.mock.calls.length
  vi.advanceTimersByTime(10_000)

  expect(mapInstance.setCenter.mock.calls.length).toBe(settled)
})


const DILDO = { id: '1', lon: -47.5, lat: 47.6, featureClass: 'P' } as const

test('focusOn resolves only once the camera movement completes', async () => {
  const globe = newGlobe()
  let settled = false

  const focus = globe.focusOn(DILDO).then(() => {
    settled = true
  })

  await Promise.resolve()
  expect(settled).toBe(false)

  mapInstance.emit('moveend')
  await focus

  expect(settled).toBe(true)
  globe.destroy()
})

test('focusOn flies with the documented arc and cancels idle spin', async () => {
  const globe = newGlobe()
  globe.startIdleSpin()
  vi.advanceTimersByTime(300)
  const frozen = center.lng

  const focus = globe.focusOn(DILDO)
  vi.advanceTimersByTime(2000)
  expect(center.lng).toBe(frozen)

  const options = mapInstance.flyTo.mock.calls[0]?.[0]
  expect(options).toMatchObject({ curve: 1.6, speed: 0.8, essential: true })

  mapInstance.emit('moveend')
  await focus
  globe.destroy()
})

test('a second focusOn supersedes the first without leaving it pending', async () => {
  const globe = newGlobe()

  const first = globe.focusOn(DILDO)
  const second = globe.focusOn({ id: '2', lon: 41, lat: 37.9, featureClass: 'P' })

  await first

  expect(mapInstance.flyTo).toHaveBeenCalledTimes(2)

  mapInstance.emit('moveend')
  await second
  globe.destroy()
})

test('target zoom is absolute, never a delta off the current zoom', async () => {
  const globe = newGlobe()

  await Promise.all([globe.focusOn(DILDO), Promise.resolve().then(() => mapInstance.emit('moveend'))])
  const fromGlobeView = mapInstance.flyTo.mock.calls[0]?.[0]?.zoom

  currentZoom = 14
  await Promise.all([globe.focusOn(DILDO), Promise.resolve().then(() => mapInstance.emit('moveend'))])
  const fromStreetView = mapInstance.flyTo.mock.calls[1]?.[0]?.zoom

  expect(fromStreetView).toBe(fromGlobeView)
  globe.destroy()
})

test('feature class picks the target zoom: a creek is not framed like a city', () => {
  const globe = newGlobe()

  void globe.focusOn({ id: 'p', lon: 0, lat: 0, featureClass: 'P' })
  void globe.focusOn({ id: 'h', lon: 0, lat: 0, featureClass: 'H' })

  const populated = mapInstance.flyTo.mock.calls[0]?.[0]?.zoom
  const hydro = mapInstance.flyTo.mock.calls[1]?.[0]?.zoom

  expect(populated).toBeGreaterThan(hydro)
  globe.destroy()
})

test('focusOn on a destroyed globe rejects rather than throwing', async () => {
  const globe = newGlobe()
  globe.destroy()

  await expect(globe.focusOn(DILDO)).rejects.toThrow(/destroyed/i)
})
