import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { useAuth } from '../auth/store'
import { server } from '../test/setup'
import TopBar from './TopBar'

const LAYERS = { discoveries: true, bookmarks: true, nicknames: true }

function renderBar(overrides: Partial<Parameters<typeof TopBar>[0]> = {}) {
  return render(
    <TopBar
      layers={LAYERS}
      onLayersChange={vi.fn()}
      onSelectPlace={vi.fn()}
      onOpenBookmarks={vi.fn()}
      onOpenPassport={vi.fn()}
      {...overrides}
    />,
  )
}

beforeEach(() => {
  useAuth.setState({ user: null, status: 'anonymous', signInOpen: false, linkSent: false })
  server.use(
    http.get('/api/activity', () =>
      HttpResponse.json({ contests_closing_soon: 3, streak_days: null, streak_at_risk: false }),
    ),
  )
})

test('it is a solid bar, not text floating on the map', () => {
  renderBar()

  const bar = screen.getByRole('banner')
  // The complaint this redesign answers: chrome must not depend on whatever
  // the basemap happens to be underneath it.
  expect(bar.className).toMatch(/bg-ink-950/)
  expect(bar.className).not.toMatch(/backdrop-blur/)
})

test('the wordmark says what the product is, not whether the database is up', () => {
  renderBar()

  expect(screen.getByText('Toponomicon')).toBeVisible()
  expect(screen.getByText(/atlas of absurd place names/i)).toBeVisible()
  expect(screen.queryByText(/redis/i)).not.toBeInTheDocument()
})

test('live contests are surfaced as a reason to come back', async () => {
  renderBar()

  const contests = await screen.findByTestId('closing-soon')
  expect(contests).toHaveTextContent('3')
  expect(contests).toHaveAccessibleName(/3 contests closing/i)
})

test('no contests closing means no badge, rather than a zero', async () => {
  server.use(
    http.get('/api/activity', () =>
      HttpResponse.json({ contests_closing_soon: 0, streak_days: null, streak_at_risk: false }),
    ),
  )
  renderBar()

  await screen.findByRole('banner')
  expect(screen.queryByTestId('closing-soon')).not.toBeInTheDocument()
})

test('a signed-in visitor sees their streak and reaches their passport', async () => {
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' } })
  server.use(
    http.get('/api/activity', () =>
      HttpResponse.json({ contests_closing_soon: 1, streak_days: 7, streak_at_risk: false }),
    ),
  )
  renderBar()

  expect(await screen.findByTestId('streak')).toHaveTextContent('7')
  expect(screen.getByRole('button', { name: /@ada/ })).toBeVisible()
})

test('a signed-out visitor is offered sign-in and shown no streak', () => {
  renderBar()

  expect(screen.getByRole('button', { name: /^sign in$/i })).toBeVisible()
  expect(screen.queryByTestId('streak')).not.toBeInTheDocument()
})
