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
    { name: 'toponomicon_session', value: sessionFor(username), domain: 'localhost', path: '/' },
  ])
}

test('a nickname can be proposed and voted on', async ({ page, context }, testInfo) => {
  const nickname = `The Unfortunate Bay ${Date.now()}`

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
