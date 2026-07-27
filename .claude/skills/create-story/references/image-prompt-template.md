# Image-prompt generation method

Method for turning a story's locked turns (from SKILL.md step 5) into **one
AI image-generation prompt (EASY) plus two image-edit prompts (MEDIUM,
HARD)** — pasted into ChatGPT or Gemini in the same chat, one after another.
Generate returns a finished comic page; each edit returns that same page with
only the bubble text swapped. Nothing to run afterwards.

## Generate once, edit twice

The story is one plot at three reading levels, so the illustration should be
one comic read three times. Three designs were tried before this one; this
is where they landed.

**Tried first: one tall page with three stacked sections.** Ask a model for
the whole thing at once and it renders 18-27 panels — and it doesn't. Gemini
and ChatGPT both squeezed the grid into fewer rows, dropped panels (the last
one, the payoff, more than once), and redrew each section with different
faces anyway. "Sections 2 and 3 are copies of section 1" is not something a
generator can honour: it redraws, it doesn't copy.

**Tried second: three independent generate prompts, one per tier.** This
fixed the panel-dropping (one page, not 18-27 panels, per request) but not
the drift: every paste is a fresh generation, so the model re-imagines the
whole scene each time regardless of a "same as before" hint. The user hit
this directly — pasting each tier's block separately, one after another,
produced three visibly different comics.

**So: generate EASY, then edit that same image for MEDIUM and HARD.** Image
editing transforms pixels the model can actually see, instead of
reconstructing the scene from a text description — it is a fundamentally
closer operation than a second generation, on both ChatGPT's and Gemini's
current image models, as long as it happens in the same chat as the original
image (or the image is uploaded fresh). Both edits target the EASY image
directly, not each other, so neither drifts more than one edit's worth from
the source:

```
   generate EASY  ->  page of N panels, easy lines
        |
        +--edit--> MEDIUM  (same page, medium lines swapped in)
        |
        +--edit--> HARD    (same page, hard lines swapped in)
```

Two things worth telling the user:

- **Stay in one chat.** Generate EASY, then paste the MEDIUM edit prompt
  right after, then the HARD edit prompt — all in that same conversation. A
  new chat or a different device has no image to edit; upload the EASY image
  file first if that happens.
- **This still isn't pixel-identical.** An edit can nudge a line, shift a
  colour, or redraw more than asked. It's much closer than three
  generations, not a guarantee. For guaranteed identical artwork, generate
  one page with blank bubbles and composite the three tiers onto it locally
  — see the repair path at the end.

Two things every prompt must be blunt about, because a model left to itself
gets both wrong:

- **The grid is uniform and full.** Same-size panels, aligned rows, no spare
  cell. A ragged row gets "tidied" by deleting a panel.
- **The Chinese is copied, not composed.** Quote each line exactly and tell
  the model to reproduce the characters as given and invent nothing.

Speaking panels get a speech bubble with a tail pointing at the speaker;
narrator-only panels get a rectangular caption box along the bottom edge, so
no panel is left with nowhere to put its line. Only the line goes inside the
bubble — never the speaker's name, which the tail already conveys and which
reads as a mistake when drawn in.

Bubbles have to be sized for the **hard** tier: its lines are much longer
than the easy tier's. Ask for generous bubbles taking roughly the top third
of each panel, with the characters composed into the lower two thirds.

Expect some characters to come out wrong anyway. That is the known cost of a
paste-and-go workflow, handled with a caution line above the prompts and the
Caption Scripts to proofread against — not a reason to redesign it.

## File shape

