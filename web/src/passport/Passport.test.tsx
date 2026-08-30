import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { server } from '../test/setup'
import Passport from './Passport'

const PASSPORT = {
  username: 'collector',
  discoveries: 12,
  first_finds: 12,
  countries: { CA: 7, GB: 5 },
  completion: { CA: 0.02, GB: 0.5 },
}

const FINDS = {
  discoveries: [
    { id: 1, place_id: 1, place_name: 'Dildo', country_code: 'CA', caption: 'Found it.' },
    { id: 2, place_id: 2, place_name: 'Dull', country_code: 'GB', caption: 'Twinned with Boring.' },
  ],
}

beforeEach(() => {
  server.use(
    http.get('/api/passport/:username', () => HttpResponse.json(PASSPORT)),
    http.get('/api/discoveries', () => HttpResponse.json(FINDS)),
  )
})

test('the first-finder count is the hero number', async () => {
  render(<Passport username="collector" onClose={vi.fn()} />)

  const hero = await screen.findByTestId('first-finds')
  expect(hero).toHaveTextContent('12')
  expect(hero).toHaveAccessibleDescription(/found first/i)
})

test('every discovery gets a stamp in the grid', async () => {
  render(<Passport username="collector" onClose={vi.fn()} />)

  const stamps = await screen.findAllByTestId('stamp-tile')
  expect(stamps).toHaveLength(2)
  expect(stamps[0]).toHaveTextContent('Dildo')
})

test('completion rings report their percentage accessibly', async () => {
  render(<Passport username="collector" onClose={vi.fn()} />)

  const rings = await screen.findAllByRole('progressbar')
  const british = rings.find((ring) => ring.getAttribute('aria-label')?.includes('GB'))
  expect(british).toHaveAttribute('aria-valuenow', '50')
})

test('the share card is offered as a real image url', async () => {
  render(<Passport username="collector" onClose={vi.fn()} />)

  const card = await screen.findByRole('link', { name: /share card/i })
  expect(card).toHaveAttribute('href', '/api/passport/collector/card.png')
})

test('an empty passport invites rather than apologises', async () => {
  server.use(
    http.get('/api/passport/:username', () =>
      HttpResponse.json({ ...PASSPORT, discoveries: 0, first_finds: 0, countries: {}, completion: {} }),
    ),
    http.get('/api/discoveries', () => HttpResponse.json({ discoveries: [] })),
  )
  render(<Passport username="collector" onClose={vi.fn()} />)

  expect(await screen.findByText(/be the first/i)).toBeVisible()
})
