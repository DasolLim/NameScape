import { useEffect, useState } from 'react'
import { fetchHealth, healthSummary, type Health } from './api/health'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return (
    <main className="grid min-h-screen place-items-center bg-[#0E131C] text-[#F5F1E8]">
      <div className="text-center">
        <h1 className="text-3xl">Toponomicon</h1>
        <p data-testid="health" className="mt-2 text-sm text-[#9B9484]">
          {health ? healthSummary(health) : 'checking…'}
        </p>
      </div>
    </main>
  )
}
