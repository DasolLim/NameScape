import { useEffect, useState } from 'react'

import { useAuth } from './store'

export default function SignInSheet() {
  const open = useAuth((state) => state.signInOpen)
  const linkSent = useAuth((state) => state.linkSent)
  const requestLink = useAuth((state) => state.requestLink)
  const close = useAuth((state) => state.closeSignIn)
  const linkError = useAuth((state) => state.linkError)

  const [email, setEmail] = useState('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, close])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sign in"
      className="pointer-events-auto w-[min(26rem,90vw)] rounded-xl bg-[#151C28] p-6 shadow-2xl ring-1 ring-[#2B3646]"
    >
      {linkError && (
        <p role="alert" className="mb-3 text-sm text-[#C9524E]">
          {linkError} Ask for a new one.
        </p>
      )}
      {linkSent ? (
        <p className="text-sm text-[#D6D0C2]">
          Check your email — the link signs you in and expires in 15 minutes.
        </p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            setFailed(false)
            requestLink(email).catch(() => setFailed(true))
          }}
        >
          <label htmlFor="signin-email" className="block text-sm text-[#D6D0C2]">
            Email
          </label>
          <input
            id="signin-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-2 w-full rounded-lg bg-[#0E131C] px-4 py-2.5 text-[#F5F1E8] ring-1 ring-[#2B3646] focus:outline-none focus:ring-[#E8A33D]"
          />
          <p className="mt-2 text-xs text-[#9B9484]">No password. We mail you a link.</p>
          {failed && (
            <p role="alert" className="mt-2 text-xs text-[#C9524E]">
              That didn&rsquo;t work. Try again in a moment.
            </p>
          )}
          <button
            type="submit"
            className="mt-4 w-full rounded-lg bg-[#E8A33D] px-4 py-3 text-sm font-medium text-[#4A320F]"
          >
            Send me a link
          </button>
        </form>
      )}
    </div>
  )
}
