import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import type { PlaceDetail } from '../api/places'
import { server } from '../test/setup'
import ClaimSheet from './ClaimSheet'

const PLACE: PlaceDetail = {
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
  claimed_by: null,
  bookmarked: false,
  eligibility: 'allowed',
  eligibility_reason: null,
}

let posted: Record<string, unknown>[] = []

beforeEach(() => {
  posted = []
  server.use(
    http.post('/api/discoveries', async ({ request }) => {
      posted.push((await request.json()) as Record<string, unknown>)
      return HttpResponse.json(
        { id: 7, place_id: 1, finder: 'firstfinder', caption: 'found it' },
        { status: 201 },
      )
    }),
  )
})

test('the caption counts down from 140 and stops there', async () => {
  const user = userEvent.setup()
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  const caption = screen.getByLabelText(/caption/i)
  await user.type(caption, 'x'.repeat(145))

  expect(caption).toHaveValue('x'.repeat(140))
  expect(screen.getByText('0 left')).toBeVisible()
})

test('an empty caption shows an inline error and sends nothing', async () => {
  const user = userEvent.setup()
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await user.click(screen.getByRole('button', { name: /stamp it/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/write a caption/i)
  expect(posted).toEqual([])
})

test('a blocked place explains itself and offers no claim button', () => {
  render(
    <ClaimSheet
      place={{ ...PLACE, eligibility: 'blocked', eligibility_reason: 'A war memorial.' }}
      onClaimed={vi.fn()}
    />,
  )

  expect(screen.getByText('A war memorial.')).toBeVisible()
  expect(screen.queryByRole('button', { name: /stamp it/i })).not.toBeInTheDocument()
})

test('a Tier B place asks what the name means before it will submit', async () => {
  const user = userEvent.setup()
  render(
    <ClaimSheet
      place={{ ...PLACE, eligibility: 'etymology_required', eligibility_reason: 'Not your language.' }}
      onClaimed={vi.fn()}
    />,
  )

  await user.type(screen.getByLabelText(/caption/i), 'A genuinely odd name.')
  await user.click(screen.getByRole('button', { name: /stamp it/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/what the name means/i)
  expect(posted).toEqual([])

  await user.type(screen.getByLabelText(/etymology/i), 'From the Boldin family estate.')
  await user.click(screen.getByRole('button', { name: /stamp it/i }))

  expect(await screen.findByText(/first finder/i)).toBeVisible()
})

test('a successful claim shows the first finder badge', async () => {
  const user = userEvent.setup()
  const onClaimed = vi.fn()
  render(<ClaimSheet place={PLACE} onClaimed={onClaimed} />)

  await user.type(screen.getByLabelText(/caption/i), 'Found it on a map.')
  await user.click(screen.getByRole('button', { name: /stamp it/i }))

  expect(await screen.findByText(/first finder/i)).toBeVisible()
  expect(screen.getByText('@firstfinder')).toBeVisible()
  expect(onClaimed).toHaveBeenCalledOnce()
})

test('being rate limited says to wait, not just "too many requests"', async () => {
  server.use(
    http.post('/api/discoveries', () =>
      HttpResponse.json({ detail: 'Too many requests' }, { status: 429 }),
    ),
  )
  const user = userEvent.setup()
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await user.type(screen.getByLabelText(/caption/i), 'Found it on a map.')
  await user.click(screen.getByRole('button', { name: /stamp it/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/moment/i)
})

test('a conflict says someone was faster, not something generic', async () => {
  server.use(
    http.post('/api/discoveries', () =>
      HttpResponse.json({ detail: 'Someone found this one first' }, { status: 409 }),
    ),
  )
  const user = userEvent.setup()
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await user.type(screen.getByLabelText(/caption/i), 'Found it on a map.')
  await user.click(screen.getByRole('button', { name: /stamp it/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/found this one first/i)
})
