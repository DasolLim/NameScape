import { useEffect, useState } from 'react'

import GlobeCanvas from './GlobeCanvas'
import { fetchHealth, healthSummary, type Health } from './api/health'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return (
    <main className="relative h-full w-full overflow-hidden bg-[#0E131C] text-[#F5F1E8]">
      <GlobeCanvas />
      <div className="pointer-events-none absolute inset-x-0 top-0 p-6 text-center">
        <h1 className="text-3xl">Toponomicon</h1>
        <p data-testid="health" className="mt-1 text-sm text-[#9B9484]">
          {health ? healthSummary(health) : 'checking…'}
        </p>
      </div>
    </main>
  )
}
