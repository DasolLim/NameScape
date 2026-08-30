import { useAuth } from './store'

/**
 * The emailed link lands on the app with `?token=`. Exchange it for a session,
 * then strip it from the address bar so a refresh or a shared URL cannot
 * replay a token that is already spent.
 */
export async function completeSignInFromUrl(): Promise<void> {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')
  if (!token) return

  try {
    await useAuth.getState().signIn(token)
  } catch {
    useAuth.setState({
      signInOpen: true,
      linkError: 'That sign-in link has expired or was already used.',
    })
  } finally {
    params.delete('token')
    const query = params.toString()
    window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}`)
  }
}
