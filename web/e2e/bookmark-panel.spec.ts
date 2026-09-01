import { execFileSync } from 'node:child_process'

import { expect, test } from '@playwright/test'

function sessionFor(username: string): string {
  return execFileSync('uv', ['run', 'python', 'scripts/dev_session.py', username], {
    cwd: '../api',
    encoding: 'utf8',
  }).trim()
}

test('the Bookmarks control opens the list and flies to a choice', async ({ page, context }) => {
  await context.addCookies([
    { name: 'namescape_session', value: sessionFor('voter'), domain: 'localhost', path: '/' },
  ])
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  const saved = await page.evaluate(async () => {
    const found = await (await fetch('/api/search?q=Cockermouth')).json()
    const place = (found.results as { id: number; name: string }[])[0]!
    await fetch(`/api/bookmarks/${place.id}`, { method: 'POST' })
    return place.name
  })
  expect(saved).toBe('Cockermouth')

  await page.getByRole('button', { name: /^bookmarks$/i }).click()

  const panel = page.getByRole('region', { name: /bookmarks/i })
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('button', { name: /cockermouth/i })).toBeVisible()

  // Choosing an entry moves the camera, which the viewport refetch proves.
  const settled = page.waitForResponse(
    (response) => response.url().includes('/api/viewport') && response.ok(),
  )
  await panel.getByRole('button', { name: /cockermouth/i }).click()
  await settled

  // The globe layer can be switched off from inside the panel.
  const layerSwitch = panel.getByRole('switch', { name: /show on the globe/i })
  await expect(layerSwitch).toHaveAttribute('aria-checked', 'true')
  await layerSwitch.click()
  await expect(layerSwitch).toHaveAttribute('aria-checked', 'false')
})

test('a signed-out visitor is asked to sign in rather than shown an empty list', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  await page.getByRole('button', { name: /^bookmarks$/i }).click()

  await expect(page.getByRole('dialog', { name: /sign in/i })).toBeVisible()
  await expect(page.getByRole('region', { name: /bookmarks/i })).toBeHidden()
})
