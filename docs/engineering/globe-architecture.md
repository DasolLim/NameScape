# 3D Globe Map — Technical Architecture

**Requirement:** A true 3D globe that zooms seamlessly from planet view to street level, showing real place names — cities, towns, lakes, rivers, roads — at Google Maps level of detail.
**Version:** 1.0

---

## 1. Summary of the recommendation

| Layer | Choice | Why |
|---|---|---|
| Renderer | MapLibre GL JS v6, `projection: {type: 'globe'}` | The only mature open renderer that does globe → street in one continuous zoom |
| Basemap data | Protomaps basemap (OSM-derived), PMTiles | Full planet, roads, POIs, labels, ODbL, one file |
| Hosting | Cloudflare R2 + CDN, HTTP range requests | No tile server, no database, near-zero cost |
| Fonts / sprites | Protomaps basemaps-assets | Bundled, Noto-based, full script coverage |
| Gazetteer (search) | GeoNames (CC-BY) + Who's On First | 11M+ named places, stable IDs for anchoring |
| Discovery layer | Own PostGIS API → GeoJSON source | Separate from basemap entirely |

Total recurring cost at launch scale: single-digit dollars per month.

---

## 2. The globe renderer

MapLibre GL JS shipped globe projection in v5.0.0 in January 2025 and it is now on v6.4. It is exactly the behaviour described in the requirement.

The technique is **Adaptive Composite Map Projection**. The library reuses the same Mercator vector tiles and reprojects them client-side: zoomed out you are looking at a sphere, and from a certain zoom level there is a smooth transition into standard Mercator. You are never switching between two different maps — it is one continuous zoom from planet to street, with real vector data the whole way.

```js
import * as maplibregl from 'maplibre-gl';

const map = new maplibregl.Map({
  container: 'map',
  style: styleUrl,
  zoom: 1.5,
  center: [0, 20],
});

map.on('style.load', () => {
  map.setProjection({ type: 'globe' });
});
```

Setting projection in the style JSON is cleaner for us, since we always want globe:

```json
{
  "version": 8,
  "projection": { "type": "globe" },
  "sky": {
    "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0]
  }
}
```

The `sky` block gives the atmospheric limb halo at low zoom that makes the globe read as a planet rather than a textured ball. It fades out by z7 so it never interferes with the working map.

### 2.1 Three gotchas worth knowing before you start

**`setProjection` before style load throws.** Always inside the `style.load` handler, or declared in the style JSON.

**Zoom math differs under globe.** The relationship between zoom level and apparent planet size is not the same as in Mercator, so any code that adjusts centre or zoom by a delta needs to account for it. MapLibre documents this specifically. It will bite you when you write the fly-to-a-discovery animation.

**Globe is not in MapLibre Native.** It is web-only. If you want true native iOS and Android apps rather than a responsive web app, the map has to run in a webview. My recommendation: ship a PWA first, and only consider native if you have a reason that isn't the map.

---

## 3. Basemap data — getting Google-level detail

### 3.1 What Protomaps gives you

Protomaps maintains a general-purpose vector basemap built from OpenStreetMap and other open data, distributed as a single PMTiles archive under ODbL. It carries city labels, roads, water features, and location context. The layers you get:

| Layer | Contents |
|---|---|
| `places` | Points from OSM and Natural Earth place tags, all zooms — cities, towns, villages, hamlets |
| `roads` | Highways and railways, physical infrastructure |
| `water` | Polygons, lines and point labels from OSM — lakes, rivers, bays |
| `pois` | Points from OSM across amenity, attraction, historic, leisure, natural, shop, tourism tags |
| `landuse` | Curated OSM polygons — parks, aeroway, leisure, landuse |
| `buildings` | Merged buildings z0–14, individual OSM buildings z15+ |
| `earth` | Natural Earth land at low zoom, OSMCoastline polygons z6+ |
| `boundaries` | Administrative boundaries |
| `landcover` | Daylight landcover z0–7 |

That covers every named feature type in the requirement — lakes, rivers, towns, cities, roads — at global scale.

### 3.2 Why PMTiles instead of a tile server

A conventional tile server answers millions of tiny questions: give me tile z/x/y. PMTiles packs the whole tile pyramid into a single file on object storage that the browser reads piece by piece using HTTP range requests. No tile server, no PostGIS-backed rendering, no API keys.

