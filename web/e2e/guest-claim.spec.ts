import { execFileSync } from 'node:child_process'

import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

const INBOX = process.env.MAIL_INBOX_URL ?? 'http://localhost:8025'

/**
 * Serial, and desktop only.
 *
 * Unlike claim.spec.ts, which mocks the API, this exercises the real thing:
 * the point is that a claim survives signing up. The guest allowance and the
 * claims themselves are global state, so two of these running at once reset
 * each other mid-flight and race for the same place.
 */
test.describe.configure({ mode: 'serial' })
test.beforeEach(({ browserName }, testInfo) => {
  void browserName
  test.skip(testInfo.project.name !== 'desktop', 'shared server state')
})

/**
 * Three guest claims per address per day is correct in production and
 * untestable more than three times a day, so the run starts from nothing.
 */
function resetGuestState(): void {
  execFileSync('uv', ['run', 'python', 'scripts/reset_guest_state.py'], {
    cwd: '../api',
    encoding: 'utf8',
  })
}

/** An unclaimed place, so the run does not depend on what earlier runs took. */
async function unclaimedPlace(request: APIRequestContext): Promise<string> {
  const response = await request.get('/api/search?q=Dildo&limit=10')
  const { results } = (await response.json()) as {
    results: { name: string; claimed_by: string | null }[]
  }
  const free = results.find((place) => place.claimed_by === null)
  expect(free, 'every candidate place is already claimed').toBeTruthy()
  return free!.name
}

async function openPlace(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill(name)
  await page.getByRole('option', { name: new RegExp(name) }).first().click()
  await expect(page.getByLabel(/caption/i)).toBeVisible()
}

async function linkFromInbox(request: APIRequestContext, email: string): Promise<string> {
  const inbox = await request.get(`${INBOX}/api/v1/search?query=${encodeURIComponent(email)}`)
  const { messages } = (await inbox.json()) as { messages: { ID: string }[] }
  const body = await request.get(`${INBOX}/api/v1/message/${messages[0].ID}`)
  const link = /http:\/\/localhost:5173\/\?token=[\w-]+/.exec(
    ((await body.json()) as { Text: string }).Text,
  )
  expect(link, 'no sign-in link in the mail').toBeTruthy()
  return link![0]
}

test('a guest claims a place, is asked to keep it, and keeps it by signing up', async ({
  page,
  request,
  context,
}, testInfo) => {
  resetGuestState()
  await context.clearCookies()
  const name = await unclaimedPlace(request)

  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  await openPlace(page, name)

  await page.getByLabel(/caption/i).fill('Found it on a map and laughed.')
  await page.getByRole('button', { name: /stamp it/i }).click()

  // The stamp lands first. The ask waits for it.
  await expect(page.getByTestId('stamp')).toBeVisible()
  await expect(page.getByTestId('claim-countdown')).toContainText(/days left/i)

  const prompt = page.getByTestId('guest-prompt')
  await expect(prompt).toBeVisible()
  await expect(prompt).toContainText(name)
  await screenshot(page, testInfo, 'guest-prompt')

  // Signing up is what keeps it: the deadline goes, the claim stays.
  const email = `keeper-${Date.now()}@example.com`
  await prompt.getByRole('button', { name: /keep it/i }).click()
  await page.getByLabel(/email/i).fill(email)
  await page.getByRole('button', { name: /send/i }).click()

  await page.goto(await linkFromInbox(request, email))
  await expect(page.getByRole('button', { name: /^@/ })).toBeVisible()

  const mine = await page.request.get('/api/discoveries')
  const { discoveries } = (await mine.json()) as {
    discoveries: { place_name: string; expires_at: string | null }[]
  }
  const kept = discoveries.find((found) => found.place_name === name)
  expect(kept, 'the claim did not survive signing up').toBeTruthy()
  expect(kept!.expires_at, 'the deadline should be gone once it is an account').toBeNull()
})

test('dismissing the ask keeps the claim and leaves the deadline on screen', async ({
  page,
  request,
  context,
}, testInfo) => {
  resetGuestState()
  await context.clearCookies()
  const name = await unclaimedPlace(request)

  await page.goto('/')
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  await openPlace(page, name)

  await page.getByLabel(/caption/i).fill('Found it on a map and laughed.')
  await page.getByRole('button', { name: /stamp it/i }).click()
  await page.getByTestId('guest-prompt').getByRole('button', { name: /later/i }).click()

  await expect(page.getByTestId('guest-prompt')).toBeHidden()
  await expect(page.getByTestId('stamp')).toBeVisible()
  await expect(page.getByTestId('claim-countdown')).toContainText(/days left/i)
  await screenshot(page, testInfo, 'guest-dismissed')
})
