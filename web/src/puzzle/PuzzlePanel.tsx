import { useEffect, useRef, useState } from 'react'

import { searchPlaces, type SearchResult } from '../api/search'
import {
  fetchArchive,
  fetchPuzzle,
  PuzzleError,
  submitGuess,
  type ArchiveEntry,
  type PuzzleGuess,
  type PuzzleState,
} from '../api/puzzle'
import { useAuth } from '../auth/store'

const DEBOUNCE_MS = 150

/** Bands to markers. The API sends the band; the marker is presentation. */
const MARKERS: Record<string, string> = {
  correct: '🟩',
  near: '🟨',
  far: '🟧',
  cold: '⬜',
}

/**
 * A habit takes two days to start.
 *
 * Asking after one solve spends the ask before it means anything, which is the
 * whole reason the prompt waits. Streaks are stored against accounts, so this
 * is also the moment an account starts being worth something.
 */
const HABIT_STARTED = 2

interface PuzzlePanelProps {
  /** Draw the pin clue on the globe. The globe module owns the map. */
  onFocusPlace: (at: { lat: number; lon: number }) => void
  onClaim: (placeId: number) => void
  /** Test seam: skips the initial fetch. */
  initialState?: PuzzleState
}

export default function PuzzlePanel({
  onFocusPlace,
  onClaim,
  initialState,
}: PuzzlePanelProps) {
  const [state, setState] = useState<PuzzleState | null>(initialState ?? null)
  const [loaded, setLoaded] = useState(Boolean(initialState))
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<SearchResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [archive, setArchive] = useState<ArchiveEntry[] | null>(null)
  const [archiveNote, setArchiveNote] = useState<string | null>(null)

  const signedIn = useAuth((store) => store.status === 'signed-in')
  const reducedMotion = useRef(
    globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  )

  useEffect(() => {
    if (initialState) return
    void fetchPuzzle()
      .then(setState)
      .catch(() => setState(null))
      .finally(() => setLoaded(true))
  }, [initialState])

  // The pin is the fifth clue, and it is a place rather than a sentence.
  const pin = state?.pin
  useEffect(() => {
    if (pin) onFocusPlace({ lat: pin.lat, lon: pin.lon })
  }, [pin, onFocusPlace])

  useEffect(() => {
    const text = query.trim()
    if (text.length < 2) {
      setOptions([])
      return
    }
    const timer = setTimeout(() => {
      void searchPlaces(text)
        .then((results) => setOptions(results.slice(0, 6)))
        .catch(() => setOptions([]))
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query])

  function guess(placeId: number) {
    if (!state) return
    setError(null)
    setQuery('')
    setOptions([])
    submitGuess(state.puzzle_id, placeId)
      .then(setState)
      .catch((thrown: unknown) => {
        setError(thrown instanceof PuzzleError ? thrown.message : 'That did not work.')
      })
  }

  function share() {
    if (!state?.share_grid) return
    void navigator.clipboard
      ?.writeText(state.share_grid)
      .then(() => setCopied(true))
      .catch(() => setError('Could not copy. Select the text and copy it by hand.'))
  }

  function openArchive() {
    setArchiveNote(null)
    fetchArchive()
      .then(setArchive)
      .catch((thrown: unknown) => {
        // The refusal explains what an account is for; pass it through rather
        // than replacing it with something vaguer.
        setArchiveNote(
          thrown instanceof PuzzleError ? thrown.message : 'Could not load past puzzles.',
        )
      })
  }

  if (!loaded) return null

  if (!state) {
    return (
      <section className="rounded-surface bg-ink-800 p-5 ring-1 ring-ink-600">
        <h2 className="font-display text-lg text-parchment-50">No puzzle today</h2>
        <p className="mt-1 text-sm text-parchment-400">
          There will be one tomorrow. Every puzzle is read by a person before it runs, and
          today&rsquo;s did not make it.
        </p>
      </section>
    )
  }

  const answer = state.answer
  const askAboutStreak = state.complete && !signedIn && state.streak >= HABIT_STARTED

  return (
    <section
      data-testid="puzzle"
      className="rounded-surface bg-ink-800 p-5 ring-1 ring-ink-600"
    >
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-lg text-parchment-50">
          Today&rsquo;s place <span className="text-parchment-400">#{state.number}</span>
        </h2>
        {!state.complete && (
          <p className="text-xs tabular-nums text-parchment-400">
            {state.remaining} guesses left
          </p>
        )}
      </header>

      <ol className="mt-3 space-y-2">
        {state.clues.map((clue, index) => (
          <li
            key={clue}
            data-testid={`clue-${index}`}
            className={`rounded-control bg-ink-900 px-3 py-2 text-sm text-parchment-50 ${
              reducedMotion.current ? '' : 'animate-[stamp-fade_300ms_ease-out]'
            }`}
          >
            {clue}
          </li>
        ))}
      </ol>

      {state.guesses.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {state.guesses.map((made: PuzzleGuess, index) => (
            <li
              key={`${made.place_id}-${index}`}
              data-testid={`guess-${index}`}
              className="flex items-center gap-2 rounded-control bg-ink-900 px-3 py-2 text-sm"
            >
              <span aria-hidden="true">{MARKERS[made.band] ?? '⬜'}</span>
              <span className="flex-1 truncate text-parchment-200">{made.name}</span>
              {made.band !== 'correct' && (
                <>
                  <span className="tabular-nums text-parchment-400">
                    {Math.round(made.distance_km)} km
                  </span>
                  <span aria-hidden="true">{made.arrow}</span>
                  <span className="w-10 text-right tabular-nums text-parchment-400">
                    {made.proximity}%
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {!state.complete && (
        <div className="relative mt-4">
          <label htmlFor="puzzle-guess" className="block text-xs text-parchment-200">
            Your guess
          </label>
          <input
            id="puzzle-guess"
            role="combobox"
            aria-expanded={options.length > 0}
            aria-controls="puzzle-options"
            autoComplete="off"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="mt-1 w-full rounded-control bg-ink-950 px-3 py-2 text-sm text-parchment-50 ring-1 ring-ink-600 focus:outline-none focus:ring-brass-500"
          />
          {options.length > 0 && (
            <ul
              id="puzzle-options"
              role="listbox"
              className="absolute left-0 right-0 z-10 mt-1 overflow-hidden rounded-control bg-ink-900 ring-1 ring-ink-600"
            >
              {options.map((option) => (
                <li key={option.id} role="option" aria-selected={false}>
                  <button
                    type="button"
                    onClick={() => guess(option.id)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-parchment-50 hover:bg-ink-700"
                  >
                    <span className="flex-1 truncate">{option.name}</span>
                    <span className="shrink-0 text-xs text-parchment-400">
                      {[option.admin1, option.country_code].filter(Boolean).join(' · ')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-wax-500">
          {error}
        </p>
      )}

      {state.complete && answer && (
        <div className="mt-4 border-t border-ink-600 pt-4">
          <p className="text-xs uppercase tracking-widest text-parchment-400">
            {state.solved ? 'Solved' : 'It was'}
          </p>
          <p data-testid="puzzle-answer" className="mt-1 font-display text-xl text-brass-300">
            {answer.name}
          </p>
          {answer.country_code && (
            <p className="text-sm text-parchment-400">{answer.country_code}</p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {answer.claimed_by ? (
              <p className="text-sm text-parchment-200">
                Found by <span className="text-verdigris-300">@{answer.claimed_by}</span>
              </p>
            ) : (
              <button
                type="button"
                onClick={() => onClaim(answer.place_id)}
                className="rounded-control bg-brass-500 px-3.5 py-2 text-sm font-medium text-brass-900 hover:bg-brass-300"
              >
                Claim it
              </button>
            )}
            <button
              type="button"
              onClick={share}
              className="rounded-control px-3 py-2 text-sm text-parchment-200 ring-1 ring-ink-600 hover:bg-ink-700"
            >
              Share
            </button>
            <button
              type="button"
              onClick={openArchive}
              className="text-sm text-parchment-400 hover:text-parchment-200"
            >
              Past puzzles
            </button>
          </div>

          {copied && <p className="mt-2 text-xs text-verdigris-300">Copied.</p>}

          {askAboutStreak && (
            <p
              data-testid="streak-prompt"
              className="mt-3 rounded-control bg-ink-900 p-3 text-sm text-parchment-200"
            >
              That is {state.streak} days in a row. Create an account and the streak is
              kept.
            </p>
          )}

          {archiveNote && <p className="mt-3 text-sm text-parchment-200">{archiveNote}</p>}

          {archive && (
            <ul className="mt-3 space-y-1 text-sm text-parchment-200">
              {archive.map((entry) => (
                <li key={entry.puzzle_id} className="flex items-center gap-2">
                  <span className="tabular-nums text-parchment-400">#{entry.number}</span>
                  <span className="flex-1">{entry.date}</span>
                  <span>{entry.solved ? `🟩 ${entry.guesses}/5` : '⬜ X/5'}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
