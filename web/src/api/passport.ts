import type { components } from './schema'

export type PassportData = components['schemas']['PassportResponse']
export type UserDiscovery = components['schemas']['UserDiscoveryResponse']

export async function fetchPassport(username: string): Promise<PassportData> {
  const response = await fetch(`/api/passport/${encodeURIComponent(username)}`)
  if (!response.ok) throw new Error(`passport failed: ${response.status}`)
  return (await response.json()) as PassportData
}

export async function fetchMyDiscoveries(): Promise<UserDiscovery[]> {
  const response = await fetch('/api/discoveries')
  if (!response.ok) return []
  const body = (await response.json()) as components['schemas']['UserDiscoveriesResponse']
  return body.discoveries
}

export function shareCardUrl(username: string): string {
  return `/api/passport/${encodeURIComponent(username)}/card.png`
}
