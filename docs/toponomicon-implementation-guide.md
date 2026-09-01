# NameScape — Claude Code Implementation Guide

Companion to `namescape-prd.md`. Every step is a self-contained prompt, in order, structured around red → green → refactor.

---

## How to use this guide

**One step per session. One step per commit.** Do not batch. The failure mode of agentic coding is a large diff nobody read.

**Every step follows the same shape**, and the prompts below assume it:

1. Write the failing test. Run it. Watch it fail.
2. Write the minimum code to pass.
3. Refactor.
4. `make verify` green.
5. Commit.

**The 200-line rule.** If a step's implementation diff exceeds ~200 lines, stop and split it. A step that grew is a step that was specified wrong.

**Never accept a test that passed on first run.** A test that has never been red proves nothing about the code — it may be asserting something already true, or nothing at all.

```bash
mkdir namescape && cd namescape
git init
mkdir docs
# copy namescape-prd.md, design-system-and-brand.md, globe-map-architecture.md into docs/
claude
```

---

# Phase 0 — The feedback loops

Nothing else starts until all three loops are closed. This phase is the highest-leverage work in the project.

## Step 0: Project context

```
Read docs/namescape-prd.md in full, plus docs/globe-map-architecture.md
and docs/design-system-and-brand.md.

Create CLAUDE.md at the repo root. It must contain:

MONOREPO LAYOUT
  /api    FastAPI backend, Python 3.12
  /web    React 19 + Vite SPA, TypeScript strict
  /infra  Docker Compose, migrations, deploy
  /docs   PRD and design docs

NON-NEGOTIABLE RULES — state these as rules, not preferences:

1. TDD. Every change starts with a failing test that has been RUN and
   OBSERVED to fail. No exceptions, including for "trivial" changes.

2. Small steps. No single change exceeds ~200 lines of implementation
   diff. If it would, split it.

3. Deep modules. Section 8.3 of the PRD lists seven backend modules and
   two frontend modules with their exact public interfaces. Those
   interfaces are budgets, not suggestions. Adding a public method
   requires justifying why the complexity cannot be hidden.

4. No maplibre-gl import may exist outside /web/src/globe/. The globe
   module is the only place that knows the map library exists.

5. The API boundary is generated, never hand-written. Frontend request
   and response types come from openapi-typescript. A backend field
   rename must break the frontend typecheck.

6. make verify passes before every commit.

DOMAIN VOCABULARY
  place, discovery, first finder, bookmark, proposal, contest, quorum,
  runoff, term, incumbent, nickname, tier, eligibility, restricted zone

Do not write application code in this step.
```

**Acceptance:** `CLAUDE.md` exists, under 120 lines, and states all six rules as rules.

---

## Step 1: Scaffold and loop 1 (static types)

```
Set up the monorepo skeleton and close the static-type loop.

/api:
- Python 3.12, uv for dependencies
- FastAPI, uvicorn, SQLAlchemy 2.0 async, asyncpg, alembic, redis,
  pydantic-settings, httpx
- Dev: pytest, pytest-asyncio, mypy, ruff
- pyproject.toml configured with mypy strict = true, no untyped defs,
  no implicit optional, warn unused ignores
- app/main.py with GET /health returning a Pydantic model that actually
  pings Postgres and Redis

/web:
- React 19 + Vite + TypeScript with strict, noUncheckedIndexedAccess,
  and noImplicitOverride all on
- ESLint with a rule banning `any`
- Zustand, Tailwind v4

/infra:
- docker-compose.yml: postgres:16 (with PostGIS and pg_trgm available),
  redis:7, typesense
- Named volumes

Root:
- Makefile with: dev, verify, test, typecheck, lint, migrate, gen-types
- `make gen-types` runs the API, fetches /openapi.json, and generates
  /web/src/api/schema.ts with openapi-typescript
- `make verify` runs: mypy --strict, ruff, tsc --noEmit, eslint,
  pytest, vitest — and fails on the first failure

TEST FIRST for this step: write a test in /api/tests/test_health.py
asserting GET /health returns 200 with db=true and redis=true. Run it,
watch it fail (no app yet), then build until it passes.

Then prove the type loop is closed: rename a field in the health
response model, run `make gen-types && make typecheck`, and confirm the
frontend typecheck breaks. Revert. Document this check in CLAUDE.md.
```

