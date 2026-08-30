import { create } from 'zustand'

import { completeSignIn, fetchMe, requestMagicLink, type Me } from '../api/auth'

type Status = 'unknown' | 'anonymous' | 'signed-in'

interface AuthState {
  user: Me | null
  status: Status
  signInOpen: boolean
  linkSent: boolean
  /** Why a sign-in link failed, so an expired one is not a silent no-op. */
  linkError: string | null
  load: () => Promise<void>
  requestLink: (email: string) => Promise<void>
  signIn: (token: string) => Promise<void>
  openSignIn: () => void
  closeSignIn: () => void
  /** Reading is never gated. Claiming, voting and bookmarking go through here. */
  requireAuth: (action: () => void) => void
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  status: 'unknown',
  signInOpen: false,
  linkSent: false,
  linkError: null,

  load: async () => {
    const user = await fetchMe().catch(() => null)
    set({ user, status: user ? 'signed-in' : 'anonymous' })
  },

  requestLink: async (email) => {
    await requestMagicLink(email)
    set({ linkSent: true })
  },

  signIn: async (token) => {
    const user = await completeSignIn(token)
    set({ user, status: 'signed-in', signInOpen: false, linkSent: false, linkError: null })
  },

  openSignIn: () => set({ signInOpen: true, linkSent: false, linkError: null }),
  closeSignIn: () => set({ signInOpen: false }),

  requireAuth: (action) => {
    if (get().status === 'signed-in') {
      action()
      return
    }
    set({ signInOpen: true, linkSent: false })
  },
}))
