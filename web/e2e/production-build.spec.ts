import { expect, test } from '@playwright/test'

/**
 * Guards a class of bug the dev server cannot show you.
 *
 * MapLibre parses vector tiles and glyphs in a web worker that Vite does not
 * emit unless told to, and which the dev server serves out of node_modules
 * regardless. So a production build can render raster hillshade with white
 * oceans and no labels, report no error, and pass every other test here.
 *
 * Run against a built app:
 *   cd web && npm run build && npx vite preview --port 4173
 *   PREVIEW_URL=http://localhost:4173 npx playwright test e2e/production-build.spec.ts
 *
 * Also works against a deployment: PREVIEW_URL=https://… .
 */
const target = process.env.PREVIEW_URL

test.describe('a built app', () => {
  test.skip(!target, 'set PREVIEW_URL to a built app or a deployment')

  test('parses vector tiles and glyphs, not just raster', async ({ page }) => {
    let vector = 0
    let glyphs = 0
    page.on('response', (response) => {
      if (!response.url().includes('openfreemap')) return
      if (response.url().includes('/fonts/')) glyphs += 1
      else if (response.url().endsWith('.pbf')) vector += 1
    })

    await page.goto(target!, { waitUntil: 'load' })
    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible({ timeout: 30000 })
    await page.waitForTimeout(9000)

    expect(vector, 'no vector tiles: the map has no water and no borders').toBeGreaterThan(0)
    expect(glyphs, 'no glyph ranges: the map has no labels').toBeGreaterThan(0)
  })
})