```
[title line, turn count, grid]

HOW TO USE THIS FILE — generate EASY, then edit that image twice, all in
the same chat. [3-step summary + upload note if starting a new chat]

(Chinese text in AI-generated images is unreliable — proofread every bubble
against the CAPTION SCRIPT under each prompt.)

═══════════════════
IMAGE PROMPT — EASY  (paste this first, to generate the base image)
═══════════════════
[... layout + ASCII grid, no-text rule, count check, style, cast, panels,
then "TEXT FOR EACH PANEL (EASY level):" with one line per panel ...]

───────────────────
CAPTION SCRIPT — EASY
───────────────────
Panel 1 — 中明：你好。
  Nǐ hǎo. — Hello.
...

═══════════════════
IMAGE EDIT PROMPT — MEDIUM  (paste in the SAME chat as the EASY image)
═══════════════════
Edit the image above. Do NOT redraw, restyle, or recompose anything — keep
the artwork exactly as it is. The ONLY change: replace the text inside each
panel's speech bubble or caption box with the lines below.
[... "TEXT FOR EACH PANEL (MEDIUM level):" with one line per panel, then a
fallback note for tools that can't edit an existing image ...]

───────────────────
CAPTION SCRIPT — MEDIUM
───────────────────
...

═══════════════════
IMAGE EDIT PROMPT — HARD
═══════════════════
[... same shape, hard lines ...]

───────────────────
FIXING A BAD GENERATION
───────────────────
[... ready-made corrections to send in the same chat ...]
```

The EASY prompt carries the full layout, cast, style and panel description;
the two edit prompts are short on purpose — they inherit all of that from
the image being edited and only need to state what's changing.

## Core method — "one prompt, one page, N panels"

This section describes the page the EASY prompt asks for — grid, cast, style
and panel descriptions. The two edit prompts inherit all of it from the image
being edited and don't restate any of it (see "File shape" above); they only
carry that tier's quoted lines and the edit instruction.

Because it's a single generation, character consistency is largely handled
by the model automatically (it's rendering one coherent image, not stitching
together separate calls with no memory of each other). The prompt's job is
to: describe the cast and style once, lay out the grid, and give each panel
its own distinct scene line so the panels read as a sequence of moments
rather than one pose copy-pasted six times.

1) **Pick the grid shape from the turn count N** (locked in step 5 — 4-6 in
   generate mode, one per book dialogue line in book mode, which can be more):
   A bubble is only as wide as its panel, so the grid choice decides how much
   Chinese fits. Prefer:
   - N=4 → 2 columns × 2 rows
   - N=5, 6 → 3 columns × 2 rows
   - N=7, 8, 9 → 3 columns × 3 rows
   - N=10, 11, 12 → 3 columns × 4 rows

   **The panel count follows the source text, never the layout.** In book
   mode that is the book's own line count, so a learner can read the page
   against the textbook line for line. Don't split a turn to reach a tidier
   grid and don't merge two to shed a panel.

   That means a grid will sometimes end with spare cells (7 panels in a 3×3).
   Ask for those as **blank white filler panels** — same size, same border,
   same gutters, empty inside — named in the ASCII diagram as `blank`, with
   an explicit "do not widen the last panel into them". A ragged row left
   undescribed is the single most reliable way to lose a panel: told a cell
   is spare, a model closes the gap by deleting one, usually the last, which
   is the story's payoff (seen repeatedly with Gemini, 2026-07-27).

   **Three columns is the practical ceiling.** At four, a panel is a quarter
   of the page wide and its bubble can only hold ~28 characters — narrower
   than an A2 hard-tier line, so the bubble either overflows or shrinks the
   text past readable. Grow downward into another row instead of sideways
   into a fourth column. Past 12 panels, keep adding rows of three; never
   merge two turns to reach a tidier grid — the panel count follows the
   story, not the layout.

   **Every panel is the same size, including the last row** — no wide panel
   to absorb an odd count. A model given permission to resize one panel
   starts resizing all of them.

   Draw the layout as an ASCII box diagram inside the prompt. Prose alone
   ("2 columns × 3 rows") gets reinterpreted; a picture of the grid doesn't:

   ```
   +---------+---------+---------+
   | Panel 1 | Panel 2 | Panel 3 |
   +---------+---------+---------+
   | Panel 4 | Panel 5 | Panel 6 |
   +---------+---------+---------+
   ```

