# Absurdia — Design System & Brand Direction

**Working title:** Absurdia (placeholder — alternatives at §11)
**Version:** 1.0
**Role:** Senior product / brand design direction
**Companion docs:** map architecture, product PRD

---

## 1. What the research says, and what it means for us

I looked at where map, travel, and discovery products are heading, plus general 2026 UI direction. Four findings actually matter for this product.

**Dark-first is now the baseline for map and exploration apps, not a toggle.** Arc, Linear, Warp, and Raycast all launched dark-first with light modes that feel secondary. For maps specifically the case is stronger: a dark canvas lets data layers glow, and OLED devices draw zero power on true black — YouTube measured 43% less power in dark mode at full brightness. We design dark-first and treat light mode as a first-class alternate, not an afterthought inversion.

**Layered dark surfaces have replaced flat black.** The current craft signal is several near-black tones stacked to convey hierarchy, rather than one background with borders doing all the work. Our surface ramp is built for this.

**Navigation is becoming exploratory rather than hierarchical.** Radial menus, hidden drawers, interactive maps, nonlinear journeys — designers are treating layout as exploration instead of a Home/About/Contact spine. That is unusually well-suited here: our product genuinely *is* a map, so we should not bolt a conventional site structure onto it.

**Saturated "dopamine" palettes are trending, and we should mostly resist.** Neon gradients and high-contrast playful hues are having a moment on lifestyle and youth brands. On a map product they are actively harmful — the basemap already carries dense information, and a loud palette competes with the content the user came to read. We take the *energy* of the trend and spend it in a narrow band: two saturated accents against a restrained ground.

**What the category gets wrong.** Atlas Obscura is the closest reference and its app is well-loved for content but repeatedly criticised for a clunky interface, weak search, and slow loading. That is the gap. In a discovery product, search *is* the product, and it is the most common place these apps fall down.

---

## 2. Design concept: "Field notes of a curious cartographer"

The product has a structural tension built into it: a **true, precise map underneath** and a **playful human layer on top**. Real coordinates, real names, real geography — annotated with jokes, votes, and nicknames.

The design should express exactly that tension rather than picking a side.

- **The map is an instrument.** Dark, desaturated, technical, quiet. It behaves like a precision tool and never begs for attention.
- **The human layer is paper.** Warm, tactile, hand-annotated. Stamps, ink, brass, marginalia. This is where all the personality lives.

Everything downstream follows from this. Discoveries land as **passport stamps**. Your profile is a **passport**. A nickname is written in **ink over the printed name**. Contests are **expedition dispatches** with a countdown.

Two things to avoid, both tempting and both wrong. Full skeuomorphic antique — torn parchment, compass roses, pirate fonts — reads as a theme park and ages in months. And generic dark SaaS reads as a dashboard, which is emotionally wrong for a product about delight.

---

## 3. Colour system

Dark-first. Every value below is checked for WCAG contrast in its intended pairing.

### 3.1 Ink — surfaces

A blue-black ramp. Deep water at night, and also literal ink. Five stops so hierarchy comes from elevation rather than borders.

| Token | Hex | Use |
|---|---|---|
| `ink-950` | `#080B11` | App chrome, deepest recess |
| `ink-900` | `#0E131C` | Map ocean, page ground |
| `ink-800` | `#151C28` | Sheets, panels |
| `ink-700` | `#1E2735` | Cards, elevated surfaces |
| `ink-600` | `#2B3646` | Borders, dividers |
| `ink-500` | `#3D4A5C` | Disabled, inactive strokes |

### 3.2 Parchment — foreground

Warm off-white. Never pure white — pure white on near-black is harsh at length and loses the paper association entirely.

| Token | Hex | Use |
|---|---|---|
| `parchment-50` | `#F5F1E8` | Primary text |
| `parchment-200` | `#D6D0C2` | Secondary text |
| `parchment-400` | `#9B9484` | Tertiary, metadata |
| `parchment-600` | `#6B665C` | Placeholder |

`parchment-50` on `ink-900` gives roughly 16:1. Comfortably AAA.

### 3.3 Brass — primary accent

Warm antique gold. Reads as discovery, instruments, treasure, achievement. This is the brand colour and it appears on every discovery pin, every stamp, every primary action.

| Token | Hex | Use |
|---|---|---|
| `brass-300` | `#F5C87E` | Hover, highlights |
| `brass-500` | `#E8A33D` | Primary accent, pins, CTAs |
| `brass-700` | `#B37A24` | Pressed, borders on brass fills |
| `brass-900` | `#4A320F` | Text on brass fills |

`brass-500` on `ink-900` is roughly 8.4:1 — passes AA for normal text and AAA for large.

