import { useCallback, useEffect, useRef, useState } from 'react'

import GlobeCanvas from './GlobeCanvas'
import { fetchHealth, healthSummary, type Health } from './api/health'
import type { SearchResult } from './api/search'
import type { GlobeHandle, PlaceRef } from './globe'
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

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

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
        <SearchOverlay onSelect={onSelect} />
      </div>
    </main>
  )
}
