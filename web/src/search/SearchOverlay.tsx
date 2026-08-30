import { useEffect, useRef, useState } from 'react'

import { searchPlaces, type SearchResult } from '../api/search'

const DEBOUNCE_MS = 150

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
        className="pointer-events-auto rounded-full bg-[#151C28] px-5 py-3 text-sm text-[#D6D0C2] shadow-lg ring-1 ring-[#2B3646] hover:text-[#F5F1E8]"
      >
        Search places
      </button>
    )
  }

  return (
    <div className="pointer-events-auto w-[min(32rem,90vw)] overflow-hidden rounded-xl bg-[#151C28] shadow-2xl ring-1 ring-[#2B3646]">
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
        className="w-full bg-transparent px-5 py-3 text-[#F5F1E8] placeholder:text-[#6B665C] focus:outline-none"
      />

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
              className={`flex cursor-pointer items-baseline gap-3 border-t border-[#2B3646]/60 px-5 py-3 text-sm ${
                index === active ? 'bg-[#1E2735] text-[#E8A33D]' : 'text-[#F5F1E8]'
              }`}
            >
              <span aria-hidden="true" className="text-[#9B9484]">
                {FEATURE_GLYPH[place.feature_class] ?? '●'}
              </span>
              <span className="flex-1">{place.name}</span>
              <span className="text-xs text-[#9B9484]">{place.country_code ?? '—'}</span>
              <span className="text-xs text-[#9B9484]">
                {place.claimed_by ? `@${place.claimed_by}` : 'unclaimed'}
              </span>
            </li>
          ))}
        </ul>
      )}

      {searched && results.length === 0 && (
        <div className="border-t border-[#2B3646]/60 px-5 py-4 text-sm text-[#9B9484]">
          <p>{broadened ? 'Still nothing by that name.' : 'Nothing here by that name.'}</p>
          {!broadened && (
            <button
              type="button"
              className="mt-2 text-[#E8A33D] underline underline-offset-4"
              onClick={() => setBroadened(true)}
            >
              Search worldwide
            </button>
          )}
        </div>
      )}
    </div>
  )
}
