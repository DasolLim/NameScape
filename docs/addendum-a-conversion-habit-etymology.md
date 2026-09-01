# NameScape — Addendum A: Conversion, Habit, Etymology

**Extends:** `namescape-prd.md` and `namescape-implementation-guide.md`
**Covers:** Guest claiming · Daily place puzzle · "What it actually means"
**Version:** 1.0

---

## How this fits the existing docs

Two of these three insert into existing phases rather than appending to the end. The daily puzzle is genuinely new surface area and gets its own phase.

| Feature | Where it goes | New public interface? |
|---|---|---|
| Guest claiming | Extends Phase 3–4 (accounts, discoveries) | No — `claim()` takes a `Claimant` union |
| "What it actually means" | Extends Phase 2 (gazetteer) | No — `enrich()` already exists |
| Daily puzzle | New Phase 4.5 | Yes — a new `puzzles` module |

Worth noticing: two of three features add substantial capability behind interfaces that do not grow at all. That is the deep-module principle doing its job — `gazetteer.enrich()` goes from a Wikidata lookup to a four-source resolution chain, and every caller is unaffected.

---

# Part 1 — Guest claiming

## 1.1 Behaviour

An unsigned visitor may claim **exactly one** discovery. The claim is real — the place is locked to them immediately — but it **expires in 7 days** unless they create an account.

The expiry is what makes this work. A provisional claim that can be stolen at any moment is not worth protecting, so loss aversion never engages. A permanent anonymous claim is a griefing vector. A real claim with a deadline is both genuinely theirs and genuinely at risk.

## 1.2 The prompt moment

The signup prompt fires **immediately after the stamp animation completes**, not on exit intent and not on the next action. That is the emotional peak of the product, and it is the only moment where "keep this" means something concrete.

Copy should name what is at stake, not what the product wants: *"Dildo, Newfoundland is yours. Create an account in the next 7 days to keep it."* A visible countdown appears in the place sheet and on the pin until they convert.

## 1.3 Constraints

| Rule | Value |
|---|---|
| Claims per guest session | 1 |
| Claims per hashed IP per day | 3 |
| Expiry | 7 days |
| Guest can vote, bookmark, propose | No — claiming only |
| Caption moderation | Same pipeline, no exceptions |
| Eligibility check | Same, no exceptions |

## 1.4 Edge cases that must be handled

- **Expiry release.** A daily job releases expired guest claims. The place returns to unclaimed and its `first_finder` credit is never awarded.
- **Signup with an existing email.** Merge the guest claim into the existing account rather than creating a duplicate.
- **Guest claims, then signs in as someone who already claimed a place.** The merge still applies — a user may hold many discoveries; the one-claim limit is on the *guest session*, not the account.
- **Race with a signed-in user.** The guest claim is a real row protected by the same unique constraint. Whoever commits first wins. No special casing.
- **Cookie cleared before signup.** The claim is lost. This is correct behaviour and should not be worked around.
- **Multiple guest sessions from one browser.** Rate-limited by hashed IP, which is stored in Redis only, never in Postgres.

## 1.5 Data model

```
guest_sessions
  id                uuid PK
  created_at        timestamptz
  merged_into       uuid FK users nullable
  merged_at         timestamptz nullable

discoveries                        -- extended
  claimant_type     text           -- 'user' | 'guest'
  user_id           uuid FK nullable
  guest_session_id  uuid FK nullable
  expires_at        timestamptz nullable   -- non-null only for guest claims

  CHECK (
    (claimant_type = 'user'  AND user_id IS NOT NULL
                             AND guest_session_id IS NULL
                             AND expires_at IS NULL)
    OR
    (claimant_type = 'guest' AND guest_session_id IS NOT NULL
                             AND user_id IS NULL
                             AND expires_at IS NOT NULL)
  )
```

The CHECK constraint is doing real work here. It makes the invalid states — a guest claim with no expiry, a user claim with an expiry — unrepresentable in the database rather than merely discouraged in code.

## 1.6 Module impact

`discoveries.claim()` takes a `Claimant` union instead of a `user_id`:

