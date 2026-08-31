import { useState } from 'react'

import { ClaimError, claimPlace, type DiscoveryResponse, type PlaceDetail } from '../api/places'
import { useAuth } from '../auth/store'
import Countdown from './Countdown'
import GuestPrompt from './GuestPrompt'
import StampBadge from './StampBadge'

const MAX_CAPTION = 140

/** A claim this visitor already holds elsewhere. Guests get exactly one. */
export interface HeldClaim {
  placeName: string
  expiresAt: string | null
}

interface ClaimSheetProps {
  place: PlaceDetail
  onClaimed: (discovery: DiscoveryResponse) => void
  heldClaim?: HeldClaim | null
}

export default function ClaimSheet({ place, onClaimed, heldClaim }: ClaimSheetProps) {
  const [caption, setCaption] = useState('')
  const [etymology, setEtymology] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [claimed, setClaimed] = useState<DiscoveryResponse | null>(null)
  const [sending, setSending] = useState(false)
  const [settled, setSettled] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  const signedIn = useAuth((state) => state.status === 'signed-in')
  const needsEtymology = place.eligibility === 'etymology_required'
  // One claim per guest session, so a guest already holding one is spent.
  const spent = !signedIn && Boolean(heldClaim)

  if (claimed) {
    // The prompt waits for the animation's last frame. Anything earlier talks
    // over the moment that earns the ask; anything later (exit intent, the
    // next action) has already lost it.
    const showPrompt = Boolean(claimed.expires_at) && settled && !dismissed
    return (
      <>
        <StampBadge
          finder={claimed.finder}
          placeName={place.name}
          expiresAt={claimed.expires_at}
          onSettled={() => setSettled(true)}
        />
        {showPrompt && claimed.expires_at && (
          <GuestPrompt
            placeName={place.name}
            expiresAt={claimed.expires_at}
            onDismiss={() => setDismissed(true)}
          />
        )}
      </>
    )
  }

  if (place.eligibility === 'blocked') {
    return (
      <div className="rounded-xl bg-[#151C28] p-6 ring-1 ring-[#2B3646]">
        <h2 className="text-lg text-[#F5F1E8]">{place.name}</h2>
        <p className="mt-2 text-sm text-[#9B9484]">
          {place.eligibility_reason ?? 'This place cannot be claimed.'}
        </p>
        <p className="mt-2 text-xs text-[#6B665C]">
          It still appears on the map and in search. Only the game stops here.
        </p>
      </div>
    )
  }

  async function submit() {
    setError(null)
    if (!caption.trim()) {
      setError('Write a caption before you stamp it.')
      return
    }
    if (needsEtymology && !etymology.trim()) {
      setError('Tell us what the name means before you claim it.')
      return
    }

    setSending(true)
    try {
      const discovery = await claimPlace(place.id, caption, etymology || undefined)
      setClaimed(discovery)
      onClaimed(discovery)
    } catch (thrown) {
      if (thrown instanceof ClaimError && thrown.status === 429) {
        // "Too many requests" tells you nothing about what to do next.
        setError('You are stamping quickly. Give it a moment and try again.')
      } else {
        setError(thrown instanceof ClaimError ? thrown.message : 'That did not work.')
      }
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="rounded-xl bg-[#151C28] p-6 ring-1 ring-[#2B3646]">
      <h2 className="text-lg text-[#F5F1E8]">{place.name}</h2>

      <label htmlFor="claim-caption" className="mt-4 block text-sm text-[#D6D0C2]">
        Caption
      </label>
      <textarea
        id="claim-caption"
        rows={3}
        value={caption}
        maxLength={MAX_CAPTION}
        onChange={(event) => setCaption(event.target.value.slice(0, MAX_CAPTION))}
        className="mt-2 w-full rounded-lg bg-[#0E131C] px-4 py-2.5 text-[#F5F1E8] ring-1 ring-[#2B3646] focus:outline-none focus:ring-[#E8A33D]"
      />
      <p className="mt-1 text-right text-xs tabular-nums text-[#9B9484]">
        {MAX_CAPTION - caption.length} left
      </p>

      {needsEtymology && (
        <>
          <label htmlFor="claim-etymology" className="mt-4 block text-sm text-[#D6D0C2]">
            Etymology
          </label>
          <p className="text-xs text-[#9B9484]">
            {place.eligibility_reason ?? 'This name is not in your language.'} A sentence is enough.
          </p>
          <input
            id="claim-etymology"
            value={etymology}
            onChange={(event) => setEtymology(event.target.value)}
            className="mt-2 w-full rounded-lg bg-[#0E131C] px-4 py-2.5 text-[#F5F1E8] ring-1 ring-[#2B3646] focus:outline-none focus:ring-[#E8A33D]"
          />
        </>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-[#C9524E]">
          {error}
        </p>
      )}

      {spent && heldClaim && (
        <p className="mt-4 rounded-control bg-ink-900 p-3 text-sm text-parchment-200">
          You are holding {heldClaim.placeName}. Create an account to keep it and claim more
          places.{' '}
          {heldClaim.expiresAt && <Countdown expiresAt={heldClaim.expiresAt} />}
        </p>
      )}

      <button
        type="button"
        disabled={sending || spent}
        onClick={() => void submit()}
        className="mt-4 w-full rounded-lg bg-[#E8A33D] px-4 py-3 text-sm font-medium text-[#4A320F] disabled:opacity-60"
      >
        Stamp it
      </button>
    </div>
  )
}
