import type { components } from './schema'

export type Health = components['schemas']['Health']

export async function fetchHealth(): Promise<Health> {
  const response = await fetch('/api/health')
  if (!response.ok) throw new Error(`health check failed: ${response.status}`)
  return (await response.json()) as Health
}

export function healthSummary(health: Health): string {
  return `db ${health.db ? 'ok' : 'down'} · redis ${health.redis ? 'ok' : 'down'}`
}
