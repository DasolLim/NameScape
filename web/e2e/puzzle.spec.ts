import { execFileSync } from 'node:child_process'

import { expect, test, type Page } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

/**
 * Serial and desktop only, like the guest claim spec: this drives the real API,
 * and a puzzle plus its attempts are global state that two runs would fight
 * over.
 */
test.describe.configure({ mode: 'serial' })
test.beforeEach(({ browserName }, testInfo) => {
  void browserName
  test.skip(testInfo.project.name !== 'desktop', 'shared server state')
})

/** A live puzzle on today's date, and no attempts at it. */
function seedPuzzle(): string {
  const output = execFileSync('uv', ['run', 'python', 'scripts/seed_puzzle.py'], {
    cwd: '../api',
    encoding: 'utf8',
  })
  const named = /puzzle for [\d-]+: (.+) \(/.exec(output)
  expect(named, `could not read the seeded place from:\n${output}`).toBeTruthy()
  return named![1]!
}

function resetGuestState(): void {
  execFileSync('uv', ['run', 'python', 'scripts/reset_guest_state.py'], {
    cwd: '../api',
    encoding: 'utf8',
  })
}

async function openPuzzle(page: Page): Promise<void> {
  await page.goto('/')
  await page.getByRole('button', { name: /today.s place/i }).click()
  await expect(page.getByTestId('puzzle')).toBeVisible()
}

async function guessPlace(page: Page, name: string): Promise<void> {
  const panel = page.getByTestId('puzzle')
  await panel.getByLabel(/your guess/i).fill(name)
  await panel.getByRole('option').filter({ hasText: name }).first().click()
}

test('a visitor plays the puzzle, solves it, and claims the place', async ({
  page,
  context,
}, testInfo) => {
  test.slow()
  resetGuestState()
  await context.clearCookies()
  const answer = seedPuzzle()

  await openPuzzle(page)
  const panel = page.getByTestId('puzzle')

  // One clue to begin with, and nothing else given away.
  await expect(panel.getByTestId('clue-0')).toBeVisible()
  await expect(panel.getByTestId('clue-1')).toHaveCount(0)
  await expect(panel).toContainText(/5 guesses left/i)
  await screenshot(page, testInfo, 'puzzle-opening')

  // A wrong guess buys a clue and reports how far off it was.
  await guessPlace(page, 'Sydney')
  const wrong = panel.getByTestId('guess-0')
  await expect(wrong).toContainText(/km/)
  await expect(panel.getByTestId('clue-1')).toBeVisible()
  await expect(panel).toContainText(/4 guesses left/i)
  await screenshot(page, testInfo, 'puzzle-one-wrong')

  // And the first clue is still there: the ladder accumulates.
  await expect(panel.getByTestId('clue-0')).toBeVisible()

  await guessPlace(page, answer)
  await expect(panel).toContainText(/solved/i)
  await expect(panel.getByTestId('puzzle-answer')).toHaveText(answer)
  await screenshot(page, testInfo, 'puzzle-solved')

  // Solving offers the place, and claiming it leaves a real discovery.
  await panel.getByRole('button', { name: /claim it/i }).click()
  await page.getByLabel(/caption/i).fill('Found it by guessing what its name meant.')
  await page.getByRole('button', { name: /stamp it/i }).click()
  await expect(page.getByTestId('stamp')).toBeVisible()

  const mine = await page.request.get('/api/discoveries')
  const { discoveries } = (await mine.json()) as { discoveries: { place_name: string }[] }
  expect(discoveries.map((found) => found.place_name)).toContain(answer)
})

test('the share grid pastes into a plain text field as it was written', async ({
  page,
  context,
}, testInfo) => {
  test.slow()
  resetGuestState()
  await context.clearCookies()
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const answer = seedPuzzle()

  await openPuzzle(page)
  await guessPlace(page, answer)
  await page.getByTestId('puzzle').getByRole('button', { name: /share/i }).click()
  await expect(page.getByText(/copied/i)).toBeVisible()

  const copied = await page.evaluate(() => navigator.clipboard.readText())

  // The format from the addendum, and nothing that spoils the answer.
  expect(copied).toMatch(/^Toponomicon #\d+ · 1\/5/)
  expect(copied).toContain('🟩')
  expect(copied).toContain('toponomicon.app')
  expect(copied).not.toContain(answer)

  // Pasted where it will actually be used: a plain textarea, no markup, no
  // styling, nothing to interpret the emoji but the font.
  await page.evaluate((text) => {
    const field = document.createElement('textarea')
    field.id = 'paste-target'
    field.value = text
    field.rows = 5
    field.style.cssText =
      'position:fixed;left:24px;top:96px;width:420px;font:14px monospace;' +
      'background:#0e131c;color:#f5f1e8;border:1px solid #2b3646;padding:12px;'
    document.body.append(field)
  }, copied)

  await expect(page.locator('#paste-target')).toHaveValue(copied)
  await screenshot(page, testInfo, 'puzzle-grid-pasted')
})
