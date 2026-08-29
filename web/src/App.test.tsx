import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import App from './App'

test('renders the health summary from the API', async () => {
  render(<App />)

  expect(await screen.findByTestId('health')).toHaveTextContent('db ok · redis ok')
})
