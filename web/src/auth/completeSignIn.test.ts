import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { server } from '../test/setup'
import { completeSignInFromUrl } from './completeSignIn'
import { useAuth } from './store'

beforeEach(() => {
  useAuth.setState({ user: null, status: 'anonymous', signInOpen: false, linkSent: false })
  window.history.replaceState({}, '', '/')
})

test('a token in the URL signs the visitor in', async () => {
  server.use(
    http.post('/api/auth/session', () => HttpResponse.json({ username: 'finder' })),
  )
  window.history.replaceState({}, '', '/?token=abc123')

  await completeSignInFromUrl()

  expect(useAuth.getState().user?.username).toBe('finder')
})

test('the token is removed from the address bar once used', async () => {
  server.use(
    http.post('/api/auth/session', () => HttpResponse.json({ username: 'finder' })),
  )
  window.history.replaceState({}, '', '/?token=abc123&keep=1')

  await completeSignInFromUrl()

  expect(window.location.search).toBe('?keep=1')
})

test('an expired link explains itself rather than failing silently', async () => {
  server.use(
    http.post('/api/auth/session', () =>
      HttpResponse.json({ detail: 'Invalid or expired token' }, { status: 401 }),
    ),
  )
  window.history.replaceState({}, '', '/?token=stale')

  await completeSignInFromUrl()

  expect(useAuth.getState().status).toBe('anonymous')
  expect(useAuth.getState().signInOpen).toBe(true)
  expect(useAuth.getState().linkError).toMatch(/expired/i)
})

test('no token means nothing happens', async () => {
  const signIn = vi.spyOn(useAuth.getState(), 'signIn')

  await completeSignInFromUrl()

  expect(signIn).not.toHaveBeenCalled()
})
