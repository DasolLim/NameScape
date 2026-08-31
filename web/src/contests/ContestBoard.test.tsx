import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { useAuth } from '../auth/store'
import { server } from '../test/setup'
import ContestBoard from './ContestBoard'

const NOW = new Date('2026-08-01T12:00:00Z')

function board(overrides: Record<string, unknown> = {}) {
  return {
    place_id: 1,
    nickname: null,
    leading_candidate: null,
    closes_at: '2026-08-02T06:30:00Z',
    reopens_at: null,
    quorum: 15,
    proposals: [
      { id: 1, text: 'Cape Embarrassment', agree: 4, disagree: 1, score: 3, is_incumbent: false, is_yours: false },
      { id: 2, text: 'The Unfortunate Bay', agree: 14, disagree: 1, score: 13, is_incumbent: false, is_yours: false },
    ],
    ...overrides,
  }
}

let votes: unknown[] = []

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  vi.setSystemTime(NOW)
  votes = []
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' }, signInOpen: false })
  server.use(
    http.get('/api/contests/:id', () => HttpResponse.json(board())),
    http.post('/api/votes', async ({ request }) => {
      votes.push(await request.json())
      return new HttpResponse(null, { status: 204 })
    }),
  )
})

afterEach(() => vi.useRealTimers())

test('proposals are ordered by net score, best first', async () => {
  render(<ContestBoard placeId={1} />)

  const cards = await screen.findAllByRole('article')
  expect(cards[0]).toHaveTextContent('The Unfortunate Bay')
  expect(cards[1]).toHaveTextContent('Cape Embarrassment')
})

test('the countdown shows time remaining and never goes negative', async () => {
  render(<ContestBoard placeId={1} />)

  expect(await screen.findByTestId('countdown')).toHaveTextContent('18h 30m')

  vi.setSystemTime(new Date('2026-08-03T00:00:00Z'))
  await vi.advanceTimersByTimeAsync(1100)
  await waitFor(() => expect(screen.getByTestId('countdown')).toHaveTextContent(/closed/i))
  expect(screen.getByTestId('countdown')).not.toHaveTextContent('-')
})

test('vote state carries icons and labels, not colour alone', async () => {
  render(<ContestBoard placeId={1} />)

  const agree = (await screen.findAllByRole('button', { name: /^agree with/i }))[0]
  expect(agree).toHaveAccessibleName(/agree/i)
  expect(agree).toHaveTextContent('▲')
  expect(screen.getAllByRole('button', { name: /^disagree with/i })[0]).toHaveTextContent('▼')
})

test('a proposal near quorum shows its progress', async () => {
  render(<ContestBoard placeId={1} />)

  const progress = (await screen.findAllByRole('progressbar'))[0]
  expect(progress).toHaveAttribute('aria-valuenow', '13')
  expect(progress).toHaveAttribute('aria-valuemax', '15')
})

test('your own proposal has voting disabled, with the reason given', async () => {
  server.use(
    http.get('/api/contests/:id', () =>
      HttpResponse.json(
        board({
          proposals: [
            {
              id: 2,
              text: 'The Unfortunate Bay',
              agree: 14,
              disagree: 1,
              score: 13,
              is_incumbent: false,
              is_yours: true,
            },
          ],
        }),
      ),
    ),
  )
  render(<ContestBoard placeId={1} />)

  const own = (await screen.findAllByRole('article'))[0]!
  const agree = within(own).getByRole('button', { name: /^agree with/i })
  expect(agree).toBeDisabled()
  expect(own).toHaveTextContent(/your own proposal/i)
})

test('voting while signed out is refused up front, not on click', async () => {
  // Superseded Addendum A step 26: this used to open the sign-in sheet. The
  // vote controls are disabled and explained instead, so nothing pretends to
  // be available and then is not.
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  render(<ContestBoard placeId={1} />)

  await user.click((await screen.findAllByRole('button', { name: /^agree with/i }))[0]!)

  expect(votes).toEqual([])
  expect(useAuth.getState().signInOpen).toBe(false)
})

test('a signed-in vote is sent', async () => {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  render(<ContestBoard placeId={1} />)

  await user.click((await screen.findAllByRole('button', { name: /^agree with/i }))[0]!)

  await waitFor(() => expect(votes).toEqual([{ proposal_id: 2, value: 1 }]))
})


test('a signed-out visitor cannot vote or propose, and is told why', async () => {
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  render(<ContestBoard placeId={1} />)

  await waitFor(() => expect(screen.getByText(/nickname contest/i)).toBeVisible())

  for (const control of screen.getAllByRole('button', { name: /agree|disagree/i })) {
    expect(control).toBeDisabled()
  }
  expect(screen.getByLabelText(/propose a nickname/i)).toBeDisabled()
  expect(screen.getByTestId('needs-account')).toHaveTextContent(/account/i)
})
