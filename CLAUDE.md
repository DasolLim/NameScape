# Toponomicon

The atlas of absurd place names. A shared 3D globe where users claim real gazetteer
places with genuinely absurd real names, and propose nicknames the community votes
on. A winning nickname renders beneath the official name — never replacing it.

## Source documents

These are the spec of record. Read the relevant one before changing its area.

| Doc | Authority over |
|---|---|
| `docs/toponomicon-prd.md` | Features, data model, API surface, module boundaries |
| `docs/toponomicon-implementation-guide.md` | Build order — steps 0–23, one per commit |
| `docs/design-system-and-brand.md` | Colour, type, motion, screen specs |
| `docs/globe-map-architecture.md` | MapLibre globe, PMTiles, gazetteer, zones |

Where the PRD and the implementation guide disagree on **ordering**, the guide wins.
Where the PRD and the design doc disagree on a **visual detail**, the design doc wins.

## Monorepo layout

```
/api     FastAPI backend, Python 3.12
/web     React 19 + Vite SPA, TypeScript strict
/infra   Docker Compose, migrations, deploy
/docs    PRD and design docs
```

## Non-negotiable rules

These are rules, not preferences. They exist because this codebase is built largely
by an LLM, and LLM-authored code degrades without fast, automatic feedback.

**1. TDD.** Every change starts with a failing test that has been RUN and OBSERVED
to fail. No exceptions, including for "trivial" changes. A test that has never been
red proves nothing — it may be asserting something already true, or nothing at all.

**2. Small steps.** No single change exceeds ~200 lines of implementation diff. If it
would, split it. A step that grew is a step that was specified wrong. Large diffs are
where unreviewed mistakes hide.

**3. Deep modules.** PRD §8.3 lists seven backend modules and two frontend modules
with their exact public interfaces. Those interfaces are budgets, not suggestions.
Adding a public method requires justifying why the complexity cannot be hidden behind
an existing one. A test asserts each module's public export count.

**4. No `maplibre-gl` import may exist outside `/web/src/globe/`.** The globe module
is the only place in the codebase that knows the map library exists. If a component
needs the map to do something, it goes through the globe interface, or the interface
grows a method. A lint rule enforces this.

**5. The API boundary is generated, never hand-written.** Frontend request and
response types come from `openapi-typescript` against the FastAPI schema. A backend
field rename must break the frontend typecheck. If it doesn't, the loop is broken and
nothing else should proceed.

**6. `make verify` passes before every commit.** It runs mypy --strict, ruff,
tsc --noEmit, eslint, pytest, and vitest, failing on the first failure.

## Working protocol

One step from the implementation guide per session, one step per commit. Do not
batch. Each step: write the failing test → run it, watch it fail → minimum code to
pass → refactor → `make verify` green → commit.

Visual changes must be verified in a real browser with a screenshot, not only by
test. Map bugs are visual — a wrong projection, mis-colliding labels, an
overshooting fly-to. None of those fail a unit test.

## Domain vocabulary

| Term | Meaning |
|---|---|
| **place** | A gazetteer record, anchored to a `geonames_id`. Never user-authored. |
| **discovery** | A user's claim of a place. Exactly one per place, ever. |
| **first finder** | The user holding that claim. Permanent, displayed with the place forever. |
| **bookmark** | A personal save. Unlimited, one tap, distinct pin style. |
| **proposal** | A nickname submitted to a contest. Free text, moderated at submission. |
| **contest** | A 24h window opened by the first proposal on a place. |
| **quorum** | Minimum net votes to resolve — 100 / 40 / 15 by tier. |
| **runoff** | A second 24h contest between the top two when the margin is under 10%. |
| **term** | The 30 days a winning nickname holds before becoming challengeable. |
| **incumbent** | The nickname holding a term. A challenger must beat its score by 20%. |
| **nickname** | The resolved winner. What the globe renders beneath the official name. |
| **tier** | A place's 1–3 significance rating. Drives quorum only. |
| **eligibility** | Whether a place may be claimed or nicknamed. Never affects rendering. |
| **restricted zone** | A PostGIS polygon gating nomination. Tier A / B / C per PRD §7. |

## Two rules the product rests on

**The map shows everything.** Eligibility gates claiming and nominating, never
display. A memorial appears in search and on the globe; it simply cannot be claimed.
Removing names from a basemap is cartographic erasure — see the architecture doc §6.

**The globe never unmounts.** Every other surface floats over it, and closing any
surface returns you to the exact view you left.
