import { useCallback, useEffect, useRef, useState } from 'react'

import GlobeCanvas from './GlobeCanvas'
import { fetchHealth, healthSummary, type Health } from './api/health'
import type { SearchResult } from './api/search'
import { fetchViewport, toLayerState } from './api/viewport'
import type { GlobeHandle, PlaceRef } from './globe'
import { fetchPlace, type PlaceDetail } from './api/places'
import SignInSheet from './auth/SignInSheet'
import ClaimSheet from './claim/ClaimSheet'
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
    handle.onViewportChange((bounds) => {
      void fetchViewport(bounds)
        .then((data) => handle.setLayers(toLayerState(data)))
        .catch(() => undefined)
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
          {user ? (
            <span className="pointer-events-auto text-sm text-[#9B9484]">@{user.username}</span>
          ) : (
            <button
              type="button"
              onClick={openSignIn}
              className="pointer-events-auto rounded-full px-4 py-2.5 text-sm text-[#9B9484] hover:text-[#F5F1E8]"
            >
              Sign in
            </button>
          )}
        </div>
        <SignInSheet />
        {place && (
          <div className="pointer-events-auto w-[min(26rem,90vw)] text-left">
            <ClaimSheet place={place} onClaimed={() => undefined} />
          </div>
        )}
      </div>
    </main>
  )
}
