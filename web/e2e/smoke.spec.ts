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

  await expect(page.getByRole('heading', { name: 'Toponomicon' })).toBeVisible()
  await expect(page.getByTestId('health')).toHaveText('db ok · redis ok')

  await screenshot(page, testInfo, 'landing')
  expect(errors).toEqual([])
})
