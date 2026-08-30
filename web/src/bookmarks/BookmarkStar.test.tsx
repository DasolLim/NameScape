import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'

import { useAuth } from '../auth/store'
import { server } from '../test/setup'
import BookmarkStar from './BookmarkStar'

let calls: string[] = []

beforeEach(() => {
  calls = []
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' }, signInOpen: false })
  server.use(
    http.post('/api/bookmarks/:id', ({ params }) => {
      calls.push(`POST ${params.id as string}`)
      return new HttpResponse(null, { status: 204 })
    }),
    http.delete('/api/bookmarks/:id', ({ params }) => {
      calls.push(`DELETE ${params.id as string}`)
      return new HttpResponse(null, { status: 204 })
    }),
  )
})

test('one tap saves, and the star flips before the request finishes', async () => {
  const user = userEvent.setup()
  render(<BookmarkStar placeId={7} saved={false} />)

  const star = screen.getByRole('button', { name: /save this place/i })
  await user.click(star)

  expect(screen.getByRole('button', { name: /saved/i })).toBeVisible()
  await waitFor(() => expect(calls).toEqual(['POST 7']))
})

test('tapping again removes it', async () => {
  const user = userEvent.setup()
  render(<BookmarkStar placeId={7} saved />)

  await user.click(screen.getByRole('button', { name: /saved/i }))

  await waitFor(() => expect(calls).toEqual(['DELETE 7']))
  expect(screen.getByRole('button', { name: /save this place/i })).toBeVisible()
})

test('a failed save rolls the star back', async () => {
  server.use(http.post('/api/bookmarks/:id', () => new HttpResponse(null, { status: 500 })))
  const user = userEvent.setup()
  render(<BookmarkStar placeId={7} saved={false} />)

  await user.click(screen.getByRole('button', { name: /save this place/i }))

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /save this place/i })).toBeVisible(),
  )
})

test('a signed-out visitor is asked to sign in, and nothing is sent', async () => {
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  const user = userEvent.setup()
  render(<BookmarkStar placeId={7} saved={false} />)

  await user.click(screen.getByRole('button', { name: /save this place/i }))

  expect(useAuth.getState().signInOpen).toBe(true)
  expect(calls).toEqual([])
})