### 3.4 Verdigris — secondary accent

Oxidised copper. Sits near-complementary to brass, which gives the palette tension without discord, and it carries the right associations: aged instruments, old sea charts, patina.

| Token | Hex | Use |
|---|---|---|
| `verdigris-300` | `#7DD9C3` | Hover |
| `verdigris-500` | `#35A48F` | Agree votes, confirmed, success |
| `verdigris-700` | `#1F6B5D` | Pressed |
| `verdigris-900` | `#0C2B26` | Text on verdigris fills |

### 3.5 Semantic

| Token | Hex | Meaning |
|---|---|---|
| `wax-500` | `#C9524E` | Disagree votes, destructive, sealing-wax red |
| `verdigris-500` | `#35A48F` | Agree, success |
| `brass-500` | `#E8A33D` | Live contest, urgency, achievement |
| `ink-600` | `#2B3646` | Ineligible, restricted, deliberately dull |

Reusing verdigris for agree and brass for urgency keeps the system tight. A palette with eight independent semantic colours is a palette nobody can remember.

### 3.6 Why this palette, in one paragraph

Brass sits near 38° hue, verdigris near 168°. That is a split-complementary relationship — harmonious enough to feel designed, distant enough to create tension. Both are desaturated relative to a dopamine palette, which is deliberate: they must sit on top of a dense basemap without fighting it. The warm accent on a cool ground is the oldest legibility trick there is, and it means a brass pin is instantly findable on a blue-black map even at low zoom. And the whole thing carries the "old instrument" association without a single skeuomorphic texture.

### 3.7 Light mode

Not an inversion. Parchment becomes the ground, ink becomes the text, accents stay identical but shift one stop darker for contrast (`brass-700`, `verdigris-700`) since they now sit on a light surface.

| Token | Hex | Use |
|---|---|---|
| `paper-50` | `#FBF8F1` | Page ground |
| `paper-100` | `#F2EDE1` | Map land |
| `paper-200` | `#E5DECE` | Cards |
| `ink-900` | `#0E131C` | Primary text |

Light mode is required, not optional. This is an outdoors product used in daylight, and forcing dark mode without a toggle frustrates users rather than impressing them.

---

## 4. Typography

Three faces, each with a reason.

**Display — Fraunces.** A variable serif with a genuine "wonk" axis and soft optical sizing. It carries the expedition-journal character without being a costume, and because it is variable we get editorial weight at large sizes and restraint at small ones from a single file. Used for: place names in the detail sheet, section headers, the wordmark, contest headlines.

**Interface — Inter.** Unglamorous and correct. We are rendering dense UI, vote counts, timestamps, and search results, and Inter is the best-tested face for exactly that. Its tabular figures matter for vote tallies and countdowns. Used for: everything structural.

**Map labels — Noto Sans.** Non-negotiable, and it is what the Protomaps basemap assets ship with anyway. This is a global place-name product: labels will be Cyrillic, Devanagari, Arabic, CJK, Thai, Greek. Noto has the widest script coverage available and substituting a prettier Latin face would silently break the map for most of the world.

### Scale

| Role | Size / line | Face |
|---|---|---|
| Display | 40 / 44 | Fraunces 400 |
| Title | 28 / 34 | Fraunces 400 |
| Heading | 20 / 28 | Inter 500 |
| Body | 16 / 26 | Inter 400 |
| UI | 14 / 20 | Inter 400 |
| Caption | 12 / 16 | Inter 400 |

Two weights per face. More than that and the system stops looking designed.

---

## 5. Information architecture

The globe is not a page. **The globe is the application**, and everything else is a surface that floats over it. This is the exploratory-navigation direction the research points at, and here it is the honest structure rather than a stylistic choice.

```
Globe (persistent, always mounted, never unmounted)
├── Search              overlay, top
├── Place sheet         bottom sheet (mobile) / right panel (desktop)
│   ├── Overview        official name, region, etymology
│   ├── Nickname        current nickname + history
│   ├── Discovery       who found it, when, their note
│   └── Contest         live vote or "propose a nickname"
├── Discover            feed of recent finds, slides up over globe
├── Contests            live votes with countdowns
└── Passport            your profile, stamps, stats, collections
```

Bottom navigation on mobile with four items — Globe, Discover, Contests, Passport. Four is the ceiling; a fifth item makes each target too narrow for a thumb.

### The critical rule

**The globe never unmounts.** Every surface animates over it, and closing any surface returns you to exactly the view you left. A map that re-initialises on every navigation is the single most common way these apps feel cheap, and it is the thing Atlas Obscura's reviewers are complaining about when they mention slow loading.

---

## 6. Key screens

### 6.1 Globe (home)

