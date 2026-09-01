import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

test('renders the app and reports both services healthy, with no console errors', async ({
  page,
}, testInfo) => {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'NameScape' })).toBeVisible()
  // Healthy is the unremarkable case, so the chrome says nothing about it.
  await expect(page.getByTestId('health')).toHaveText('')

  await screenshot(page, testInfo, 'landing')
  expect(errors).toEqual([])
})