**Acceptance:** `make verify` green. Renaming a backend field demonstrably breaks the frontend typecheck. If it doesn't, the loop is not closed and nothing else should proceed.

---

## Step 2: Loop 2 (browser access)

```
Give Claude Code eyes.

1. Configure Playwright MCP in .mcp.json so browser tools are available
   in this project. Document in CLAUDE.md that the browser is available
   and MUST be used to verify any visual change.

2. Install Playwright in /web with a config pointing at the dev server,
   projects for chromium desktop and a mobile viewport.

3. Write the first e2e test at /web/e2e/smoke.spec.ts: load the app,
   assert the page renders, assert zero console errors. Run it, watch it
   fail against the empty app, then make it pass.

4. Add a screenshot helper that captures to /web/e2e/__screenshots__/
   with a stable naming scheme.

5. Add `make e2e` to the Makefile and wire it into CI (not into
   `make verify`, which must stay fast).

Then verify the loop by hand: use the browser tool to navigate to the
running dev server, take a screenshot, and read the console. Confirm you
can actually see the rendered page.

This loop matters more here than in most projects. Map bugs are visual —
a wrong projection, mis-colliding labels, an overshooting fly-to. None
of those fail a unit test.
```

**Acceptance:** Claude can navigate to localhost, screenshot it, and report console output. The smoke test passes in CI.

---

## Step 3: Loop 3 (test infrastructure)

```
Complete the test infrastructure.

/api:
- A pytest fixture giving each test a transactional database rolled back
  after the test
- A fixture for a fake Redis
- factory-boy or plain builder functions for test data — every test must
  be able to create a place, a user, and a discovery in one line
- Coverage config with a fail-under of 80 on /api/app/modules/

/web:
- Vitest with jsdom, plus @testing-library/react
- MSW for mocking the API in component tests, with handlers generated
  from the OpenAPI schema so mocks cannot drift from reality

Contract testing:
- Schemathesis running property-based fuzzing against /openapi.json,
  wired into CI

CI (GitHub Actions):
- On PR: make verify, then make e2e
- Fail the build if coverage drops relative to main

TEST FIRST: before building any of this, write one test that uses every
fixture you are about to create. It will fail. Build until it passes.
That test is your proof the harness works.
```

**Acceptance:** A test can create a place, a user, and a discovery in one line each. Coverage gate active. Schemathesis runs in CI.

---

# Phase 1 — The globe

The riskiest part of the product and the most important module boundary. Build it before anything else, so you learn early whether the interaction feels right.

## Step 4: Globe module skeleton

```
Create /web/src/globe/ as a deep module. Read section 8.3 of the PRD
for the interface budget.

PUBLIC INTERFACE — exactly these, nothing more:
  createGlobe(container: HTMLElement, opts: GlobeOptions): GlobeHandle

  interface GlobeHandle {
    focusOn(place: PlaceRef, opts?: FocusOptions): Promise<void>
    setLayers(layers: LayerState): void
    onPlaceTap(handler: (placeId: string) => void): Unsubscribe
    startIdleSpin(): void
    stopIdleSpin(): void
    destroy(): void
  }

Everything else is private: MapLibre setup, style loading, projection,
sources, layers, sprites, collision priority, the spin loop, globe
zoom-delta math, feature-state.

TEST FIRST — /web/src/globe/globe.test.ts:
- createGlobe returns a handle exposing exactly the six methods above
- destroy() removes the map and cancels any running animation frame
- The module's public export surface is exactly one function
Mock maplibre-gl in these tests; this step is about the boundary, not
rendering.

Then implement with OpenFreeMap as the basemap and globe projection set
in the style JSON, not via setProjection (calling setProjection before
style load throws).

Add the ESLint rule banning maplibre-gl imports outside src/globe/, and
write a test asserting the rule is configured.

Use the browser tool to confirm a globe actually renders.
```

**Acceptance:** A globe renders in the browser (verify with a screenshot). `maplibre-gl` appears nowhere outside `src/globe/`. The handle exposes exactly six methods.

---

## Step 5: Spin

