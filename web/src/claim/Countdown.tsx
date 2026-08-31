const HOUR_MS = 3600_000
const DAY_MS = 24 * HOUR_MS

/** Below this, days round the urgency away: "1 day left" for 30 hours is a lie. */
const HOURS_THRESHOLD_MS = 48 * HOUR_MS

interface CountdownProps {
  /** ISO timestamp. */
  expiresAt: string
  className?: string
}

/**
 * How long a guest claim has left.
 *
 * Deliberately coarse. A ticking second counter turns a promise into a threat,
 * and nobody needs to watch a seven day deadline drain in real time.
 */
// Rounded rather than floored throughout: a claim made a moment ago has seven
// days, and greeting the visitor with "6 days left" reads as a day already
// lost to them.
export function remainingLabel(expiresAt: string, now: number = Date.now()): string {
  const left = new Date(expiresAt).getTime() - now
  if (Number.isNaN(left)) return ''
  if (left <= 0) return 'Released'
  if (left < HOUR_MS) return 'Under an hour left'
  if (left < HOURS_THRESHOLD_MS) return `${Math.round(left / HOUR_MS)} hours left`
  return `${Math.round(left / DAY_MS)} days left`
}

export default function Countdown({ expiresAt, className }: CountdownProps) {
  const label = remainingLabel(expiresAt)
  if (!label) return null

  const expires = new Date(expiresAt)
  return (
    <span
      data-testid="claim-countdown"
      // The absolute date as well: a relative countdown alone cannot be
      // checked against a calendar, and this one decides who keeps a place.
      title={`Expires ${expires.toLocaleString()}`}
      className={className ?? 'text-xs font-medium tabular-nums text-brass-300'}
    >
      {label}
    </span>
  )
}
