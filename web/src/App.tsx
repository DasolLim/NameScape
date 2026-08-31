import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchHealth, type Health } from './api/health'
import { fetchPlace, type PlaceDetail } from './api/places'
import type { SearchResult } from './api/search'
import { fetchMyDiscoveries } from './api/passport'
import { fetchViewport, toLayerState } from './api/viewport'
import { completeSignInFromUrl } from './auth/completeSignIn'
import SignInSheet from './auth/SignInSheet'
import { useAuth } from './auth/store'
import BookmarkList from './bookmarks/BookmarkList'
import BookmarkStar from './bookmarks/BookmarkStar'
import type { Layers } from './chrome/LayersMenu'
import TopBar from './chrome/TopBar'
import ClaimSheet, { type HeldClaim } from './claim/ClaimSheet'
import ContestBoard from './contests/ContestBoard'
import EtymologyPanel from './etymology/EtymologyPanel'
import GlobeCanvas from './GlobeCanvas'
import type { GlobeHandle, PlaceRef } from './globe'
import Passport from './passport/Passport'
import PuzzlePanel from './puzzle/PuzzlePanel'
import Starfield from './Starfield'

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
  const [place, setPlace] = useState<PlaceDetail | null>(null)
  const [bookmarksOpen, setBookmarksOpen] = useState(false)
  //: What this visitor already holds. A guest gets one claim, so this is what
  //: tells the sheet to explain itself rather than offer a second.
  const [held, setHeld] = useState<HeldClaim | null>(null)
  const [passportOpen, setPassportOpen] = useState(false)
  const [puzzleOpen, setPuzzleOpen] = useState(false)
  const [layers, setLayers] = useState<Layers>({
    discoveries: true,
    bookmarks: true,
    nicknames: true,
  })

  const globe = useRef<GlobeHandle | null>(null)
  const visible = useRef(layers)

  const user = useAuth((state) => state.user)
  const loadAuth = useAuth((state) => state.load)
  const requireAuth = useAuth((state) => state.requireAuth)

  useEffect(() => {
    // An emailed link lands here with ?token=; exchange it before asking who
    // the visitor is, so a fresh sign-in is not reported as anonymous.
    void completeSignInFromUrl().then(() => loadAuth())
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [loadAuth])

  const loadHeld = useCallback(async () => {
    const found = await fetchMyDiscoveries().catch(() => [])
    // Only a live guest claim constrains anything: an account may hold many.
    const guest = found.find((item) => item.expires_at)
    setHeld(guest ? { placeName: guest.place_name, expiresAt: guest.expires_at ?? null } : null)
  }, [])

  useEffect(() => {
    void loadHeld()
  }, [loadHeld, user])

  const onReady = useCallback((handle: GlobeHandle) => {
    globe.current = handle

    // The idle spin settles constantly, so an un-debounced fetch would hit the
    // viewport endpoint once per frame the drift pauses on.
    let pending: ReturnType<typeof setTimeout> | undefined
    handle.onViewportChange((bounds) => {
      clearTimeout(pending)
      pending = setTimeout(() => {
        void fetchViewport(bounds)
          .then((data) => handle.setLayers(toLayerState(data, visible.current)))
          .catch(() => undefined)
      }, 300)
    })
  }, [])

  const onSelectPlace = useCallback((result: SearchResult) => {
    void globe.current?.focusOn(toPlaceRef(result))
    // Open for everyone. Reading was never meant to be gated, and claiming
    // no longer is either: a guest gets one claim, with a deadline.
    void fetchPlace(result.id)
      .then(setPlace)
      .catch(() => setPlace(null))
  }, [])

  const onLayersChange = useCallback((next: Layers) => {
    setLayers(next)
    visible.current = next
    globe.current?.setLayers({
      discoveries: { visible: next.discoveries, features: [] },
      bookmarks: { visible: next.bookmarks, features: [] },
      nicknames: { visible: next.nicknames, features: [] },
    })
  }, [])

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-ink-950 text-parchment-50">
      <TopBar
        layers={layers}
        onLayersChange={onLayersChange}
        onSelectPlace={onSelectPlace}
        onOpenPuzzle={() => setPuzzleOpen((open) => !open)}
        onOpenBookmarks={() => requireAuth(() => setBookmarksOpen((open) => !open))}
        onOpenPassport={() => setPassportOpen(true)}
      />

      {/* The globe owns everything below the chrome. Surfaces float over it;
          it never unmounts. */}
      <main className="relative flex-1 overflow-hidden">
        <Starfield />
        <GlobeCanvas onReady={onReady} />

        <div className="pointer-events-none absolute inset-0 flex flex-col items-center gap-3 overflow-y-auto p-4">
          <SignInSheet />

          {puzzleOpen && (
            <div className="pointer-events-auto w-[min(26rem,92vw)] text-left">
              <PuzzlePanel
                onFocusPlace={(at) => {
                  // The globe module owns the map; this asks it to look.
                  void globe.current?.focusOn({
                    id: 'puzzle-pin',
                    lon: at.lon,
                    lat: at.lat,
                    featureClass: 'P',
                  })
                }}
                onClaim={(placeId) => {
                  void fetchPlace(placeId)
                    .then((found) => {
                      setPlace(found)
                      setPuzzleOpen(false)
                    })
                    .catch(() => undefined)
                }}
              />
            </div>
          )}

          {bookmarksOpen && user && (
            <div className="pointer-events-auto">
              <BookmarkList
                onClose={() => setBookmarksOpen(false)}
                showOnGlobe={layers.bookmarks}
                onToggleGlobe={(bookmarks) => onLayersChange({ ...layers, bookmarks })}
                onSelect={(saved) => {
                  void globe.current?.focusOn({
                    id: String(saved.place_id),
                    lon: saved.lon,
                    lat: saved.lat,
                    featureClass: 'P',
                  })
                }}
              />
            </div>
          )}

          {passportOpen && user && (
            <div className="pointer-events-auto">
              <Passport username={user.username} onClose={() => setPassportOpen(false)} />
            </div>
          )}

          {place && (
            <div className="pointer-events-auto w-[min(26rem,92vw)] text-left">
              <div className="mb-2 flex items-center justify-end">
                <BookmarkStar
                  key={place.id}
                  placeId={place.id}
                  saved={place.bookmarked}
                />
              </div>
              <ClaimSheet
                place={place}
                heldClaim={held}
                onClaimed={() => void loadHeld()}
              />
              <EtymologyPanel place={place} />
              <div className="mt-3">
                <ContestBoard placeId={place.id} />
              </div>
            </div>
          )}
        </div>

        {/* Kept, but out of the wordmark's way: this is operator information,
            not part of the product's identity. */}
        <p
          data-testid="health"
          className="pointer-events-none absolute bottom-2 left-3 text-[11px] text-parchment-600"
        >
          {health ? (health.db && health.redis ? '' : 'service degraded') : ''}
        </p>
      </main>
    </div>
  )
}