Full-bleed dark globe on `ink-950`, subtle atmosphere halo at the limb. Discovery pins in `brass-500`, clustered at low zoom with counts.

Floating elements only: a search pill at the top, bottom navigation, and a single circular **Surprise me** button in `brass-500` at the lower right. That button spins the globe to a random discovery — a slot-machine pull, and the cheapest possible engagement loop. It should be the most tactile control in the product.

First load animates from full globe down to the user's region over about 1.2 seconds. It sets the tone in one gesture and costs nothing.

### 6.2 Place sheet

Three-stage bottom sheet — peek at 120px, half at 50%, full at 90%.

Peek shows the official name in Fraunces, the nickname beneath it in brass if one exists, and the finder's handle. Half adds etymology, the discovery note, and vote controls. Full adds nickname history and the full contest board.

Etymology is not a nice-to-have. It is the design mechanism that stops this product from becoming "laugh at foreign names" — showing what a name actually means, right next to the joke, reframes the whole interaction as curiosity rather than mockery.

### 6.3 Discovery flow

Search the gazetteer → confirm the place → write a caption → **stamp it**.

The stamp is the emotional peak of the product and deserves real animation budget: the pin scales down onto the map with a slight overshoot, a brass ring pulses outward, haptic thunk on mobile. If you are the first finder, the sheet reveals a **first finder** badge with your handle set in Fraunces. That badge is the permanent reward and it should feel like one.

### 6.4 Contest board

A live nickname vote. Brass countdown ring depleting around the header. Proposals as cards, sorted by net votes, with agree in verdigris and disagree in wax. Vote count animates on change. Cards near the quorum line get a subtle brass edge glow — visible progress toward a threshold is what makes people vote.

### 6.5 Passport

A collection artifact, not a settings page. A grid of stamps for every discovery. Country completion rings. First-finder count called out as the hero number, since that is the scarce thing. Shareable as a generated image — this is your growth surface.

---

## 7. Motion

| Interaction | Motion | Duration |
|---|---|---|
| Globe fly-to | Ease-out cubic, arc path | 1200ms |
| Sheet open | Spring, damping 0.8 | 320ms |
| Stamp drop | Scale 1.4 → 1.0, overshoot | 400ms |
| Vote register | Card tilt 2°, count roll | 200ms |
| Pin cluster split | Stagger 20ms per pin | 300ms |
| Surface transition | Fade + 8px rise | 180ms |

Everything respects `prefers-reduced-motion`, with the globe fly-to becoming an instant jump rather than an arc.

---

## 8. Component notes

**Surfaces** get elevation from the ink ramp, not from shadows. Shadows on near-black are mud.

**Borders** at `0.5px` in `ink-600`. Hairlines read as precision; 1px reads as chunky at this palette.

**Radius** 12px on cards and sheets, 8px on controls, fully round on pins and the Surprise me button.

**Pins** are `brass-500` circles at 12px with a 2px `ink-950` stroke so they hold their edge over any basemap colour. Clusters scale by count and carry a tabular number.

**Buttons.** Primary is a brass fill with `brass-900` text. Secondary is a transparent fill with an `ink-600` border. Ghost is text only. One primary per view.

**Empty states** are invitations, never apologies. "No discoveries here yet — be the first" with a stamp affordance, not "Nothing found."

---

## 9. Accessibility

Every accent pairing above clears AA at minimum. Beyond contrast:

- Vote state is never colour alone — agree and disagree carry icons and labels.
- The globe is keyboard navigable: arrow keys pan, `+`/`−` zoom, tab cycles visible pins.
- The place sheet traps focus and announces via `aria-live`.
- 44px minimum tap targets throughout, which is why bottom nav is capped at four.
- Map labels honour system font scaling up to 200% without the layout breaking.

---

## 10. What we are deliberately not doing

No neon gradients, no glassmorphism over the map (frosted blur over dense cartography destroys legibility and costs GPU on the one surface that cannot afford it), no torn-paper textures, no compass-rose ornament, no more than two accent colours, and no light mode as an afterthought.

---

## 11. Naming

Absurdia is a placeholder. Alternatives worth testing:

| Name | Note |
|---|---|
| **NameScape** | Technically precise, memorable, slightly nerdy — arguably a feature |
| **Oddnames** | Plain, clear, easy to say, probably taken |
| **Nomen** | Short, ownable, international, less descriptive |
| **The Odd Atlas** | Descriptive and warm; sits close to Atlas Obscura, which cuts both ways |
| **Placenames** | Boring but honest and very searchable |

My preference is **NameScape** for the wordmark with "the atlas of absurd place names" as the tagline. It rewards the curious, which is exactly our audience, and it is unmistakably ownable.
