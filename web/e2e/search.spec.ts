import { expect, test } from '@playwright/test'

import { fractionChanged, samplePixels } from './helpers/pixels'
import { screenshot } from './helpers/screenshot'

test('searching a place flies the globe to it', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  await page.waitForTimeout(5000)

  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Dildo')

  const option = page.getByRole('option').first()
  await expect(option).toContainText('Dildo')
  await expect(option).toContainText('CA')
  await screenshot(page, testInfo, 'search-results')

  const before = await samplePixels(page)
  await option.click()
  await page.waitForTimeout(4000)

  expect(fractionChanged(before, await samplePixels(page))).toBeGreaterThan(0.2)
  await screenshot(page, testInfo, 'search-landed')
})
