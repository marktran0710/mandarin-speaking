---
name: Academic Mandarin Research Studio
colors:
  surface: '#f7f9ff'
  surface-dim: '#d7dadf'
  surface-bright: '#f7f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f1f4f9'
  surface-container: '#ebeef3'
  surface-container-high: '#e5e8ed'
  surface-container-highest: '#e0e3e8'
  on-surface: '#181c20'
  on-surface-variant: '#42474b'
  inverse-surface: '#2d3135'
  inverse-on-surface: '#eef1f6'
  outline: '#73787c'
  outline-variant: '#c2c7cb'
  surface-tint: '#49626f'
  primary: '#49626f'
  on-primary: '#ffffff'
  primary-container: '#bdd7e7'
  on-primary-container: '#465e6c'
  inverse-primary: '#b0cada'
  secondary: '#4d6452'
  on-secondary: '#ffffff'
  secondary-container: '#d0e9d2'
  on-secondary-container: '#536a58'
  tertiary: '#665a71'
  on-tertiary: '#ffffff'
  tertiary-container: '#ddcde9'
  on-tertiary-container: '#62566e'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cce6f7'
  primary-fixed-dim: '#b0cada'
  on-primary-fixed: '#031e2a'
  on-primary-fixed-variant: '#314a57'
  secondary-fixed: '#d0e9d2'
  secondary-fixed-dim: '#b4cdb7'
  on-secondary-fixed: '#0b2012'
  on-secondary-fixed-variant: '#364c3b'
  tertiary-fixed: '#eddcf9'
  tertiary-fixed-dim: '#d0c1dc'
  on-tertiary-fixed: '#21172c'
  on-tertiary-fixed-variant: '#4e4259'
  background: '#f7f9ff'
  on-background: '#181c20'
  surface-variant: '#e0e3e8'
typography:
  headline-lg:
    fontFamily: Newsreader
    fontSize: 30px
    fontWeight: '500'
    lineHeight: 38px
  headline-md:
    fontFamily: Newsreader
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
  headline-sm:
    fontFamily: Newsreader
    fontSize: 19px
    fontWeight: '500'
    lineHeight: 26px
  body-lg:
    fontFamily: Noto Serif
    fontSize: 17px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Noto Serif
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Noto Serif
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  character-hero:
    fontFamily: Noto Serif
    fontSize: 48px
    fontWeight: '400'
    lineHeight: 56px
  character-display:
    fontFamily: Noto Serif
    fontSize: 28px
    fontWeight: '400'
    lineHeight: 36px
  character-inline:
    fontFamily: Noto Serif
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 26px
  pinyin-sm:
    fontFamily: Source Sans 3
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  label-md:
    fontFamily: Source Sans 3
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Source Sans 3
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.05em
  caption:
    fontFamily: Source Sans 3
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-tablet: 2rem
  margin-desktop: 3rem
  space-xs: 0.25rem
  space-sm: 0.375rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system targets serious adult scholars, linguists, and university researchers studying Mandarin Chinese. It explicitly rejects hyper-gamification, cartoon mascots, aggressive reward loops, and sensory fatigue.

The aesthetic is grounded in scholarly restraint, warmth, and cognitive clarity:
- **Design Movement**: Warm Editorial Minimalism combined with functional linguistic tools.
- **Atmosphere**: Resembles an illuminated philological manuscript rendered through a crisp, contemporary interface. It prioritizes quiet concentration, micro-density, and typographic hierarchy.
- **Bilingual Typographic Poise**: Latin and Hanzi characters sit side-by-side with carefully calibrated x-heights, baseline balance, and dedicated vertical rhythm for multi-tier annotations (Hanzi, Pinyin, tone contours, and English glosses).

## Colors

> **Implementation note (added by the redesign build, 2026-09-24):** the YAML
> `colors:` block above is the one actually wired into the running app
> (`frontend/src/student/tokens.css`) and is what every Student Mode screen
> renders with — a cool blue-grey/teal Material-You-style palette (surface
> `#f7f9ff`, primary `#49626f`). The prose below this line describes a
> *different*, warmer pastel palette (`#FBFAF7` canvas, `#E6E2DC` border,
> pastel blue/sage/butter/peach/rose/lavender) inherited from an earlier
> draft of this document and was **not** updated to match the final YAML.
> Treat the YAML + the attached HTML mockups as ground truth; treat the
> prose Colors/Elevation sections below as historical/superseded unless the
> user says otherwise.

The palette relies on a tactile, warm off-white canvas paired with an expansive, functional spectrum of desaturated pastels. Colors are never used decoratively; each pastel hue denotes a precise pedagogical state.

### Base Surfaces & Neutrals
- **Canvas Base (`#FBFAF7`)**: Warm paper ground providing reduced ocular glare during sustained reading.
- **Card Surface (`#FFFFFF`)**: Pure crisp white for focused working surfaces and lexicon cards.
- **Subtle Border (`#E6E2DC`)**: Neutral parchment stroke defining structure without visual weight.
- **Text Primary (`#303438`)**: Deep charcoal with warm undertones; maximizes legibility without the harsh contrast of pure black.
- **Text Secondary (`#70767C`)**: Balanced graphite for grammatical tags, radical breakdowns, and meta-commentary.
- **Text Subtle (`#9CA1A6`)**: De-emphasized slate for tonal guidelines, IPA markers, and grid lines.

### Pedagogical Pastel Accents
- **Pastel Blue (`#BDD7E7`)**: Focus state, linguistic baseline, current cursor/token tracker.
- **Pastel Sage (`#BFD8C2`)**: Empirical accuracy, verified mastery, validated syntactic structure.
- **Soft Butter (`#F3D99B`)**: Selected morpheme, active audio scrubbing region, user inspection.
- **Soft Peach (`#F2C7B5`)**: Tone deflection alert, phonological warning, acoustic friction.
- **Muted Rose (`#E6BBC5`)**: Sub-optimal alignment, morphological mismatch, retry checkpoint.
- **Soft Lavender (`#D8C8E4`)**: Discourse context, synthetic phonology, AI linguistic analysis.

