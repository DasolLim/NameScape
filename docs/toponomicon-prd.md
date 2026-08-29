# Toponomicon — Product Requirements Document

**Working title:** Toponomicon — *the atlas of absurd place names*
**Version:** 1.0 (finalized)
**Date:** August 2026
**Author:** David (Dasol Lim)
**Companion docs:** `design-system-and-brand.md`, `globe-map-architecture.md`

---

## 1. Overview

Toponomicon is a shared 3D globe where people find, claim, and share real places with absurd names. Dildo in Newfoundland. Batman in Turkey. Truth or Consequences in New Mexico. Cockermouth, Ffynnongroyw, Boring, Dull.

Every place on the globe is real and every name shown is the true one. The play sits on top: users **discover** places (each place can be claimed exactly once, and the finder is credited permanently), and users **propose nicknames** that the community votes on. A nickname that wins its contest renders on the globe beneath the official name — never replacing it.

The core insight is that the world is already funnier than anything users could invent. The product's job is to help people find that and put their name on it.

### 1.1 Two content types, deliberately separate

These behave nothing alike and must not share a system.

| | Discovery | Nickname proposal |
|---|---|---|
| Nature | Curatorial — a real place, verified | Creative — invented text |
| Frequency | Once per place, ever | Many per place, recurring |
| Verification | Gazetteer anchor | Moderation pipeline |
| Reward | Permanent first-finder credit | Winning the contest |
| Failure mode | Fabricated places | Abusive text |

### 1.2 The architectural decision everything rests on

**Every discovery anchors to a real gazetteer record.** A user does not type a place name — they search a gazetteer and claim a record by its `geonames_id`. This single decision:

- Makes fabricated places impossible
- Gives permanent, deduplicated identity to every place
- Supplies exact coordinates, feature class, and country for free
- Removes most of the moderation surface before it exists

Discovery captions and nickname proposals are free text and need moderation. The *place itself* never does.

---

## 2. Goals and non-goals

### 2.1 Goals

| # | Goal |
|---|---|
| G1 | A globe that feels genuinely good to spin and zoom — the product lives or dies here |
| G2 | Search that works, because search is the product and it's where this category fails |
| G3 | Make first-finder credit feel like a real, scarce reward |
| G4 | Nickname contests that produce a recurring reason to return |
| G5 | Keep the map complete and truthful while keeping the game out of sensitive places |
| G6 | A codebase that stays testable and modifiable as it grows |

### 2.2 Non-goals

- Turn-by-turn navigation or routing
- Editing basemap geometry — users name places, they don't draw them
- Real-money anything
- Native mobile apps at v1 (see §11.4)
- Being a travel guide — Atlas Obscura already is one

### 2.3 Content stance

The failure mode of this product is that it becomes "laugh at foreign and Indigenous names." Many toponyms that sound funny in English are ordinary or sacred in their own language. The eligibility tiers in §7 exist specifically to design against this, and etymology display is a P0 feature, not decoration.

---

## 3. Success metrics

| Metric | Target (first 60 days) |
|---|---|
| Globe first meaningful paint | < 1.5s on 4G |
| Search p95 latency | < 200ms |
| Sessions with ≥ 1 discovery claimed | ≥ 20% |
| Day-7 return rate | ≥ 25% |
| Contests reaching quorum | ≥ 40% of contests opened |
| Passport shares per week | ≥ 100 |
| Frame rate, 500 pins, mid-range Android | ≥ 55fps |

Search latency is the leading indicator. Every product in this category that failed, failed at search first.

---

## 4. Users

**The Browser (~55%).** Arrived from a share. Spins the globe, taps a few pins, reads captions. Success is that the globe is fun to touch and nothing blocks them.

**The Collector (~25%).** Wants stamps in their passport and country completion. Success is that first-finder credit is visible and scarce.

**The Wit (~12%).** Here for nickname contests. Success is a fast propose-and-vote loop with a visible countdown.

**The Etymologist (~8%).** Genuinely interested in toponymy. Small group, highest-quality contributions, and their presence is what keeps the tone curious rather than mocking. Design for them explicitly.

---

## 5. Core loops

**Spin loop (seconds).** Open → globe drifts → drag to spin → tap a brass pin → read → keep spinning.

**Discovery loop (minutes).** Search a name → find a real place → check it's unclaimed → write a caption → stamp it → first-finder badge.

**Contest loop (days).** Propose a nickname → 24h contest → vote → result → nickname renders on the globe for a 30-day term.

**Collection loop (weeks).** Passport fills → country completion rings advance → share the passport.

---

## 6. Feature specification

**P0** launch, **P1** fast-follow, **P2** later.

