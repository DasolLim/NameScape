export const STAR_COUNT = 240

export interface Star {
  x: number
  y: number
  r: number
  o: number
}

/**
 * A deterministic field. A seeded generator rather than Math.random so the
 * sky is identical on every render and between server and client - a
 * reshuffling starfield reads as flicker.
 */
export function starsFor(count: number): Star[] {
  let seed = 0x2f6e2b1
  const next = () => {
    // xorshift32: small, fast, and stable across engines.
    seed ^= seed << 13
    seed ^= seed >>> 17
    seed ^= seed << 5
    return ((seed >>> 0) % 100000) / 100000
  }

  return Array.from({ length: count }, () => {
    const depth = next()
    return {
      x: Math.round(next() * 10000) / 100,
      y: Math.round(next() * 10000) / 100,
      // Most stars are faint and small; a few are close and bright.
      r: depth > 0.97 ? 1.4 : depth > 0.85 ? 1 : 0.6,
      o: 0.25 + depth * 0.65,
    }
  })
}

export default function Starfield() {
  const reducedMotion =
    globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  const stars = starsFor(STAR_COUNT)

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full"
      preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 100 100"
    >
      <defs>
        {/* Deep space, not flat black: the ink ramp taken one stop further. */}
        <radialGradient id="deep-space" cx="50%" cy="45%" r="75%">
          <stop offset="0%" stopColor="#141C2B" />
          <stop offset="55%" stopColor="#0B1018" />
          <stop offset="100%" stopColor="#05070C" />
        </radialGradient>
        {/* A faint wash of verdigris and brass, far too dim to compete with
            the map but enough that the void is not uniform. */}
        <radialGradient id="nebula-cool" cx="22%" cy="26%" r="42%">
          <stop offset="0%" stopColor="#35A48F" stopOpacity="0.13" />
          <stop offset="100%" stopColor="#35A48F" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="nebula-warm" cx="80%" cy="76%" r="46%">
          <stop offset="0%" stopColor="#E8A33D" stopOpacity="0.1" />
          <stop offset="100%" stopColor="#E8A33D" stopOpacity="0" />
        </radialGradient>
      </defs>

      <rect width="100" height="100" fill="url(#deep-space)" />
      <rect width="100" height="100" fill="url(#nebula-cool)" />
      <rect width="100" height="100" fill="url(#nebula-warm)" />

      {stars.map((star, index) => (
        <circle
          key={index}
          cx={star.x}
          cy={star.y}
          r={star.r / 6}
          fill="#F5F1E8"
          opacity={star.o}
        >
          {!reducedMotion && star.r > 1 && (
            <animate
              attributeName="opacity"
              values={`${star.o};${star.o * 0.45};${star.o}`}
              dur={`${3 + (index % 5)}s`}
              repeatCount="indefinite"
            />
          )}
        </circle>
      ))}
    </svg>
  )
}