```
Implement idle auto-rotation and drag-to-spin inside the globe module.

TEST FIRST — with fake timers and a mocked map:
- startIdleSpin advances the map centre longitude over time
- Any user interaction cancels the spin immediately
- Spin resumes after 5 seconds of idle
- stopIdleSpin cancels the animation frame and does not leak it
- destroy() while spinning cancels cleanly

Then implement:
- ~4°/sec rotation via requestAnimationFrame
- Cancel on mousedown, touchstart, wheel, keydown
- Resume after a 5s idle timer
- Respect prefers-reduced-motion by not spinning at all
- Drag-to-spin needs no code — under globe projection, panning is
  rotation. Confirm this in the browser rather than assuming it.

Verify in the browser: screenshot at two moments and confirm the centre
longitude changed. Confirm dragging spins the globe.
```

**Acceptance:** The globe drifts on load, stops the instant you touch it, resumes after 5s. No leaked animation frames — check by mounting and unmounting 20 times and asserting the frame count returns to zero.

---

## Step 6: Fly-to

```
Implement focusOn() inside the globe module.

TEST FIRST:
- focusOn resolves only after the camera movement completes
- Calling focusOn twice in quick succession cancels the first
- focusOn cancels idle spin
- Zoom deltas are computed correctly under globe projection — write an
  explicit test for this, because globe zoom-to-planet-size math differs
  from Mercator and this is the documented trap
- focusOn on an unmounted globe rejects rather than throwing

Then implement with flyTo using curve 1.6 and speed 0.8, essential true,
and a zoom target derived from the place's feature class — a country
lands at a different zoom than a creek.

Verify in the browser: focus a place, screenshot mid-flight and after,
confirm the arc and the final framing.
```

**Acceptance:** The swoop from planet view to a town feels good — this is a signature moment, so judge it by eye in the browser, not just by test.

---

# Phase 2 — Gazetteer

## Step 7: Places schema and import

```
TEST FIRST — /api/tests/modules/gazetteer/test_import.py:
- Importing a GeoNames fixture row creates a place with the correct
  geonames_id, feature class, and centroid
- Re-importing the same row updates rather than duplicating
- Rows outside feature classes P, H, T are skipped
- Tier is assigned correctly: tier 1 for population > 500k or major
  hydro, tier 2 for towns and notable features, tier 3 for the rest
- Alternate names are parsed into the array column

Then implement:
- Alembic migration enabling PostGIS and pg_trgm, creating the places
  table per section 9 of the PRD with all indexes
- /api/scripts/import_geonames.py — streams a GeoNames dump, filters to
  P/H/T, assigns tier, populates centroid, idempotent on geonames_id
- Commit a small fixture dump (~200 rows across several countries) for
  tests. Never hit the network in a test.
```

**Acceptance:** Importing the fixture twice yields the same row count. Tier assignment matches the PRD table.

---

## Step 8: Gazetteer module

```
Create /api/app/modules/gazetteer/ as a deep module.

PUBLIC INTERFACE — exactly three functions:
  async def search(query: str, opts: SearchOptions) -> list[PlaceResult]
  async def resolve(geonames_id: int) -> Place | None
  async def enrich(place_id: int) -> Place        # etymology via Wikidata

Hidden inside: Typesense indexing and querying, Photon fuzzy fallback,
alternate-name matching, result ranking, Wikidata lookup and caching.
Callers must never know Typesense or Photon exist.

TEST FIRST:
- search returns exact matches first, then alternate-name matches
- search tolerates typos ("Dildoo" finds "Dildo") via the Photon path
- search respects a country filter
- search returns claim status for each result
- An empty query returns an empty list, not an error
- resolve returns None for an unknown id rather than raising
- enrich caches — a second call makes no outbound request
- enrich degrades gracefully when Wikidata has no entry
Mock Typesense, Photon, and Wikidata. No network in tests.

Then implement, plus a Typesense indexing job and docker-compose
service for Photon.

Assert the module exposes exactly three public functions.
```

**Acceptance:** Typo search works. `search` p95 under 200ms against the fixture set. Exactly three public functions.

---

## Step 9: Search UI

```
Build the search overlay in /web.

TEST FIRST — Vitest with MSW:
- Typing debounces at 150ms — three keystrokes produce one request
- Results render name, feature type, country, and claim status
- Selecting a result calls globe.focusOn with the right place
- An empty result set shows the "search worldwide" affordance, not a
  dead end
- Arrow keys navigate results and Enter selects
- Escape closes and returns focus to the trigger

Then implement to the design doc: floating pill at the top, ink-800
surface, parchment text, brass highlight on the active row. Feature type
icons. Claimed places show the finder's handle in parchment-400.

E2E TEST: type a query, select a result, assert the globe camera moved.

Verify in the browser at both desktop and mobile viewports. Screenshot
both.
```

