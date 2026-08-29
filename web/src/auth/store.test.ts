import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test, vi } from 'vitest'

import { server } from '../test/setup'
import { useAuth } from './store'

beforeEach(() => {
  useAuth.setState({ user: null, status: 'unknown', signInOpen: false, linkSent: false })
})

test('loading resolves an anonymous visitor without erroring', async () => {
  server.use(http.get('/api/auth/me', () => HttpResponse.json(null)))

  await useAuth.getState().load()

  expect(useAuth.getState().status).toBe('anonymous')
  expect(useAuth.getState().user).toBeNull()
})

test('loading resolves a signed-in visitor', async () => {
  server.use(http.get('/api/auth/me', () => HttpResponse.json({ username: 'ada' })))

  await useAuth.getState().load()

  expect(useAuth.getState().status).toBe('signed-in')
  expect(useAuth.getState().user?.username).toBe('ada')
})

test('requesting a link records that it was sent', async () => {
  server.use(http.post('/api/auth/magic-link', () => new HttpResponse(null, { status: 204 })))

  await useAuth.getState().requestLink('ada@example.com')

  expect(useAuth.getState().linkSent).toBe(true)
})

test('a guarded action runs immediately when signed in', () => {
  useAuth.setState({ status: 'signed-in', user: { username: 'ada' } })
  const action = vi.fn()

  useAuth.getState().requireAuth(action)

  expect(action).toHaveBeenCalledOnce()
  expect(useAuth.getState().signInOpen).toBe(false)
})

test('a guarded action opens the sign-in sheet when anonymous, and does not run', () => {
  useAuth.setState({ status: 'anonymous', user: null })
  const action = vi.fn()

  useAuth.getState().requireAuth(action)

  expect(action).not.toHaveBeenCalled()
  expect(useAuth.getState().signInOpen).toBe(true)
})
