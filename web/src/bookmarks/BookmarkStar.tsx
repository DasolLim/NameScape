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
    <button
      type="button"
      onClick={toggle}
      aria-pressed={isSaved}
      aria-label={isSaved ? 'Saved. Remove this place' : 'Save this place'}
      className={`rounded-full px-3 py-2 text-lg leading-none ${
        isSaved ? 'text-[#35A48F]' : 'text-[#6B665C] hover:text-[#9B9484]'
      }`}
    >
      {isSaved ? '★' : '☆'}
    </button>
  )
}
