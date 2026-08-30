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

export interface LayerFeature {
  id: number
  lon: number
  lat: number
  name?: string
  count?: number
}

export interface LayerSpec {
  visible: boolean
  features: LayerFeature[]
}

export type LayerName = 'discoveries' | 'clusters' | 'bookmarks'

/** Both the data and whether it is shown, so one method covers the layer. */
export type LayerState = Partial<Record<LayerName, LayerSpec>>

export interface GlobeOptions {
  center?: [number, number]
  zoom?: number
  styleUrl?: string
}

export type Unsubscribe = () => void

export interface Viewport {
  west: number
  south: number
  east: number
  north: number
  zoom: number
}

export interface GlobeHandle {
  focusOn(place: PlaceRef, options?: FocusOptions): Promise<void>
  setLayers(layers: LayerState): void
  /**
   * PRD 8.3 permits growing this interface when a caller genuinely needs the
   * map to do something. Nothing outside the module can know when the camera
   * settled, so without this there is no way to refetch what is on screen.
   */
  onViewportChange(handler: (viewport: Viewport) => void): Unsubscribe
  onPlaceTap(handler: (placeId: string) => void): Unsubscribe
  startIdleSpin(): void
  stopIdleSpin(): void
  destroy(): void
}
