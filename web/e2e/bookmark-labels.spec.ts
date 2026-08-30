import { execFileSync } from 'node:child_process'

import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

function sessionFor(username: string): string {
  return execFileSync('uv', ['run', 'python', 'scripts/dev_session.py', username], {
    cwd: '../api',
    encoding: 'utf8',
  }).trim()
}

test('a bookmarked place is named on the globe, not just dotted', async ({
  page,
  context,
}, testInfo) => {
  // @voter, not @demo: the bookmarks spec clears @demo's saves and the two
  // run in parallel.
  await context.addCookies([
    { name: 'toponomicon_session', value: sessionFor('voter'), domain: 'localhost', path: '/' },
  ])

  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  // Own the state rather than depending on what the UI happens to show.
  const saved = await page.evaluate(async () => {
    const found = await (await fetch('/api/search?q=Cockermouth')).json()
    const place = (found.results as { id: number; name: string }[])[0]!
    await fetch(`/api/bookmarks/${place.id}`, { method: 'POST' })
    return place.name
  })
  expect(saved).toBe('Cockermouth')

  const settled = page.waitForResponse(
    (response) =>
      response.url().includes('/api/viewport') &&
      new URL(response.url()).searchParams.get('zoom') === '11' &&
      response.ok(),
  )
  await page.evaluate(() => {
    const globe = (
      globalThis as unknown as { __globe: { focusOn: (p: unknown, o: unknown) => void } }
    ).__globe
    // Offset east so Cockermouth sits left of the overlay panel, which
    // otherwise covers the centre of the viewport.
    globe.focusOn({ id: 'x', lon: -3.28, lat: 54.6624 }, { zoom: 11 })
  })
  const body = await (await settled).json()
  expect(body.bookmarks.map((bookmark: { name: string }) => bookmark.name)).toContain(
    'Cockermouth',
  )

  await page.waitForTimeout(3000)
  await screenshot(page, testInfo, 'bookmark-label')
})