```python
Claimant = UserClaimant | GuestClaimant

async def claim(place_id: int, claimant: Claimant, caption: str) -> Discovery
```

The merge runs **inside `accounts.authenticate()`**. When a session is created and a guest cookie is present, the merge happens transparently. No new public function, and callers never orchestrate it.

---

# Part 2 — Daily place puzzle

## 2.1 Behaviour

One mystery place per day, **identical for every player worldwide**. Five guesses. Each wrong guess reveals the next clue.

| Guess | Clue revealed |
|---|---|
| Start | The name's meaning or etymology, with the name itself redacted |
| After 1 | Feature type and rough scale |
| After 2 | Continent |
| After 3 | Country |
| After 4 | Pin location on the globe |

Guessing uses the gazetteer autocomplete. Knowing the name exists is not the hard part — knowing *which* place is.

## 2.2 Feedback

Per guess, in the proven geography-daily convention: **distance, bearing, and proximity percentage**.

| Band | Marker |
|---|---|
| Correct | 🟩 |
| Within 500km | 🟨 |
| Within 3000km | 🟧 |
| Beyond | ⬜ |

Bearing as an arrow: ⬆️ ↗️ ➡️ ↘️ ⬇️ ↙️ ⬅️ ↖️

## 2.3 Share grid

```
NameScape #142 · 3/5 · 🔥7
⬜➡️  🟧↗️  🟩

namescape.app
```

No spoilers in the text, which is what makes the format spreadable. Streak included because a visible streak is the cheapest retention mechanic available and it only costs an integer.

## 2.4 Selection and generation

**The puzzle pool is curated, not the raw gazetteer.** Twelve million places includes a great many that are unguessable or uninteresting. Eligible places must:

- Have a resolved etymology (otherwise there is no first clue)
- Be tier 1 or 2
- Sit outside all restricted zones
- Pass a quality score for guessability and interest

**Generation runs offline, in batches, ninety days ahead.** This is the most important engineering decision in this feature:

> **Never call an LLM in the request path for the daily puzzle.**

The puzzle must be deterministic, identical worldwide, instant, and unchanged if it is regenerated. A live model call is none of those things. It also cannot fail at 00:00 UTC in front of every user simultaneously.

Instead: a batch job selects candidates, calls the model to draft clue text, writes rows to a `puzzles` table with `status = 'draft'`, and a human approves before they go live. Ninety days of buffer means a bad batch is caught long before it ships.

## 2.5 Using OpenRouter

OpenRouter fits well here precisely because this is a batch path. The volume is roughly 365 generations a year, so unit cost is irrelevant and model quality is the only thing that matters — that argues for a strong model, not a cheap one.

The model's job is narrow: **write a clue from an etymology without revealing the name.** That is a genuine writing task with a clear failure mode, which is exactly where a model earns its place.

```
Given: place name, its etymology, feature type, country.
Write a one-sentence clue describing what the name MEANS,
without using the name, any part of it, or any obvious cognate.
Return JSON: {"clue": str, "leaks_name": bool}
```

Ask for `leaks_name` as a self-check, then run a deterministic verification pass on top — substring match against the name, its parts, and its alternate names. Do not trust the model's self-assessment alone. A leaked clue makes the puzzle trivial and is the main quality risk.

Keep the provider behind a `LLMClient` interface so OpenRouter is swappable and fully mockable in tests. No test ever makes a network call.

## 2.6 Conversion hooks

- Solving reveals the place. If unclaimed, a **claim it** action sits directly under the answer.
- Streaks require an account, and the prompt fires on the second consecutive solve — after the habit has started, not before.
- The archive of past puzzles is account-gated.

## 2.7 Data model

```
puzzles
  id              bigserial PK
  puzzle_date     date unique
  place_id        bigint FK
  clues           jsonb        -- ordered array of clue strings
  status          text         -- draft | approved | live | archived
  generated_by    text         -- model identifier
  approved_by     text nullable
  created_at      timestamptz

puzzle_attempts
  id              bigserial PK
  puzzle_id       bigint FK
  user_id         uuid FK nullable
  guest_session_id uuid FK nullable
  guesses         jsonb        -- ordered array of {place_id, distance_km, bearing}
  solved          boolean
  guess_count     smallint
  completed_at    timestamptz nullable
  UNIQUE (puzzle_id, user_id)
  UNIQUE (puzzle_id, guest_session_id)

streaks
  user_id         uuid PK FK
  current         integer
  longest         integer
  last_played_on  date
```