## Typography

The type system supports a tripartite reading model:
1. **Academic Headings & Meta (`Newsreader`)**: Editorial authority, used for chapter titles, corpus source attribution, and theoretical notes.
2. **Chinese Glyphs & Reading Corpus (`Noto Serif`)**: Highly legible calligraphic stroke architecture suitable for both Traditional characters (繁體字) and literary prose. Implementation uses **Noto Serif TC** specifically (Traditional Chinese) — see `frontend/src/student/tokens.css` `--sa-font-body`.
3. **Phonetic & Functional UI (`Source Sans 3`)**: Humanist sans-serif providing crystal-clear tonal mark legibility for Pinyin (`ā`, `á`, `ǎ`, `à`), IPA symbols, grammatical abbreviations, and tabular analysis.

### Ruby/Interlinear Notation
When Pinyin or IPA accompanies Hanzi, vertical stacking must adhere to:
- Interlinear spacing: 2px gap between Hanzi top-edge and Pinyin baseline.
- Proportion: Pinyin font size remains 55–60% of the associated Hanzi glyph size.

## Layout & Spacing

The design system maintains a high-density, compact vertical rhythm to present complex linguistic data (radical breakdowns, concordance lines, audio spectrograms) without excessive scrolling.

### Grid & Breakpoints
- **Mobile (< 768px)**: 4-column layout, compact outer canvas margin (16px), strictly linear pedagogical progression.
- **Tablet (768px - 1024px)**: 8-column layout, 32px canvas margin. Split-screen workbench (e.g., text document on the left, morpheme inspector on the right).
- **Desktop (> 1024px)**: 12-column layout, max-width 1320px, 48px canvas margin. Three-pane linguistic console: Corpus Context (25%), Active Workspace (50%), Philological / AI Synthesis Inspector (25%).

Vertical stack offsets are compressed: cards and list items utilize standard `0.75rem` (12px) gaps to simulate the layout density of physical linguistic field manuals.

## Elevation & Depth

This system avoids drop shadows entirely (`box-shadow: none`). Spatial hierarchy is established solely through surface tonal layering and structural hairline borders.

### Surface Hierarchy
1. **Level 0 (Canvas)**: outer page environment and background substrate — implemented as `--sa-surface`/`--sa-background` (`#f7f9ff`), not the `#FBFAF7` named here (see note above).
2. **Level 1 (Panels & Cards)**: `--sa-surface-container-lowest` (`#ffffff`) enclosed by a 1px solid `--sa-surface-container-highest` boundary (implementation uses that token, not the `#E6E2DC` named here).
3. **Level 2 (Active Sub-regions & Callouts)**: Subtle tinted fills using the container tokens (`--sa-surface-container-low`) or a semantic container (`--sa-secondary-container`, `--sa-tertiary-container`) at partial opacity for selected/AI-coaching regions.
4. **Level 3 (Popovers & Lexicon Tooltips)**: raised surface with a stronger border/shadow — reserved for modal/drawer/popover only, per the flat-elsewhere rule.

## Shapes

Corner radii (implemented as `--sa-radius-*` in `tokens.css`):
- **Base Components (Inputs, Buttons, Badges, Morpheme Tiles)**: 8px (`--sa-radius`).
- **Containers (Panels, Lexicon Cards, Modal Sheets)**: 12px (`--sa-radius-md`).
- **Annotation Pills & Radical Badges**: 4px (`--sa-radius-sm`) for compact tags — pill/full radius reserved for status chips and segmented controls only.

## Components

### Buttons
Implemented as `StudentButton` (`frontend/src/student/primitives/StudentButton.tsx`) — 4 variants: primary / secondary / subtle / danger. Default height 44px (a real touch target — deliberately taller than this doc's original 34px desktop-dense suggestion, per the accessibility minimum), `sm` 34px for dense inline row actions only, `lg` 50px for a page's one primary CTA. No shadows, no hover motion beyond background/border.

### Morpheme & Tone Chips
Implemented as `WordChip` inside `StudentInlineFeedback` — neutral/ok (sage, `--sa-secondary-container`) vs. attention (rose/error, `--sa-error-container`), always paired with a ✓/△ icon, never color-only.

### Cards & Lexicon Workbenches
Implemented as `StudentSection` (`panel` variant): `--sa-surface-container-lowest` background, 1px `--sa-surface-container-highest` border, `--sa-radius-md` (12px) corner radius.

### AI Linguistic Coach
Implemented as the `.sa-ai-coach` block inside `StudentInlineFeedback` — tertiary-container tint at ~30% over the card surface, `school` icon, `body-sm` text.

## Screens implemented (frontend/src/student/)

- `study/StudyPage.tsx` — lesson list (課程目錄), wired to `utils/lessonGroups.ts`.
- `vocabulary/VocabularyPreviewPage.tsx` — wired to `utils/speakingVocabulary.ts`.
- `vocabulary/VocabularyQuizPage.tsx` — wired to `components/story-vocab-quiz/useQuizSession.ts` (Know It / Say It / Use It rounds).
- `speaking/StorySpeakingPage.tsx` — wired to a new shared `useSpeakingRecorder` hook + the real `analyzeSpeakingResult` verdict logic.
- `conversation/ConversationPage.tsx` — pending.
- `progress/ProgressPage.tsx` — pending.
- **Completion screen** — intentionally not designed by this document. The
  user is adding it themselves; edit this file directly with that design
  when ready, and the build will follow it.
