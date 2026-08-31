import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import StreakBadge from './StreakBadge'

test('a live streak states the count and what it means', () => {
  render(<StreakBadge days={7} atRisk={false} />)

  const badge = screen.getByTestId('streak')
  expect(badge).toHaveTextContent('7')
  expect(badge).toHaveAccessibleName(/7 day streak/i)
})

test('a streak at risk says so, not just in colour', () => {
  render(<StreakBadge days={4} atRisk />)

  // Colour alone would fail anyone who cannot distinguish brass from grey.
  expect(screen.getByTestId('streak')).toHaveAccessibleName(/keep it alive today/i)
})

test('nothing is shown before a streak exists, rather than a proud zero', () => {
  const { container } = render(<StreakBadge days={0} atRisk={false} />)

  expect(container).toBeEmptyDOMElement()
})

test('a signed-out visitor is not shown a streak at all', () => {
  const { container } = render(<StreakBadge days={null} atRisk={false} />)

  expect(container).toBeEmptyDOMElement()
})