2) Write ONE cast + style block, stated once at the top of the prompt (not
   repeated per panel):
   - **Style**: one art style + color mood, ending with "no text anywhere
     except inside each panel's speech bubble or caption box".
     Prefer flat/vector or clean digital-illustration styles with a limited
     palette — they compress smaller and stay consistent panel to panel.
   - **Each character**: name, age, face shape, hair + ONE signature
     accessory, full outfit with SPECIFIC colors, that stays identical in
     every panel. Give each character one unmistakable signature (a colored
     shirt, a hairclip, a backpack color) so it's easy to spot them
     consistent across all N panels.
   - **Layout instruction**: state the grid shape from step 1 explicitly, and
     insist on uniform sizing — e.g. "6 panels in 2 columns × 3 rows, every
     panel exactly the same width and height with aligned edges and equal
     thin gutters, no wide panels, no insets, no irregular comic layout,
     consistent lighting and color palette across all panels."

3) Write one **"Panel N:"** line per turn, in reading order (left-to-right,
   top-to-bottom), reusing the exact turns and scene notes already locked in
   step 5 (don't invent new beats). Expand each turn's short bracketed scene
   note into a full visual description: setting, pose, expression, props.
   Only mention the characters who actually appear in that turn.

4) Deliberately vary pose and framing panel to panel (see "Vary composition"
   rule below) so the six panels don't all show the same standing pose with
   one prop swapped.

