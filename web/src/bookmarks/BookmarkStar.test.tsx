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

test('a signed-out visitor cannot save, and nothing is sent', async () => {
  // Superseded Addendum A step 26: this used to open the sign-in sheet on
  // click. A control that looks live and then demands an account is a trap,
  // so it is disabled with the reason beside it instead.
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  const user = userEvent.setup()
  render(<BookmarkStar placeId={7} saved={false} />)

  await user.click(screen.getByRole('button', { name: /save this place/i }))

  expect(calls).toEqual([])
  expect(useAuth.getState().signInOpen).toBe(false)
})


test('a signed-out visitor sees the star disabled and told why, not a trap', async () => {
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
  render(<BookmarkStar placeId={1} saved={false} />)

  const star = screen.getByRole('button', { name: /save this place/i })

  // Claiming works without an account; saving does not, and a control that
  // looks live and then demands a sign-in is a trap rather than an offer.
  expect(star).toBeDisabled()
  expect(star).toHaveAccessibleDescription(/account/i)
})
