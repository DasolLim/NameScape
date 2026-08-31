import { expect, test, type Page } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

/**
 * The four tiers, side by side in a real browser.
 *
 * Routes are matched with anchored regexes, not globs. The dev server serves
 * the app's own modules from /src/api/, so an unanchored glob for the search
 * endpoint also matches src/api/search.ts and answers the app's own JavaScript
 * with JSON, which stops the page mounting at all.
 *
 * Stubbed rather than seeded: the point here is the visual treatment, and a
 * reader has to be able to tell a cited source from a model's guess at a
 * glance. That is a claim about pixels, so it is checked against pixels.
 */
const PLACE = {
  id: 1,
  geonames_id: 2_650_100,
  name: 'Ffynnongroyw',
  feature_class: 'P',
  feature_code: 'PPL',
  country_code: 'GB',
  tier: 3,
  lat: 53.3417,
  lon: -3.3167,
  claimed_by: null,
  bookmarked: false,
  eligibility: 'allowed',
  eligibility_reason: null,
  name_language: 'cy',
}

const TIERS = {
  sourced: {
    etymology: 'The name derives from the Welsh ffynnon groyw, meaning clear well.',
    etymology_confidence: 'high',
    etymology_source: 'https://en.wikipedia.org/wiki/Ffynnongroyw',
  },
  lexicon: {
    etymology: 'Ffynnongroyw begins with “-ffynnon”, a well or spring, from Welsh.',
    etymology_confidence: 'medium',
    etymology_source: 'lexicon:name_elements',
  },
  unverified: {
    etymology: 'Possibly a compound describing fresh water rising from the ground.',
    etymology_confidence: 'unverified',
    etymology_source: 'anthropic/claude-opus-5',
  },
  unknown: {
    etymology: null,
    etymology_confidence: 'unknown',
    etymology_source: null,
  },
}

async function openPlaceWith(page: Page, tier: keyof typeof TIERS): Promise<void> {
  await page.route(/\/api\/places\/1$/, (route) =>
    route.fulfill({ json: { ...PLACE, ...TIERS[tier] } }),
  )
  await page.route(/\/api\/search\?/, (route) =>
    route.fulfill({
      json: {
        results: [
          {
            id: 1,
            geonames_id: 2_650_100,
            name: 'Ffynnongroyw',
            feature_class: 'P',
            country_code: 'GB',
            admin1: 'Wales',
            lat: 53.3417,
            lon: -3.3167,
            claimed_by: null,
          },
        ],
      },
    }),
  )

  await page.goto('/')
  // The chrome, not the canvas: this spec is about a panel, and waiting on
  // several MapLibre instances booting at once only makes it flaky.
  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Ffynnongroyw')
  await page.getByRole('option', { name: /Ffynnongroyw/ }).first().click()
  await page.getByRole('button', { name: /what it actually means/i }).click()
  await expect(page.getByTestId('etymology')).toBeVisible()
}

for (const tier of ['sourced', 'lexicon', 'unverified', 'unknown'] as const) {
  test(`a ${tier} etymology is presented as what it is`, async ({ page }, testInfo) => {
    await openPlaceWith(page, tier)

    await screenshot(page, testInfo, `etymology-${tier}`)
  })
}

test('a sourced entry can be followed to its source', async ({ page }) => {
  await openPlaceWith(page, 'sourced')

  await expect(page.getByRole('link', { name: /source/i })).toHaveAttribute(
    'href',
    'https://en.wikipedia.org/wiki/Ffynnongroyw',
  )
})

test('a generated entry says in words that nobody checked it', async ({ page }) => {
  await openPlaceWith(page, 'unverified')

  const panel = page.getByTestId('etymology')
  await expect(panel).toContainText(/unverified/i)
  await expect(panel).toContainText(/language model/i)
  // Nothing to cite, so nothing that looks citable.
  await expect(panel.getByRole('link', { name: /source/i })).toHaveCount(0)
})

test('an English name in an English interface offers no reveal', async ({ page }) => {
  await page.route(/\/api\/places\/1$/, (route) =>
    route.fulfill({ json: { ...PLACE, name: 'Boring', name_language: 'en', ...TIERS.unknown } }),
  )
  await page.route(/\/api\/search\?/, (route) =>
    route.fulfill({
      json: {
        results: [
          {
            id: 1,
            geonames_id: 5_713_376,
            name: 'Boring',
            feature_class: 'P',
            country_code: 'US',
            admin1: 'Oregon',
            lat: 45.43,
            lon: -122.37,
            claimed_by: null,
          },
        ],
      },
    }),
  )

  await page.goto('/')
  // The chrome, not the canvas: this spec is about a panel, and waiting on
  // several MapLibre instances booting at once only makes it flaky.
  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Boring')
  await page.getByRole('option', { name: /Boring/ }).first().click()
  await expect(page.getByLabel(/caption/i)).toBeVisible()

  await expect(page.getByRole('button', { name: /what it actually means/i })).toHaveCount(0)
})