---

# Part 3 — "What it actually means"

## 3.1 Behaviour

Tapping any non-English place name reveals its real meaning and origin, inline in the place sheet. Ffynnongroyw is Welsh for "clear well." Batman in Turkey takes its name from a river.

This is the feature that keeps the product curious rather than mocking. Nothing else on the roadmap does that job.

## 3.2 Resolution chain

Four sources, in strict priority order, first hit wins:

| Priority | Source | Confidence | Cost |
|---|---|---|---|
| 1 | Wikidata structured statements (P138 named-after, P1705 native label) | High, citable | Free |
| 2 | Wikipedia extract, etymology or name section | High, citable | Free |
| 3 | A curated language-element lexicon (`-by`, `-chester`, `llan-`, `-stan`) | Medium, rule-based | Free |
| 4 | LLM synthesis | **Unverified** | OpenRouter |

## 3.3 The hallucination problem

This needs saying plainly, because it is the one way this feature could actively harm the product.

**Language models produce confident, plausible, false etymologies.** Folk etymology is abundant in training data, and place-name origins are exactly the kind of thing where a fluent wrong answer is indistinguishable from a right one. A product whose entire premise is respecting what names actually mean cannot quietly serve invented meanings.

Guards, all required:

- Tier 4 output is **visually distinguished** and explicitly labelled unverified. Not a footnote — a different treatment.
- Tier 1 and 2 show their source with a link.
- Every entry has a **correct this** action, feeding the etymology-contributor-credit path.
- The model is never asked for an etymology when the name's language is unknown. No language, no guess.
- The prompt must permit refusal, and a refusal must be stored as a refusal rather than retried until something comes back.

```
Given a place name and its known language and country, explain the
literal meaning of the name's components.
If you are not confident, respond {"known": false}. Do not speculate.
Return JSON: {"known": bool, "meaning": str|null, "components": [...]}
```

`known: false` is a success, not a failure. Design the prompt, the schema, and the UI so that returning nothing is an acceptable outcome — otherwise every pressure in the system pushes toward fabrication.

## 3.4 Caching

Etymology is effectively immutable. Cache indefinitely on the `places` row, invalidate only on an accepted community correction. A given place is resolved once, ever.

## 3.5 Module impact

None to the interface. `gazetteer.enrich(place_id)` already exists and already returns a `Place`. Its implementation grows from a single Wikidata lookup into a four-tier resolution chain with caching and confidence levels. Every caller is unchanged.

This is the clearest demonstration in the codebase of why deep modules matter: substantial new capability, zero interface churn, zero caller churn.

---

# Implementation steps

Continuing the numbering and the red → green → refactor structure from the main guide. The 200-line diff cap and `make verify` before commit still apply.

---

## Step 24: Guest sessions and the claim path

```
Extend guest claiming into the accounts and discoveries modules.

TEST FIRST — /api/tests/modules/discoveries/test_guest_claim.py:
- A guest session can claim exactly one place; the second claim is rejected
- A guest claim writes expires_at 7 days out
- A user claim writes expires_at NULL
- The CHECK constraint rejects a guest claim with no expiry (test at the
  database level, not just the application level)
- The CHECK constraint rejects a user claim that has an expiry
- Hashed-IP rate limit blocks a 4th guest claim in a day
- A guest cannot vote, bookmark, or propose — each returns 401
- Caption moderation and eligibility run identically for guests
- Two concurrent claims on one place, one guest and one user: exactly
  one wins

Then implement:
- Migration adding guest_sessions and extending discoveries with
  claimant_type, guest_session_id, and expires_at, plus the CHECK
  constraint exactly as written in section 1.5
- Change discoveries.claim() to take a Claimant union. Do NOT add a
  second public function for guest claims — the interface budget is
  three functions and this is a parameter change, not a new capability.
- Redis-backed IP rate limit, hashed, never persisted to Postgres
```

