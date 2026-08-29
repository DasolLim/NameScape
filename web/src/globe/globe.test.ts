import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const container = document.createElement('div')
let center = { lng: 0, lat: 20 }

const mapInstance = {
  on: vi.fn(),
  off: vi.fn(),
  remove: vi.fn(),
  flyTo: vi.fn(),
  getContainer: vi.fn(() => container),
  getCenter: vi.fn(() => center),
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
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

function newGlobe() {
  return createGlobe(document.createElement('div'))
}

test('the handle exposes exactly the six documented methods', () => {
  expect(Object.keys(newGlobe()).sort()).toEqual([
    'destroy',
    'focusOn',
    'onPlaceTap',
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

  container.dispatchEvent(new Event('mousedown'))
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
