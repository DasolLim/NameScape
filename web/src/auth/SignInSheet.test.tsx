import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, test } from 'vitest'

import { server } from '../test/setup'
import SignInSheet from './SignInSheet'
import { useAuth } from './store'

beforeEach(() => {
  useAuth.setState({ user: null, status: 'anonymous', signInOpen: true, linkSent: false })
  server.use(http.post('/api/auth/magic-link', () => new HttpResponse(null, { status: 204 })))
})

test('is not rendered while closed', () => {
  useAuth.setState({ signInOpen: false })
  render(<SignInSheet />)

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('sends a link and confirms it, without ever asking for a password', async () => {
  const user = userEvent.setup()
  render(<SignInSheet />)

  expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  await user.type(screen.getByLabelText(/email/i), 'ada@example.com')
  await user.click(screen.getByRole('button', { name: /send/i }))

  expect(await screen.findByText(/check your email/i)).toBeVisible()
})

test('closes on Escape', async () => {
  const user = userEvent.setup()
  render(<SignInSheet />)

  await user.keyboard('{Escape}')

  expect(useAuth.getState().signInOpen).toBe(false)
})
