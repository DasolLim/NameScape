import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'

import { useAuth } from '../auth/store'
import GuestPrompt from './GuestPrompt'

const EXPIRES = new Date(Date.now() + 7 * 24 * 3600_000).toISOString()

beforeEach(() => {
  useAuth.setState({ status: 'anonymous', user: null, signInOpen: false })
})

test('it names the place and what is at stake, not what the product wants', () => {
  render(<GuestPrompt placeName="Dildo" expiresAt={EXPIRES} onDismiss={vi.fn()} />)

  const prompt = screen.getByTestId('guest-prompt')
  expect(prompt).toHaveTextContent('Dildo')
  expect(prompt).toHaveTextContent(/yours/i)
  expect(prompt).toHaveTextContent(/7 days|6 days/i)
})

test('it offers to keep the claim, and that opens sign-in', async () => {
  const user = userEvent.setup()
  render(<GuestPrompt placeName="Dildo" expiresAt={EXPIRES} onDismiss={vi.fn()} />)

  await user.click(screen.getByRole('button', { name: /keep it/i }))

  expect(useAuth.getState().signInOpen).toBe(true)
})

test('dismissing is a real option, spelled out rather than an unlabelled cross', async () => {
  const onDismiss = vi.fn()
  const user = userEvent.setup()
  render(<GuestPrompt placeName="Dildo" expiresAt={EXPIRES} onDismiss={onDismiss} />)

  await user.click(screen.getByRole('button', { name: /later/i }))

  expect(onDismiss).toHaveBeenCalledOnce()
})

test('it is a sheet, not a modal: nothing behind it is blocked', () => {
  render(<GuestPrompt placeName="Dildo" expiresAt={EXPIRES} onDismiss={vi.fn()} />)

  const prompt = screen.getByTestId('guest-prompt')
  expect(prompt).not.toHaveAttribute('aria-modal')
  expect(prompt.getAttribute('role')).not.toBe('dialog')
})