Protomaps builds the full OSM planet into PMTiles daily at `build.protomaps.com`. The planet file is around 120GB, but the `pmtiles` CLI can extract a region directly from the remote build without downloading the whole thing first.

Hosted on Cloudflare R2, which has no egress fees, with a small CORS policy. Realistic cost is a few dollars a month and often zero.

```bash
# extract a region from the remote planet build
pmtiles extract https://build.protomaps.com/20260801.pmtiles \
  north-america.pmtiles \
  --bbox=-170,15,-50,75

# or serve locally for development
pmtiles serve ./tiles --cors=*
```

Client side, register the protocol:

```js
import { Protocol } from 'pmtiles';
const protocol = new Protocol();
maplibregl.addProtocol('pmtiles', protocol.tile);
// style source: "url": "pmtiles://https://tiles.yourdomain.com/planet.pmtiles"
```

### 3.3 Staged rollout

Downloading and hosting 120GB on day one is premature. Sensible progression:

1. **Development** — Protomaps' CDN-cached basemap API. Free for noncommercial use, zero setup.
2. **Beta** — a regional extract on R2, a few hundred MB, covering wherever your first users are.
3. **Launch** — full planet on R2 behind the CDN.

OpenFreeMap is a reasonable alternative at every stage: free OSM map hosting with no usage limits, no registration, and no API keys, either as a public instance or self-hosted.

### 3.4 Fonts and sprites

Easy to overlook and it will block you for an afternoon if you do. Styles need glyph and sprite files to render place names and road shields at all.

Using the Protomaps basemaps library, fonts and sprites come bundled via the `basemaps-assets` repo and are hosted on GitHub Pages. That is the path of least resistance and it ships Noto, which is what you want for global script coverage anyway.

For custom typography later: `font-maker` generates the SDF glyph pyramids, `spreet` generates sprite sheets.

### 3.5 Styling

OpenMapTiles publishes both a schema and permissively licensed styles; Protomaps ships reasonable defaults. For custom cartography, Maputnik is the open-source MapLibre style editor — but note it cannot read PMTiles natively and needs an intermediate server generating x/y/z URLs from the archive.

Practical approach: fork the Protomaps dark style, retint to the ink palette from the design doc, and suppress basemap labels for any feature type you render yourself, or names will double up.

---

## 4. The gazetteer — a separate system

This is the architectural point that matters most, and it is easy to get wrong.

**The basemap is what you render. The gazetteer is what you search and what discoveries anchor to.** They are different datasets with different jobs, and conflating them produces a product where users can see a place but not claim it, or claim a place that has no stable identity.

### 4.1 GeoNames

Over 11 million place names with coordinates, free to download, licensed CC-BY-4.0. Daily dumps at `download.geonames.org/export/dump/`, available per-country or whole-planet, with a separate alternate-names dataset.

The decisive property: GeoNames IDs are effectively the gold standard for building concordances between geo datasets. Every discovery in our system anchors to a `geonames_id`. That gives us a stable, canonical, deduplicated identity for every place, permanently.

Feature classes matter for us. `P` is populated places, `H` is hydrographic (lakes, rivers, bays), `T` is terrain (mountains, valleys). Those three cover the requirement almost entirely.

### 4.2 Who's On First

Worth importing alongside. It is a gazetteer of administrative boundaries, place hierarchies, names and alternate names, geographic shapes, and — critically — concordances linking to OSM, Wikidata, and GeoNames. Most of the data is CC0. It gives us polygons where GeoNames only gives points, and the Wikidata links are how we pull etymology.

### 4.3 Import and search

```
GeoNames dump
  → filter to feature classes P, H, T
  → load into Postgres with PostGIS
  → pg_trgm index on name + alternate names
  → Typesense or Meilisearch index for user-facing search
```

Do not use the hosted GeoNames web service for production search. It is rate-limited, and search latency is where competitors in this category visibly fail — Atlas Obscura's reviewers complain that broad queries return two results. Own the index.

The alternate-names dataset is what makes search work for non-English users, and it is also where etymology hooks in via the Wikidata concordance.

---

## 5. Rendering the discovery layer

Discoveries are our data, not basemap data. They live in a separate MapLibre source fed by our API.

```
GET /api/discoveries?bbox=w,s,e,n&zoom=8
```

- Snap the bbox to a tile grid so the cache key is stable across small pans. Without snapping, every pixel of movement is a cache miss.
- PostGIS `ST_Intersects` on the snapped box, capped at 500 features.
- Cache in Redis with a short TTL.
- Return GeoJSON.