**Acceptance:** Search feels instant. Keyboard navigation works end to end. E2E passes.

---

# Phase 3 — Accounts

## Step 10: Auth and accounts module

```
Create /api/app/modules/accounts/.

PUBLIC INTERFACE:
  async def authenticate(token: str) -> Session
  async def request_magic_link(email: str) -> None
  async def profile(username: str) -> PublicProfile
  async def passport(username: str) -> Passport

Hidden: token generation and expiry, session cookies, username
validation and locking, stamp aggregation, country completion math.

TEST FIRST:
- A magic link token is single-use — the second use fails
- Tokens expire after 15 minutes
- Usernames are 3-20 chars, alphanumeric plus underscore, case-insensitively unique
- Username is immutable after username_locked_at passes
- profile() on an unknown username returns None, not a 500
- passport() aggregates discoveries by country correctly
- Rate limit: 3 magic link requests per email per hour

Then implement. HTTP-only, Secure, SameSite=Lax signed cookies. Never
store an IP address in Postgres.

Frontend: auth state in Zustand, a sign-in sheet, and route guards that
gate claiming, voting, and bookmarking — but never gate reading.
```

**Acceptance:** Full sign-in flow works e2e. Reading the globe requires no account.

---

# Phase 4 — Discoveries

## Step 11: Moderation module

```
Create /api/app/modules/moderation/ per section 7.3 of the PRD.

PUBLIC INTERFACE — exactly one function:
  async def screen(text: str, context: ScreenContext) -> ScreenResult

ScreenResult is ACCEPT, REJECT, or DUPLICATE(existing_id). The rejection
reason stays internal and is logged, never returned.

Hidden: normalization, homoglyph mapping, leetspeak folding, blocklist,
the Claude Haiku call, the circuit breaker, pg_trgm duplicate matching.

TEST FIRST:
- Zero-width and homoglyph characters are stripped before matching
- Leetspeak evasion is caught by the blocklist
- The classifier rejecting any category produces REJECT
- A classifier timeout produces REJECT — FAIL CLOSED. Write this test
  explicitly; it is the one that matters most.
- Five consecutive classifier failures trip the circuit breaker
- A near-duplicate at 0.85 similarity returns DUPLICATE with the
  existing id
- ScreenResult never carries the rejection reason
Mock the Anthropic client entirely.

Ship /api/data/blocklist.txt as a placeholder with a header comment
stating it must be sourced externally before launch. Do not author a
slur list — use a maintained one.

Assert the module exposes exactly one public function. This is the
clearest example of a deep module in the codebase: five stages of
complexity behind one call.
```

**Acceptance:** Every stage has a passing rejection test. Killing the Anthropic client causes rejection, never admission.

---

## Step 12: Eligibility module

```
Create /api/app/modules/eligibility/ per section 7 of the PRD.

PUBLIC INTERFACE — exactly one function:
  async def check(place_id: int, user_id: UUID) -> EligibilityVerdict

Verdict is ALLOWED, or BLOCKED(reason), or ETYMOLOGY_REQUIRED.

Hidden: restricted_zones polygon lookup, OSM tag rules, tier resolution,
the language comparison for Tier B.

TEST FIRST:
- A place inside a no_nomination zone returns BLOCKED
- A place inside an etymology_required zone returns ETYMOLOGY_REQUIRED
- A place whose name language differs from the user's UI language
  returns ETYMOLOGY_REQUIRED
- An ordinary Tier C place returns ALLOWED
- A place with no zone match returns ALLOWED
- The PostGIS query uses the GIST index — assert via EXPLAIN

Then implement:
- Migration for restricted_zones with the GIST index
- /api/scripts/build_zones.py querying Overpass for Tier A OSM tags
  (place_of_worship, memorial, hospital, cemetery, prison) and writing
  polygons. Commit a fixture; never hit Overpass in tests.
- Hand-drawn polygons for disputed territories, in a reviewed YAML file

Note for the implementer: this module NEVER affects rendering. The map
shows every place. Eligibility only gates claiming and nominating.
```

