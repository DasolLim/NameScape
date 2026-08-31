import { useEffect, useRef, useState } from 'react'

import Countdown from './Countdown'

/** Matches the animation durations below. */
const SETTLE_MS = 400

//: Written out rather than built from a variable. Tailwind scans source text,
//: so `animate-[${name}_400ms]` generates no class at all: the keyframes ship
//: and the utility does not, and the stamp silently stops animating.
const DROP = 'animate-[stamp-drop_400ms_cubic-bezier(0.34,1.56,0.64,1)]'
const FADE = 'animate-[stamp-fade_400ms_ease-out]'

interface StampBadgeProps {
  finder: string
  placeName: string
  /** ISO timestamp, for a guest claim. Absent means the claim is permanent. */
  expiresAt?: string | null
  /** Fired once the stamp has landed, which is when an ask has earned itself. */
  onSettled?: () => void
}

/** The emotional peak of the product: the pin lands with overshoot and a brass pulse. */
export default function StampBadge({
  finder,
  placeName,
  expiresAt,
  onSettled,
}: StampBadgeProps) {
  const reducedMotion = useRef(
    globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  )
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    if (reducedMotion.current) return
    // A short, sharp thunk. Ignored on desktop, where vibrate is undefined.
    globalThis.navigator?.vibrate?.(12)
  }, [])

  // A timer as well as the event, whichever lands first. An animation can be
  // cancelled, interrupted, or never start at all, and none of those should
  // cost the visitor the one prompt that offers to keep their claim.
  useEffect(() => {
    if (!onSettled || settled) return
    const timer = setTimeout(() => {
      setSettled(true)
      onSettled()
    }, SETTLE_MS)
    return () => clearTimeout(timer)
  }, [onSettled, settled])

  function finish() {
    if (settled) return
    setSettled(true)
    onSettled?.()
  }

  return (
    <div
      data-testid="stamp"
      className="relative grid place-items-center rounded-xl bg-[#151C28] p-8 ring-1 ring-[#2B3646]"
    >
      <span
        aria-hidden="true"
        className={`absolute h-24 w-24 rounded-full ring-2 ring-[#E8A33D] ${
          reducedMotion.current ? 'opacity-0' : 'animate-[stamp-pulse_500ms_ease-out_forwards]'
        }`}
      />
      <div
        data-testid="stamp-body"
        onAnimationEnd={finish}
        className={`${reducedMotion.current ? FADE : DROP} text-center`}
      >
        <p className="text-xs uppercase tracking-widest text-[#9B9484]">First finder</p>
        <p className="mt-1 font-serif text-2xl text-[#E8A33D]">@{finder}</p>
        <p className="mt-1 text-sm text-[#D6D0C2]">{placeName}</p>
        {expiresAt && (
          <p className="mt-3">
            <Countdown expiresAt={expiresAt} />
          </p>
        )}
      </div>
    </div>
  )
}
