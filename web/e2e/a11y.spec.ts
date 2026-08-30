import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

const MIN_TAP_TARGET = 44

test('the landing view has no serious accessibility violations', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    // The basemap canvas and MapLibre's own attribution are third-party markup.
    .exclude('.maplibregl-control-container')
    .analyze()

  const serious = results.violations.filter((violation) =>
    ['serious', 'critical'].includes(violation.impact ?? ''),
  )
  expect(serious.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([])
})

test('the sign-in sheet has no serious violations either', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /^sign in$/i }).click()
  await expect(page.getByRole('dialog', { name: /sign in/i })).toBeVisible()

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .exclude('.maplibregl-control-container')
    .analyze()

  const serious = results.violations.filter((violation) =>
    ['serious', 'critical'].includes(violation.impact ?? ''),
  )
  expect(serious.map((violation) => `${violation.id}: ${violation.help}`)).toEqual([])
})

test('every control meets the 44px tap target minimum', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  const controls = page.locator('main button:visible')
  const undersized: string[] = []

  for (const control of await controls.all()) {
    const box = await control.boundingBox()
    const label = (await control.textContent())?.trim() ?? '?'
    if (box && (box.height < MIN_TAP_TARGET || box.width < MIN_TAP_TARGET)) {
      undersized.push(`${label} ${Math.round(box.width)}x${Math.round(box.height)}`)
    }
  }

  expect(undersized).toEqual([])
})

test('the globe can be panned and zoomed from the keyboard', async ({ page }) => {
  await page.goto('/')
  const canvas = page.locator('canvas.maplibregl-canvas')
  await expect(canvas).toBeVisible()
  await page.waitForTimeout(4000)

  await canvas.focus()
  const before = await page.evaluate(() => {
    const globe = (globalThis as unknown as { __globe: unknown }).__globe
    return Boolean(globe)
  })
  expect(before).toBe(true)

  const settled = page.waitForResponse(
    (response) => response.url().includes('/api/viewport') && response.ok(),
  )
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Equal')
  await settled
})

test('the layout survives 200% text scaling', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
  await page.waitForTimeout(500)

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})
