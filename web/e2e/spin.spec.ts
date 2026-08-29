import { expect, test } from '@playwright/test'

const canvasSelector = 'canvas.maplibregl-canvas'

test('the globe drifts on its own, and stops the moment it is touched', async ({ page }) => {
  await page.goto('/')
  const canvas = page.locator(canvasSelector)
  await expect(canvas).toBeVisible()

  // Let the basemap settle so tile loading cannot be mistaken for drift.
  await page.waitForTimeout(5000)

  const before = await canvas.screenshot()
  await page.waitForTimeout(2000)
  const after = await canvas.screenshot()
  expect(Buffer.compare(before, after)).not.toBe(0)

  await page.mouse.move(640, 400)
  await page.mouse.down()
  await page.mouse.up()
  await page.waitForTimeout(500)

  const stoppedA = await canvas.screenshot()
  await page.waitForTimeout(1500)
  const stoppedB = await canvas.screenshot()
  expect(Buffer.compare(stoppedA, stoppedB)).toBe(0)
})

test('dragging rotates the globe, with no code of our own', async ({ page }) => {
  await page.goto('/')
  const canvas = page.locator(canvasSelector)
  await expect(canvas).toBeVisible()
  await page.waitForTimeout(5000)

  await page.mouse.move(640, 400)
  await page.mouse.down()
  await page.waitForTimeout(1500)
  const beforeDrag = await canvas.screenshot()

  await page.mouse.move(300, 400, { steps: 20 })
  await page.mouse.up()
  await page.waitForTimeout(1200)

  const afterDrag = await canvas.screenshot()
  expect(Buffer.compare(beforeDrag, afterDrag)).not.toBe(0)
})
