import { useEffect, useRef } from 'react'

interface StampBadgeProps {
  finder: string
  placeName: string
}

/** The emotional peak of the product: the pin lands with overshoot and a brass pulse. */
export default function StampBadge({ finder, placeName }: StampBadgeProps) {
  const reducedMotion = useRef(
    globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  )

  useEffect(() => {
    if (reducedMotion.current) return
    // A short, sharp thunk. Ignored on desktop, where vibrate is undefined.
    globalThis.navigator?.vibrate?.(12)
  }, [])

  const animation = reducedMotion.current ? 'stamp-fade' : 'stamp-drop'

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
      <div className={`animate-[${animation}_400ms_cubic-bezier(0.34,1.56,0.64,1)] text-center`}>
        <p className="text-xs uppercase tracking-widest text-[#9B9484]">First finder</p>
        <p className="mt-1 font-serif text-2xl text-[#E8A33D]">@{finder}</p>
        <p className="mt-1 text-sm text-[#D6D0C2]">{placeName}</p>
      </div>
    </div>
  )
}
