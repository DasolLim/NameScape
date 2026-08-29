import { expect, test } from '@playwright/test'

import { screenshot } from './helpers/screenshot'

test('reading needs no account, but signing in is one tap away', async ({ page }, testInfo) => {
  await page.goto('/')

  // Everything readable is readable while anonymous.
  await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible()
  await page.getByRole('button', { name: /search places/i }).click()
  await page.getByRole('combobox').fill('Dildo')
  await expect(page.getByRole('option').first()).toContainText('Dildo')
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: /^sign in$/i }).click()
  const sheet = page.getByRole('dialog', { name: /sign in/i })

  await expect(sheet).toBeVisible()
  await expect(sheet.getByLabel(/email/i)).toBeVisible()
  await expect(sheet.getByText(/no password/i)).toBeVisible()
  await screenshot(page, testInfo, 'sign-in')

  // Unique per run: magic links are rate limited to 3 per email per hour, and
  // Redis keeps that count across runs and across both viewports.
  const email = `finder-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`
  await sheet.getByLabel(/email/i).fill(email)
  await sheet.getByRole('button', { name: /send me a link/i }).click()
  await expect(page.getByText(/check your email/i)).toBeVisible()
})
