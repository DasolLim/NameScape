import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'

import type { PlaceDetail } from '../api/places'
import { useAuth } from '../auth/store'
import { server } from '../test/setup'
import EtymologyPanel from './EtymologyPanel'

const WELSH: PlaceDetail = {
  id: 1,
  geonames_id: 2_650_100,
  name: 'Ffynnongroyw',
  feature_class: 'P',
  feature_code: 'PPL',
  country_code: 'GB',
  tier: 3,
  lat: 53.3,
  lon: -3.3,
  etymology: null,
  etymology_confidence: null,
  etymology_source: null,
  name_language: 'cy',
  claimed_by: null,
  bookmarked: false,
  eligibility: 'allowed',
  eligibility_reason: null,
}

function place(overrides: Partial<PlaceDetail>): PlaceDetail {
  return { ...WELSH, ...overrides }
}

beforeEach(() => {
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' }, signInOpen: false })
})

async function reveal(): Promise<void> {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /what it actually means/i }))
}

test('a sourced meaning shows where it came from, as a link', async () => {
  render(
    <EtymologyPanel
      place={place({
        etymology: 'The name derives from the Welsh for clear well.',
        etymology_confidence: 'high',
        etymology_source: 'https://en.wikipedia.org/wiki/Ffynnongroyw',
      })}
    />,
  )
  await reveal()

  expect(screen.getByText(/clear well/i)).toBeVisible()
  const source = screen.getByRole('link', { name: /source/i })
  expect(source).toHaveAttribute('href', 'https://en.wikipedia.org/wiki/Ffynnongroyw')
})

test('a generated meaning says in words that nobody checked it', async () => {
  render(
    <EtymologyPanel
      place={place({
        etymology: 'Possibly from a word for a pin.',
        etymology_confidence: 'unverified',
        etymology_source: 'anthropic/claude-opus-5',
      })}
    />,
  )
  await reveal()

  // The label is text, not a colour or a border: a reader who cannot see the
  // treatment still has to be told this was written by a model.
  const panel = screen.getByTestId('etymology')
  expect(panel).toHaveTextContent(/unverified/i)
  expect(panel).toHaveTextContent(/language model/i)
  expect(panel).toHaveTextContent(/not from a source/i)
  // And no link: there is nothing to cite.
  expect(screen.queryByRole('link', { name: /source/i })).toBeNull()
})

test('a rule-based meaning says which element it read, and cites no page', async () => {
  render(
    <EtymologyPanel
      place={place({
        name: 'Grimsby',
        name_language: 'cy',
        etymology: 'Grimsby ends with “-by”, a farmstead, from Old Norse “byr”.',
        etymology_confidence: 'medium',
        etymology_source: 'lexicon:name_elements',
      })}
    />,
  )
  await reveal()

  expect(screen.getByTestId('etymology')).toHaveTextContent(/known name element/i)
  expect(screen.queryByRole('link', { name: /source/i })).toBeNull()
})

test('an unresolved name invites a contribution rather than reporting an error', async () => {
  render(<EtymologyPanel place={place({ etymology_confidence: 'unknown' })} />)
  await reveal()

  const panel = screen.getByTestId('etymology')
  expect(panel).toHaveTextContent(/nobody has established/i)
  expect(panel).not.toHaveTextContent(/error|failed|unavailable/i)
  expect(screen.getByRole('button', { name: /tell us/i })).toBeVisible()
})

test('a name in the reader’s own language gets no reveal: there is nothing to reveal', () => {
  render(
    <EtymologyPanel
      place={place({ name: 'Boring', name_language: 'en', etymology_confidence: 'unknown' })}
    />,
  )

  expect(screen.queryByRole('button', { name: /what it actually means/i })).toBeNull()
})

test('correcting an entry opens a form and files it', async () => {
  const filed: { text: string }[] = []
  server.use(
    http.post('/api/places/1/etymology', async ({ request }) => {
      filed.push((await request.json()) as { text: string })
      return HttpResponse.json({ id: 3, place_id: 1, status: 'pending' }, { status: 201 })
    }),
  )
  const user = userEvent.setup()
  render(
    <EtymologyPanel
      place={place({
        etymology: 'Possibly from a word for a pin.',
        etymology_confidence: 'unverified',
        etymology_source: 'anthropic/claude-opus-5',
      })}
    />,
  )
  await reveal()

  await user.click(screen.getByRole('button', { name: /correct this/i }))
  await user.type(screen.getByLabelText(/what it really means/i), 'Welsh for clear well.')
  await user.click(screen.getByRole('button', { name: /send/i }))

  expect(filed).toEqual([{ text: 'Welsh for clear well.' }])
  // Held for review, and the reader is told that rather than seeing it applied.
  expect(await screen.findByText(/review/i)).toBeVisible()
})

test('a signed-out reader is told a correction needs an account', async () => {
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  render(<EtymologyPanel place={place({ etymology_confidence: 'unknown' })} />)
  await reveal()

  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /tell us/i }))

  expect(useAuth.getState().signInOpen).toBe(true)
})

test('a refused correction says so without repeating the rule it broke', async () => {
  server.use(
    http.post('/api/places/1/etymology', () =>
      HttpResponse.json({ detail: 'That correction cannot be used' }, { status: 422 }),
    ),
  )
  const user = userEvent.setup()
  render(<EtymologyPanel place={place({ etymology_confidence: 'unknown' })} />)
  await reveal()

  await user.click(screen.getByRole('button', { name: /tell us/i }))
  await user.type(screen.getByLabelText(/what it really means/i), 'nonsense')
  await user.click(screen.getByRole('button', { name: /send/i }))

  expect(await screen.findByRole('alert')).toHaveTextContent(/cannot be used/i)
})