**Acceptance:** The database rejects invalid claimant states directly. `discoveries` still exposes exactly three public functions.

---

## Step 25: Merge on signup, and expiry

```
TEST FIRST:
- Signing up with a guest cookie present transfers the discovery: it
  gains user_id, loses guest_session_id, and expires_at becomes NULL
- The merge is idempotent — running authenticate twice does not
  double-transfer or raise
- Signing in to an EXISTING account with a guest claim merges into that
  account rather than creating a duplicate user
- A guest session with no claim merges cleanly (no-op, no error)
- The expiry job releases claims past expires_at, returns the place to
  unclaimed, and awards no first-finder credit
- The expiry job is idempotent — a second run changes nothing
- A claim merged one minute before expiry survives

Then implement:
- Merge logic INSIDE accounts.authenticate(), not as a new public
  function. Callers must never orchestrate the merge.
- A daily APScheduler job releasing expired guest claims, single
  instance with a Redis lock

Assert accounts still exposes exactly four public functions.
```

**Acceptance:** Merge and expiry are both idempotent. No public interface grew.

---

## Step 26: Guest claiming UI

```
TEST FIRST (Vitest + MSW):
- The signup prompt fires immediately on stamp animation completion,
  not on exit intent or the next action
- The prompt names the place and the deadline
- A countdown renders in the place sheet and on the pin
- A guest who has already claimed sees the claim control disabled with
  a reason, not hidden
- Dismissing the prompt does not lose the claim
- Vote and bookmark controls are visibly disabled for guests, with an
  explanation

Then implement to the design doc. The prompt is a sheet, not a modal —
it must not feel like a wall.

E2E: claim as a guest, sign up, assert the discovery persists and the
countdown disappears.

Verify the prompt timing in the browser. It must land on the stamp
animation's final frame — screenshot to confirm.
```

**Acceptance:** The prompt lands at the emotional peak. Dismissing it never costs the claim.

---

## Step 27: Etymology resolution chain

```
Extend gazetteer.enrich() into the four-tier chain from Part 3. The
public interface does NOT change.

TEST FIRST:
- Tier 1 (Wikidata) hit returns high confidence with a source URL
- Tier 2 (Wikipedia) is tried only when Wikidata misses
- Tier 3 (lexicon) matches known suffixes: -by, -chester, llan-, -stan
- Tier 4 (LLM) is tried only when 1-3 all miss
- Tier 4 is NEVER called when the name's language is unknown — assert
  the client is not invoked at all
- A model response of {"known": false} is stored as a resolved
  "unknown", not retried
- Tier 4 results carry confidence = 'unverified'
- Results cache — a second enrich() call makes no outbound request
- All four sources failing returns a Place with etymology None, and
  does not raise
Mock Wikidata, Wikipedia, and the LLM client. No network in tests.

Then implement, plus:
- An LLMClient interface with an OpenRouter implementation, fully
  mockable
- A curated lexicon file at /api/data/name_elements.yaml
- Confidence stored alongside the etymology on the places row

Assert gazetteer still exposes exactly three public functions.
```

**Acceptance:** `known: false` is treated as success. The LLM is never called without a known language. Interface unchanged.

---

## Step 28: Etymology UI and corrections

```
TEST FIRST:
- Sourced etymology renders with a visible source link
- Unverified etymology renders with distinct visual treatment and an
  explicit label — assert the label text exists, not just a CSS class
- A place with no etymology shows an invitation to contribute, not an
  error
- The "correct this" action opens a submission form
- A correction submission goes through the moderation pipeline
- A non-English name shows the reveal affordance; an English name in an
  English UI does not

Then implement per the design doc: reveal inline in the place sheet,
brass affordance, parchment body. Unverified entries get a muted
treatment and a plain-language label.

Verify in the browser with all four confidence levels. Screenshot each.
```

**Acceptance:** A user can tell at a glance whether an etymology is sourced or generated. That distinction must survive a screenshot test.

---

