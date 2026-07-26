---
name: create-story
description: Generates an A1-A2 Mandarin learning story as a script-style .txt file, written in three parallel difficulty versions (easy/medium/hard) of the SAME plot. Optionally grounds the story in a specific lesson (and dialogue) of the 時代華語 1 / Modern Chinese Book 1 source textbook, e.g. "/create-story 5-2" for Lesson 5, Dialogue 2. Use this whenever the user types /create-story, or asks to write/generate a Chinese practice story, dialogue, or reading passage for beginner (A1/A2, HSK1-2, or "Modern Chinese Book 1" level) learners. Triggers on requests like "make a story about ordering food," "write a beginner dialogue," "create a story from lesson 3," or "create a Traditional Chinese practice text," even if the user doesn't say the words "story" or "script" explicitly — a request for beginner-level Chinese conversation practice content should trigger this skill.
---

# Create Story

Generates a situational Mandarin story for A1-A2 learners, grounded in the style of 時代華語 1 (Modern Chinese Book 1) — see `references/book1-style.md` for the exact conventions (Traditional characters, young casual speakers, sentence patterns, vocabulary annotation format). Read that file before writing if you haven't already this session.

The output is one `.txt` file containing the **same story told three times** — easy, medium, and hard — because the point isn't three different stories, it's the same meaningful situation stretched across a learner's early growth curve. A student should be able to reread a story they liked at a harder level later and recognize it.

## 1. Parse the request

