import { useAuth } from '../auth/store'
import { remainingLabel } from './Countdown'

interface GuestPromptProps {
  placeName: string
  /** ISO timestamp the claim runs out at. */
  expiresAt: string
  onDismiss: () => void
}

/**
 * The ask, at the one moment it means something.
 *
 * A sheet rather than a modal: the claim is already theirs, so blocking the
 * screen to demand an account would be a wall where an offer belongs. It is
 * also why "Later" is spelled out instead of hidden behind a cross.
 *
 * The copy names what is at stake rather than what the product wants. "Sign up
 * for NameScape" is about us. "Dildo is yours, keep it" is about them.
 */
export default function GuestPrompt({ placeName, expiresAt, onDismiss }: GuestPromptProps) {
  const openSignIn = useAuth((state) => state.openSignIn)

  return (
    <section
      data-testid="guest-prompt"
      aria-labelledby="guest-prompt-heading"
      className="mt-3 rounded-surface bg-ink-800 p-5 ring-1 ring-brass-700/60"
    >
      <h3 id="guest-prompt-heading" className="font-display text-lg text-parchment-50">
        {placeName} is yours.
      </h3>
      <p className="mt-1.5 text-sm text-parchment-200">
        Create an account to keep it. {remainingLabel(expiresAt)}, then the place goes back to
        unclaimed and someone else can find it.
      </p>

      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={openSignIn}
          className="rounded-control bg-brass-500 px-4 py-2.5 text-sm font-medium text-brass-900 hover:bg-brass-300"
        >
          Keep it
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-control px-3 py-2.5 text-sm text-parchment-400 hover:bg-ink-700 hover:text-parchment-200"
        >
          Later
        </button>
      </div>
    </section>
  )
}
