import { useEffect, useState } from 'react'

import { fetchActivity, type Activity } from '../api/activity'
import type { SearchResult } from '../api/search'
import { useAuth } from '../auth/store'
import SearchOverlay from '../search/SearchOverlay'
import LayersMenu, { type Layers } from './LayersMenu'
import StreakBadge from './StreakBadge'
import Wordmark from './Wordmark'

interface TopBarProps {
  onOpenPuzzle: () => void
  layers: Layers
  onLayersChange: (layers: Layers) => void
  onSelectPlace: (place: SearchResult) => void
  onOpenBookmarks: () => void
  onOpenPassport: () => void
}

/**
 * A solid chrome layer, not an overlay.
 *
 * The previous chrome put bare text and ghost buttons directly on the map, so
 * legibility depended on whether the user happened to be over ocean, desert
 * or ice. Translucency is the fashionable answer and the wrong one here:
 * blur over dense cartography costs GPU on the one surface that cannot
 * afford it, and it still leaves contrast at the mercy of the basemap.
 */
export default function TopBar({
  onOpenPuzzle,
  layers,
  onLayersChange,
  onSelectPlace,
  onOpenBookmarks,
  onOpenPassport,
}: TopBarProps) {
  const [activity, setActivity] = useState<Activity | null>(null)
  const user = useAuth((state) => state.user)
  const openSignIn = useAuth((state) => state.openSignIn)

  useEffect(() => {
    void fetchActivity().then(setActivity)
  }, [user])

  const closingSoon = activity?.contests_closing_soon ?? 0

  return (
    <header
      role="banner"
      className="pointer-events-auto flex items-center gap-2 border-b border-ink-600 bg-ink-950 px-3 py-2 sm:gap-3 sm:px-4 sm:py-2.5"
    >
      <Wordmark />

      <div className="ml-auto flex shrink-0 items-center gap-2 sm:ml-6 sm:mr-auto sm:max-w-md sm:flex-1">
        <SearchOverlay onSelect={onSelectPlace} />
      </div>

      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {closingSoon > 0 && (
          <button
            type="button"
            data-testid="closing-soon"
            aria-label={`${closingSoon} contests closing within a day`}
            onClick={onOpenBookmarks}
            className="hidden items-center gap-1.5 rounded-full bg-verdigris-500/12 px-3 py-1.5 text-sm font-medium text-verdigris-300 ring-1 ring-verdigris-700/60 sm:inline-flex"
          >
            <span aria-hidden="true">⚡</span>
            {closingSoon}
          </button>
        )}

        <button
          type="button"
          onClick={onOpenPuzzle}
          aria-label="Today's place, the daily puzzle"
          className="min-h-11 min-w-11 rounded-control px-2 text-sm text-parchment-200 hover:bg-ink-800 hover:text-parchment-50 sm:min-h-0 sm:min-w-0 sm:px-3 sm:py-2"
        >
          <span aria-hidden="true" className="sm:hidden">
            ?
          </span>
          <span className="hidden whitespace-nowrap sm:inline">Today&rsquo;s place</span>
        </button>

        <StreakBadge
          days={user ? (activity?.streak_days ?? null) : null}
          atRisk={activity?.streak_at_risk ?? false}
        />

        <button
          type="button"
          aria-label="Bookmarks"
          onClick={onOpenBookmarks}
          className="min-h-11 min-w-11 rounded-control px-2 text-sm text-parchment-200 hover:bg-ink-800 hover:text-parchment-50 sm:min-h-0 sm:min-w-0 sm:px-3 sm:py-2"
        >
          <span aria-hidden="true" className="sm:hidden">
            ★
          </span>
          <span className="hidden sm:inline">Bookmarks</span>
        </button>

        <LayersMenu layers={layers} onChange={onLayersChange} />

        {user ? (
          <button
            type="button"
            onClick={onOpenPassport}
            className="max-w-28 truncate rounded-control px-2 py-2 text-sm font-medium text-parchment-50 hover:bg-ink-800 sm:max-w-40 sm:px-3"
          >
            @{user.username}
          </button>
        ) : (
          <button
            type="button"
            onClick={openSignIn}
            className="whitespace-nowrap rounded-control bg-brass-500 px-3 py-2 text-sm font-medium text-brass-900 hover:bg-brass-300 sm:px-3.5"
          >
            Sign in
          </button>
        )}
      </div>
    </header>
  )
}
