import type { components } from './schema'

export type SearchResult = components['schemas']['SearchResult']

export async function searchPlaces(
  query: string,
  signal?: AbortSignal,
  broad = false,
): Promise<SearchResult[]> {
  const url = `/api/search?q=${encodeURIComponent(query)}${broad ? '&broad=true' : ''}`
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`search failed: ${response.status}`)
  const payload = (await response.json()) as components['schemas']['SearchResponse']
  return payload.results
}
