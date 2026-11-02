/**
 * Error reporting. Off unless a DSN is configured, so development and tests
 * never send anything. Loaded on demand, so the SDK is not in the main bundle
 * of a deployment that does not use it.
 */
export function startErrorReporting(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return

  void import('@sentry/react').then((Sentry) =>
    Sentry.init({
      dsn,
      tracesSampleRate: 0.1,
      environment: import.meta.env.MODE,
    }),
  )
}