**Acceptance:** A memorial returns BLOCKED but still appears in search and on the map. Verify both in the browser.

---

## Step 13: Discoveries module

```
Create /api/app/modules/discoveries/.

PUBLIC INTERFACE:
  async def claim(place_id: int, user_id: UUID, caption: str) -> Discovery
  async def list_in_bounds(bbox: BBox, zoom: int) -> list[DiscoveryPin]
  async def for_user(user_id: UUID) -> list[Discovery]

Hidden: the eligibility check, the moderation call, first-finder
uniqueness, and the unique-constraint race.

TEST FIRST:
- claim() on an unclaimed place succeeds and marks first finder
- claim() on an already-claimed place returns a clear conflict
- TWO CONCURRENT claims on the same place: exactly one wins. Write this
  as a real concurrency test with two transactions, not a mock. The
  unique constraint on place_id is what makes first-finder credit
  meaningful, so prove it holds under race.
- claim() on an ineligible place is rejected before moderation runs
  (do not spend a classifier call on a blocked place)
- A caption failing moderation rejects the whole claim atomically —
  no orphan discovery row
- list_in_bounds respects the 500-feature cap

Then implement. Order matters: eligibility, then moderation, then the
insert, all in one transaction.
```

**Acceptance:** The concurrency test proves exactly one winner. No orphan rows on moderation failure.

---

## Step 14: Claiming UI and the stamp

```
Build the discovery flow in /web.

TEST FIRST (Vitest + MSW):
- The caption field caps at 140 characters with a live counter
- Submitting with an empty caption shows an inline error and does not
  send a request
- A BLOCKED eligibility verdict shows a plain explanation and hides the
  claim button
- ETYMOLOGY_REQUIRED reveals the etymology field and blocks submit
  until it is filled
- A successful claim shows the first-finder badge
- A conflict (someone claimed it first) shows a clear message, not a
  generic error

Then implement to the design doc:
- The stamp animation: scale 1.4 to 1.0 with overshoot over 400ms, a
  brass ring pulsing outward, haptic thunk on mobile
- prefers-reduced-motion replaces it with a simple fade
- The first-finder badge sets the handle in Fraunces

E2E: sign in, search, claim, assert the pin appears on the globe and the
badge renders.

Verify the stamp in the browser. This is the emotional peak of the
product — judge it by eye, and iterate on the timing until it feels
good.
```

**Acceptance:** The stamp feels satisfying. Every eligibility state renders correctly.

---

# Phase 5 — The map layers

## Step 15: Viewport module and pins

```
Create /api/app/modules/viewport/.

PUBLIC INTERFACE — exactly one function:
  async def query(bbox: BBox, zoom: int, user_id: UUID | None) -> ViewportData

Hidden: bbox snapping, Redis caching, clustering thresholds, priority
scoring, the 500-cap.

TEST FIRST:
- Small pans produce the same cache key (bbox snapping works). This is
  the test that makes or breaks viewport performance — without snapping,
  every pixel of movement is a cache miss.
- The result is capped at 500 features
- Zoom bands return the right shape: country aggregates at z0-3,
  clusters at z4-7, individual pins at z8+
- A cache hit and a cache miss return identical payloads
- Bookmarks are included only when user_id is provided

Then implement, and extend the globe module with setLayers() rendering:
- Discovery pins as brass circles with a glow ring underneath, drawn
  from a sprite sheet — NEVER DOM markers, which is the standard way to
  destroy map performance
- Cluster circles scaled by count with tabular numerals
- Bookmark pins in a distinct style, toggleable
- feature-state for hover and selected so interaction does not
  re-upload the source

Verify in the browser at multiple zoom levels. Screenshot each band.
```

**Acceptance:** 500 pins render at 55fps+ on a mobile viewport. Panning hits the cache.

---

## Step 16: Bookmarks

```
Add bookmarks. Small step — this should be well under 200 lines.

TEST FIRST:
- POST /api/bookmarks/{placeId} is idempotent
- DELETE is idempotent
- GET returns the user's bookmarks with place data joined
- Bookmarking requires auth
- Bookmarks appear in viewport queries when the user is authenticated

Then implement the API endpoints, a one-tap star control in the place
sheet with optimistic UI, and a bookmark layer toggle on the globe.

E2E: bookmark a place, reload, confirm it persists and renders.
```

