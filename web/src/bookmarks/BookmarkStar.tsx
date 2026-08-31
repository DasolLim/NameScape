import { useState } from 'react'

import { removeBookmark, saveBookmark } from '../api/bookmarks'
import { useAuth } from '../auth/store'

interface BookmarkStarProps {
  placeId: number
  saved: boolean
  onChange?: (saved: boolean) => void
}

/** The lightest engagement action in the product: exactly one tap. */
export default function BookmarkStar({ placeId, saved, onChange }: BookmarkStarProps) {
  const [isSaved, setIsSaved] = useState(saved)
  const requireAuth = useAuth((state) => state.requireAuth)
  // Claiming works without an account. Saving does not, and a control that
  // looks live until it demands a sign-in is a trap rather than an offer.
  const needsAccount = useAuth((state) => state.status !== 'signed-in')

  function toggle() {
    requireAuth(() => {
      const next = !isSaved
      // Optimistic: the star moves now and rolls back only if the write fails.
      setIsSaved(next)
      onChange?.(next)

      const request = next ? saveBookmark(placeId) : removeBookmark(placeId)
      request.catch(() => {
        setIsSaved(!next)
        onChange?.(!next)
      })
    })
  }

  return (
    <span className="inline-flex items-center gap-2">
      {needsAccount && (
        <span id="bookmark-needs-account" className="text-xs text-parchment-400">
          Saving needs an account
        </span>
      )}
      <button
        type="button"
        onClick={toggle}
        disabled={needsAccount}
        aria-pressed={isSaved}
        aria-label={isSaved ? 'Saved. Remove this place' : 'Save this place'}
        aria-describedby={needsAccount ? 'bookmark-needs-account' : undefined}
        className={`rounded-full px-3 py-2 text-lg leading-none disabled:opacity-40 ${
          isSaved ? 'text-[#35A48F]' : 'text-[#6B665C] hover:text-[#9B9484]'
        }`}
      >
        {isSaved ? '★' : '☆'}
      </button>
    </span>
  )
}
