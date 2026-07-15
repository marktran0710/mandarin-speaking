# Image-prompt generation method

Method for turning a story's locked turns (from SKILL.md step 5) into AI
image-generation prompts (ChatGPT/DALL·E, Midjourney, Canva Magic Media,
etc.), each producing a **single image containing a grid of panels** — one
panel per turn, comic-strip style, consistent characters and art style
throughout. Each prompt is a single generation call, not a batch of separate
prompts: the whole story fits on one page. Two prompts — text-free and
speech-bubble — are written into the same `-images.txt` file; see "Two
modes" below.

## Two modes, both written into the same file

SKILL.md step 10 writes **both** prompts into one `-images.txt` file, so the
user can pick whichever they want without asking for a regenerate:

- **Text-free** — no words anywhere in the image, including no speech
  bubbles. Safer: image models are unreliable at rendering legible Chinese
  text, so garbled/wrong characters are a real risk in bubble mode. This is
  the mode documented in the "Core method" and "Example output" sections
  below. Write this one first.
- **Speech bubbles** — each speaking panel gets a bubble pointing at the
  character *with that panel's real Chinese dialogue written inside it*,
  and each narrator-only panel gets a rectangular caption box (no tail)
  with its narration text — so pasting this prompt straight into an image
  generator produces a finished page with the actual script already in it,
  no manual editing step required. AI image models render Chinese text
  inconsistently (a real risk of garbled or wrong characters), so this mode
  says so explicitly right above the prompt and tells the user to proofread
  every bubble/box after generating — see the "Speech bubble mode" section
  near the end for exactly what changes from the core method, including the
  fallback (text-free + `scripts/overlay_captions.py` from SKILL.md step 11)
  for when a generation comes back garbled. Write this one second.

Both modes share the same grid layout, cast block, and panel-by-panel scene
descriptions — only the "no text" style line and the per-panel dialogue
differ, so most of the prompt text can be reused between the two sections.

## File shape

Separate the two prompts with a clear header so each is easy to find and
copy on its own — just the header and the prompt text, no explanatory
bracketed notes:

```
═══════════════════
TEXT-FREE VERSION
═══════════════════

[... text-free prompt, per "Core method" below ...]

═══════════════════
SPEECH-BUBBLE VERSION
═══════════════════
(AI image models render Chinese text inconsistently — proofread every
bubble/box after generating. If any line comes out garbled or wrong,
regenerate, or fall back to the TEXT-FREE VERSION above plus
scripts/overlay_captions.py, per SKILL.md step 11.)

[... speech-bubble prompt, per "Speech bubble mode" below, with each
panel's real Chinese dialogue/narration written directly into that
panel's bubble or caption box, using the medium tier's lines ...]
```

OUTPUT SIZE TARGET: the final image must be under 1.5 MB. File size is set
at export, not by the prompt, so (a) favor simple flat art and plain
backgrounds, which compress much smaller, and (b) follow the EXPORT SETTINGS
section at the end.

## Core method — "one prompt, one page, N panels"

Because it's a single generation, character consistency is largely handled
by the model automatically (it's rendering one coherent image, not stitching
together separate calls with no memory of each other). The prompt's job is
to: describe the cast and style once, lay out the grid, and give each panel
its own distinct scene line so the panels read as a sequence of moments
rather than one pose copy-pasted six times.

1) **Pick the grid shape from the turn count N** (4-6, locked in step 5):
   - N=4 → 2 columns × 2 rows
   - N=5 → 2 columns × 3 rows, with the final row a single wide panel
     spanning both columns (5 panels total)
   - N=6 → 2 columns × 3 rows (matches a standard comic page)

2) Write ONE cast + style block, stated once at the top of the prompt (not
   repeated per panel):
   - **Style**: one art style + color mood, ending with "no text, no
     letters, no words, no speech bubbles, no panel numbers, no captions".
     Prefer flat/vector or clean digital-illustration styles with a limited
     palette — they compress smaller and stay consistent panel to panel.
   - **Each character**: name, age, face shape, hair + ONE signature
     accessory, full outfit with SPECIFIC colors, that stays identical in
     every panel. Give each character one unmistakable signature (a colored
     shirt, a hairclip, a backpack color) so it's easy to spot them
     consistent across all N panels.
   - **Layout instruction**: state the grid shape from step 1 explicitly —
     e.g. "single image divided into a clean grid of 6 equal panels (2
     columns × 3 rows), thin light gutters between panels, no hard comic-book
     borders, consistent lighting and color palette across all panels."