### 6.1 The globe (P0)

MapLibre GL JS v6 with `projection: {type: 'globe'}`. Full detail in the companion architecture doc. Product requirements:

- Idle auto-rotation at ~4°/sec on the landing view, cancelling on any interaction and resuming after 5s idle.
- Drag to spin. Under globe projection, panning *is* rotation.
- Continuous zoom from planet to street with no mode switch.
- `flyTo` with `curve: 1.6, speed: 0.8` when focusing a place — the arcing swoop is a signature moment.
- Discovery pins in brass with a glow ring, clustered by zoom band.
- The globe **never unmounts**. Every other surface floats over it.

### 6.2 Search (P0)

The most important non-globe feature.

- Instant results as you type, debounced 150ms.
- Searches the local gazetteer index (GeoNames + alternate names), not a hosted third-party service.
- Results show: name, feature type icon, country, and claim status (unclaimed / claimed by @user).
- Photon handles fuzzy and typo tolerance.
- Selecting a result flies the globe to it and opens the place sheet.
- Empty results offer "search worldwide" rather than a dead end.

### 6.3 Place sheet (P0)

Three-stage bottom sheet on mobile, right panel on desktop.

- **Peek** — official name, nickname if any, finder handle.
- **Half** — etymology, discovery caption, vote controls, feature type and country.
- **Full** — nickname history, full contest board, bookmark control.

Etymology comes from Wikidata via the Who's On First concordance, with a graceful fallback when absent.

### 6.4 Discovery / claiming (P0)

1. User searches and selects a real gazetteer record.
2. System checks eligibility (§7) and claim status.
3. User writes a caption, max 140 characters, which goes through moderation.
4. **Stamp.** The pin drops with overshoot, a brass ring pulses, haptic thunk.
5. If unclaimed, a **first finder** badge is awarded permanently and displayed with the place forever.

A claimed place can still be bookmarked, voted on, and nicknamed by anyone. Only the *discovery credit* is exclusive.

### 6.5 Bookmarks (P0)

Save any place to a personal list, rendered on the globe as a distinct pin style when the bookmarks layer is toggled on. No cap. This is the lightest-weight engagement action in the product and should require exactly one tap.

### 6.6 Nickname contests (P0)

The full mechanic:

- The first proposal on a place opens a **24-hour contest**. All proposals submitted during that window compete in it.
- Score is **net votes** (agree − disagree) with a **60% agree-ratio floor**.
- One vote per account per proposal, changeable until close. Proposers cannot vote on their own proposal.
- **Quorum scales by place tier:**

| Tier | Example | Net votes |
|---|---|---|
| 1 | Major cities, Great Lakes | 100 |
| 2 | Towns, notable features | 40 |
| 3 | Villages, minor lakes and creeks | 15 |

- The winner must lead the runner-up by **10%**. Inside that margin, the top two go to a 24-hour **runoff**.
- The winner holds a **30-day term**, then becomes challengeable.
- **Incumbent defence:** a challenger must beat the incumbent's original winning score by 20% to unseat it. No challenger, and the incumbent renews silently.
- **No quorum:** the top proposal becomes a visible *leading candidate* in the place sheet, and the contest may reopen after 7 days.
- Ties break by higher agree ratio, then by earlier submission.

Moderation runs at **proposal time**, never at contest close. A slur that collects 100 votes before anyone checks is a far worse state than one rejected at submission.

### 6.7 Nickname rendering (P0)

A second symbol layer above the basemap label, offset below, in brass, in quotes. `symbol-sort-key` bound to the winning score so better-supported nicknames win collisions. Official name always primary. A global toggle hides nicknames entirely for users who want the clean map.

### 6.8 Accounts (P0)

- Email magic link or OAuth. No passwords.
- A username, 3–20 chars, unique, immutable after 7 days.
- Public profile at `/@username`.
- Everything readable without an account. Claiming, voting, and bookmarking require one.

### 6.9 Passport (P1)

The collection artifact. A grid of stamps for every discovery, country completion rings, and the first-finder count as the hero number. Generates a shareable image — this is the growth surface.

### 6.10 Discover feed (P1)

Recent discoveries globally, with filters for newest, most-voted, and near me. Tapping an entry flies the globe there.

### 6.11 Collections (P2)

Themed sets — "places named after body parts," "towns that sound like insults," "hydronyms that are just a sigh." Curated at first, user-created later.

### 6.12 Weekly hunt (P2)

A themed challenge pushing discovery into under-explored regions. Purely a distribution-shaping tool; without it everything concentrates on the same forty famous places.

---

## 7. Eligibility and content policy

