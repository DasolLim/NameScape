import type { components } from './schema'

export type SavedPlace = components['schemas']['SavedPlaceResponse']

export async function saveBookmark(placeId: number): Promise<void> {
  const response = await fetch(`/api/bookmarks/${placeId}`, { method: 'POST' })
  if (!response.ok) throw new Error(`save failed: ${response.status}`)
}

export async function removeBookmark(placeId: number): Promise<void> {
  const response = await fetch(`/api/bookmarks/${placeId}`, { method: 'DELETE' })
  if (!response.ok) throw new Error(`remove failed: ${response.status}`)
}

export async function fetchBookmarks(): Promise<SavedPlace[]> {
  const response = await fetch('/api/bookmarks')
  if (!response.ok) return []
  const body = (await response.json()) as components['schemas']['BookmarksResponse']
  return body.bookmarks
}
