import * as Sentry from '@sentry/react'

/**
 * Error reporting. Off unless a DSN is configured, so development and tests
 * never send anything.
 */
export function startErrorReporting(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return

  Sentry.init({
    dsn,
    tracesSampleRate: 0.1,
    environment: import.meta.env.MODE,
  })
}
