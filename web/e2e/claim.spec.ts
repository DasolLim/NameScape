import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

test('the stamp lands and credits the first finder', async ({ page }, testInfo) => {
  // The claim sheet is driven directly here: the sign-in round trip needs a
  // mailbox, and the API's own tests already cover the claim pipeline.
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({ json: { username: 'firstfinder' } }),
  )
  await page.route('**/api/places/*', (route) =>
    route.fulfill({
      json: {
        id: 1,
        geonames_id: 6942553,
        name: 'Dildo',
        feature_class: 'P',
        feature_code: 'PPL',
        country_code: 'CA',
        tier: 3,
        lat: 47.5766,
        lon: -53.5442,
        etymology: null,
        claimed_by: null,
        bookmarked: false,
        eligibility: 'allowed',
        eligibility_reason: null,
      },
    }),
  )
  await page.route('**/api/discoveries', (route) =>
    route.fulfill({
      status: 201,
      json: { id: 7, place_id: 1, finder: 'firstfinder', caption: 'Found it on a map.' },
    }),
  )

  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()

  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Dildo')
  await page.getByRole('option').first().click()

  await page.getByLabel(/caption/i).fill('Found it on a map, laughed for a minute.')
  await screenshot(page, testInfo, 'claim-sheet')

  await page.getByRole('button', { name: /stamp it/i }).click()

  const stamp = page.getByTestId('stamp')
  await expect(stamp).toBeVisible()
  await expect(stamp.getByText(/first finder/i)).toBeVisible()
  await expect(stamp.getByText('@firstfinder')).toBeVisible()
  await page.waitForTimeout(600)
  await screenshot(page, testInfo, 'stamp')
})
