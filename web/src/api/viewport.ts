import type { components } from './schema'
import type { LayerState } from '../globe'

export type ViewportResponse = components['schemas']['ViewportResponse']
export type ViewportFeature = components['schemas']['ViewportFeature']

export interface Bounds {
  west: number
  south: number
  east: number
  north: number
  zoom: number
}

export async function fetchViewport(bounds: Bounds): Promise<ViewportResponse> {
  const query = new URLSearchParams(
    Object.entries(bounds).map(([key, value]) => [key, String(value)]),
  )
  const response = await fetch(`/api/viewport?${query}`)
  if (!response.ok) throw new Error(`viewport failed: ${response.status}`)
  return (await response.json()) as ViewportResponse
}

function toFeatures(features: ViewportFeature[]) {
  return features.map((feature, index) => ({
    id: feature.place_id ?? index,
    lon: feature.lon,
    lat: feature.lat,
    name: feature.name ?? undefined,
    count: feature.count,
    score: feature.score,
  }))
}

export interface LayerToggles {
  bookmarks: boolean
  nicknames: boolean
}

/** The band decides which layer draws; the others are emptied, not removed. */
export function toLayerState(data: ViewportResponse, toggles: LayerToggles): LayerState {
  const aggregated = data.band !== 'pin'
  return {
    discoveries: { visible: !aggregated, features: aggregated ? [] : toFeatures(data.features) },
    clusters: { visible: aggregated, features: aggregated ? toFeatures(data.features) : [] },
    bookmarks: { visible: toggles.bookmarks, features: toFeatures(data.bookmarks) },
    nicknames: { visible: toggles.nicknames, features: toFeatures(data.nicknames) },
  }
}
