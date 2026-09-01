import { execFileSync } from 'node:child_process'

import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

function sessionFor(username: string): string {
  return execFileSync('uv', ['run', 'python', 'scripts/dev_session.py', username], {
    cwd: '../api',
    encoding: 'utf8',
  }).trim()
}

async function signIn(context: import('@playwright/test').BrowserContext, username: string) {
  await context.clearCookies()
  await context.addCookies([
    { name: 'namescape_session', value: sessionFor(username), domain: 'localhost', path: '/' },
  ])
}

// Distinct words, not a shared prefix with a suffix: proposals within 0.85
// trigram similarity are merged as near-duplicates, which would fold this
// run's nickname into the previous one.
const ADJECTIVES = ['Rueful', 'Sheepish', 'Wistful', 'Bashful', 'Sullen', 'Bemused']
const NOUNS = ['Headland', 'Narrows', 'Tickle', 'Gulch', 'Sound', 'Reach']

function distinctNickname(): string {
  const pick = <T,>(items: readonly T[]): T =>
    items[Math.floor(Math.random() * items.length)]!
  return `${pick(ADJECTIVES)} ${pick(NOUNS)} ${Math.floor(Math.random() * 9000) + 1000}`
}

test('a nickname can be proposed and voted on', async ({ page, context }, testInfo) => {
  // Two full sign-in-and-search cycles in one test: legitimately long, and
  // longer still when the rest of the suite is running beside it.
  test.slow()
  const nickname = distinctNickname()

  await signIn(context, 'demo')
  await page.goto('/')
  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Dull')
  await page.getByRole('option').first().click()

  const board = page.locator('section', { hasText: /nickname contest/i })
  await expect(board).toBeVisible()
  await board.getByLabel(/propose a nickname/i).fill(nickname)
  await board.getByLabel(/propose a nickname/i).press('Enter')

  await expect(board.getByText(nickname)).toBeVisible()
  await expect(page.getByTestId('countdown')).toContainText(/\d+h/)
  await screenshot(page, testInfo, 'contest-board')

  // The proposer cannot vote for themselves; a settled account can.
  await expect(board.getByRole('button', { name: new RegExp(`^agree with ${nickname}`, 'i') })).toBeDisabled()

  await signIn(context, 'voter')
  await page.reload()
  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Dull')
  await page.getByRole('option').first().click()

  const voterBoard = page.locator('section', { hasText: /nickname contest/i })
  await voterBoard.getByRole('button', { name: new RegExp(`^agree with ${nickname}`, 'i') }).click()

  await expect(voterBoard.getByRole('button', { name: new RegExp(`^agree with ${nickname}`, 'i') })).toContainText('1')
})
