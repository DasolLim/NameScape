import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { server } from '../test/setup'
import SearchOverlay from './SearchOverlay'

const DILDO = {
  id: 1,
  geonames_id: 6942553,
  name: 'Dildo',
  feature_class: 'P',
  feature_code: 'PPL',
  country_code: 'CA',
  tier: 3,
  lat: 47.5766,
  lon: -53.5442,
  claimed_by: null,
}
const BORING = { ...DILDO, id: 2, geonames_id: 5722064, name: 'Boring', country_code: 'US' }
const CLAIMED = { ...DILDO, id: 3, geonames_id: 3141537, name: 'Hell', claimed_by: 'ada' }

let requests: string[] = []

beforeEach(() => {
  requests = []
  server.use(
    http.get('/api/search', ({ request }) => {
      const query = new URL(request.url).searchParams.get('q') ?? ''
      requests.push(query)
      if (query === 'nowhere') return HttpResponse.json({ results: [] })
      return HttpResponse.json({ results: [DILDO, BORING, CLAIMED] })
    }),
  )
})

// Real timers throughout: vitest's fake timers deadlock React 19's scheduler,
// and a 150ms debounce is short enough to simply wait out.
function setup(onSelect = vi.fn()) {
  const user = userEvent.setup()
  render(<SearchOverlay onSelect={onSelect} />)
  return { user, onSelect }
}

async function openAndType(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.click(screen.getByRole('button', { name: /search/i }))
  await user.type(screen.getByRole('combobox'), text)
}

test('three keystrokes inside the debounce window produce one request', async () => {
  const { user } = setup()

  await openAndType(user, 'dil')

  await waitFor(() => expect(requests).toEqual(['dil']))
})

test('results show the name, country, and who claimed it', async () => {
  const { user } = setup()

  await openAndType(user, 'dil')

  const options = await screen.findAllByRole('option')
  expect(options[0]).toHaveTextContent('Dildo')
  expect(options[0]).toHaveTextContent('CA')
  expect(options[2]).toHaveTextContent('@ada')
})

test('arrow keys move the active row and Enter selects it', async () => {
  const { user, onSelect } = setup()

  await openAndType(user, 'dil')
  await screen.findAllByRole('option')

  await user.keyboard('{ArrowDown}{ArrowDown}{Enter}')

  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ name: 'Boring' }))
})

test('an empty result set offers a worldwide search instead of a dead end', async () => {
  const { user } = setup()

  await openAndType(user, 'nowhere')

  expect(await screen.findByRole('button', { name: /search worldwide/i })).toBeVisible()
})

test('Escape closes the overlay and returns focus to the trigger', async () => {
  const { user } = setup()

  await user.click(screen.getByRole('button', { name: /search/i }))
  await user.keyboard('{Escape}')

  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  // Re-queried: closing remounts the trigger, so the old node is stale.
  expect(screen.getByRole('button', { name: /search/i })).toHaveFocus()
})