The map shows everything. The **game** does not run everywhere. This distinction is load-bearing — see §6 of the architecture doc for why hiding basemap names is both harmful and impractical.

### 7.1 Tiers

**Tier A — never nominatable.** Places of worship and ceremonial sites, memorials, atrocity and genocide sites, cemeteries and war graves, hospitals, prisons and detention facilities, refugee camps, disaster sites, disputed territories, and anything named for a living or recently deceased person. Most derive automatically from OSM tags via Overpass rather than hand curation.

**Tier B — etymology required.** Any name in a language other than the submitter's UI language requires an etymology note before the caption can be submitted. This is the highest-leverage rule in the policy: it converts "haha, weird foreign word" into a small research task, filtering lazy mockery while letting genuine absurdity through. Indigenous toponyms sit here, not in Tier A — a blanket ban is its own erasure — plus a community flag channel.

**Tier C — free.** Coincidental English-language absurdity and self-aware novelty names.

### 7.2 Implementation

A `restricted_zones` table of PostGIS polygons with a `rule_type` enum, checked at nomination time. When a place is ineligible, say so plainly. The place still appears on the map and in search; it simply cannot be claimed or nicknamed.

### 7.3 Moderation pipeline

Applies to captions and nickname proposals, never to places.

1. **Normalize** — trim, collapse whitespace, strip zero-width and homoglyph characters.
2. **Blocklist** — deterministic match after leetspeak normalization. Source the list externally; do not author it.
3. **Classify** — a Claude Haiku call returning structured booleans for: targets protected group, targets private individual, sexual, violent, spam. Any positive rejects. **Fails closed** — on timeout or error, reject.
4. **Near-duplicate** — `pg_trgm` similarity at 0.85 against existing proposals for that place. Duplicates merge rather than reject.

Rejection reasons stay server-side. Telling users which rule they hit teaches them to beat it.

---

## 8. Engineering requirements

These are product requirements, not suggestions. They exist because this codebase will be built largely by an LLM, and LLM-authored code degrades without fast, automatic feedback.

### 8.1 Three feedback loops

**Loop 1 — Static types.** TypeScript `strict` on the frontend with no `any`. Python with `mypy --strict` and Pydantic v2 on the backend. Critically, the **API boundary is generated, not hand-written**: FastAPI emits OpenAPI, and `openapi-typescript` generates the frontend client types in CI. A backend field rename must break the frontend typecheck. If it doesn't, the loop is broken.

**Loop 2 — Browser access.** Playwright MCP is configured so Claude Code can drive a real browser: navigate, screenshot, click, and read the console. This matters more here than in most projects because **map bugs are visual**. A globe that renders at the wrong projection, pins that don't collide correctly, a fly-to that overshoots — none of these fail a unit test. Claude must be able to look.

**Loop 3 — Automated tests.** Vitest for frontend units, pytest for backend, Playwright for end-to-end, and Schemathesis for contract fuzzing against the OpenAPI schema. A single `make verify` runs typecheck, lint, and the full suite. Every implementation step ends with it green.

### 8.2 TDD is mandatory

Every step follows red → green → refactor:

1. Write the failing test. **Run it. Watch it fail.** A test that has never failed proves nothing.
2. Write the minimum code to pass.
3. Refactor with the test as a safety net.

**Small steps are enforced structurally.** No implementation step may produce more than ~200 lines of diff. If a step is bigger, it was specified wrong and must be split. This is the single most effective constraint on LLM-authored code: large diffs are where unreviewed mistakes hide.

`make verify` runs after every step. CI rejects any commit where coverage drops.

### 8.3 Deep modules

The codebase follows Ousterhout's principle: **the best modules provide a lot of functionality through a simple interface.** Interface complexity is a cost paid by every caller; implementation complexity is paid once. A module earns its place when it hides much more than it exposes.

The failure mode to avoid is the **shallow module** — a class with fifteen public methods that leak its internal steps, forcing every caller to understand the sequence. A `ContestService` exposing `getProposals`, `computeNetVotes`, `checkQuorum`, `checkMargin`, `resolveTies`, and `applyIncumbentBonus` has not encapsulated anything. It has just renamed a procedure.

The same logic behind `contests.resolve(placeId) -> ContestOutcome` is a deep module. One entry point, all of the quorum tiers, margins, runoffs, terms, and incumbency hidden behind it.

**Module boundaries (backend):**

