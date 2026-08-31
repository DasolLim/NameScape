import type { components } from './schema'

export type Activity = components['schemas']['ActivityResponse']

export async function fetchActivity(): Promise<Activity | null> {
  const response = await fetch('/api/activity')
  if (!response.ok) return null
  return (await response.json()) as Activity
}
