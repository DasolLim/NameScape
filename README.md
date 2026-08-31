# Toponomicon

**The atlas of absurd place names.** A shared 3D globe where people claim real
gazetteer places with genuinely absurd real names, propose nicknames the
community votes on, and find out what those names actually mean.

🌍 **Live (development):** [toponomicon.vercel.app](https://toponomicon.vercel.app)

A winning nickname renders *beneath* the official name, never replacing it. The
map shows everything: eligibility gates claiming and nominating, never display.
Removing names from a basemap is cartographic erasure.

---

## Contents

- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Running it locally](#running-it-locally)
- [System architecture](#system-architecture)
- [The rules this codebase is built under](#the-rules-this-codebase-is-built-under)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project layout](#project-layout)
- [Domain vocabulary](#domain-vocabulary)

---

## What it does

### Claim a place
Search real gazetteer places and claim one. Exactly one person can ever
be the **first finder** of a place, enforced by a database unique constraint
rather than by application logic. Their name stays with it permanently.

**You do not need an account to claim.** An unsigned visitor gets one real
claim that expires in seven days unless they create an account. The expiry is
what makes it work: a provisional claim nobody can take is not worth
protecting, and a permanent anonymous one is a griefing vector.

### Name it
The first nickname proposal on a place opens a 24-hour contest. The community
votes; a winner needs quorum (100/40/15 net votes by significance tier) and
holds a 30-day term. A challenger has to beat the incumbent's score by 20%. If
the top two finish within 10% of each other, a runoff opens.

### Find out what the name means
Tap a non-English name and the place sheet tells you what it actually means,
resolved through four sources in priority order — Wikidata statements, a
Wikipedia etymology section, a curated lexicon of name elements (`-by`,
`-chester`, `llan-`), and only then a language model.

**A model's answer is labelled unverified, in words**, with a visibly different
treatment and no source link, because there is nothing to cite. Models produce
confident, plausible, false etymologies, and a product about respecting what
names mean cannot quietly serve invented ones. Every entry can be corrected.

### Play the daily puzzle
One mystery place per day, the same for everyone worldwide. Five guesses, each
wrong one revealing the next clue: the name's meaning, then feature type, then
continent, then country, then the pin on the globe. Guesses report distance,
bearing and proximity, and the shareable result grid gives nothing away.

Clues are drafted **ninety days ahead, offline, and approved by a person**. No
model is ever called while a player waits.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| **Frontend** | React 19, TypeScript (strict), Vite | — |
| **Globe** | MapLibre GL JS, globe projection | Real 3D globe, vector tiles |
| **Basemap** | OpenFreeMap / OpenMapTiles | Keeps place names on the map |
| **State** | Zustand | Small, no ceremony |
| **Styling** | Tailwind v4 `@theme` tokens | Design tokens, not scattered hex |
| **Backend** | FastAPI, Python 3.12+ | Async, and the OpenAPI schema is the contract |
| **ORM** | SQLAlchemy 2.0 async, asyncpg | — |
| **Database** | PostgreSQL + PostGIS + pg_trgm | Spatial queries and fuzzy name search |
| **Cache / locks** | Redis | Rate limits, viewport cache, scheduler locks |
| **Migrations** | Alembic (14 revisions) | — |
| **Scheduling** | APScheduler, or platform cron | Contest resolution, claim expiry, puzzle rollover |
| **Models** | OpenRouter | Moderation, etymology, puzzle clues |
| **Mail** | SMTP (Resend); Mailpit locally | Passwordless sign-in links |
| **Tests** | pytest, Vitest, MSW, Playwright | 628 tests |
| **Types** | mypy `--strict`, `openapi-typescript` | The API boundary is generated |

---

## Running it locally

### Prerequisites

- **Docker** — via [Colima](https://github.com/abiosoft/colima) on macOS
  (`postgis/postgis` is amd64-only, so this project uses `imresamu/postgis`)
- **[uv](https://github.com/astral-sh/uv)** for Python
- **Node 20+**

### First run

```bash
git clone https://github.com/DasolLim/FindPlaces.git
cd FindPlaces

make seed-demo                    # migrate, fetch GeoNames data, add demo pins
make dev                          # api :8000, web :5173, mail :8025
```

That loads `cities500 GB CA US:P` — **744k places in 429 MB**, the same dataset
the deployment runs. Override it to load something else:

```bash
make seed GEONAMES="cities500"          # 235k places, faster to set up
make seed GEONAMES="cities500 GB CA US" # everything, 1.48M places in 787 MB
```

A dump name may carry a feature-class filter. `US:P` takes the United States'
populated places without its half a million lakes and quarter million hills,
which is the difference between 470 MB and 101 MB — and still includes Boring,
Oregon.

`make dev` brings up the Linux VM if it is not running. **Postgres listens on
55432 and Redis on 56379** — deliberately off the default ports, because host
installs of both usually claim 5432 and 6379.

### What you need in `api/.env`

Local development needs **nothing**: `make dev` supplies development values,
sends mail to Mailpit at `localhost:8025`, and sets `MODERATION_DEV_BYPASS=true`
so you can submit text without a model key.

For anything beyond that:

| Variable | Needed for | Without it |
|---|---|---|
| `OPENROUTER_API_KEY` | Moderation, etymology, puzzle clues | Moderation **fails closed** — every caption is rejected |
| `SMTP_HOST` etc. | Sign-in mail | Links are logged, not sent |
| `SECRET_KEY` | Signing session cookies | Uses a public dev default |
| `REDIS_URL` | Every write | Writes return 503 |

`MODERATION_DEV_BYPASS` must never be true outside development: it turns a
fail-closed pipeline into a fail-open one.

### Useful targets

```bash
make verify          # mypy --strict, ruff, tsc, eslint, pytest, vitest
make e2e             # Playwright, desktop and mobile
make seed            # real GeoNames data
make gen-types       # regenerate web/src/api/schema.ts from the OpenAPI schema
make migrate-remote  # apply migrations to the deployment database
```

---

## System architecture

```
                    ┌──────────────────────────────────┐
   browser ────────▶│  React 19 SPA                    │
                    │  ┌────────────────────────────┐  │
                    │  │ globe/  (MapLibre)         │  │  ← only module that
                    │  │  focusOn · setLayers ·     │  │    knows MapLibre
                    │  │  onPlaceTap · onViewport   │  │    exists
                    │  └────────────────────────────┘  │
                    │  chrome · search · claim ·       │
                    │  contests · etymology · puzzle   │
                    └───────────────┬──────────────────┘
                                    │ generated types
                                    ▼
                    ┌──────────────────────────────────┐
                    │  FastAPI                         │
                    │                                  │
                    │  gazetteer   search · resolve ·  │
                    │              enrich              │
                    │  discoveries claim · for_user ·  │
                    │              list_in_bounds      │
                    │  accounts    authenticate ·      │
                    │              profile · passport  │
                    │  contests    propose · vote ·    │
                    │              resolve_due · state │
                    │  moderation  screen              │
                    │  eligibility check               │
                    │  viewport    query               │
                    │  puzzles     today · guess ·     │
                    │              state_for           │
                    └────┬───────────────┬─────────────┘
                         ▼               ▼
              ┌────────────────┐  ┌──────────────┐
              │ PostgreSQL     │  │ Redis        │
              │ + PostGIS      │  │ rate limits  │
              │ + pg_trgm      │  │ viewport TTL │
              │ 744k places    │  │ job locks    │
              └────────────────┘  └──────────────┘

  Scheduled work (contest resolution · claim expiry · puzzle rollover)
  runs in-process on a long-lived server, or by cron over HTTP on
  serverless. Every job takes a Redis lock and is idempotent.
```

### Deep modules

Each backend module exposes a deliberately small public interface, and the
count is **asserted by a test**. Adding a public function requires justifying
why the complexity cannot hide behind an existing one.

Guest claiming, for instance, added a whole identity concept, a database
constraint, an expiry job and a merge-on-signup path — and `discoveries` still
exposes three functions, because `claim()` took a `Claimant` union rather than
growing a sibling. Etymology went from one Wikidata lookup to a four-tier
resolution chain behind an unchanged `enrich()`.

### The globe never unmounts

Every other surface floats over it, and closing any surface returns you to the
exact view you left. `maplibre-gl` may not be imported anywhere outside
`web/src/globe/` — **enforced by a lint rule**. If a component needs the map to
do something, it goes through the globe interface, or the interface grows a
method.

### The API boundary is generated

Frontend request and response types come from `openapi-typescript` run against
the live FastAPI schema. A backend field rename **must** break the frontend
typecheck. To confirm the loop still works: rename a field on a Pydantic
response model, `make gen-types`, then `cd web && npm run typecheck` — it must
fail with TS2339.

---

## The rules this codebase is built under

These are rules, not preferences. They exist because this codebase was built
largely by an LLM, and LLM-authored code degrades without fast, automatic
feedback.

1. **TDD.** Every change starts with a failing test that has been *run and
   observed to fail*. A test that has never been red proves nothing — it may be
   asserting something already true.
2. **Small steps.** No change exceeds ~200 lines of implementation diff.
3. **Deep modules.** Public interfaces are budgets. A test asserts each one.
4. **No `maplibre-gl` outside `web/src/globe/`.** A lint rule enforces it.
5. **The API boundary is generated, never hand-written.**
6. **`make verify` passes before every commit.**

Visual changes are verified in a real browser with a screenshot, not only by
test. A wrong projection, mis-colliding labels or an overshooting fly-to fails
no unit test.

---

## Testing

```
416  backend        pytest, real Postgres, transactional rollback per test
142  frontend       Vitest + MSW
 70  end-to-end     Playwright, desktop and mobile
───
628
```

Plus contract fuzzing (Schemathesis), property tests (Hypothesis), accessibility
checks (axe) and load tests (Locust).

**No test makes a network call.** The suite refuses any HTTP client opened
without an explicit transport — a guard added after a test was found quietly
calling Wikipedia and, once an API key existed, spending money on a model.

---

## Deployment

Deployed on **Vercel** with **Supabase** Postgres and **Upstash** Redis.

```bash
make migrate-remote        # schema to the deployment database
vercel deploy --prod
```

Two things that are easy to get wrong:

- **Migrations need a session or direct connection.** Supabase's transaction
  pooler (port 6543) has no prepared statements; Alembic requires them. The
  runtime uses the pooler and disables asyncpg's statement cache, where caching
  is not a slow path but an error on the second query.
- **Serverless starts no scheduler.** Every function instance would start one.
  `RUN_SCHEDULER` stays false and platform cron invokes the same jobs at
  `/api/cron/{job}`, authorised by `CRON_SECRET` and failing closed if it is
  unset. The endpoint accepts GET, because Vercel's scheduler sends GET.

The gazetteer is imported from a developer machine, never from a function.
`cities500 CA GB US:P` is 744k places in 429 MB — the feature-class filter drops
half a million US lakes and a quarter million hills that nobody searches for,
while keeping Boring, Oregon.

---

## Project layout

```
api/                    FastAPI backend, Python 3.12+
  app/
    modules/            the eight deep modules
    llm.py              one provider behind one interface
    ratelimit.py        hashed addresses, Redis only, never Postgres
    scheduler.py        contest resolution, claim expiry, puzzle rollover
  migrations/           Alembic, 14 revisions
  scripts/              gazetteer import, puzzle generation, approval
  tests/
web/                    React 19 + Vite SPA
  src/
    globe/              the only module that imports maplibre-gl
    api/schema.ts       generated, never hand-edited
  e2e/                  Playwright
infra/                  Docker Compose
docs/                   PRD, implementation guide, design system, architecture
```

### Source documents

The specs of record. Read the relevant one before changing its area.

| Doc | Authority over |
|---|---|
| `docs/toponomicon-prd.md` | Features, data model, API surface, module boundaries |
| `docs/toponomicon-implementation-guide.md` | Build order, one step per commit |
| `docs/addendum-a-conversion-habit-etymology.md` | Guest claiming, the puzzle, etymology |
| `docs/design-system-and-brand.md` | Colour, type, motion, screen specs |
| `docs/globe-map-architecture.md` | MapLibre globe, PMTiles, gazetteer, zones |

---

## Domain vocabulary

| Term | Meaning |
|---|---|
| **place** | A gazetteer record, anchored to a `geonames_id`. Never user-authored. |
| **discovery** | A user's claim of a place. Exactly one per place, ever. |
| **first finder** | The user holding that claim. Permanent, shown with the place forever. |
| **bookmark** | A personal save. Unlimited, one tap, distinct pin style. |
| **proposal** | A nickname submitted to a contest. Free text, moderated at submission. |
| **contest** | A 24h window opened by the first proposal on a place. |
| **quorum** | Minimum net votes to resolve — 100 / 40 / 15 by tier. |
| **runoff** | A second 24h contest between the top two when the margin is under 10%. |
| **term** | The 30 days a winning nickname holds before becoming challengeable. |
| **incumbent** | The nickname holding a term. A challenger must beat it by 20%. |
| **nickname** | The resolved winner, rendered beneath the official name. |
| **tier** | A place's 1–3 significance rating. Drives quorum only. |
| **eligibility** | Whether a place may be claimed or nicknamed. Never affects rendering. |
| **restricted zone** | A PostGIS polygon gating nomination. Tier A / B / C. |

---

## Data attribution

- Place data from [GeoNames](https://www.geonames.org/) (CC BY 4.0)
- Basemap from [OpenFreeMap](https://openfreemap.org/) and
  [OpenMapTiles](https://openmaptiles.org/), data
  © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL)
- Etymology from [Wikidata](https://www.wikidata.org/) and
  [Wikipedia](https://www.wikipedia.org/) (CC BY-SA)
