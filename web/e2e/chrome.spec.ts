import { execFileSync } from 'node:child_process'

import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

/**
 * The bar is the only chrome that takes height from the globe, so it may not
 * wrap to a second row and may not push a control off the side, at any width.
 */
async function expectOneRow(page: import('@playwright/test').Page): Promise<void> {
  const bar = page.getByRole('banner')
  const box = (await bar.boundingBox())!
  expect(box.height).toBeLessThanOrEqual(64)

  const viewport = page.viewportSize()!
  for (const control of await bar.getByRole('button').all()) {
    const control_box = (await control.boundingBox())!
    expect(control_box.x).toBeGreaterThanOrEqual(0)
    expect(control_box.x + control_box.width).toBeLessThanOrEqual(viewport.width)
  }
}

function sessionFor(username: string): string {
  return execFileSync('uv', ['run', 'python', 'scripts/dev_session.py', username], {
    cwd: '../api',
    encoding: 'utf8',
  }).trim()
}

test('the chrome is a solid bar above the globe, legible over any basemap', async ({
  page,
}, testInfo) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  const bar = page.getByRole('banner')
  await expect(bar).toBeVisible()
  await expect(bar.getByText('NameScape')).toBeVisible()

  // The bar is opaque: its legibility cannot depend on what is under it,
  // which is the whole point of moving off the overlay.
  const alpha = await bar.evaluate((element) => {
    const parts = getComputedStyle(element)
      .backgroundColor.replace(/^rgba?\(|\)$/g, '')
      .split(',')
    // rgb() has no fourth component, which means fully opaque.
    return parts.length < 4 ? 1 : Number(parts[3])
  })
  expect(alpha).toBe(1)

  // And it does not sit on top of the map: the globe starts below it.
  const barBox = (await bar.boundingBox())!
  const canvasBox = (await page.locator('canvas.maplibregl-canvas').boundingBox())!
  expect(canvasBox.y).toBeGreaterThanOrEqual(barBox.y + barBox.height - 1)

  await expectOneRow(page)
  await screenshot(page, testInfo, 'chrome-anonymous')
})

test('a visitor who has been finding places sees their streak', async ({
  page,
  context,
}, testInfo) => {
  await context.addCookies([
    { name: 'namescape_session', value: sessionFor('demo'), domain: 'localhost', path: '/' },
  ])
  await page.goto('/')

  await expect(page.getByRole('button', { name: /@demo/ })).toBeVisible()
  await expect(page.getByTestId('streak')).toContainText(/\d/)
  await expectOneRow(page)
  await screenshot(page, testInfo, 'chrome-signed-in')
})

test('a visitor with nothing to their name is shown no streak, not a zero', async ({
  page,
  context,
}, testInfo) => {
  await context.addCookies([
    {
      name: 'namescape_session',
      value: sessionFor('unknownderek34'),
      domain: 'localhost',
      path: '/',
    },
  ])
  await page.goto('/')

  await expect(page.getByRole('button', { name: /@unknownderek34/ })).toBeVisible()
  await expect(page.getByTestId('streak')).toHaveCount(0)
  await screenshot(page, testInfo, 'chrome-no-streak')
})