Clustering by zoom band:

| Zoom | Rendering |
|---|---|
| z0–3 (globe) | Aggregate count per country, one label per country |
| z4–7 | Supercluster clusters with counts |
| z8–11 | Individual pins, clustered where dense |
| z12+ | Individual pins, all visible |

MapLibre's built-in `cluster: true` on a GeoJSON source handles most of this. Only reach for Supercluster directly if you need custom cluster properties.

### 5.1 Nickname labels

A nickname renders as a second symbol layer above the basemap label, offset downward, in brass, in quotes. `symbol-sort-key` bound to the nickname's vote score so that when labels collide, the more strongly supported nickname wins the space. Let MapLibre's collision engine do the work — do not implement collision detection yourself.

---

## 6. On restricting names — an important correction

The brief asks for the map to show all place names *excluding* restricted areas such as Indigenous and sensitive-country regions. I want to flag a direct conflict with the content policy we already settled on, because building it as written would be both harmful and expensive.

**Do not remove names from the basemap.**

Removing Indigenous toponyms from a map is cartographic erasure, which has a long colonial history and is the opposite of respect. And blanking regions on a world map does not read as sensitivity — it reads as a broken product, and it draws far more attention to those areas than showing them would.

It is also impractical. Basemap labels are baked into the vector tiles. Stripping them means rebuilding the planet tileset with a custom Planetiler profile, at meaningful compute cost, to achieve an outcome you do not want.

**The restriction belongs in the nomination layer, which is our own data.**

| Lever | Setting |
|---|---|
| Basemap display | Show everything. Complete and truthful. |
| Nomination eligibility | Where restriction actually lives — PostGIS polygon check |
| Discovery visibility | Rare, for takedowns only |

```sql
CREATE TABLE restricted_zones (
  id          bigserial PRIMARY KEY,
  geom        geography(Polygon, 4326),
  rule_type   text,  -- no_nomination | etymology_required | review_required
  reason      text,
  source      text
);
CREATE INDEX ON restricted_zones USING GIST (geom);
```

Checked at nomination time, not at render time. Tier A rules (memorials, places of worship, hospitals, cemeteries, disaster sites, disputed territories) derive mostly from OSM tags rather than hand curation. When a place is ineligible, say so plainly — the map still shows it, you just cannot nominate it.

For disputed territories specifically, the cheapest correct answer is to take OSM and GeoNames as-is without editorialising, render disputed boundaries with the standard dashed convention, and disable nomination inside those polygons.

---

## 7. Performance

The globe is the most demanding surface in the product. Budget for it.

| Concern | Mitigation |
|---|---|
| Tile fetch on pan | PMTiles range requests are cheap; CDN cache does the rest |
| Discovery pins at scale | 500-feature cap, clustering, bbox snapping |
| Label collision cost | Let MapLibre handle it; keep our symbol layers to two |
| Globe reprojection on mobile | Cap pitch, disable atmosphere below mid-range GPUs |
| Cold start | Preload the low-zoom tile pyramid; it is tiny |
| Style size | Strip unused basemap layers from the forked style |

Targets: 60fps panning at 500 visible pins on a mid-range Android device, first meaningful globe paint under 1.5s on 4G.

Test on real hardware, not a throttled desktop. Globe reprojection is GPU work and desktop throttling does not simulate it.

---

## 8. Build order

1. MapLibre + globe projection + Protomaps CDN basemap. One afternoon, and you will know immediately whether the interaction feels right.
2. Fork and retint the style to the ink palette. Suppress duplicate labels.
3. Move to a regional PMTiles extract on R2.
4. GeoNames import, Postgres + PostGIS, search index.
5. Discovery API and GeoJSON source with clustering.
6. Restricted zones table and the nomination eligibility check.
7. Nickname symbol layer with vote-weighted sort key.
8. Full planet PMTiles before launch.

---

## 9. Licensing and attribution

Non-negotiable, and cheap to get right.

- **OpenStreetMap / Protomaps basemap** — ODbL. Requires attribution and is share-alike. Attribution control must be visible on the map.
- **GeoNames** — CC-BY-4.0. Requires attribution.
- **Who's On First** — mostly CC0, but licensed per-dataset at attribute level. Check what you actually import.
- **Natural Earth** — public domain.

A single attribution line in the MapLibre attribution control covers the map. Credit GeoNames in an about page and in the API response headers.
