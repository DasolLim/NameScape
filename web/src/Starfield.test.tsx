import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import Starfield, { STAR_COUNT, starsFor } from './Starfield'

test('the field is decorative and hidden from assistive technology', () => {
  const { container } = render(<Starfield />)

  expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

test('stars are deterministic, so the sky does not reshuffle on every render', () => {
  expect(starsFor(STAR_COUNT)).toEqual(starsFor(STAR_COUNT))
})

test('stars are spread across the whole field, not clustered in a corner', () => {
  const stars = starsFor(STAR_COUNT)

  expect(stars).toHaveLength(STAR_COUNT)
  expect(stars.every((star) => star.x >= 0 && star.x <= 100)).toBe(true)
  expect(stars.every((star) => star.y >= 0 && star.y <= 100)).toBe(true)
  // Roughly half on each side of the middle.
  const left = stars.filter((star) => star.x < 50).length
  expect(left).toBeGreaterThan(STAR_COUNT * 0.35)
  expect(left).toBeLessThan(STAR_COUNT * 0.65)
})

test('stars vary in size, so the field reads as depth rather than noise', () => {
  const radii = new Set(starsFor(STAR_COUNT).map((star) => star.r))

  expect(radii.size).toBeGreaterThan(2)
})

test('nothing twinkles when reduced motion is asked for', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn() }))
  const { container } = render(<Starfield />)

  expect(container.querySelector('animate')).toBeNull()
  vi.unstubAllGlobals()
})