3) Write one **"Panel N:"** line per turn, in reading order (left-to-right,
   top-to-bottom), reusing the exact turns and scene notes already locked in
   step 5 (don't invent new beats). Expand each turn's short bracketed scene
   note into a full visual description: setting, pose, expression, props.
   Only mention the characters who actually appear in that turn.

4) Deliberately vary pose and framing panel to panel (see "Vary composition"
   rule below) so the six panels don't all show the same standing pose with
   one prop swapped.

5) End with a short CONSISTENCY TIPS section and the EXPORT SETTINGS below.

## Rules

- Write the prompt in English (most stable for image models), even though
  the story itself is in Chinese — translate names to pinyin (Zhōngmíng →
  Zhongming) for readability in the prompt.
- Be almost boringly specific about each character in the cast block; vague
  descriptions produce a different-looking person panel to panel.
- Number the panels to match the turn numbers (Panel 1 = Turn 1, etc.).
- Do NOT put any caption, dialogue, panel-number, or speech-bubble text
  inside the prompt's requested output — the image should contain no words
  anywhere, including inside panels.
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

## Example output (asking-for-directions story, two speakers: Chenghan, Wanting, 6 turns)

```
Single square-ish image, divided into a clean grid of 6 equal panels (2
columns × 3 rows), thin light gutters between panels, no hard comic-book
borders, no text, no letters, no words, no speech bubbles, no panel numbers,
no captions. Flat digital illustration style, soft rounded shapes, warm
morning color palette, limited color palette, gentle clean outlines,
friendly simple style, consistent lighting and color palette across all
panels.

CHARACTERS (identical in every panel they appear in):
[CHENGHAN] a friendly young man, early 20s, short tousled black hair, slim
build, light blue button-up shirt, dark grey pants, white sneakers, navy
blue backpack with one visible strap over one shoulder.
[WANTING] a friendly young woman, early 20s, straight black hair in a low
ponytail tied with a yellow scrunchie, round glasses, soft green cardigan
over a white t-shirt, denim skirt, tan tote bag over one shoulder.

Panel 1 (top-left): wide shot, full figure, Chenghan alone on a city
sidewalk in the early morning, looking around anxiously and raising one
hand to shade his eyes, simple low buildings and trees in the background.

Panel 2 (top-right): medium shot at eye level, Chenghan stopping Wanting on
the sidewalk, raising one hand politely to get her attention while asking a
question, Wanting turning toward him with a friendly, attentive expression.

Panel 3 (middle-left): medium shot, Wanting pointing down the street with
one arm extended, Chenghan following her gesture and looking in that
direction, both standing on the sidewalk.

Panel 4 (middle-right): close-up on Chenghan's face and shoulders, a
slightly worried expression, one hand shading his eyes as he judges the
distance, Wanting visible beside him watching him with a reassuring look.

Panel 5 (bottom-left): medium shot from a slight side angle, Wanting
shaking her head gently and smiling, one hand making a small "it's close"
gesture, Chenghan looking relieved as he listens.

Panel 6 (bottom-right): wide shot from behind and to the side, Chenghan
walking away toward a small MRT station entrance sign in the distance,
glancing back with a wave, Wanting waving back from where she is standing.

CONSISTENCY TIPS:
- Keep the exact same character design (Chenghan's navy backpack, Wanting's
  yellow scrunchie and round glasses) recognizable in every panel.
- Keep one art style and one lighting mood across all 6 panels so the page
  reads as one connected world.
- Vary pose, shot framing, and camera angle panel to panel (see Rules) so it
  reads as six different moments, not one pose repeated six times.
- If one panel looks off after generation, it's harder to regenerate in
  isolation than with separate images — accept minor variance, or fall back
  to generating that one beat as its own image and swapping it in during
  editing if it matters.

EXPORT SETTINGS (to keep the file under 1.5 MB):
- Generate at a resolution that keeps individual panels legible — e.g.
  1024 x 1536 for a 2×3 grid, or 1024 x 1024 for a 2×2 grid.
- Export as JPG (much smaller than PNG) at about 80-85% quality.
- If the file is still too large, lower JPG quality slightly, reduce overall
  dimensions, or simplify panel backgrounds.
- Use PNG only if you need transparency; if so, expect larger files and
  compress with a tool like TinyPNG to get under 1.5 MB.
```

