import { useEffect, useState } from 'react'

const MINUTE = 60_000
const HOUR = 60 * MINUTE

function remaining(closesAt: string): string {
  const left = new Date(closesAt).getTime() - Date.now()
  // Never negative: a finished contest reads as closed, not as minus four hours.
  if (left <= 0) return 'Closed'
  const hours = Math.floor(left / HOUR)
  const minutes = Math.floor((left % HOUR) / MINUTE)
  return `${hours}h ${minutes}m`
}

export default function Countdown({ closesAt }: { closesAt: string | null }) {
  const [label, setLabel] = useState(() => (closesAt ? remaining(closesAt) : 'Closed'))

  useEffect(() => {
    if (!closesAt) return
    const tick = () => setLabel(remaining(closesAt))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [closesAt])

  return (
    <span data-testid="countdown" className="text-xs tabular-nums text-[#E8A33D]">
      {label}
    </span>
  )
}