**Acceptance:** One tap to bookmark. Optimistic UI rolls back on failure.

---

# Phase 6 — Contests

The most intricate logic in the product. Take it slowly.

## Step 17: Contest resolution — pure logic

```
Create /api/app/modules/contests/resolution.py — PURE FUNCTIONS ONLY.
No database, no I/O. This is where all the rules from section 6.6 of the
PRD live, and isolating them from I/O is what makes them testable.

  def quorum_for(tier: int) -> int
  def score(agree: int, disagree: int) -> int
  def meets_ratio_floor(agree: int, disagree: int) -> bool
  def resolve(proposals: list[ProposalTally], tier: int,
              incumbent: ProposalTally | None) -> Outcome

Outcome is WINNER(id, score), RUNOFF(id_a, id_b), or NO_QUORUM(leader_id).

TEST FIRST — this needs the most thorough suite in the codebase:
- Quorum is 100 / 40 / 15 for tiers 1 / 2 / 3
- A proposal below the 60% agree ratio cannot win even with high net votes
- 150 agree / 400 disagree loses to 120 agree / 5 disagree
- A margin under 10% between the top two produces RUNOFF
- A margin of exactly 10% produces WINNER, not RUNOFF (boundary)
- Below quorum produces NO_QUORUM carrying the leader
- An incumbent survives unless the challenger beats it by 20%
- A challenger at exactly 20% above the incumbent wins (boundary)
- Ties break by agree ratio, then by earlier submission
- An empty proposal list produces NO_QUORUM without raising
- A single proposal meeting quorum wins outright
- Property test: resolve() is deterministic and total — never raises for
  any input in range

Only after every one of these is green, move on.
```

**Acceptance:** Every boundary case tested explicitly. Zero I/O in this module.

---

## Step 18: Contests module

```
Create /api/app/modules/contests/ wrapping the pure resolution logic.

PUBLIC INTERFACE — exactly four functions:
  async def propose(place_id: int, user_id: UUID, text: str) -> Proposal
  async def vote(proposal_id: int, user_id: UUID, value: int) -> None
  async def resolve_due() -> list[ContestOutcome]
  async def state_for(place_id: int) -> ContestState

Hidden: the 24h window, moderation, opening a contest on first proposal,
runoff scheduling, term tracking, incumbent injection, nickname
promotion, history writing.

TEST FIRST:
- The first proposal on a place opens a contest closing in 24h
- A later proposal joins the existing contest, does not open a new one
- A proposer cannot vote on their own proposal
- Voting requires an account ≥ 48h old with ≥ 1 prior discovery
- A vote can be changed until close, not after
- Moderation runs at proposal time, never at resolution
- resolve_due promotes the winner to the nicknames table with a 30-day
  term and writes nickname_history
- A RUNOFF outcome opens a 24h runoff contest with only the top two
- NO_QUORUM leaves a leading candidate and permits reopening after 7 days
- A term expiring with no challenger renews the incumbent silently
- resolve_due is IDEMPOTENT — running it twice does not double-promote.
  Test this explicitly; the scheduler will retry.

Then implement, plus an APScheduler job on a single instance with a
Redis lock as a second guard.
```

**Acceptance:** The idempotency test passes. A full contest lifecycle runs end to end in a test with a controllable clock.

---

## Step 19: Contest UI

```
Build the contest board in the place sheet.

TEST FIRST:
- The countdown renders remaining time and reaches zero without going negative
- Proposals sort by net score
- Agree renders verdigris, disagree renders wax
- Vote state is never conveyed by colour alone — icons and labels too
- Voting when signed out opens the sign-in sheet, and the vote completes
  after auth
- A proposal near quorum shows a brass progress indicator
- A user's own proposal has its vote controls disabled with a reason

Then implement to the design doc: brass countdown ring depleting around
the header, proposal cards, vote count roll animation, the propose field
with a live character counter.

E2E: propose, vote, advance the clock, assert the nickname resolves and
renders on the globe.
```

**Acceptance:** The full loop works e2e with a controllable clock.

---

## Step 20: Nickname rendering

