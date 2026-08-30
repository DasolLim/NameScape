# Test fixtures

## `geonames_sample.txt`

A curated GeoNames-format extract used only by the test suite. The places and
coordinates are real; **the `geonames_id` values are illustrative, not real
GeoNames identifiers.**

That means this file must never be imported into a database that also holds a
real GeoNames dump. The ids collide, and the upsert on `geonames_id` silently
replaces a curated row with whatever really lives at that id — which is how
"Boring, Oregon" disappeared from the development database.

Development seeding uses real data (`scripts/fetch_geonames.py`). This file is
for tests, which run against an isolated database of their own.
