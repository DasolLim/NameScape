import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

const DILDO = { id: '1', lon: -53.5442, lat: 47.5766, featureClass: 'P' as const }

test('focusOn arcs to a place and lands framed on it', async ({ page }, testInfo) => {
  await page.goto('/')
  const canvas = page.locator('canvas.maplibregl-canvas')
  await expect(canvas).toBeVisible()
  await page.waitForTimeout(5000)

  await screenshot(page, testInfo, 'flyto-before')

  const flight = page.evaluate((place) => {
    const globe = (globalThis as unknown as { __globe: { focusOn: (p: unknown) => Promise<void> } })
      .__globe
    return globe.focusOn(place)
  }, DILDO)

  await page.waitForTimeout(900)
  await screenshot(page, testInfo, 'flyto-midflight')

  await flight
  await page.waitForTimeout(2500)
  await screenshot(page, testInfo, 'flyto-after')

  const before = await canvas.screenshot()
  await page.waitForTimeout(1200)
  const after = await canvas.screenshot()
  // The flight cancelled the idle spin, so the camera is now still.
  expect(Buffer.compare(before, after)).toBe(0)
})
