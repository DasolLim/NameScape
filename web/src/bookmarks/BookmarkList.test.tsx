import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { server } from '../test/setup'
import BookmarkList from './BookmarkList'

const SAVED = {
  bookmarks: [
    { place_id: 1, name: 'Cockermouth', country_code: 'GB', lon: -3.36, lat: 54.66 },
    { place_id: 2, name: 'Dildo', country_code: 'CA', lon: -53.54, lat: 47.58 },
  ],
}

beforeEach(() => {
  server.use(http.get('/api/bookmarks', () => HttpResponse.json(SAVED)))
})

test('it lists the places the visitor saved', async () => {
  render(<BookmarkList onSelect={vi.fn()} onClose={vi.fn()} showOnGlobe onToggleGlobe={vi.fn()} />)

  const entries = await screen.findAllByRole('listitem')
  expect(entries).toHaveLength(2)
  expect(entries[0]).toHaveTextContent('Cockermouth')
  expect(entries[0]).toHaveTextContent('GB')
})

test('choosing one asks the globe to go there', async () => {
  const onSelect = vi.fn()
  const user = userEvent.setup()
  render(<BookmarkList onSelect={onSelect} onClose={vi.fn()} showOnGlobe onToggleGlobe={vi.fn()} />)

  await user.click(await screen.findByRole('button', { name: /cockermouth/i }))

  expect(onSelect).toHaveBeenCalledWith(
    expect.objectContaining({ name: 'Cockermouth', lon: -3.36, lat: 54.66 }),
  )
})

test('an empty list says how to start one', async () => {
  server.use(http.get('/api/bookmarks', () => HttpResponse.json({ bookmarks: [] })))
  render(<BookmarkList onSelect={vi.fn()} onClose={vi.fn()} showOnGlobe onToggleGlobe={vi.fn()} />)

  expect(await screen.findByText(/nothing saved yet/i)).toBeVisible()
  expect(screen.getByText(/star/i)).toBeVisible()
})

test('the globe layer can be turned off from here', async () => {
  const onToggleGlobe = vi.fn()
  const user = userEvent.setup()
  render(
    <BookmarkList onSelect={vi.fn()} onClose={vi.fn()} showOnGlobe onToggleGlobe={onToggleGlobe} />,
  )

  await user.click(await screen.findByRole('switch', { name: /show on the globe/i }))

  expect(onToggleGlobe).toHaveBeenCalledWith(false)
})

test('it can be dismissed', async () => {
  const onClose = vi.fn()
  const user = userEvent.setup()
  render(<BookmarkList onSelect={vi.fn()} onClose={onClose} showOnGlobe onToggleGlobe={vi.fn()} />)

  await user.click(await screen.findByRole('button', { name: /close/i }))

  expect(onClose).toHaveBeenCalled()
})
