import { afterEach, expect, test, vi } from 'vitest'

const mapInstance = {
  on: vi.fn(),
  off: vi.fn(),
  remove: vi.fn(),
  flyTo: vi.fn(),
  setCenter: vi.fn(),
  getCenter: vi.fn(() => ({ lng: 0, lat: 20 })),
}

vi.mock('maplibre-gl', () => ({
  // An arrow function cannot be used with `new`, so the stub is a plain function.
  Map: vi.fn(function MapStub() {
    return mapInstance
  }),
}))

import * as globeModule from './index'
import { createGlobe } from './index'

afterEach(() => vi.clearAllMocks())

test('the handle exposes exactly the six documented methods', () => {
  const handle = createGlobe(document.createElement('div'))

  expect(Object.keys(handle).sort()).toEqual([
    'destroy',
    'focusOn',
    'onPlaceTap',
    'setLayers',
    'startIdleSpin',
    'stopIdleSpin',
  ])
})

test('the module exports exactly one runtime value', () => {
  const runtimeExports = Object.keys(globeModule)

  expect(runtimeExports).toEqual(['createGlobe'])
})

test('destroy removes the map and cancels a running animation frame', () => {
  const cancel = vi.spyOn(globalThis, 'cancelAnimationFrame')
  const handle = createGlobe(document.createElement('div'))
  handle.startIdleSpin()

  handle.destroy()

  expect(mapInstance.remove).toHaveBeenCalledOnce()
  expect(cancel).toHaveBeenCalled()
})