5) List the **EASY** tier's lines panel by panel — `Panel N (bubble → Name):`
   or `Panel N (caption box):` followed by the line — then close with a TEXT
   ACCURACY line ("reproduce the Chinese characters exactly as written,
   invent nothing") and an EXPORT line. Those two are what stand between the
   user and a page full of invented characters. The MEDIUM and HARD prompts
   reuse this same shape for step 5 only — their own tier's lines, TEXT
   ACCURACY, and a fallback note — since steps 1-4 don't need restating when
   editing an existing image.

## Rules

- Write the prompt in English (most stable for image models), even though
  the story itself is in Chinese — translate names to pinyin (Zhōngmíng →
  Zhongming) for readability in the prompt.
- Be almost boringly specific about each character in the cast block; vague
  descriptions produce a different-looking person panel to panel.
- Number the panels to match the turn numbers (Panel 1 = Turn 1, etc.).
- The only text in the image is each panel's speech bubble or caption box.
  No tier label, no panel numbers, no title cards, no signage inside the
  artwork — every extra word is another chance for the model to render
  broken characters, and which tier a page is is already obvious from which
  file/prompt produced it.
- Keep each panel uncluttered (few objects, plain backgrounds) so the
  overall image stays legible at grid size and the exported file stays
  small.
- **Vary composition and pose, panel to panel.** If every panel repeats the
  same framing ("both standing, facing camera, smiling"), the page reads as
  one pose stamped six times instead of a story. For each panel,
  deliberately change at least one of: body pose (standing / sitting /
  walking / leaning / pointing), shot framing (close-up on faces / medium
  shot head-to-waist / wider shot showing more of the setting), and camera
  angle (straight-on / slightly from the side / from behind one character's
  shoulder). Write that choice directly into the panel line, e.g. "close-up,
  shot from slightly to the side" or "wider shot showing the whole street."

## Example output (asking-for-directions story, Chenghan + Wanting, 6 turns)

The EASY generate prompt first, then the MEDIUM edit prompt that follows it.

```
Single image — one comic page of 6 panels in a STRICT UNIFORM GRID of
3 COLUMNS × 2 ROWS, laid out exactly like this:

+---------+---------+---------+
| Panel 1 | Panel 2 | Panel 3 |
+---------+---------+---------+
| Panel 4 | Panel 5 | Panel 6 |
+---------+---------+---------+

Every cell is filled — no spare cell, no ragged row. Every panel is EXACTLY
THE SAME SIZE: identical width, identical height, each a landscape rectangle
roughly 4:3, edges aligned, equal thin light gutters, no hard comic-book
borders. No panel may span two cells and no panel changes size because its
scene has more detail in it. No splash panel, no inset, no irregular layout.

ONE PANEL = ONE LINE. All 6 lines listed below must appear, each alone in its
own panel, in reading order. A panel whose line is spoken gets ONE simple
rounded speech bubble, plain white with a black outline and a small tail
pointing at the character named below; a narrator panel gets ONE rectangular
caption box (no tail) along the bottom edge instead. Write only the quoted
Chinese inside a bubble; never write the speaker's name in it. No other text
anywhere in the image: no title, no level label, no panel numbers, no
signage, no letters of any alphabet outside the bubbles and boxes.

COUNT CHECK — before finishing, count the panels: exactly 6, filling the 3×2
grid. If a line has nowhere to go, a panel has been dropped: add it back
rather than merging two lines into one bubble.

Flat digital illustration style, soft rounded shapes, warm morning colour
palette, limited palette, gentle clean outlines, consistent lighting and
colour across every panel.

CHARACTERS (identical in every panel they appear in):
[CHENGHAN] a friendly young man, early 20s, short tousled black hair, light
blue button-up shirt, dark grey pants, navy blue backpack over one shoulder.
[WANTING] a friendly young woman, early 20s, straight black hair in a low
ponytail tied with a yellow scrunchie, round glasses, soft green cardigan,
denim skirt, tan tote bag.

PANELS:
Panel 1 (row 1, left): wide shot, Chenghan alone on a city sidewalk in the
early morning, looking around anxiously, checking a wristwatch.
Panel 2 (row 1, centre): medium shot at eye level, Chenghan raising one hand
politely to stop Wanting on the sidewalk, Wanting turning toward him.
... Panels 3-6 ...

TEXT FOR EACH PANEL (EASY level):
Panel 1 (caption box): 承翰要去學校。
Panel 2 (bubble → Chenghan): 請問，捷運站在哪裡？
Panel 3 (bubble → Wanting): 捷運站在那裡。
... Panels 4-6 ...

TEXT ACCURACY: reproduce the Chinese characters exactly as written above. Do
not invent, simplify, or substitute characters, and do not add any text that
is not listed here.

EXPORT: about 2:1 (e.g. 1536 × 768). Export as JPG at 80-85% quality, keeping
backgrounds plain so each panel stays legible when scaled down.
```

The CAPTION SCRIPT for EASY follows in the file, then the edit prompt:

```
Edit the image above. Do NOT redraw, restyle, or recompose anything — keep
the artwork exactly as it is: same characters, same poses, same background,
same colours, same panel grid, same panel sizes.

The ONLY change: replace the text inside each panel's speech bubble or
caption box with the lines below, panel by panel. If a bubble is now too
small for its new text, resize ONLY that bubble to fit — never resize the
artwork, move a panel, or change the panel count to make room.

TEXT FOR EACH PANEL (MEDIUM level):
Panel 1 (caption box): 今天承翰要去學校上課，可是他不知道捷運站在哪裡，心裡很緊張。
Panel 2 (bubble → Chenghan): 不好意思，請問捷運站怎麼走？
... Panels 3-6 ...

TEXT ACCURACY: reproduce the Chinese characters exactly as written above. Do
not invent, simplify, or substitute characters, and do not add any text that
is not listed here.

If your tool can't edit an existing image, fall back to a fresh generation:
paste the IMAGE PROMPT — EASY block again with its TEXT FOR EACH PANEL
section swapped for the MEDIUM lines above, and add "match the style,
characters and panel layout of the image already generated in this chat as
closely as possible" at the top.
```

Its own CAPTION SCRIPT — MEDIUM follows, then the HARD edit prompt repeats
the same shape.

## Repair path — compositing the text locally

Two reasons to come here: the generated Chinese keeps coming out garbled, or
the user wants all three tiers to share **identical** artwork, which no
prompt can deliver. Generate ONE page with **empty** bubbles and boxes
("leave every speech bubble and caption box completely blank, no text or
characters inside"), or reuse a text-free generation, and hand that single
page to the builder:

```
python scripts/build_tiered_page.py <art>.png stories/<slug>-captions.json \
    stories/<slug>-page.png --parts-dir stories/<slug>-tiers
```

It writes the three tiers onto copies of that one page and stacks them
simplest-first, separated by a thin rule and unlabelled by default, so the
blocks are pixel-identical. `--parts-dir` also drops the three tiers as
separate images. Captions land in a
strip under each panel; add `"boxes": {"1": [left, top, right, bottom], ...}`
to the JSON — panel-local coordinates, measured once with
`scripts/grid_panels.py` — to draw them inside bubbles instead. One set of
coordinates serves all three tiers, because it is one image.

`scripts/overlay_captions.py` captions a single image on its own, for
repairing one panel by hand.
