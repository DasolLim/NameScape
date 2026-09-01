# Product

## Register

product

## Users

Four audiences, in the proportions the PRD sets out (docs/namescape-prd.md §4):

- **The Browser (~55%)** — arrived from a shared link. Spins the globe, taps a few pins, reads captions. Context: idle minutes on a phone. Success is that the globe is fun to touch and nothing blocks them. They are not signed in and must never be forced to be.
- **The Collector (~25%)** — wants stamps in a passport and country completion. Success is that first-finder credit reads as scarce and visible.
- **The Wit (~12%)** — here for nickname contests. Wants a fast propose-and-vote loop with a visible countdown.
- **The Etymologist (~8%)** — genuinely interested in toponymy. Small, highest-quality contributions, and their presence is what keeps the tone curious rather than mocking. Designed for explicitly.

The job to be done: find a real place with a genuinely absurd real name, put your name on it permanently, and come back to see whether the community agreed with your nickname.

## Product Purpose

A shared 3D globe of real places with real, absurd names. Users claim a place once and for all (first-finder credit is permanent), and propose nicknames the community votes on. A winning nickname renders beneath the official name, never replacing it.

Success looks like: the globe is good enough to spin idly, search finds what you meant on the third keystroke, and contests give a reason to return tomorrow.

## Brand Personality

"Field notes of a curious cartographer." A true, precise map underneath; a playful human layer annotated on top.

- **The map is an instrument.** Dark, desaturated, technical, quiet. It behaves like a precision tool and never begs for attention.
- **The human layer is paper.** Warm, tactile, hand-annotated. Stamps, ink, brass, marginalia. All personality lives here.

Three words: **curious, precise, wry.** Wry, never sneering: the world is already funnier than anything we could invent, so the product's job is to point at it, not to make the joke.

## Anti-references

- **Full skeuomorphic antique.** Torn parchment, compass roses, pirate fonts. Reads as a theme park and ages in months.
- **Generic dark SaaS.** A dashboard aesthetic is emotionally wrong for a product about delight.
- **Atlas Obscura's app.** The closest reference and the clearest warning: loved for content, repeatedly criticised for a clunky interface, weak search, and slow loading.
- **"Laugh at foreign names."** The product's real failure mode. Many toponyms that sound funny in English are ordinary or sacred in their own language.
- **Neon gradients, glassmorphism over the map, dopamine palettes.** A loud palette competes with the cartography the user came to read.

## Design Principles

1. **The map shows everything.** Eligibility gates claiming and nicknaming, never display. Removing names from a basemap is cartographic erasure.
2. **The globe never unmounts.** Every other surface floats over it, and closing any surface returns the exact view you left.
3. **Chrome must never fight the cartography.** The basemap changes colour under the interface as the user pans from ocean to desert. Interface legibility cannot depend on what is beneath it.
4. **Etymology is the mechanism, not decoration.** Showing what a name means, next to the joke, is what makes this curiosity instead of mockery.
5. **Reading is never gated.** Claiming, voting and bookmarking need an account. Looking never does.

## Accessibility & Inclusion

- WCAG 2.1 AA minimum on every pairing; the parchment-on-ink body pairing runs ~16:1.
- Vote and toggle state is never conveyed by colour alone: icons and text labels accompany every state.
- The globe is keyboard navigable (arrows pan, +/- zoom); sheets trap focus and announce via aria-live.
- 44px minimum tap targets throughout, which is why primary navigation is capped at four items.
- `prefers-reduced-motion` removes the idle spin, the stamp overshoot, and all twinkle; the fly-to becomes a jump.
- Map labels honour system font scaling to 200% without the layout breaking.
