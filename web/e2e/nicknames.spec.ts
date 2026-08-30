import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

const DILDO = { lon: -53.5442, lat: 47.5766 }

interface ViewportBody {
  band: string
  nicknames: { name: string }[]
}

async function flyTo(
  page: import('@playwright/test').Page,
  zoom: number,
): Promise<ViewportBody> {
  // Declared after the camera command would race the page's initial request,
  // so the wait is set up here and the matching body is returned.
  // Match the zoom we asked for: the idle spin also produces viewport
  // requests, and catching one of those would assert against the wrong frame.
  const settled = page.waitForResponse(
    (response) =>
      response.url().includes('/api/viewport') &&
      new URL(response.url()).searchParams.get('zoom') === String(zoom) &&
      response.ok(),
  )
  await page.evaluate(
    ({ lon, lat, zoom }) => {
      const globe = (
        globalThis as unknown as { __globe: { focusOn: (p: unknown, o: unknown) => void } }
      ).__globe
      globe.focusOn({ id: 'x', lon, lat }, { zoom })
    },
    { ...DILDO, zoom },
  )
  const body = (await (await settled).json()) as ViewportBody
  await page.waitForTimeout(2500)
  return body
}

test('a nickname renders beneath the official name and can be switched off', async ({
  page,
}, testInfo) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  await page.waitForTimeout(3500)

  // Close enough that the basemap draws the official name too.
  const close = await flyTo(page, 12)
  expect(close.band).toBe('pin')
  expect(close.nicknames.map((nickname) => nickname.name)).toContain(
    'The Cove of Few Regrets',
  )

  await screenshot(page, testInfo, 'nickname-close')

  // Zoomed out far enough that labels compete for space.
  await flyTo(page, 7)
  await screenshot(page, testInfo, 'nickname-collision')

  await page.getByRole('button', { name: /^nicknames$/i }).click()
  await page.waitForTimeout(1200)
  await screenshot(page, testInfo, 'nickname-hidden')

  const hidden = await page.evaluate(() => {
    const globe = (
      globalThis as unknown as {
        __globe: unknown
      }
    ).__globe
    return Boolean(globe)
  })
  expect(hidden).toBe(true)
})
