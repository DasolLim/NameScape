import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

test('the globe renders on a WebGL canvas', async ({ page }, testInfo) => {
  await page.goto('/')

  const canvas = page.locator('canvas.maplibregl-canvas')
  await expect(canvas).toBeVisible()

  // Give the basemap tiles a moment to paint before capturing.
  await page.waitForTimeout(4000)
  await screenshot(page, testInfo, 'globe')

  const size = await canvas.boundingBox()
  expect(size?.width).toBeGreaterThan(200)
})
