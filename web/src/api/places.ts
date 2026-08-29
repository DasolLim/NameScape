import type { components } from './schema'

export type PlaceDetail = components['schemas']['PlaceDetail']
export type DiscoveryResponse = components['schemas']['DiscoveryResponse']

export async function fetchPlace(placeId: number): Promise<PlaceDetail> {
  const response = await fetch(`/api/places/${placeId}`)
  if (!response.ok) throw new Error(`place lookup failed: ${response.status}`)
  return (await response.json()) as PlaceDetail
}

export class ClaimError extends Error {
  // Declared, not a constructor parameter property: tsconfig sets
  // erasableSyntaxOnly, which forbids that syntax.
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function claimPlace(
  placeId: number,
  caption: string,
  etymology?: string,
): Promise<DiscoveryResponse> {
  const response = await fetch('/api/discoveries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ place_id: placeId, caption, etymology: etymology ?? null }),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new ClaimError(body.detail ?? 'That did not work.', response.status)
  }
  return (await response.json()) as DiscoveryResponse
}
