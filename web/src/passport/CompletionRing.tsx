const SIZE = 56
const STROKE = 5
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

interface CompletionRingProps {
  country: string
  found: number
  completion: number
}

export default function CompletionRing({ country, found, completion }: CompletionRingProps) {
  const percent = Math.round(completion * 100)

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        role="progressbar"
        aria-label={`${country} completion`}
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="relative"
      >
        <svg width={SIZE} height={SIZE} aria-hidden="true">
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="#2B3646"
            strokeWidth={STROKE}
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="#E8A33D"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - Math.min(completion, 1))}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          />
        </svg>
        <span className="absolute inset-0 grid place-items-center text-xs tabular-nums text-[#F5F1E8]">
          {found}
        </span>
      </div>
      <span className="text-xs text-[#9B9484]">{country}</span>
    </div>
  )
}
