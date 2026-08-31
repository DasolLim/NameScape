import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { useAuth } from './auth/store'
import { server } from './test/setup'

// jsdom has no WebGL; the globe module has its own tests.
vi.mock('./globe', () => ({
  createGlobe: () => ({
    focusOn: vi.fn(),
    setLayers: vi.fn(),
    onPlaceTap: vi.fn(),
    onViewportChange: vi.fn(() => () => undefined),
    startIdleSpin: vi.fn(),
    stopIdleSpin: vi.fn(),
    destroy: vi.fn(),
  }),
}))

import App from './App'

beforeEach(() => {
  useAuth.setState({ user: null, status: 'anonymous', signInOpen: false, linkSent: false })
  server.use(
    http.get('/api/activity', () =>
      HttpResponse.json({ contests_closing_soon: 0, streak_days: null, streak_at_risk: false }),
    ),
  )
})

test('the chrome names the product rather than reporting the database', async () => {
  render(<App />)

  expect(await screen.findByText('Toponomicon')).toBeVisible()
  expect(screen.getByText(/atlas of absurd place names/i)).toBeVisible()
  // A health readout is operator information, not the product's subtitle.
  expect(screen.queryByText(/redis/i)).not.toBeInTheDocument()
  expect(screen.getByTestId('health')).toBeEmptyDOMElement()
})

test('a degraded service says so quietly, without shouting on the wordmark', async () => {
  server.use(
    http.get('/api/health', () =>
      HttpResponse.json({ status: 'degraded', db: true, redis: false }),
    ),
  )
  render(<App />)

  await waitFor(() =>
    expect(screen.getByTestId('health')).toHaveTextContent(/service degraded/i),
  )
})

test('the chrome sits above the globe rather than floating on it', async () => {
  render(<App />)

  const bar = await screen.findByRole('banner')
  const globe = screen.getByTestId('globe')

  // Siblings in the layout, not one stacked over the other: this is the
  // separation the old overlay lacked.
  expect(bar.contains(globe)).toBe(false)
  expect(bar.className).toMatch(/bg-ink-950/)
})


test('a signed-out visitor reaches the claim form, not a sign-in wall', async () => {
  const user = userEvent.setup()
  server.use(
    http.get('/api/search', () =>
      HttpResponse.json({
        results: [
          {
            id: 1,
            geonames_id: 6942553,
            name: 'Dildo',
            feature_class: 'P',
            country_code: 'CA',
            admin1: 'Newfoundland and Labrador',
            lat: 47.5766,
            lon: -53.5442,
            claimed_by: null,
          },
        ],
      }),
    ),
    http.get('/api/places/1', () =>
      HttpResponse.json({
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
        etymology_confidence: null,
        etymology_source: null,
        name_language: null,
        claimed_by: null,
        bookmarked: false,
        eligibility: 'allowed',
        eligibility_reason: null,
      }),
    ),
  )
  render(<App />)

  await user.click(await screen.findByRole('button', { name: /search places/i }))
  await user.type(screen.getByRole('combobox'), 'Dildo')
  await user.click(await screen.findByRole('option', { name: /Dildo/ }))

  // Claiming without an account is the product now, so the sheet must open.
  // Gating it behind sign-in also gated reading, which is never gated.
  expect(await screen.findByLabelText(/caption/i)).toBeVisible()
  expect(useAuth.getState().signInOpen).toBe(false)
})
