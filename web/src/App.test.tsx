import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

// jsdom has no WebGL; the globe module has its own tests.
vi.mock('./globe', () => ({
  createGlobe: () => ({
    focusOn: vi.fn(),
    setLayers: vi.fn(),
    onPlaceTap: vi.fn(),
    onViewportChange: vi.fn(() => () => undefined),
    startIdleSpin: vi.fn(),
    stopIdleSpin: vi.fn(),
    destroy: vi.fn(),
  }),
}))

import App from './App'

test('renders the health summary from the API', async () => {
  render(<App />)

  expect(await screen.findByTestId('health')).toHaveTextContent('db ok · redis ok')
})
