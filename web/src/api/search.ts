import type { components } from './schema'

export type SearchResult = components['schemas']['SearchResult']

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<SearchResult[]> {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal })
  if (!response.ok) throw new Error(`search failed: ${response.status}`)
  const payload = (await response.json()) as components['schemas']['SearchResponse']
  return payload.results
}
