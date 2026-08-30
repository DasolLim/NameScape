import { useCallback, useEffect, useRef, useState } from 'react'

import GlobeCanvas from './GlobeCanvas'
import { fetchHealth, healthSummary, type Health } from './api/health'
import type { SearchResult } from './api/search'
import { fetchViewport, toLayerState } from './api/viewport'
import type { GlobeHandle, PlaceRef } from './globe'
import { fetchPlace, type PlaceDetail } from './api/places'
import SignInSheet from './auth/SignInSheet'
import BookmarkStar from './bookmarks/BookmarkStar'
import ClaimSheet from './claim/ClaimSheet'
import ContestBoard from './contests/ContestBoard'
import Passport from './passport/Passport'
import { useAuth } from './auth/store'
import SearchOverlay from './search/SearchOverlay'

function toPlaceRef(place: SearchResult): PlaceRef {
  const featureClass = place.feature_class
  return {
    id: String(place.id),
    lon: place.lon,
    lat: place.lat,
    featureClass:
      featureClass === 'P' || featureClass === 'H' || featureClass === 'T'
        ? featureClass
        : undefined,
  }
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const globe = useRef<GlobeHandle | null>(null)

  const [place, setPlace] = useState<PlaceDetail | null>(null)
  const [showBookmarks, setShowBookmarks] = useState(true)
  const [showNicknames, setShowNicknames] = useState(true)
  const [passportOpen, setPassportOpen] = useState(false)
  const toggles = useRef({ bookmarks: true, nicknames: true })
  const user = useAuth((state) => state.user)
  const requireAuth = useAuth((state) => state.requireAuth)
  const loadAuth = useAuth((state) => state.load)
  const openSignIn = useAuth((state) => state.openSignIn)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
    void loadAuth()
  }, [loadAuth])

  const onReady = useCallback((handle: GlobeHandle) => {
    globe.current = handle

    // The idle spin settles constantly, so an un-debounced fetch would hit the
    // viewport endpoint once per frame the drift pauses on.
    let pending: ReturnType<typeof setTimeout> | undefined
    handle.onViewportChange((bounds) => {
      clearTimeout(pending)
      pending = setTimeout(() => {
        void fetchViewport(bounds)
          .then((data) => handle.setLayers(toLayerState(data, toggles.current)))
          .catch(() => undefined)
      }, 300)
    })
  }, [])

  const onSelect = useCallback(
    (result: SearchResult) => {
      void globe.current?.focusOn(toPlaceRef(result))
      // Reading is never gated; claiming is.
      requireAuth(() => {
        void fetchPlace(result.id).then(setPlace).catch(() => setPlace(null))
      })
    },
    [requireAuth],
  )

  return (
    <main className="relative h-full w-full overflow-hidden bg-[#0E131C] text-[#F5F1E8]">
      <GlobeCanvas onReady={onReady} />

      <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-col items-center gap-4 p-6">
        <div className="text-center">
          <h1 className="text-3xl">Toponomicon</h1>
          <p data-testid="health" className="mt-1 text-sm text-[#9B9484]">
            {health ? healthSummary(health) : 'checking\u2026'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <SearchOverlay onSelect={onSelect} />
          <button
            type="button"
            aria-pressed={showBookmarks}
            onClick={() => {
              const next = !showBookmarks
              setShowBookmarks(next)
              toggles.current = { ...toggles.current, bookmarks: next }
              globe.current?.setLayers({ bookmarks: { visible: next, features: [] } })
            }}
            className={`pointer-events-auto rounded-full px-4 py-3 text-sm ${
              showBookmarks ? 'text-[#35A48F]' : 'text-[#6B665C]'
            }`}
          >
            Bookmarks
          </button>
          <button
            type="button"
            aria-pressed={showNicknames}
            onClick={() => {
              const next = !showNicknames
              setShowNicknames(next)
              toggles.current = { ...toggles.current, nicknames: next }
              globe.current?.setLayers({ nicknames: { visible: next, features: [] } })
            }}
            className={`pointer-events-auto rounded-full px-4 py-3 text-sm ${
              showNicknames ? 'text-[#E8A33D]' : 'text-[#6B665C]'
            }`}
          >
            Nicknames
          </button>
          {user ? (
            <button
              type="button"
              onClick={() => setPassportOpen(true)}
              className="pointer-events-auto rounded-full px-4 py-3 text-sm text-[#9B9484] hover:text-[#F5F1E8]"
            >
              @{user.username}
            </button>
          ) : (
            <button
              type="button"
              onClick={openSignIn}
              className="pointer-events-auto rounded-full px-4 py-3 text-sm text-[#9B9484] hover:text-[#F5F1E8]"
            >
              Sign in
            </button>
          )}
        </div>
        <SignInSheet />
        {passportOpen && user && (
          <div className="pointer-events-auto">
            <Passport username={user.username} onClose={() => setPassportOpen(false)} />
          </div>
        )}
        {place && (
          <div className="pointer-events-auto w-[min(26rem,90vw)] text-left">
            <div className="mb-2 flex items-center justify-end">
              <BookmarkStar key={place.id} placeId={place.id} saved={place.bookmarked} />
            </div>
            <ClaimSheet place={place} onClaimed={() => undefined} />
            <div className="mt-3">
              <ContestBoard placeId={place.id} />
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
