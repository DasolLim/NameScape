import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import type { PlaceDetail } from '../api/places'
import { useAuth } from '../auth/store'
import { server } from '../test/setup'
import ClaimSheet from './ClaimSheet'

const EXPIRES = new Date(Date.now() + 7 * 24 * 3600_000).toISOString()

/** A guest claim: the API answers with a deadline attached. */
function guestClaimResponse() {
  return http.post('/api/discoveries', () =>
    HttpResponse.json(
      {
        id: 7,
        place_id: 1,
        finder: 'a guest',
        caption: 'found it',
        expires_at: EXPIRES,
      },
      { status: 201 },
    ),
  )
}

async function stampAsGuest(): Promise<void> {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/caption/i), 'Found it on a map.')
  await user.click(screen.getByRole('button', { name: /stamp it/i }))
}

/**
 * Let the stamp land.
 *
 * The component settles on animationend or on a timer, whichever comes first,
 * because a cancelled or missing animation must not cost the visitor the
 * prompt. jsdom fires no animation, so the timer is what runs here, which is
 * also the path that has to work when the animation does not.
 */
async function letTheStampLand(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 450))
  })
}

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
  etymology_confidence: null,
  etymology_source: null,
  name_language: null,
  claimed_by: null,
  bookmarked: false,
  eligibility: 'allowed',
  eligibility_reason: null,
}

let posted: Record<string, unknown>[] = []

beforeEach(() => {
  posted = []
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
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


test('a guest sees no prompt until the stamp animation has finished', async () => {
  server.use(guestClaimResponse())
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await stampAsGuest()

  // The stamp has landed; the prompt must wait for its last frame. Firing it
  // on the claim response instead would talk over the one moment that earns
  // the ask.
  expect(await screen.findByTestId('stamp')).toBeVisible()
  expect(screen.queryByTestId('guest-prompt')).toBeNull()

  await letTheStampLand()

  expect(await screen.findByTestId('guest-prompt')).toBeVisible()
})

test('the prompt names the place and the deadline', async () => {
  server.use(guestClaimResponse())
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await stampAsGuest()
  await letTheStampLand()

  const prompt = await screen.findByTestId('guest-prompt')
  expect(prompt).toHaveTextContent('Dildo')
  expect(prompt).toHaveTextContent(/days/i)
})

test('dismissing the prompt does not lose the claim', async () => {
  const user = userEvent.setup()
  server.use(guestClaimResponse())
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await stampAsGuest()
  await letTheStampLand()
  await user.click(await screen.findByRole('button', { name: /later/i }))

  expect(screen.queryByTestId('guest-prompt')).toBeNull()
  expect(screen.getByTestId('stamp')).toBeVisible()
  // And the deadline stays on screen, which is the whole point of dismissing
  // being safe: the claim is still theirs and still running out.
  expect(screen.getByText(/days left/i)).toBeVisible()
})

test('a signed-in claim gets no prompt: there is nothing to convert', async () => {
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' }, signInOpen: false })
  render(<ClaimSheet place={PLACE} onClaimed={vi.fn()} />)

  await stampAsGuest()
  await letTheStampLand()

  expect(screen.queryByTestId('guest-prompt')).toBeNull()
})

test('a guest who already holds a claim is told why, with the control disabled', () => {
  render(
    <ClaimSheet
      place={PLACE}
      onClaimed={vi.fn()}
      heldClaim={{ placeName: 'Boring', expiresAt: EXPIRES }}
    />,
  )

  // Disabled and explained, not hidden: a control that vanishes reads as a bug.
  const stamp = screen.getByRole('button', { name: /stamp it/i })
  expect(stamp).toBeDisabled()
  expect(screen.getByText(/Boring/)).toBeVisible()
  expect(screen.getByText(/account/i)).toBeVisible()
})
