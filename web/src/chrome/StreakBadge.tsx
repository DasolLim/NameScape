interface StreakBadgeProps {
  /** Null when nobody is signed in. */
  days: number | null
  atRisk: boolean
}

/**
 * The return driver. Streaks work through loss aversion and self-concept
 * ("I'm someone who keeps a streak"), which is why the number is stated
 * plainly rather than dressed up.
 */
export default function StreakBadge({ days, atRisk }: StreakBadgeProps) {
  // A proud zero is a discouragement, not a nudge.
  if (!days) return null

  const label = atRisk
    ? `${days} day streak. Keep it alive today.`
    : `${days} day streak, safe for today.`

  return (
    <span
      data-testid="streak"
      aria-label={label}
      title={label}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ring-1 ${
        atRisk
          ? 'bg-ink-800 text-parchment-400 ring-ink-600'
          : 'bg-brass-500/12 text-brass-300 ring-brass-700/60'
      }`}
    >
      <span aria-hidden="true" className={atRisk ? 'opacity-50' : ''}>
        ◈
      </span>
      {days}
      {/* Stated, not implied by colour: an at-risk streak has to read as
          at-risk to someone who cannot distinguish brass from grey. */}
      {atRisk && <span className="text-xs font-normal">today?</span>}
    </span>
  )
}
