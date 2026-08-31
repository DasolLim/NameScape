import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'

import LayersMenu from './LayersMenu'

const LAYERS = { discoveries: true, bookmarks: true, nicknames: true }

test('the menu is closed until asked for', () => {
  render(<LayersMenu layers={LAYERS} onChange={vi.fn()} />)

  expect(screen.getByRole('button', { name: /layers/i })).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
})

test('it groups the map layers behind one control', async () => {
  const user = userEvent.setup()
  render(<LayersMenu layers={LAYERS} onChange={vi.fn()} />)

  await user.click(screen.getByRole('button', { name: /layers/i }))

  const items = screen.getAllByRole('menuitemcheckbox')
  expect(items).toHaveLength(3)
  for (const name of ['Discoveries', 'Bookmarks', 'Nicknames']) {
    expect(screen.getByRole('menuitemcheckbox', { name })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  }
})

test('toggling one reports just that change', async () => {
  const onChange = vi.fn()
  const user = userEvent.setup()
  render(<LayersMenu layers={LAYERS} onChange={onChange} />)

  await user.click(screen.getByRole('button', { name: /layers/i }))
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Nicknames' }))

  expect(onChange).toHaveBeenCalledWith({ ...LAYERS, nicknames: false })
})

test('Escape closes it and returns focus to the trigger', async () => {
  const user = userEvent.setup()
  render(<LayersMenu layers={LAYERS} onChange={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: /layers/i }))

  await user.keyboard('{Escape}')

  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /layers/i })).toHaveFocus()
})

test('the count of hidden layers is surfaced on the trigger', async () => {
  render(<LayersMenu layers={{ ...LAYERS, nicknames: false }} onChange={vi.fn()} />)

  expect(screen.getByRole('button', { name: /layers/i })).toHaveAccessibleName(/1 hidden/i)
})