```
Render nicknames on the globe. Inside the globe module only.

TEST FIRST:
- A nickname layer is added below the official label with the correct offset
- symbol-sort-key is bound to the winning score
- The nickname toggle hides the layer entirely
- Places with no nickname render no second label
- The layer updates when the nickname source changes without a full
  style reload

Then implement: a second symbol layer, brass, quoted, offset below the
official name, with sort key from the score so better-supported
nicknames win collisions. Let MapLibre's collision engine do the work —
do not implement collision detection.

Verify in the browser: zoom to a nicknamed place, screenshot, confirm
both labels render and the nickname is visually subordinate. Then zoom
out until labels collide and confirm the right one survives.
```

**Acceptance:** Both labels render correctly. Collision priority follows score. Screenshots at three zoom levels.

---

# Phase 7 — Ship

## Step 21: Passport and share cards

```
TEST FIRST:
- Country completion percentages compute correctly
- First-finder count excludes discoveries on already-claimed places
- The share card renders without user text overflowing
- User-submitted text is HTML-escaped in the card
- The card caches with the right headers

Then implement the passport grid, completion rings, and server-rendered
share card images. Validate every card in at least two social preview
debuggers — a broken preview kills the growth loop silently.
```

**Acceptance:** Cards validate in real preview tools.

---

## Step 22: Performance and hardening

```
1. Load test the viewport and search endpoints with locust. Targets:
   search p95 under 200ms, viewport p95 under 400ms at 1000 concurrent.

2. Frontend performance on a REAL mid-range Android device, not a
   throttled desktop. Globe reprojection is GPU work and desktop
   throttling does not simulate it. Target 55fps+ panning at 500 pins.
   If it misses: tighten the pin cap, then the clustering thresholds.

3. Rate limits on all write endpoints. Hashed IP in Redis only, never
   in Postgres.

4. Observability: Sentry both ends, structured logging with a request id
   propagated end to end, Prometheus metrics for search p95, viewport
   cache hit rate, contests resolved, and moderation rejection rate.

5. Degradation checklist — verify each by actually killing the service:
   - Typesense down: search falls back to pg_trgm, slower
   - Photon down: exact search still works
   - Anthropic down: proposals rejected, everything else unaffected
   - Redis down: viewport reads from Postgres, writes disabled

6. Accessibility audit: keyboard navigation of the globe, focus trap in
   the place sheet, aria-live on results, 44px tap targets, 200% font
   scaling without layout break. Run axe in the e2e suite.
```

**Acceptance:** Load targets met. Every dependency killed in turn without losing the globe.

---

## Step 23: Deploy

```
- /web to Cloudflare Pages
- /api and the scheduler worker to Fly.io as separate processes. The
  worker MUST be pinned to a single instance or contests will resolve
  twice.
- Postgres on Supabase with PostGIS and pg_trgm
- Redis on Upstash, Typesense and Photon on Fly
- Basemap: switch from OpenFreeMap to Protomaps PMTiles on Cloudflare R2
  behind the CDN
- GitHub Actions: verify and e2e on PR, deploy on merge, migrations as a
  release command before the new version takes traffic

Write docs/DEPLOY.md and docs/RUNBOOK.md. The runbook must cover:
tripping the moderation kill switch, hiding a discovery, freezing a
contest, rolling back a migration, and recovering from a double-resolved
contest.

Pre-launch checklist:
- Blocklist sourced from a real maintained list
- 500 seed discoveries across 60 countries, hand-reviewed
- Restricted zones built from Overpass and spot-checked
- Attribution visible: OpenStreetMap ODbL, GeoNames CC-BY
- All share cards validated
- Sentry receiving from both apps
```

**Acceptance:** Push to main deploys. The rollback procedure works when you actually try it.

---

# Notes on sequencing

**The globe comes before the product.** Phases 0–1 exist before any business logic because the globe is the highest-risk component and the one thing that cannot be salvaged by later polish. If it doesn't feel good after step 6, better to know on day 4 than day 15.

**Phase 0 is not optional and not reorderable.** Building features before the three loops are closed means every subsequent step is unverifiable. The type-boundary check in step 1 in particular — rename a field, watch the frontend break — is the single check that keeps the API contract honest for the whole project.

**Three steps deserve extra care.** Step 11 (moderation) is where fail-closed behaviour must be proven, not assumed. Step 13 (claiming) has a real concurrency requirement that a mock cannot test. Step 17 (contest resolution) has the most boundary conditions in the codebase, which is exactly why it is pure functions with no I/O.

**Estimated total: 19–22 focused days.** Launch cut through step 20 is roughly 17.