| Module | Public interface | Hides |
|---|---|---|
| `gazetteer` | `search()`, `resolve()`, `enrich()` | GeoNames import, alternate names, Photon fuzzy matching, ranking, Wikidata etymology |
| `discoveries` | `claim()`, `listInBounds()`, `forUser()` | First-finder logic, uniqueness, caption moderation, XP |
| `contests` | `propose()`, `vote()`, `resolve()`, `stateFor()` | Quorum tiers, ratio floors, margins, runoffs, terms, incumbency, ties |
| `eligibility` | `check()` | Zone polygons, OSM tag rules, tier lookup, etymology requirement |
| `moderation` | `screen()` | Normalize, blocklist, classifier, circuit breaker, near-duplicate merge |
| `accounts` | `authenticate()`, `profile()`, `passport()` | Magic links, sessions, username rules, stamp aggregation |
| `viewport` | `query()` | Bbox snapping, caching, clustering thresholds, priority scoring |

Seven modules, none with more than four public methods.

**Module boundaries (frontend):**

| Module | Public interface | Hides |
|---|---|---|
| `globe` | `focusOn()`, `setLayers()`, `onPlaceTap()`, `startIdleSpin()` | All of MapLibre — projection setup, sources, layers, sprite loading, collision priority, spin loop, globe zoom-delta math, feature-state |
| `api` | Generated typed client | Fetch, auth headers, error normalization |

The `globe` module is the most important boundary in the project. **No MapLibre import exists anywhere else in the codebase.** If a component needs the map to do something, it goes through this interface or the interface grows a method. This is what makes the map testable and what makes it replaceable.

### 8.4 Enforcement

- A lint rule bans `maplibre-gl` imports outside `src/globe/`.
- A test asserts each module's public export count stays under its budget.
- Coverage gate at 80% on backend modules, 70% overall.
- `make verify` must pass before any commit.

---

## 9. Data model

```
places                       -- gazetteer cache, not user data
  id                bigserial PK
  geonames_id       bigint unique
  wof_id            bigint nullable
  wikidata_id       text nullable
  name              text
  name_normalized   text
  alternate_names   text[]
  feature_class     char(1)        -- P populated, H hydro, T terrain
  feature_code      text
  country_code      char(2)
  admin1            text
  centroid          geography(Point, 4326)
  tier              smallint        -- 1..3, drives contest quorum
  population        integer
  etymology         text nullable
  gin index on name_normalized gin_trgm_ops
  gist index on centroid

users
  id                uuid PK
  username          text unique
  email             text unique
  username_locked_at timestamptz
  created_at        timestamptz

discoveries
  id                bigserial PK
  place_id          bigint FK unique   -- one discovery per place, ever
  user_id           uuid FK
  caption           text
  created_at        timestamptz
  index on (user_id, created_at desc)

bookmarks
  user_id           uuid FK
  place_id          bigint FK
  created_at        timestamptz
  PK (user_id, place_id)

contests
  id                bigserial PK
  place_id          bigint FK
  status            text          -- open | runoff | resolved | expired
  opened_at         timestamptz
  closes_at         timestamptz
  winner_proposal_id bigint FK nullable
  winning_score     integer nullable
  term_ends_at      timestamptz nullable

proposals
  id                bigserial PK
  contest_id        bigint FK
  place_id          bigint FK
  user_id           uuid FK
  text              text
  normalized_text   text
  agree             integer
  disagree          integer
  is_incumbent      boolean
  created_at        timestamptz
  index on (contest_id, agree desc)

votes
  user_id           uuid FK
  proposal_id       bigint FK
  value             smallint      -- +1 | -1
  created_at        timestamptz
  PK (user_id, proposal_id)

nicknames                     -- resolved winners, what the globe renders
  place_id          bigint PK FK
  text              text
  proposal_id       bigint FK
  score             integer
  term_ends_at      timestamptz
  created_at        timestamptz

nickname_history
  id                bigserial PK
  place_id          bigint FK
  text              text
  held_from         timestamptz
  held_until        timestamptz

restricted_zones
  id                bigserial PK
  geom              geography(Polygon, 4326)
  rule_type         text          -- no_nomination | etymology_required | review_required
  reason            text
  source            text
  gist index on geom
```

---

## 10. API surface

| Method | Path | Module |
|---|---|---|
| GET | `/api/search` | gazetteer |
| GET | `/api/places/{id}` | gazetteer |
| GET | `/api/viewport` | viewport |
| POST | `/api/discoveries` | discoveries |
| GET | `/api/discoveries/{id}` | discoveries |
| POST/DELETE | `/api/bookmarks/{placeId}` | accounts |
| GET | `/api/bookmarks` | accounts |
| GET | `/api/contests/{placeId}` | contests |
| POST | `/api/proposals` | contests |
| POST | `/api/votes` | contests |
| POST | `/api/auth/magic-link` | accounts |
| GET | `/api/users/{username}` | accounts |
| GET | `/api/passport/{username}` | accounts |

