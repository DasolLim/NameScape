import type { FeatureCollection } from 'geojson'
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'

import type { LayerFeature, LayerName, LayerSpec } from './types'

const BRASS = '#E8A33D'
const BRASS_GLOW = '#F5C87E'
const INK_950 = '#080B11'
const VERDIGRIS = '#35A48F'

function toGeoJSON(features: LayerFeature[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: features.map((feature) => ({
      type: 'Feature',
      id: feature.id,
      geometry: { type: 'Point', coordinates: [feature.lon, feature.lat] },
      properties: {
        name: feature.name ?? '',
        count: feature.count ?? 1,
        label: String(feature.count ?? ''),
      },
    })),
  }
}

/**
 * Circle and symbol layers only. DOM markers are the standard way to destroy
 * map performance: every one is a positioned element the browser must lay out
 * on each frame, where these are drawn by the GPU.
 */
function layerDefinitions(name: LayerName): Record<string, unknown>[] {
  if (name === 'clusters') {
    return [
      {
        id: 'clusters-circle',
        type: 'circle',
        source: name,
        paint: {
          'circle-color': BRASS,
          'circle-opacity': 0.85,
          // Scaled by count, so a dense region reads as dense.
          'circle-radius': ['interpolate', ['linear'], ['get', 'count'], 1, 12, 500, 34],
          'circle-stroke-width': 2,
          'circle-stroke-color': INK_950,
        },
      },
      {
        id: 'clusters-count',
        type: 'symbol',
        source: name,
        layout: {
          'text-field': ['get', 'label'],
          'text-size': 12,
          // Tabular figures so counts do not jitter as they change.
          'text-font': ['Noto Sans Regular'],
        },
        paint: { 'text-color': INK_950 },
      },
    ]
  }

  const colour = name === 'bookmarks' ? VERDIGRIS : BRASS
  return [
    {
      id: `${name}-glow`,
      type: 'circle',
      source: name,
      paint: {
        'circle-color': name === 'bookmarks' ? VERDIGRIS : BRASS_GLOW,
        'circle-blur': 1,
        'circle-opacity': 0.45,
        'circle-radius': 14,
      },
    },
    {
      id: `${name}-pin`,
      type: 'circle',
      source: name,
      paint: {
        'circle-color': colour,
        'circle-radius': 6,
        'circle-stroke-width': 2,
        'circle-stroke-color': INK_950,
        // feature-state, so hover and selection never re-upload the source.
        'circle-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 1, 0.92],
      },
    },
  ]
}

export function applyLayer(map: MapLibreMap, name: LayerName, spec: LayerSpec): void {
  const data = toGeoJSON(spec.features)
  const existing = map.getSource(name) as GeoJSONSource | undefined

  if (existing) {
    existing.setData(data)
  } else {
    map.addSource(name, { type: 'geojson', data })
    for (const definition of layerDefinitions(name)) {
      map.addLayer(definition as never)
    }
  }

  const visibility = spec.visible ? 'visible' : 'none'
  for (const definition of layerDefinitions(name)) {
    map.setLayoutProperty(String(definition.id), 'visibility', visibility)
  }
}
