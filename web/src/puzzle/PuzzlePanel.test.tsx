import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import type { PuzzleState } from '../api/puzzle'
import { useAuth } from '../auth/store'
import { server } from '../test/setup'
import PuzzlePanel from './PuzzlePanel'

const CLUES = [
  'A fort on a river.',
  'It is a populated place, a city.',
  'Europe',
  'Wales',
] as const

interface StateOverrides {
  clues?: readonly string[]
  guesses?: unknown[]
  solved?: boolean
  complete?: boolean
  remaining?: number
  pin?: { lat: number; lon: number } | null
  answer?: unknown
  share_grid?: string
  streak?: number
}

function state(overrides: StateOverrides = {}): PuzzleState {
  const { clues, ...rest } = overrides
  return {
    puzzle_id: 1,
    number: 142,
    guesses: [],
    solved: false,
    complete: false,
    remaining: 5,
    pin: null,
    answer: null,
    share_grid: '',
    streak: 0,
    ...rest,
    clues: [...(clues ?? [CLUES[0]])],
  } as PuzzleState
}

const NEAR_GUESS = {
  place_id: 9,
  name: 'Bristol',
  distance_km: 41.3,
  bearing: 271.4,
  arrow: '⬅️',
  band: 'near',
  proximity: 100,
}

const ANSWER = {
  place_id: 5,
  name: 'Cardiff',
  country_code: 'GB',
  lat: 51.4816,
  lon: -3.1791,
  claimed_by: null,
}

beforeEach(() => {
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  server.use(http.get('/api/puzzle', () => HttpResponse.json(state())))
})

test('it opens with one clue and five guesses left', async () => {
  render(<PuzzlePanel onFocusPlace={vi.fn()} onClaim={vi.fn()} />)

  expect(await screen.findByText(CLUES[0])).toBeVisible()
  expect(screen.getByText(/5 guesses left/i)).toBeVisible()
  expect(screen.getByText(/#142/)).toBeVisible()
})

test('a day without a puzzle says so instead of showing an empty board', async () => {
  server.use(http.get('/api/puzzle', () => HttpResponse.json(null)))
  render(<PuzzlePanel onFocusPlace={vi.fn()} onClaim={vi.fn()} />)

  expect(await screen.findByText(/no puzzle today/i)).toBeVisible()
})

test('the guess box autocompletes over the gazetteer', async () => {
  server.use(
    http.get('/api/search', ({ request }) => {
      const query = new URL(request.url).searchParams.get('q')
      return HttpResponse.json({
        results:
          query === 'Bris'
            ? [
                {
                  id: 9,
                  geonames_id: 2_654_675,
                  name: 'Bristol',
                  feature_class: 'P',
                  country_code: 'GB',
                  admin1: 'England',
                  lat: 51.45,
                  lon: -2.58,
                  claimed_by: null,
                },
              ]
            : [],
      })
    }),
  )
  const user = userEvent.setup()
  render(<PuzzlePanel onFocusPlace={vi.fn()} onClaim={vi.fn()} />)

  await user.type(await screen.findByLabelText(/your guess/i), 'Bris')

  expect(await screen.findByRole('option', { name: /Bristol/ })).toBeVisible()
})

test('a guess shows how far, which way, and how close', async () => {
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({ guesses: [NEAR_GUESS], clues: CLUES.slice(0, 2), remaining: 4 })}
    />,
  )

  const row = await screen.findByTestId('guess-0')
  expect(row).toHaveTextContent('Bristol')
  expect(row).toHaveTextContent('41 km')
  expect(row).toHaveTextContent('⬅️')
  expect(row).toHaveTextContent('🟨')
  expect(row).toHaveTextContent('100%')
})

test('earlier clues stay on screen as later ones arrive', async () => {
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({ clues: CLUES.slice(0, 3), guesses: [NEAR_GUESS, NEAR_GUESS] })}
    />,
  )

  for (const clue of CLUES.slice(0, 3)) {
    expect(await screen.findByText(clue)).toBeVisible()
  }
})

test('the pin clue is drawn on the globe rather than described', async () => {
  const onFocusPlace = vi.fn()
  render(
    <PuzzlePanel
      onFocusPlace={onFocusPlace}
      onClaim={vi.fn()}
      initialState={state({ clues: CLUES, pin: { lat: 51.4816, lon: -3.1791 } })}
    />,
  )

  await waitFor(() => expect(onFocusPlace).toHaveBeenCalledWith({ lat: 51.4816, lon: -3.1791 }))
})