Every response schema is a Pydantic model. The frontend never hand-writes a request or response type.

---

## 11. Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Map | MapLibre GL JS v6, globe projection | Vector labels that stay upright, styleable, any language — the reason Cesium is disqualified |
| Basemap (dev) | OpenFreeMap | Free, no keys, no limits, zero setup |
| Basemap (prod) | Protomaps PMTiles on Cloudflare R2 | Single file, range requests, near-zero cost |
| Geocoding | Photon, self-hosted | OSM-based, fuzzy, no rate limits in production |
| Gazetteer | GeoNames dumps + Who's On First | 12M places, CC-BY, stable IDs for anchoring |
| Etymology | Wikidata API | Free, reachable via WOF concordance |
| Zone sourcing | Overpass API | Builds Tier A polygons from OSM tags |
| Frontend | React 19 + Vite, TypeScript strict | SPA; the globe never unmounts, so SSR buys nothing |
| State | Zustand | Map state does not fit server components |
| Backend | FastAPI, Python 3.12, Pydantic v2, mypy strict | Matches existing depth; strong runtime + static typing |
| Database | Postgres 16 + PostGIS + pg_trgm | |
| Cache | Redis 7 | Viewport cache, rate limits |
| Search | Typesense | Sub-50ms typo-tolerant place search |
| Jobs | APScheduler, single instance, Redis-locked | Contest resolution must never double-run |
| Moderation | Claude Haiku | |
| Testing | Vitest, pytest, Playwright, Schemathesis | |
| Deploy | Cloudflare Pages, Fly.io, Supabase, Upstash, R2 | |

### 11.1 On the backend language choice

TypeScript end-to-end would give a single shared type system with no generation step. FastAPI plus generated OpenAPI types is one indirection more, but it keeps the backend in Python where the existing depth is, and `mypy --strict` plus Pydantic is a genuinely strong type boundary. The generation step is CI-enforced, so the loop is still closed. Either is defensible; this doc assumes FastAPI.

### 11.2 Globe gotchas

- `setProjection` before style load throws. Set it in the style JSON.
- Zoom-to-planet-size math differs under globe projection. Any centre or zoom delta must account for it. This will bite in the fly-to animation.
- Globe is web-only — not in MapLibre Native.

### 11.3 Performance targets

60fps panning at 500 visible pins on a mid-range Android device. Test on real hardware; desktop throttling does not simulate GPU reprojection cost.

### 11.4 Mobile

PWA at v1. Native would need a webview for the map, which removes most of the reason to go native.

---

## 12. Milestones

| Phase | Scope | Days |
|---|---|---|
| 0 | Repo, tooling, three feedback loops, CI | 1.5 |
| 1 | Globe module — projection, spin, fly-to | 2 |
| 2 | Gazetteer — import, search, Typesense, Photon | 2 |
| 3 | Accounts and auth | 1 |
| 4 | Discoveries, claiming, stamps | 2 |
| 5 | Viewport, pins, clustering, bookmarks | 2 |
| 6 | Eligibility and moderation | 1.5 |
| 7 | Contests — propose, vote, resolve, terms | 2.5 |
| 8 | Nickname rendering on globe | 1 |
| 9 | Passport, feed, share cards | 1.5 |
| 10 | E2E suite, performance, deploy | 2 |

**Launch cut:** phases 0–8. Passport and feed follow within a week.

**Total: ~19 days.**

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Globe performance on mid-range mobile | Pin cap, clustering, sprite-based pins never DOM markers, test on real hardware |
| Search quality — the category killer | Own the index, Typesense + Photon, alternate names, measure p95 |
| Product reads as mocking foreign names | Tier B etymology gate, etymology display P0, community flags |
| Contest quorum never reached | Tiered quorum, leading-candidate fallback, reopen after 7 days |
| Sockpuppet voting | Account age ≥ 48h plus one prior discovery required to vote |
| Empty globe at launch | Seed 500 hand-curated discoveries across 60 countries before opening |
| LLM-authored code rots | The three feedback loops, TDD, 200-line diff cap, module export budgets |

---

## 14. Open questions

1. Should the 30-day term vary by tier? A village nickname probably deserves longer, since fewer people will re-contest it.
2. Can one place hold multiple concurrent nicknames? Single-winner is cleaner and is what this doc assumes.
3. Should place pages be search-indexable? Good for growth, but it makes every satirical nickname a permanent search result attached to a real place.
4. Is first-finder credit transferable or revocable if the account is deleted?
