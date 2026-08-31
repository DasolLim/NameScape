import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import Countdown from './Countdown'

function inHours(hours: number): string {
  return new Date(Date.now() + hours * 3600_000).toISOString()
}

test('a fresh seven day claim says seven days, not six', () => {
  render(<Countdown expiresAt={inHours(24 * 7 - 1)} />)

  expect(screen.getByText(/7 days left/i)).toBeVisible()
})

test('most of a week gone reads as the days that are actually left', () => {
  render(<Countdown expiresAt={inHours(24 * 3 + 2)} />)

  expect(screen.getByText(/3 days left/i)).toBeVisible()
})

test('inside two days it reads in hours, because days would round away the urgency', () => {
  render(<Countdown expiresAt={inHours(30)} />)

  expect(screen.getByText(/30 hours left/i)).toBeVisible()
})

test('the last hour says so in words rather than counting seconds', () => {
  render(<Countdown expiresAt={inHours(0.4)} />)

  expect(screen.getByText(/under an hour left/i)).toBeVisible()
})

test('a passed deadline says the place has gone back, not "0 days left"', () => {
  render(<Countdown expiresAt={inHours(-1)} />)

  expect(screen.getByText(/released/i)).toBeVisible()
})

test('the deadline is stated as a date too, so it is not only relative', () => {
  render(<Countdown expiresAt={inHours(48)} />)

  // A relative countdown alone cannot be checked against a calendar.
  expect(screen.getByTitle(/expires/i)).toBeVisible()
})