The argument after `/create-story` can start with an optional **mode** keyword, `book` or `generate`, followed by the rest of the request:
- A **lesson reference**: a bare number (`5`) or `lesson-chapter` (`5-2`, meaning Lesson 5, section 2). A lesson's numbered sections are 對話一 = 1, 對話二 = 2, and the 短文 Reading = 3 where the lesson has one — the book's own audio track numbers confirm this (Lesson 5's reading is labelled 05-3-1 / 05-3-2). **A source text doesn't have to be a dialogue.** A 短文 reading passage is a perfectly valid chapter and goes through the identical three-tier template; don't report a chapter as missing just because there's no 對話 with that number.
- A **free-text topic** ("ordering coffee").
- **Both** — a lesson reference followed by a topic (`5-2 losing a phone` → ground vocab in Lesson 5 Dialogue 2, but the situation is about losing a phone). A trailing topic only applies in `generate` mode; `book` mode's situation always comes from the lesson's own dialogue, so ignore a topic if one is given alongside `book`.
- **Neither** — pick everything yourself. No lesson reference means the mode keyword doesn't apply either; skip straight to step 3.

**A lesson reference requires a mode keyword — don't guess which one.** If the request has a lesson/chapter number but no leading `book`/`generate`, stop and ask the user which mode they want before doing anything else. Likewise, if `book` or `generate` is given with no lesson reference, ask which lesson/chapter to ground it in — both modes require one.

- **`book`** — the lesson's dialogue **is** the story. Its own lines become the **easy** tier verbatim; medium and hard keep the same beats and escalate the language *above* the book. Never a new plot, and never a rewritten easy tier.
- **`generate`** — the lesson is a springboard, not a script: use its vocabulary/situation for inspiration but write an original situation. This is the skill's long-standing default behavior, from before this mode existed.

Examples: `/create-story book 5-1`, `/create-story generate 5-2 losing a phone`, `/create-story ordering coffee` (no lesson → no mode needed).

## 2. Ground in a lesson, if one was given

If a lesson (and optionally chapter) was specified, read `references/lesson-index.md` to find its page range and title, then use `scripts/render_pages.py` to render that range to images and read them:

```
python .claude/skills/create-story/scripts/render_pages.py <start> <end> <scratch-dir>
```

Render into a scratch/temp directory, not the repo. Start with just the first page to confirm the lesson title/badge matches the index (it's been verified against the book's actual divider pages, but a quick check costs nothing) before rendering the rest.

If a chapter number was given, scan the rendered pages for the "對話一 Dialogue 1" / "對話二 Dialogue 2" / "短文 Reading" section headers and focus on the requested one (see `references/lesson-index.md` for how chapters map to sections). Pull from that lesson: the actual source text, and its vocabulary list (word/pinyin/POS/gloss). **Scan for all three header types before concluding a chapter doesn't exist** — the 短文 sits near the back of the lesson, after the grammar notes, so a scan that stops at the dialogues will miss it.

- **generate mode:** use the dialogue for tone/situation inspiration only, not to copy verbatim. Its vocabulary list is the pool the **easy** tier should stay within; medium/hard can extend beyond it (see step 6) but should still favor this lesson's words where natural.
- **book mode:** transcribe the actual dialogue lines **character for character** into your working notes — these exact lines *become* the easy tier, so a paraphrase at this step corrupts the whole file. Also read the lesson's Simplified/Pinyin/English companion spread for that dialogue (it sits a page or two after it) and transcribe its pinyin and English too: the easy tier's pinyin and English lines come from the book, not from your own translation. If you can't locate the companion spread, write pinyin/English yourself but keep the characters verbatim. The vocabulary list is the pool medium/hard escalate *above*, not a fence around the easy tier — the book's own line may already exceed it.

If no lesson was given, skip this step entirely — no need to open the PDF at all.

## 3. Pick the situation

**book mode:** the situation is whatever the lesson's actual dialogue is about — don't invent or substitute one. Skip the rest of this step.

**generate mode or no lesson:** If a free-text topic was given (alone or alongside a lesson), use it. If a lesson was given without a topic, base the situation on that lesson's actual dialogue/topic (see its title in the index) rather than inventing something unrelated. If neither was given, pick a fresh everyday situation a young person in Taiwan would realistically encounter — ordering food, asking directions, meeting a new roommate, buying a bus ticket, texting a friend to reschedule, returning an item at a shop, small talk at a night market, etc. Before picking, check the `stories/` folder (glob `stories/*.txt`) so you don't repeat a situation that's already there.

Favor situations with real conversational payoff: phrases the learner could actually reuse the same week. Avoid abstract or purely descriptive topics ("the four seasons") — the value here is rehearsing a real exchange, not reading a paragraph.

## 4. Decide the cast

**book mode:** use the same characters, and the same names, as the lesson's actual dialogue.

**generate mode or no lesson:** Use **one narrator (monologue)** or **two characters (dialogue)** — whichever fits the situation more naturally. A transaction (ordering, buying, asking a stranger for directions) often reads better as dialogue; a personal recount (what I did this weekend, why I'm late) can work as monologue. Even in a dialogue story, it's fine for the opening and closing turns to be narrator lines that set or close the scene (see the example in step 5). Characters are always young people (students, young workers, roommates, friends) with real-sounding given names, following the book's convention (中明, 宜文, 友美, etc. — invent similar names, don't reuse the exact same pair every time, unless you're deliberately continuing the same cast from the source lesson).

## 5. Build the turn-by-turn scene plot once

Before writing any Chinese, outline the story as a fixed sequence of turns. Lock this count in now — all three difficulty levels below reuse exactly this many turns, because each turn is meant to eventually pair 1:1 with one image.

**generate mode or no lesson:** outline **4-6 turns**.

**book mode: one turn per line of the book's source text — the 4-6 range does not apply here.** A 9-line dialogue is 9 turns and a 9-panel grid. For a **短文 reading passage** the unit is one *sentence* (full stop to full stop, not comma to comma): a 4-sentence passage is 4 turns and a 2×2 grid, and every turn is spoken by "Narrator" since the passage is a first-person monologue with no named cast. Never merge two of the book's lines into one turn, never drop a short line (a bare「好。」or「沙發下面呢？」is its own turn), never split one line across two turns, and never trim the count to make a tidier grid — the grid follows the dialogue, not the reverse. Stage directions in parentheses (（中明再去房間）) are not turns; fold them into the following turn's scene note.

A turn is **one line spoken by one character (or the narrator)** — not a back-and-forth exchange. A greeting followed by a question is two turns, not one. The turns should move the situation forward in space or time (not just restate the same moment), and each one should be visually distinct enough to illustrate on its own.

For each turn, jot down: who's speaking (or narrator), what's physically happening/visible, and the gist of the line. Example — lunch with a friend, 6 turns:

1. Narrator — noon, we're both hungry, heading out to eat
2. Owner — greets us warmly, asks what we'd like
3. Us — order rice, pork, and vegetables
4. Us — thank her and start eating
5. Us — finish, clear the table, say goodbye
6. Narrator — the food was great, she was so kind, we'll come back tomorrow

## 6. Write the three difficulty levels

Same turns, same order, same characters — only the language in each turn changes. Every level has exactly the same number of turns from step 5; turn 3 in easy and turn 3 in hard are the same beat, just in simpler or richer Chinese. Stay within A1-A2 scope for all three; "hard" here means the upper end of A2, not intermediate Chinese.

**book mode — the easy tier IS the book's dialogue, copied, not rewritten.** Reproduce every line character for character, keeping its connectors, particles and multi-clause sentences intact. The book's text is the easy ceiling in book mode, so the "one short clause, no connectors" rule in the Easy bullet below **does not apply to it**: don't strip 可是 out of a line, don't shorten a two-clause line, don't swap a word for a more common one, don't drop a tag question. If a line looks harder than the Easy bullet allows, leave it exactly as it is — it's what the learner's own textbook already asks them to read.

**Medium and hard escalate above that baseline**, keeping the same beats, speakers and intent — strictly easy < medium < hard, with all three still inside A1-A2 (roughly ≤HSK3/TOCFL A2; no HSK4+ vocabulary, no 把/被). Escalate primarily by **word choice**: upgrade a plain word to a richer one of the same meaning, add a degree or frequency adverb, make a vague noun specific. Reach for a new *structure* only where that beat genuinely offers one. Typical ladder:
  - medium adds: 快…了, 可是, 每…都, 太…了, 非常, basic time words
  - hard adds: 如果, 過, 比, 覺得…最, 很久沒…了, multi-clause lines

**Never bend the scene to fit a structure.** If a beat gives you nowhere natural to put 比, don't invent a comparison for it (a mother carrying a pot out of the kitchen does not say 我今天比昨天忙) — escalate that turn with vocabulary instead, and spend 比 on a turn where the situation actually supplies two things to compare. A grammar point forced into a line no real speaker would say costs more on Turn Craft and Situation Focus than the structure gains on Language Fit.

- **Easy (A1 low)** — *generate mode / no lesson only; in book mode the easy tier is the book's own text, see above*: each turn is one short clause, highest-frequency ~150 words, only 是/很/叫/在/有 style patterns and present tense, no connectors. Sentence length matches the Lesson 1 example in the style reference. If a lesson was given, stay within that lesson's vocabulary list.
- **Medium (A1 high / A2 low):** each turn is a slightly longer single line, basic time words (今天/昨天/明天), at most one simple connector where it's natural (可是, 因為...所以...), a bit more vocabulary variety. If a lesson was given, you can pull in a modest number of words from earlier lessons in the index too, not just this one.
- **Hard (A2):** each turn can be one multi-clause line, comparison (比), aspect markers (了/過), more descriptive vocabulary — but still one short, spoken, natural line, not a paragraph. Don't drift into written/literary register or intermediate grammar (把, 被, complex complement structures) — that's past A2.

Write in **Traditional characters**. For each turn, give a short bracketed scene note (who/where/what's visually happening — this doubles as context for the future image) followed by three stacked lines: Chinese, pinyin, English. Label the speaker by name (or "Narrator") for every turn.

## 7. Add a vocabulary list per level

After each level's story text, list the new/level-appropriate words introduced in that version: number, word, pinyin, POS tag, English gloss — matching the book's annotation format. Keep each level's list focused on words that are new *for that level* (easy's list can be a subset of what appears in medium/hard).

## 8. Call out key phrases per level

For each level, pull out **at least 2 reusable phrases or applied grammar patterns** actually used in that level's story text — the takeaways a learner could lift straight into their own speech, distinct from the single-word vocabulary list in step 7. For each one give: the pattern (generalized with a blank where useful, e.g. "X 在哪裡？" or "因為...，所以..."), one example line pulled verbatim from that level's story, and a one-line usage note (when/why you'd reach for it). Draw these from the grammar toolkit each level is already scoped to in step 6 — 是/很/在/叫/有 patterns for easy, time words/connectors for medium, 比/了/過 for hard — rather than inventing patterns the story doesn't actually contain. In book mode the easy tier's phrases come from whatever the book's own lines actually use, which is often richer than that toolkit (是不是…？, 幫我…, …吧) — pull what's there.

## 9. Assemble and save the file

One file, three sections, in this shape:

```
《[Story Title in Chinese]》[English title]
Situation: [one-line description of the real-life context]
[Source: Lesson N – 課名 (Dialogue C), mode: book|generate — omit this line entirely if no lesson was specified]

═══════════════════
EASY (A1)
═══════════════════

[Turn 1 — scene note: who/where/what's visible]
[Speaker]：[Chinese line]
[Pinyin line]
[English line]

[Turn 2 — scene note]
[Speaker]：[Chinese line]
[Pinyin line]
[English line]
...through Turn N (same N as every other level — 4-6 in generate mode, one per book line in book mode)...

Vocabulary
1  [word]  [pinyin]  [POS]  [gloss]
...

Key Phrases
1  [pattern]  —  [example line from this level's story]  —  [usage note]
2  [pattern]  —  [example line from this level's story]  —  [usage note]
...(2+ per level)...

═══════════════════
MEDIUM (A1-A2)
═══════════════════
... same N turns, same scene notes, richer language ...
... own Vocabulary and Key Phrases (2+) for this level ...

═══════════════════
HARD (A2)
═══════════════════
... same N turns, same scene notes, richer language ...
... own Vocabulary and Key Phrases (2+) for this level ...
```

Save to `stories/<kebab-case-slug>.txt` in the project root (create the `stories/` folder if it doesn't exist). Derive the slug from the situation, e.g. `stories/ordering-milk-tea.txt`. If a file with that name already exists, pick a more specific slug rather than overwriting — treat existing story files as the user's saved work.

## 10. Self-score each tier against the story quality rubric

Before generating images, score the story against the rubric below — a beginner-story adaptation of a standard narrative-writing rubric, scored 5 (Poor) to 10 (Exceptional) per criterion. **Language Fit is scored per tier** (it's what separates them); the other four criteria are scored **once for the story as a whole** and repeated across all three tiers. See the scoring rules under the table, and don't generate images for a story that hasn't cleared the revision gate there.

| Criterion | 10 Exceptional | 9 Above Average | 8 Good | 7 Needs Improvement | 6 Below Average | 5 Poor |
|---|---|---|---|---|---|---|
| **Situation Focus** — stays on the chosen scenario | Every turn stays tightly on the situation; vivid, reinforcing detail | Every turn stays on the situation; clear, well-supported development | Turns relate to the situation; development is generally logical | Shows awareness of the situation but development is mediocre, may include unrelated detail | Only somewhat related to the situation; weak development | Only slightly connected to the situation; inconsistent or illogical detail |
| **Turn Craft** — natural dialogue, distinct scenes, consistent voice | Vivid natural dialogue, visually distinct scene notes, fully consistent voice | Natural dialogue, clear distinct scene notes | Dialogue generally natural; scene notes present but less specific | Dialogue/scene notes attempted but some turns feel generic | Dialogue feels stiff or written-register; scene notes vague or repetitive | Little natural dialogue or distinct scene notes |
| **Turn Progression** — setup → development → resolution, identical across all 3 tiers | Clear setup/development/resolution; identical turns/order across all tiers | Turns move forward clearly; all three stages connected | Three stages present, one stage thin | Three stages attempted but rushed, or a turn restates a prior moment | Progression unclear; a turn repeats or skips a stage | No clear progression; turns disconnected or hard to follow |
| **Language Fit per Tier** — how far up the A1-A2 ladder this tier actually sits (step 6). Fixed target per tier: **easy 8, medium 9, hard 10** — a tier can score below its target, never above | **Hard only.** Multi-clause lines, 如果/過/比/很久沒…了, top of A2, still natural spoken register | **Medium only.** 快…了/可是/每…都/太…了/非常, one clear step above easy | **Easy only.** The bottom rung, correctly occupied — in book mode the textbook's line reproduced exactly; in generate mode one short A1 clause | The tier failed to climb: medium reads no richer than easy, or hard no richer than medium | The tier sits below the one beneath it, or register drifts toward written/literary Chinese | Vocabulary/grammar clearly mismatched, or 把/被/complex complements/HSK4+ words appear at any tier |
| **Accuracy & Conventions** — characters, pinyin, format | Characters, pinyin, tone marks all correct; vocab/Key Phrases match book format exactly; file matches template precisely | Correct with only trivial formatting slips | Adequate control; format mostly matches template | Follows conventions most of the time; a few pinyin/tone/format errors | Noticeable errors that could confuse a learner | Errors frequent enough to undermine the story's usefulness |

Unlike the essay rubric this is adapted from, figurative/literary language and complex sentence variety are never rewarded here — A1-A2 spoken register is the ceiling at every score band, including 10.

**Language Fit is a ladder position, not a compliance check.** Each tier has exactly one correct score and cannot beat it: easy 8, medium 9, hard 10. A tier drops below its target only when it failed to climb — medium that reads no richer than easy is an 8, hard that reads like medium is a 9. **Easy scoring 8 is a pass, not a deduction:** it means the bottom rung is correctly occupied. Never award easy a 9 or 10 for being well written; that's what the other four criteria are for.

**The other four criteria are scored once and shared by all three tiers.** Same story, same beats, same scene notes, same speakers — so Situation Focus, Turn Craft, Turn Progression and Accuracy & Conventions each get one value, repeated down the column. If you find yourself wanting to score one tier lower on any of them, that isn't a scoring nuance: that tier has drifted from the other two. Fix the tier so the shared score is true again, rather than recording the difference.

**Revision gate — revise and re-score before step 11 if:** any tier misses its Language Fit target, two tiers tie on it, or any shared criterion is below 7. A hard tier stuck at 9 almost always means a structure was forced into a beat that didn't want one (see step 6's "never bend the scene") — escalate that turn by vocabulary instead, rather than explaining the gap in your reply.

**In book mode**, score the easy tier's Language Fit **against the book, not against the Easy bullet** — the question is "does this match the source dialogue character for character?", not "is it one short clause?". A line richer than the Easy bullet is correct at 8; a line you smoothed, shortened or re-translated drops easy below 8 and is an Accuracy failure too, however well it reads.

Display the three tiers' scores as a compact table (tier × criterion) in your reply right after saving the story file — this is a self-check for you as the generator, not content that belongs inside the story `.txt` file itself.

## 11. Generate an image prompt

Read `references/image-prompt-template.md` (the "one prompt, one page, N panels" method) and use it to write **four** AI image-generation prompts (one text-free, plus one speech-bubble prompt per difficulty tier), each for **one image containing a grid of panels** — one panel per turn, comic-strip style, reusing the exact turns and scene notes locked in step 5 (don't invent new beats). Pick the grid shape from the turn count (2×2 for 4 turns, 2×3 for 5-6 turns; past 6 — which only happens in book mode — grow the grid to the next shape that fits, e.g. 2×4 for 7-8 turns, 3×3 for 9 — see the reference file). When the source is a **短文**, every panel is narrator-only, so all of them take a rectangular caption box along the bottom edge and the page has no speech bubbles at all — say that explicitly in the style line so the model doesn't add tails. Write the cast/style/layout once at the top of each prompt, then one "Panel N:" line per turn expanding that turn's bracketed scene note into a full visual description, listing only the characters who actually appear in that panel and deliberately varying pose, shot framing, and camera angle panel to panel so they don't all look like the same picture — see the "Vary composition" rule in the reference file.

Write **four** prompts into the same file, text-free first:

1. **Text-free** — no words anywhere in the image, safest since image models often garble Chinese text.
2. **Speech bubbles — one prompt per tier (easy, medium, hard)** — every panel gets somewhere to put its line, not just the speaking ones: a panel with a speaking character gets a bubble pointing at them, a narrator-only panel gets a rectangular caption box instead (no tail, along the bottom edge) — and this time **the real Chinese line is written directly into the prompt** for that bubble/box, so pasting the prompt into an image generator produces a finished page in one shot. Because the story has three difficulty tiers, produce three separate speech-bubble prompts — not one defaulting to a single tier — so the user can illustrate whichever level they're practicing. Each tier's prompt quotes only that tier's own lines exactly (Chinese only, no pinyin/English inside the bubble), after checking each line actually matches that panel's visual scene note first — if a panel's note was drawn from a different tier's phrasing (turns can drift in wording between tiers), fix the mismatch before writing that tier's prompt, so the bubble never describes something the panel doesn't show; check this separately per tier. Because AI image models render Chinese text inconsistently, add a caution note right above each of the three prompts (proofread every bubble/box after generating; fall back to the text-free version + step 12's overlay scripts if a line comes out garbled) and append a consolidated **Caption Script** after each prompt (Chinese/pinyin/English per panel, narrator panels included, matching that prompt's own tier) as a proofreading reference.

Save this as `stories/<same-slug>-images.txt`, alongside the story file, with all four prompts (the text-free prompt, plus the easy/medium/hard speech-bubble prompts and their own Caption Scripts) clearly labeled and separated (see the file shape in `references/image-prompt-template.md`) so the user can copy whichever one they want to paste into an image generator without regenerating anything.

## 12. Optional: fill in the bubbles on a generated image

If a speech-bubble generation comes back with garbled or missing text (or the user generated from the text-free version and wants captions added after the fact), the Chinese can be placed in by hand with the two helper scripts in `scripts/`:

1. `python scripts/grid_panels.py IMAGE_PATH ROWS COLS OUT_DIR` — crops the image into its panels and saves a gridded, upscaled version of each (`panelN_grid.png`) with pixel-coordinate gridlines. Read a few of these (via the Read tool, they're images) to eyeball each bubble's safe interior box — comfortably inside the drawn outline, since the auto-fit still needs margin.
2. Write a small JSON config mapping panel number → `{"box": [left, top, right, bottom], "text": "..."}` (local coordinates within that panel, from step 1) — one entry per speaking panel, using the Caption Script's Chinese text (trim long lines slightly if a bubble is small; the full grammar/vocabulary point still lives in the story file, this is just the in-image caption).
3. `python scripts/overlay_captions.py IMAGE_PATH CONFIG_JSON OUT_PATH` — auto-shrinks and centers each caption to fit its box, saves the composed image.

Check the output (Read the saved PNG) before calling it done — text that touches or crosses a bubble's outline means the box needs tightening or the line needs trimming; iterate rather than accepting an overflowing result.

## Why this shape

The turn/level structure exists so a beginner can track real progress: reread the same story they enjoyed and notice they're ready for more complex language, rather than being handed unrelated stories at each level. Locking one turn count across all three levels means the same beats — and eventually the same images — carry every difficulty version, so leveling up never means learning a new plot.

Book mode puts the textbook's own dialogue at the *bottom* of the ladder rather than the middle, on purpose: the lines the student is already being taught in class become their entry-level reading, and the generated tiers are growth steps above something they've genuinely mastered. Anchoring the book at medium instead would leave the easy tier as invented filler and give the student nowhere to climb from. Grounding word choice and sentence rhythm in the actual textbook (rather than generic "simple Chinese") keeps stories consistent with what the learner is used to seeing and makes new vocabulary land in a familiar voice.
