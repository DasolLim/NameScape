import { execFileSync } from 'node:child_process'

import { expect, test } from '@playwright/test'

/** A real session for the seeded demo user, so this hits the real endpoints. */
function devSessionCookie(): string {
  return execFileSync('uv', ['run', 'python', 'scripts/dev_session.py', 'demo'], {
    cwd: '../api',
    encoding: 'utf8',
  }).trim()
}

test('a bookmark saves in one tap and survives a reload', async ({ page, context }) => {
  await context.addCookies([
    {
      name: 'toponomicon_session',
      value: devSessionCookie(),
      domain: 'localhost',
      path: '/',
    },
  ])

  await page.goto('/')
  // Both viewports share one dev database, so start from a known state.
  await page.evaluate(async () => {
    const response = await fetch('/api/bookmarks')
    const body = (await response.json()) as { bookmarks: { place_id: number }[] }
    await Promise.all(
      body.bookmarks.map((bookmark) =>
        fetch(`/api/bookmarks/${bookmark.place_id}`, { method: 'DELETE' }),
      ),
    )
  })
  await page.reload()
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Cockermouth')
  await page.getByRole('option').first().click()

  const star = page.getByRole('button', { name: /save this place/i })
  await expect(star).toBeVisible()
  await star.click()
  await expect(page.getByRole('button', { name: /saved/i })).toBeVisible()

  // Ask the API directly: the star is optimistic, the database is the truth.
  const saved = await page.evaluate(async () => {
    const response = await fetch('/api/bookmarks')
    return (await response.json()) as { bookmarks: { name: string }[] }
  })
  expect(saved.bookmarks.map((b) => b.name)).toContain('Cockermouth')

  await page.reload()
  const stillSaved = await page.evaluate(async () => {
    const response = await fetch('/api/bookmarks')
    return (await response.json()) as { bookmarks: { name: string }[] }
  })
  expect(stillSaved.bookmarks.map((b) => b.name)).toContain('Cockermouth')
})
