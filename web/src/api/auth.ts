import type { components } from './schema'

export type Me = components['schemas']['Me']

export async function fetchMe(): Promise<Me | null> {
  const response = await fetch('/api/auth/me')
  if (!response.ok) return null
  return (await response.json()) as Me | null
}

export async function requestMagicLink(email: string): Promise<void> {
  const response = await fetch('/api/auth/magic-link', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!response.ok) throw new Error(`magic link request failed: ${response.status}`)
}

export async function completeSignIn(token: string): Promise<Me> {
  const response = await fetch('/api/auth/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!response.ok) throw new Error(`sign-in failed: ${response.status}`)
  return (await response.json()) as Me
}
