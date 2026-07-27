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

**book mode: one turn per line of the book's source text — the 4-6 range does not apply here.** A 9-line dialogue is 9 turns; a 7-line dialogue is 7. Keep the book's own segmentation even when a line carries two sentences («那不是我的，是哥哥的。我的錢包不在客廳裡。» is one turn, because it is one of the book's lines). Never merge two lines into one turn, never drop a short one (a bare「好。」or「沙發下面呢？」is its own turn), never split a line across two turns, and never trim the count to make a tidier grid — the grid follows the text, not the reverse. For a **短文 reading passage** the unit is one *sentence* (full stop to full stop, not comma to comma), and every turn is spoken by "Narrator" since the passage is a first-person monologue with no named cast. Stage directions in parentheses (（中明再去房間）) are not turns; fold them into the following turn's scene note.

A turn is **one line spoken by one character (or the narrator)** — not a back-and-forth exchange. A greeting followed by a question is two turns. The turns should move the situation forward in space or time (not just restate the same moment), and each one should be visually distinct enough to illustrate on its own.

**Cap what one bubble carries** — but the turn count itself is fixed by step 5's rule above and is never adjusted for this. A panel's bubble is shared by all three tiers, so the number that decides whether the panel works is the **longest** of the three lines, not the average — a turn where easy says 「遠嗎？」and hard says 34 characters needs a bubble sized for 34. Budget by how many columns the grid has, since that's what sets a panel's width:

| Grid | Longest tier's line |
|---|---|
| 2 columns | up to ~45 characters |
| 3 columns | up to ~36 characters |
| 4 columns | up to ~28 — prefer a 3-column grid instead |

When a line is over budget, fix it in this order: widen the panel by choosing a grid with fewer columns; if it's still over, tighten the medium or hard wording (never the book's own easy line, which is fixed). Never split the turn to shrink the line — the panel count mirrors the source text (a book's lines, or the 4-6 turns you outlined), and a learner following the page against the textbook needs that count to hold. A line comfortably under budget stays exactly as it is even if it holds two short sentences: 「不遠，很近。」does not need trimming.

Keep this in mind while writing step 6: a hard line that keeps drifting past budget forces a rewrite later, so escalate *within* a sentence (richer words, an added adverb, one more comma-joined clause) with an eye on length as you go, rather than writing it long and cutting it back afterward.

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

**Watch the hard tier's length as you write it.** It sets the bubble size for all three tiers, and step 5 rules out fixing an overlong line by splitting the turn — so a hard line that drifts past its grid's budget has to be tightened after the fact instead, which usually costs it some of the colour that made it feel like the top of the ladder. Escalate inside the sentence — a richer verb, an added adverb, one more comma-joined clause — and keep an eye on the character count as you go rather than writing it long and cutting it back later.

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

## 11. Write one generate prompt and two edit prompts

The output of this step is **one image-generation prompt (EASY) plus two image-edit prompts (MEDIUM, HARD)**, pasted into ChatGPT or Gemini in the same chat, one after another. No local build step, no second tool.

Two designs were tried and rejected before this one, both on 2026-07-27:

1. **A single stacked page holding all three tiers.** Asked for 18-27 panels at once, both Gemini and ChatGPT dropped panels — including the story's final one — squeezed the grid into fewer rows, and still redrew each section differently.
2. **Three independent generate prompts, one per tier.** Each paste is a fresh generation, so even with a "same as before" hint the model re-imagines the whole scene — different faces, different framing — every time. The user hit this directly: pasting each tier's block separately produced three visibly different comics.

**Editing an existing image beats generating a new one from text**, because the model transforms pixels it can see instead of reconstructing the scene from a description. So: generate EASY once, then for MEDIUM and HARD, ask the model to *edit* that same image — "keep the artwork exactly as it is, only replace the bubble text" — rather than generating fresh. Both edits target the EASY image directly (not chained medium→hard), so neither is more than one edit away from the source and errors don't compound. This still won't produce pixel-identical art — an edit can nudge a line or shift a colour — but it's much closer than three separate generations, and requires no local step. Tell the user explicitly: generate and edit **in the same chat**; if they start a new chat or switch devices, they need to upload the EASY image before pasting an edit prompt. Only step 12's local compositing produces truly identical artwork.

Read `references/image-prompt-template.md` for the full method and an example. The EASY prompt has five parts; the two edit prompts are much shorter — just the edit instruction and that tier's lines, since the artwork, cast and layout are already fixed by the image being edited:

1. **Layout instruction** — one comic page, N panels, a strict uniform grid drawn as an **ASCII box diagram**. Prose ("3 columns × 2 rows") gets reinterpreted; a picture of the grid doesn't. Every panel the same width and height, aligned edges, equal gutters, no wide panels, no insets, no irregular comic layout. Left to itself a model "improves" the page with a dramatic splash panel and the rest shrink around it.
2. **No text outside the bubbles** — no title, no level label, no panel numbers, no signage, no letters of any alphabet. Every word left out of the artwork is one less chance for the model to render broken characters, and the tier is already obvious from the file the page came from.
3. **Cast + style block** — named characters with one unmistakable signature each (a colour, an accessory), one art style, one lighting mood, held identical across every panel.
4. **The panel descriptions** — one `Panel N:` line per turn from step 5, expanding that turn's bracketed scene note, varying pose/framing/angle between panels so the page reads as a sequence rather than one pose repeated.
5. **That tier's text, panel by panel** — the real Chinese line, quoted exactly, labelled with where it goes. A spoken line gets a **speech bubble** with a tail pointing at the character; a narrator turn gets a rectangular caption box along the bottom edge, so no panel is left with nowhere to put its line. Two things to say explicitly: **write only the line inside the bubble, never the speaker's name** (the tail already says who's talking, and a name inside reads as a mistake), and **size the bubble generously** — roughly the top third of the panel, characters in the lower two thirds. A 短文 source is narrator-only throughout, so that page has caption boxes and no tails at all.

**Never let a line go undrawn.** A ragged last row invites the model to close the gap by dropping a panel — usually the last one, the story's payoff (seen repeatedly with Gemini, 2026-07-27). Since the turn count follows the source text and is never trimmed, handle the leftover cells head-on: ask for them as **blank white filler panels** (same size, same border, empty inside, named in the ASCII diagram), forbid widening the last real panel into them, and close the layout section with a count check naming both numbers — "exactly N drawn panels plus M blank fillers; if a line has nowhere to go, a panel has been dropped, add it back rather than merging two lines into one bubble." A missing panel is a line of the story the learner never sees, which is worse than an ugly page.

**Run a mismatch check before saving the file — spawn a subagent for it if one is available.** A panel's visual is shared across all three tiers, so it has to plausibly support the easy line, the medium line, and the hard line at once; a scene note that only fits one of them is a real bug (caught for real, twice: `my-room-and-my-cat.txt` once had a panel showing a books-stack reaction while the medium line was about room comfort, and `asking-for-directions.txt`'s final panel once showed Chenghan calmly walking away while the hard tier has him sprinting because he's ten minutes late). You wrote both the scene notes and the escalated dialogue yourself, so you're the worst-positioned reviewer for this — a fresh subagent catches it faster because it has no attachment to either draft. Give it the story `.txt` and the images `.txt`, and ask it to check, panel by panel, whether the shared visual description still makes sense against all three tiers' lines: does it contradict what a line says, show something a line can't support (a search scene with no reaching-for-it pose), or read as the wrong emotional register for what's happening. Ask for a plain PASS or a list of concrete panel-by-panel problems with a suggested fix — not a style critique. Apply anything real it finds, then move on; don't loop on the check itself. If no subagent is available, do the same pass yourself before saving.

**Chinese text will sometimes come out wrong.** Image models render Traditional characters inconsistently — that's the known cost of the one-paste workflow, not a reason to change it. Handle it the way the file already does: tell the prompt to copy the characters exactly and invent nothing, and put a caution line above the prompt telling the user to proofread every caption against the Caption Script below it. Step 12 is the repair path when a line does come out garbled.

Save one file: `stories/<same-slug>-images.txt` — the header (turn count, grid, and the "generate EASY, then edit it twice, same chat" instructions), the caution line, then the EASY generate prompt with its Caption Script, then the MEDIUM edit prompt with its Caption Script, then the HARD edit prompt with its Caption Script. Close with a **FIXING A BAD GENERATION** section of ready-made corrections to send in the same chat — a missing panel, an uneven grid, an edit that changed more than the text, garbled characters. Don't write a companion JSON; step 12's repair path needs one, but it's a mechanical transcription of the Caption Scripts and is quicker to produce on the day it's actually needed than to keep in sync forever.

## 12. Repair path, only if the generated text is wrong

If the captions come back garbled, or the user would rather have clean typeset text than whatever the model drew, the Chinese can be composited locally instead. This is a fallback — don't route the user here by default.

Ask for the same page **with empty bubbles and boxes** (change the text instruction to "leave every speech bubble and caption box completely blank, no text or characters inside"), or reuse an existing text-free generation, then:

```
python .claude/skills/create-story/scripts/build_tiered_page.py \
    <art>.png stories/<slug>-captions.json stories/<slug>-page.png \
    --parts-dir stories/<slug>-tiers
```

Write the JSON at this point by transcribing the file's three Caption Scripts (`{"rows": R, "cols": C, "title": ..., "tiers": {"easy": {"1": "...", ...}, "medium": ..., "hard": ...}}`, panel keys 1-indexed in reading order). `<art>.png` is the single generated page (blank bubbles) — the script writes the three tiers onto copies of it and stacks them simplest-first with a thin rule between, no labels drawn (add `"labels": true` to the JSON if you do want them named). Captions land in a strip under each panel; add `"boxes": {"1": [left, top, right, bottom], ...}` to the JSON (panel-local coordinates, measured once with `scripts/grid_panels.py`) to put them inside drawn bubbles instead. One set of coordinates serves all three tiers because it is literally one image. `scripts/overlay_captions.py` captions a single image on its own, for fixing one panel by hand.

Re-Read any composited page before calling it done — text touching a bubble outline means tightening the box or trimming the line.

## Why this shape

The turn/level structure exists so a beginner can track real progress: reread the same story they enjoyed and notice they're ready for more complex language, rather than being handed unrelated stories at each level. Locking one turn count across all three levels means the same beats — and one single set of images — carry every difficulty version, so leveling up never means learning a new plot. The images get close to delivering that literally: MEDIUM and HARD are edits of the EASY image rather than fresh generations, so the same artwork mostly carries forward and only the bubble text changes. An edit can still nudge a pose or a colour, so it's not a guarantee — the local compositing route in step 12 is the only way to close that last gap completely.

Book mode puts the textbook's own dialogue at the *bottom* of the ladder rather than the middle, on purpose: the lines the student is already being taught in class become their entry-level reading, and the generated tiers are growth steps above something they've genuinely mastered. Anchoring the book at medium instead would leave the easy tier as invented filler and give the student nowhere to climb from. Grounding word choice and sentence rhythm in the actual textbook (rather than generic "simple Chinese") keeps stories consistent with what the learner is used to seeing and makes new vocabulary land in a familiar voice.