## Step 29: Puzzle selection and clue generation

```
Create /api/app/modules/puzzles/ — batch generation only. No request
path in this step.

TEST FIRST:
- Candidate filtering excludes places without etymology, tier 3 places,
  and anything inside a restricted zone
- Clue generation calls the LLM once per puzzle and parses structured
  JSON
- LEAK VERIFICATION: a generated clue containing the place name, any
  part of it, or any alternate name is rejected and regenerated. Test
  with a deliberately leaking fixture response. This is the main
  quality risk in the feature.
- A model returning malformed JSON is retried, then fails the batch
  rather than writing a bad row
- Generated rows are written with status='draft', never 'live'
- The same date never generates twice
Mock the LLM client entirely.

Then implement:
- /api/scripts/generate_puzzles.py --days 90
- LLMClient with an OpenRouter implementation
- A separate approval command flipping draft to approved

Do NOT add a live generation path. Generation is offline, ninety days
ahead, human-approved. A model call in the request path would make the
puzzle nondeterministic, slow, and capable of failing for every user
simultaneously at 00:00 UTC.
```

**Acceptance:** A leaking clue is caught by deterministic verification, not by trusting the model's self-report.

---

## Step 30: Puzzle module and play

```
Extend /api/app/modules/puzzles/ with the play path.

PUBLIC INTERFACE — exactly three functions:
  async def today() -> Puzzle
  async def guess(puzzle_id: int, player: Claimant, place_id: int) -> GuessResult
  async def state_for(puzzle_id: int, player: Claimant) -> AttemptState

Hidden: clue progression, distance and bearing math, proximity banding,
streak updates, share-grid construction.

TEST FIRST:
- today() returns the same puzzle for every caller on a given date
- today() returns nothing when no approved puzzle exists for the date,
  and does not fall back to a random place
- The first clue is available before any guess
- Each wrong guess reveals exactly one more clue
- A correct guess ends the attempt and reveals the place
- A 5th wrong guess ends the attempt as unsolved
- Guessing after the attempt is complete is rejected
- Distance and bearing are correct — test against known coordinate
  pairs, including an antimeridian crossing
- Proximity bands are correct at exactly 500km and exactly 3000km
  (boundaries)
- Streaks increment on consecutive days and reset on a gap
- A guest can play; their attempt is keyed to the guest session
- The share grid contains no place name and no country

Then implement, plus the daily rollover job.
```

**Acceptance:** Boundary tests at 500km and 3000km pass. The share grid provably leaks nothing.

---

## Step 31: Puzzle UI

```
TEST FIRST:
- The guess input autocompletes over the gazetteer
- Each guess renders distance, bearing arrow, and proximity band
- Clues reveal progressively and previously revealed clues stay visible
- Solving reveals the place with a "claim it" action when unclaimed
- The share button copies the grid to the clipboard
- The streak prompt fires on the SECOND consecutive solve, not the first
- The archive is account-gated with a clear explanation
- Reduced-motion disables the reveal animations

Then implement to the design doc. Brass for correct, parchment for
clues, the globe pin clue rendered via globe.focusOn.

E2E: play a full puzzle, solve it, claim the place, assert the
discovery exists.

Verify the share grid renders correctly when pasted into a plain-text
field — that is where it will actually be used.
```

**Acceptance:** A full play-solve-claim path works end to end. The grid pastes cleanly as plain text.

---

# Sequencing

**Fold steps 24–28 into the launch cut.** Guest claiming and etymology are both small and both fix problems that get worse with users — conversion and content tone. Shipping without them means launching with a known leak and a known risk.

**Steps 29–31 ship in week one after launch.** The puzzle needs an approved ninety-day batch generated and reviewed beforehand, so start the generation run during launch week even though the play surface comes after.

**Estimated addition: 5–6 days**, roughly 2 for guest claiming, 1.5 for etymology, and 2.5 for the puzzle.

**The one thing to be strict about:** no LLM call in any request path. Both features here use a model, and both use it offline — puzzle clues ninety days ahead, etymology cached permanently on first resolution. That constraint is what keeps the product deterministic, fast, and honest.
