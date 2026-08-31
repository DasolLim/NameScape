import { useEffect, useRef, useState } from 'react'

export interface Layers {
  discoveries: boolean
  bookmarks: boolean
  nicknames: boolean
}

const ITEMS: { key: keyof Layers; label: string; swatch: string }[] = [
  { key: 'discoveries', label: 'Discoveries', swatch: 'bg-brass-500' },
  { key: 'bookmarks', label: 'Bookmarks', swatch: 'bg-verdigris-500' },
  { key: 'nicknames', label: 'Nicknames', swatch: 'bg-brass-300' },
]

interface LayersMenuProps {
  layers: Layers
  onChange: (layers: Layers) => void
}

/**
 * One control for what the globe draws. Three separate top-level toggles cost
 * three of the four navigation slots and told nobody they were related.
 */
export default function LayersMenu({ layers, onChange }: LayersMenuProps) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)

  const hidden = ITEMS.filter((item) => !layers[item.key]).length

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      trigger.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <div className="relative">
      <button
        ref={trigger}
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={hidden ? `Layers, ${hidden} hidden` : 'Layers'}
        onClick={() => setOpen((was) => !was)}
        className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-control px-2 text-sm text-parchment-200 hover:bg-ink-800 hover:text-parchment-50 sm:min-h-0 sm:min-w-0 sm:justify-start sm:px-3 sm:py-2"
      >
        <span aria-hidden="true">☰</span>
        <span className="hidden sm:inline">Layers</span>
        {hidden > 0 && (
          <span
            aria-hidden="true"
            className="rounded-full bg-ink-700 px-1.5 text-xs text-parchment-400"
          >
            {hidden}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-20 mt-2 w-56 overflow-hidden rounded-surface bg-ink-800 p-1 ring-1 ring-ink-600"
        >
          {ITEMS.map((item) => (
            <button
              key={item.key}
              role="menuitemcheckbox"
              aria-checked={layers[item.key]}
              type="button"
              onClick={() => onChange({ ...layers, [item.key]: !layers[item.key] })}
              className="flex w-full items-center gap-3 rounded-control px-3 py-2.5 text-left text-sm text-parchment-50 hover:bg-ink-700"
            >
              <span
                aria-hidden="true"
                className={`h-2 w-2 shrink-0 rounded-full ${item.swatch} ${
                  layers[item.key] ? '' : 'opacity-25'
                }`}
              />
              <span className="flex-1">{item.label}</span>
              <span aria-hidden="true" className="text-parchment-400">
                {layers[item.key] ? '✓' : ''}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
