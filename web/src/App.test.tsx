import { render, screen, waitFor } from '@testing-library/react'
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
