# Design

## Visual Theme

Dark-first, and not as a toggle. The scene: someone spinning a globe on a phone in the evening, or a laptop in a dim room, looking for somewhere absurd. A dark canvas lets the brass discovery pins glow and the basemap read as an instrument. Light mode is a required first-class alternate, not an inverted afterthought, because this is also used outdoors in daylight.

The interface is two materials in deliberate tension: **ink** (the instrument) and **parchment** (the annotation).

## Color

OKLCH, tinted toward the ink hue. Never pure black or pure white.

### Ink — surfaces

Blue-black. Deep water at night, and literal ink. Elevation comes from the ramp, never from shadows: shadows on near-black are mud.

| Token | Hex | Use |
|---|---|---|
| `ink-950` | `#080B11` | App chrome, deepest recess |
| `ink-900` | `#0E131C` | Map ocean, page ground |
| `ink-800` | `#151C28` | Sheets, panels |
| `ink-700` | `#1E2735` | Cards, elevated surfaces |
| `ink-600` | `#2B3646` | Borders, dividers |
| `ink-500` | `#3D4A5C` | Disabled, inactive strokes |

### Parchment — foreground

Warm off-white. Never pure white: harsh at length on near-black, and it loses the paper association.

| Token | Hex | Use |
|---|---|---|
| `parchment-50` | `#F5F1E8` | Primary text |
| `parchment-200` | `#D6D0C2` | Secondary text |
| `parchment-400` | `#9B9484` | Tertiary, metadata |
| `parchment-600` | `#6B665C` | Placeholder |

### Brass — primary accent

Warm antique gold at ~38° hue. Discovery, instruments, achievement. The brand colour: every discovery pin, every stamp, every primary action. `brass-500` on `ink-900` is ~8.4:1.

| Token | Hex | Use |
|---|---|---|
| `brass-300` | `#F5C87E` | Hover, highlights |
| `brass-500` | `#E8A33D` | Primary accent, pins, CTAs |
| `brass-700` | `#B37A24` | Pressed, borders on brass fills |
| `brass-900` | `#4A320F` | Text on brass fills |

### Verdigris — secondary accent

Oxidised copper at ~168° hue: split-complementary to brass, harmonious enough to feel designed, distant enough to create tension.

| Token | Hex | Use |
|---|---|---|
| `verdigris-300` | `#7DD9C3` | Hover |
| `verdigris-500` | `#35A48F` | Agree votes, saved, success |
| `verdigris-700` | `#1F6B5D` | Pressed |
| `verdigris-900` | `#0C2B26` | Text on verdigris fills |

### Semantic

| Token | Hex | Meaning |
|---|---|---|
| `wax-500` | `#C9524E` | Disagree, destructive, sealing-wax red |
| `verdigris-500` | `#35A48F` | Agree, saved, success |
| `brass-500` | `#E8A33D` | Live contest, urgency, achievement |
| `ink-600` | `#2B3646` | Ineligible, restricted, deliberately dull |

**Strategy: Restrained.** Tinted neutrals plus brass; verdigris is a second role, not decoration. Two accents, never three.

## Typography

Three faces, each with a reason.

- **Fraunces** (display, variable, wonk axis) — place names in the detail sheet, section headers, the wordmark, contest headlines. Expedition-journal character without being a costume.
- **Inter** (interface) — everything structural. Tabular figures matter for vote tallies and countdowns.
- **Noto Sans** (map labels) — non-negotiable. Labels will be Cyrillic, Devanagari, Arabic, CJK, Thai, Greek; substituting a prettier Latin face silently breaks the map for most of the world.

Fixed rem scale, ratio ~1.25. Two weights per face.

| Role | Size / line | Face |
|---|---|---|
| Display | 40 / 44 | Fraunces 400 |
| Title | 28 / 34 | Fraunces 400 |
| Heading | 20 / 28 | Inter 500 |
| Body | 16 / 26 | Inter 400 |
| UI | 14 / 20 | Inter 400 |
| Caption | 12 / 16 | Inter 400 |

## Layout

The globe is not a page: **the globe is the application**, and everything else is a surface floating over it.

```
Globe (persistent, never unmounted)
├── Chrome        top bar: wordmark, search, layers, account
├── Place sheet   bottom sheet (mobile) / right panel (desktop)
├── Bookmarks     saved places
└── Passport      stamps, completion, share
```

Primary navigation caps at four items: a fifth makes each target too narrow for a thumb.

## Components

- **Surfaces** get elevation from the ink ramp, not shadows.
- **Borders** at 0.5px in `ink-600`. Hairlines read as precision; 1px reads as chunky at this palette.
- **Radius** 12px on cards and sheets, 8px on controls, fully round on pins.
- **Pins** are `brass-500` circles at 12px with a 2px `ink-950` stroke, so they hold their edge over any basemap colour. Never DOM markers.
- **Buttons.** Primary is a brass fill with `brass-900` text. Secondary is transparent with an `ink-600` border. Ghost is text only. One primary per view.
- **Empty states** are invitations, never apologies.
- Every interactive component ships default, hover, focus, active, disabled, loading, error.

## Motion

150–250ms on most transitions; motion conveys state, not decoration.

| Interaction | Motion | Duration |
|---|---|---|
| Globe fly-to | Ease-out, arc path | 1200ms |
| Sheet open | Spring, damping 0.8 | 320ms |
| Stamp drop | Scale 1.4 → 1.0, overshoot | 400ms |
| Vote register | Count roll | 200ms |
| Surface transition | Fade + 8px rise | 180ms |

Ease out with exponential curves. No bounce, no elastic. Everything respects `prefers-reduced-motion`.

## Deliberately not doing

No neon gradients. **No glassmorphism over the map** — frosted blur over dense cartography destroys legibility and costs GPU on the one surface that cannot afford it. No torn-paper textures, no compass-rose ornament, no more than two accent colours, no light mode as an afterthought.
