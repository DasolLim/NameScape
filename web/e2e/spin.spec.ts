import { expect, test } from '@playwright/test'

import { fractionChanged, samplePixels } from './helpers/pixels'

async function settledGlobe(page: import('@playwright/test').Page) {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  // Let the basemap finish loading so tiles cannot be mistaken for motion.
  await page.waitForTimeout(5000)
}

test('the globe drifts on its own, and stops the moment it is touched', async ({
  page,
  isMobile,
}) => {
  await settledGlobe(page)

  const before = await samplePixels(page)
  await page.waitForTimeout(2000)
  const drifting = fractionChanged(before, await samplePixels(page))
  expect(drifting).toBeGreaterThan(0.02)

  if (isMobile) {
    await page.touchscreen.tap(180, 380)
  } else {
    await page.mouse.move(640, 400)
    await page.mouse.down()
    await page.mouse.up()
  }
  await page.waitForTimeout(600)

  const stoppedA = await samplePixels(page)
  await page.waitForTimeout(1800)
  const stopped = fractionChanged(stoppedA, await samplePixels(page))

  expect(stopped).toBeLessThan(drifting / 5)
})

test('dragging rotates the globe, with no code of our own', async ({ page }) => {
  await settledGlobe(page)

  await page.mouse.move(640, 400)
  await page.mouse.down()
  await page.waitForTimeout(1200)

  const beforeDrag = await samplePixels(page)
  await page.mouse.move(320, 400, { steps: 20 })
  await page.mouse.up()
  await page.waitForTimeout(1200)

  expect(fractionChanged(beforeDrag, await samplePixels(page))).toBeGreaterThan(0.05)
})
