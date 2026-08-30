import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

const BANDS = [
  { name: 'country', zoom: 2, center: [-40, 45] },
  { name: 'cluster', zoom: 6, center: [-53.5, 47.6] },
  { name: 'pin', zoom: 10, center: [-53.5442, 47.5766] },
] as const

test('each zoom band draws its own layer', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  await page.waitForTimeout(4000)

  for (const band of BANDS) {
    const requested = page.waitForResponse(
      (response) => response.url().includes('/api/viewport') && response.ok(),
    )
    await page.evaluate(
      ({ zoom, center }) => {
        const globe = (globalThis as unknown as { __globe: { focusOn: (p: unknown) => void } })
          .__globe
        globe.focusOn({ id: 'x', lon: center[0], lat: center[1] }, { zoom })
      },
      { zoom: band.zoom, center: band.center },
    )

    const body = await (await requested).json()
    expect(body.band).toBe(band.name)

    await page.waitForTimeout(2500)
    await screenshot(page, testInfo, `pins-${band.name}`)
  }
})
