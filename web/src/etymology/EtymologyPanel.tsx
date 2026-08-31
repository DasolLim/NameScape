import { useState } from 'react'

import { CorrectionError, correctEtymology } from '../api/etymology'
import type { PlaceDetail } from '../api/places'
import { useAuth } from '../auth/store'

/** The interface is English, so an English name needs no translating. */
const READER_LANGUAGE = 'en'

const MAX_CORRECTION = 500

/**
 * How each tier is presented.
 *
 * The whole point of the confidence field is that these do not look alike. A
 * model's guess and a cited source both arrive as a fluent sentence about a
 * name, and only one of them is evidence. The distinction is carried in words,
 * not only in colour: a reader who cannot see the treatment still has to be
 * told which they are looking at.
 */
const TREATMENTS = {
  high: {
    label: 'Sourced',
    note: null,
    chip: 'bg-verdigris-500/12 text-verdigris-300 ring-verdigris-700/60',
    body: 'text-parchment-50',
  },
  medium: {
    label: 'From a known name element',
    note: 'Read from the name itself, so it may not be the whole story here.',
    chip: 'bg-brass-500/12 text-brass-300 ring-brass-700/60',
    body: 'text-parchment-50',
  },
  unverified: {
    label: 'Unverified',
    note: 'Written by a language model, not from a source. It may be wrong.',
    chip: 'bg-ink-700 text-parchment-200 ring-ink-600',
    body: 'text-parchment-200 italic',
  },
} as const

type Tier = keyof typeof TREATMENTS

interface EtymologyPanelProps {
  place: PlaceDetail
}

export default function EtymologyPanel({ place }: EtymologyPanelProps) {
  const [open, setOpen] = useState(false)
  const [correcting, setCorrecting] = useState(false)
  const [draft, setDraft] = useState('')
  const [filed, setFiled] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const requireAuth = useAuth((state) => state.requireAuth)

  // Tapping a name you can already read to be told what it means is noise.
  if (!place.name_language || place.name_language === READER_LANGUAGE) return null

  const tier = (
    place.etymology && place.etymology_confidence && place.etymology_confidence in TREATMENTS
      ? place.etymology_confidence
      : null
  ) as Tier | null
  const treatment = tier ? TREATMENTS[tier] : null
  // A URL is citable; a lexicon marker and a model id are not links.
  const sourceUrl = place.etymology_source?.startsWith('http') ? place.etymology_source : null

  function file() {
    requireAuth(() => {
      setError(null)
      correctEtymology(place.id, draft.trim())
        .then(() => {
          setFiled(true)
          setCorrecting(false)
          setDraft('')
        })
        .catch((thrown: unknown) => {
          setError(thrown instanceof CorrectionError ? thrown.message : 'That did not work.')
        })
    })
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-3 text-sm font-medium text-brass-500 hover:text-brass-300"
      >
        What it actually means
      </button>
    )
  }

  return (
    <section data-testid="etymology" className="mt-3 rounded-surface bg-ink-900 p-4">
      {treatment ? (
        <>
          <p className={`text-sm leading-relaxed ${treatment.body}`}>{place.etymology}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${treatment.chip}`}
            >
              {treatment.label}
            </span>
            {sourceUrl && (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-verdigris-300 underline hover:text-verdigris-500"
              >
                Source
              </a>
            )}
          </div>
          {treatment.note && (
            <p className="mt-2 text-xs text-parchment-400">{treatment.note}</p>
          )}
        </>
      ) : (
        <p className="text-sm text-parchment-200">
          Nobody has established what this name means. If you know, the atlas would like to.
        </p>
      )}

      {filed && (
        <p className="mt-3 text-xs text-verdigris-300">
          Filed. Every correction is reviewed by a person before it stands, so it will not
          appear straight away.
        </p>
      )}

      {!correcting && !filed && (
        <button
          type="button"
          onClick={() => (treatment ? setCorrecting(true) : requireAuth(() => setCorrecting(true)))}
          className="mt-3 text-xs font-medium text-brass-500 hover:text-brass-300"
        >
          {treatment ? 'Correct this' : 'Tell us what it means'}
        </button>
      )}

      {correcting && (
        <div className="mt-3">
          <label htmlFor="correction" className="block text-xs text-parchment-200">
            What it really means
          </label>
          <textarea
            id="correction"
            rows={3}
            value={draft}
            maxLength={MAX_CORRECTION}
            onChange={(event) => setDraft(event.target.value.slice(0, MAX_CORRECTION))}
            className="mt-1 w-full rounded-control bg-ink-950 px-3 py-2 text-sm text-parchment-50 ring-1 ring-ink-600 focus:outline-none focus:ring-brass-500"
          />
          {error && (
            <p role="alert" className="mt-2 text-xs text-wax-500">
              {error}
            </p>
          )}
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              disabled={!draft.trim()}
              onClick={file}
              className="rounded-control bg-brass-500 px-3 py-1.5 text-xs font-medium text-brass-900 disabled:opacity-50"
            >
              Send it
            </button>
            <button
              type="button"
              onClick={() => setCorrecting(false)}
              className="text-xs text-parchment-400 hover:text-parchment-200"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
