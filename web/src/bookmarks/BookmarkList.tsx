import { useEffect, useState } from 'react'

import { fetchBookmarks, type SavedPlace } from '../api/bookmarks'

interface BookmarkListProps {
  onSelect: (place: SavedPlace) => void
  onClose: () => void
  showOnGlobe: boolean
  onToggleGlobe: (visible: boolean) => void
}

export default function BookmarkList({
  onSelect,
  onClose,
  showOnGlobe,
  onToggleGlobe,
}: BookmarkListProps) {
  const [saved, setSaved] = useState<SavedPlace[] | null>(null)

  useEffect(() => {
    fetchBookmarks()
      .then(setSaved)
      .catch(() => setSaved([]))
  }, [])

  return (
    <section
      aria-label="Bookmarks"
      className="w-[min(24rem,92vw)] rounded-xl bg-[#151C28] p-5 text-left ring-1 ring-[#2B3646]"
    >
      <header className="flex items-center justify-between">
        <h2 className="text-sm text-[#D6D0C2]">Bookmarks</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close bookmarks"
          className="rounded-full px-3 py-2 text-[#9B9484] hover:text-[#F5F1E8]"
        >
          ✕
        </button>
      </header>

      <button
        type="button"
        role="switch"
        aria-checked={showOnGlobe}
        onClick={() => onToggleGlobe(!showOnGlobe)}
        className="mt-3 flex w-full items-center justify-between rounded-lg bg-[#1E2735] px-3 py-3 text-xs text-[#D6D0C2]"
      >
        <span>Show on the globe</span>
        <span className={showOnGlobe ? 'text-[#35A48F]' : 'text-[#6B665C]'}>
          {showOnGlobe ? 'On' : 'Off'}
        </span>
      </button>

      {saved === null ? null : saved.length === 0 ? (
        <p className="mt-4 text-sm text-[#9B9484]">
          Nothing saved yet — tap the star on any place to keep it here.
        </p>
      ) : (
        <ul className="mt-3 max-h-80 space-y-1 overflow-y-auto">
          {saved.map((place) => (
            <li key={place.place_id}>
              <button
                type="button"
                onClick={() => onSelect(place)}
                className="flex w-full items-baseline justify-between gap-3 rounded-lg px-3 py-3 text-left text-sm text-[#F5F1E8] hover:bg-[#1E2735]"
              >
                <span>{place.name}</span>
                <span className="text-xs text-[#9B9484]">{place.country_code ?? '—'}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
