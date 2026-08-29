import { useCallback, useEffect, useRef, useState } from 'react'

import GlobeCanvas from './GlobeCanvas'
import { fetchHealth, healthSummary, type Health } from './api/health'
import type { SearchResult } from './api/search'
import type { GlobeHandle, PlaceRef } from './globe'
import SignInSheet from './auth/SignInSheet'
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

  const user = useAuth((state) => state.user)
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
  }, [])

  const onSelect = useCallback((place: SearchResult) => {
    void globe.current?.focusOn(toPlaceRef(place))
  }, [])

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
      </div>
    </main>
  )
}
