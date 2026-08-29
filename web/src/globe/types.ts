/** A place the camera can be pointed at. */
export interface PlaceRef {
  id: string
  lon: number
  lat: number
  /** GeoNames feature class: P populated, H hydro, T terrain. Drives target zoom. */
  featureClass?: 'P' | 'H' | 'T'
}

export interface FocusOptions {
  zoom?: number
}

export interface LayerState {
  discoveries?: boolean
  bookmarks?: boolean
  nicknames?: boolean
}

export interface GlobeOptions {
  center?: [number, number]
  zoom?: number
  styleUrl?: string
}

export type Unsubscribe = () => void

export interface GlobeHandle {
  focusOn(place: PlaceRef, options?: FocusOptions): Promise<void>
  setLayers(layers: LayerState): void
  onPlaceTap(handler: (placeId: string) => void): Unsubscribe
  startIdleSpin(): void
  stopIdleSpin(): void
  destroy(): void
}