## Speech bubble mode

Everything above is written for text-free mode. Speech-bubble mode asks the
image model to render each panel's real Chinese line **directly inside**
its bubble or caption box, so the pasted-in prompt alone produces a
finished page — no separate editing step. The tradeoff: AI image models
render Chinese text inconsistently, so a caution note and a fallback path
are required (see below).

To generate a speech-bubble version, keep the same grid layout, cast block,
and per-panel scene descriptions, but make these changes:

1) **Header caution**: immediately under the `SPEECH-BUBBLE VERSION` divider
   (before the prompt itself), add a note that Chinese text rendering is
   unreliable, to proofread every bubble/box after generating, and that the
   fallback is the TEXT-FREE VERSION plus `scripts/overlay_captions.py`
   (SKILL.md step 11) if a generation comes back garbled. See the File
   shape example above for the exact wording.

2) **Style line**: drop "no text, no letters, no words, no speech bubbles,
   no panel numbers, no captions" and replace with something like "each
   panel that has a speaking character includes one simple rounded speech
   bubble with a small tail pointing at that character, containing that
   panel's Chinese text written clearly and accurately inside, plain white
   bubble with black outline; each narrator-only panel instead includes one
   small rectangular caption box (no tail) along the bottom edge containing
   that panel's Chinese narration text, plain white box with a thin black
   border; no other text, letters, words, or captions anywhere else in the
   image." Every panel gets either a bubble or a caption box with its own
   text — there is no panel left with nowhere to put its line, and no panel
   left silently text-free in this mode.

3) **Per-panel text**: write each panel's real Chinese line directly into
   that panel's description — quote it exactly (verbatim from the
   **medium** tier unless the user says otherwise, and only after checking
   it actually matches that panel's visual scene note, per the mismatch
   check below). Chinese only inside the bubble/box (no pinyin, no
   English). Example:

   ```
   Panel 1 (top-left): wide shot, full figure, Chenghan alone on a city
   sidewalk in the early morning, looking around anxiously and checking a
   wristwatch. Narration caption box at the bottom contains the Chinese
   text "今天承翰要去學校上課，可是他不知道捷運站在哪裡，心裡很緊張。"
   written clearly.

   Panel 2 (top-right): medium shot at eye level, Chenghan stopping Wanting
   on the sidewalk, raising one hand politely to get her attention. Speech
   bubble near Chenghan contains the Chinese text "請問，捷運站怎麼走？"
   written clearly.
   ```

4) **Append a consolidated Caption Script** after the full image prompt
   (before EXPORT SETTINGS) — the same per-panel lines (narrator panels
   included), Chinese + pinyin + English, as a proofreading reference to
   check the generated bubbles against (and to fall back on if a bubble
   needs fixing by hand or regenerating):

   ```
   CAPTION SCRIPT (for proofreading the generated bubbles/boxes against —
   not part of the prompt above):
   Panel 1 — Narrator: 今天承翰要去學校上課，可是他不知道捷運站在哪裡，心裡很緊張。
     Jīntiān Chénghàn yào qù xuéxiào shàngkè, kěshì tā bù zhīdào jiéyùnzhàn
     zài nǎlǐ, xīnlǐ hěn jǐnzhāng. — Today Chenghan needs to go to school
     for class, but he doesn't know where the MRT station is, and he feels
     very nervous.
   Panel 2 — Chenghan: 請問，捷運站怎麼走？
     Qǐngwèn, jiéyùnzhàn zěnme zǒu? — Excuse me, how do I get to the MRT
     station?
   Panel 3 — Wanting: 你往前走，咖啡店旁邊就是捷運站。
     Nǐ wǎng qián zǒu, kāfēidiàn pángbiān jiù shì jiéyùnzhàn. — Walk
     straight ahead, the MRT station is right beside the coffee shop.
   ```

   Both copies must always agree — if a panel's tier-matched line changes
   (see the mismatch check above), update it in both places.

5) Keep the rest of the method identical: grid shape by turn count, one
   cast/style block stated once, varied pose/framing/angle panel to panel,
   and the same EXPORT SETTINGS.
