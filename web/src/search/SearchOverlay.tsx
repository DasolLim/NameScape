import { useEffect, useRef, useState } from 'react'

import { searchPlaces, type SearchResult } from '../api/search'

const DEBOUNCE_MS = 150

/** Mac shows the command glyph; everything else says Ctrl. */
const SHORTCUT_LABEL =
  typeof navigator !== 'undefined' && /Mac|iP(hone|ad)/.test(navigator.platform ?? '')
    ? '⌘K'
    : 'Ctrl K'

/** P populated, H hydrographic, T terrain. */
const FEATURE_GLYPH: Record<string, string> = { P: '●', H: '≈', T: '▲' }

interface SearchOverlayProps {
  onSelect: (place: SearchResult) => void
}

export default function SearchOverlay({ onSelect }: SearchOverlayProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [active, setActive] = useState(-1)
  const [searched, setSearched] = useState(false)
  const [broadened, setBroadened] = useState(false)

  const triggerRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const hasOpened = useRef(false)

  useEffect(() => {
    if (open) {
      hasOpened.current = true
      inputRef.current?.focus()
      return
    }
    if (hasOpened.current) triggerRef.current?.focus()
  }, [open])

  // Search is the product, so it gets the shortcut people already expect.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      setOpen(true)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (!open) return
    const text = query.trim()
    if (!text) {
      setResults([])
      setSearched(false)
      return
    }

    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(text, controller.signal, broadened)
        .then((found) => {
          setResults(found)
          setSearched(true)
          setActive(-1)
        })
        .catch(() => undefined)
    }, DEBOUNCE_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, open, broadened])

  function close() {
    setOpen(false)
    setQuery('')
    setResults([])
    setSearched(false)
    setBroadened(false)
    setActive(-1)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      close()
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, results.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
      return
    }
    if (event.key === 'Enter') {
      const chosen = results[active]
      if (chosen) {
        onSelect(chosen)
        close()
      }
    }
  }

  if (!open) {
    return (
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        // The label stays on the element at every width, so the control has
        // the same name whether or not there is room to print it.
        aria-label="Search places"
        className="flex min-h-11 w-full min-w-11 items-center justify-center gap-2.5 rounded-control bg-ink-900 px-2.5 text-sm text-parchment-400 ring-1 ring-ink-600 hover:bg-ink-800 hover:text-parchment-200 sm:min-h-0 sm:justify-start sm:px-3.5 sm:py-2.5"
      >
        <span aria-hidden="true" className="text-base text-parchment-200 sm:text-sm sm:text-parchment-600">
          ⌕
        </span>
        <span aria-hidden="true" className="hidden flex-1 whitespace-nowrap text-left sm:block">
          Search places
        </span>
        <kbd
          aria-hidden="true"
          className="hidden rounded border border-ink-600 px-1.5 py-0.5 text-[11px] text-parchment-600 sm:block"
        >
          {SHORTCUT_LABEL}
        </kbd>
      </button>
    )
  }

  return (
    <div className="relative w-full">
      {/* The field stays in the chrome; only the results overlay the map, so
          the bar never changes height as you type. */}
      <input
        ref={inputRef}
        role="combobox"
        aria-expanded={results.length > 0}
        aria-controls="search-results"
        aria-label="Search places"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setBroadened(false)
        }}
        onKeyDown={onKeyDown}
        placeholder="Dildo, Batman, Truth or Consequences…"
        className="w-full rounded-control bg-ink-900 px-3.5 py-2.5 text-sm text-parchment-50 ring-1 ring-brass-700/70 outline-none placeholder:text-parchment-600"
      />

      {(results.length > 0 || (searched && results.length === 0)) && (
        <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-surface bg-ink-800 shadow-2xl ring-1 ring-ink-600">
          {results.length > 0 && (
            <ul id="search-results" role="listbox" className="max-h-80 overflow-y-auto">
              {results.map((place, index) => (
                <li
                  key={place.id}
                  role="option"
                  aria-selected={index === active}
                  onMouseDown={() => {
                    onSelect(place)
                    close()
                  }}
                  className={`flex cursor-pointer items-baseline gap-3 px-4 py-2.5 text-sm not-first:border-t not-first:border-ink-600/50 ${
                    index === active ? 'bg-ink-700 text-brass-300' : 'text-parchment-50'
                  }`}
                >
                  <span aria-hidden="true" className="text-parchment-400">
                    {FEATURE_GLYPH[place.feature_class] ?? '●'}
                  </span>
                  <span className="flex-1 truncate">{place.name}</span>
                  <span className="shrink-0 text-xs text-parchment-400">
                    {[place.admin1, place.country_code].filter(Boolean).join(' · ') || '·'}
                  </span>
                  <span
                    className={`text-xs ${
                      place.claimed_by ? 'text-brass-500' : 'text-parchment-600'
                    }`}
                  >
                    {place.claimed_by ? `@${place.claimed_by}` : 'unclaimed'}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {searched && results.length === 0 && (
            <div className="px-4 py-4 text-sm text-parchment-400">
              <p>{broadened ? 'Still nothing by that name.' : 'Nothing here by that name.'}</p>
              {!broadened && (
                <button
                  type="button"
                  className="mt-2 text-brass-300 underline underline-offset-4"
                  onClick={() => setBroadened(true)}
                >
                  Search worldwide
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
