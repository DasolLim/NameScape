import { http, HttpResponse } from 'msw'

import type { components } from '../api/schema'

/**
 * Handlers are typed with the generated schema, so a backend field rename
 * breaks these mocks at typecheck rather than silently drifting.
 */
type Health = components['schemas']['Health']

export const handlers = [
  http.get('/api/health', () =>
    HttpResponse.json<Health>({ status: 'ok', db: true, redis: true }),
  ),
]