test('solving reveals the place, and offers to claim it when nobody has', async () => {
  const onClaim = vi.fn()
  const user = userEvent.setup()
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={onClaim}
      initialState={state({
        solved: true,
        complete: true,
        answer: ANSWER,
        share_grid: 'Toponomicon #142 · 1/5\n🟩\n\ntoponomicon.app',
      })}
    />,
  )

  expect(await screen.findByText('Cardiff')).toBeVisible()
  await user.click(screen.getByRole('button', { name: /claim it/i }))

  expect(onClaim).toHaveBeenCalledWith(5)
})

test('a place somebody already found is named, not offered', async () => {
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({
        solved: true,
        complete: true,
        answer: { ...ANSWER, claimed_by: 'ada' },
      })}
    />,
  )

  expect(await screen.findByText(/@ada/)).toBeVisible()
  expect(screen.queryByRole('button', { name: /claim it/i })).toBeNull()
})

test('the share button copies the grid', async () => {
  const grid = 'Toponomicon #142 · 1/5\n🟩\n\ntoponomicon.app'
  const writeText = vi.fn(() => Promise.resolve())
  const user = userEvent.setup()
  // After setup, which installs a clipboard stub of its own, and defined
  // rather than assigned because navigator.clipboard is getter-only.
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  })
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({ solved: true, complete: true, answer: ANSWER, share_grid: grid })}
    />,
  )

  await user.click(await screen.findByRole('button', { name: /share/i }))

  expect(writeText).toHaveBeenCalledWith(grid)
  expect(await screen.findByText(/copied/i)).toBeVisible()
})

test('a failed attempt shows the answer without pretending it was solved', async () => {
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({
        solved: false,
        complete: true,
        remaining: 0,
        answer: ANSWER,
        share_grid: 'Toponomicon #142 · X/5\n⬜⬜⬜⬜⬜\n\ntoponomicon.app',
      })}
    />,
  )

  expect(await screen.findByText(/it was/i)).toBeVisible()
  expect(screen.getByText('Cardiff')).toBeVisible()
  expect(screen.queryByLabelText(/your guess/i)).toBeNull()
})

test('the streak prompt waits for the second consecutive solve', async () => {
  const first = state({ solved: true, complete: true, answer: ANSWER, streak: 1 })
  const { unmount } = render(
    <PuzzlePanel onFocusPlace={vi.fn()} onClaim={vi.fn()} initialState={first} />,
  )

  // One solve is not a habit. Asking now spends the ask before it means
  // anything.
  expect(await screen.findByText('Cardiff')).toBeVisible()
  expect(screen.queryByTestId('streak-prompt')).toBeNull()
  unmount()

  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={{ ...first, streak: 2 }}
    />,
  )

  expect(await screen.findByTestId('streak-prompt')).toHaveTextContent(/2 days/i)
})

test('a signed-in player is never asked to make an account', async () => {
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' }, signInOpen: false })
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({ solved: true, complete: true, answer: ANSWER, streak: 2 })}
    />,
  )

  expect(await screen.findByText('Cardiff')).toBeVisible()
  expect(screen.queryByTestId('streak-prompt')).toBeNull()
})

test('the archive explains what an account is for rather than just refusing', async () => {
  server.use(
    http.get('/api/puzzle/archive', () =>
      HttpResponse.json(
        { detail: 'Past puzzles are kept with your account. Create one to play them.' },
        { status: 401 },
      ),
    ),
  )
  const user = userEvent.setup()
  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({ solved: true, complete: true, answer: ANSWER })}
    />,
  )

  await user.click(await screen.findByRole('button', { name: /past puzzles/i }))

  expect(await screen.findByText(/kept with your account/i)).toBeVisible()
})

test('reduced motion drops the reveal animation but never the clue', async () => {
  // jsdom has no matchMedia at all, so there is nothing to spy on.
  vi.stubGlobal(
    'matchMedia',
    () =>
      ({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  )

  render(
    <PuzzlePanel
      onFocusPlace={vi.fn()}
      onClaim={vi.fn()}
      initialState={state({ clues: CLUES.slice(0, 2) })}
    />,
  )

  const clue = await screen.findByTestId('clue-1')
  expect(clue.className).not.toMatch(/animate-/)
  expect(clue).toHaveTextContent(CLUES[1]!)
})
