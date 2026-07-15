---
name: create-story
description: Generates an A1-A2 Mandarin learning story as a script-style .txt file, written in three parallel difficulty versions (easy/medium/hard) of the SAME plot. Optionally grounds the story in a specific lesson (and dialogue) of the 時代華語 1 / Modern Chinese Book 1 source textbook, e.g. "/create-story 5-2" for Lesson 5, Dialogue 2. Use this whenever the user types /create-story, or asks to write/generate a Chinese practice story, dialogue, or reading passage for beginner (A1/A2, HSK1-2, or "Modern Chinese Book 1" level) learners. Triggers on requests like "make a story about ordering food," "write a beginner dialogue," "create a story from lesson 3," or "create a Traditional Chinese practice text," even if the user doesn't say the words "story" or "script" explicitly — a request for beginner-level Chinese conversation practice content should trigger this skill.
---

# Create Story

Generates a situational Mandarin story for A1-A2 learners, grounded in the style of 時代華語 1 (Modern Chinese Book 1) — see `references/book1-style.md` for the exact conventions (Traditional characters, young casual speakers, sentence patterns, vocabulary annotation format). Read that file before writing if you haven't already this session.

The output is one `.txt` file containing the **same story told three times** — easy, medium, and hard — because the point isn't three different stories, it's the same meaningful situation stretched across a learner's early growth curve. A student should be able to reread a story they liked at a harder level later and recognize it.

## 1. Parse the request

The argument after `/create-story` can be:
- A **lesson reference**: a bare number (`5`) or `lesson-chapter` (`5-2`, meaning Lesson 5, Dialogue 2).
- A **free-text topic** ("ordering coffee").
- **Both** — a lesson reference followed by a topic (`5-2 losing a phone` → ground vocab in Lesson 5 Dialogue 2, but the situation is about losing a phone).
- **Neither** — pick everything yourself.

## 2. Ground in a lesson, if one was given

If a lesson (and optionally chapter) was specified, read `references/lesson-index.md` to find its page range and title, then use `scripts/render_pages.py` to render that range to images and read them:

```
python .claude/skills/create-story/scripts/render_pages.py <start> <end> <scratch-dir>
```

Render into a scratch/temp directory, not the repo. Start with just the first page to confirm the lesson title/badge matches the index (it's been verified against the book's actual divider pages, but a quick check costs nothing) before rendering the rest.

If a chapter/dialogue number was given, scan the rendered pages for the "對話一 Dialogue 1" / "對話二 Dialogue 2" headers and focus on the requested one (see `references/lesson-index.md` for how chapters map to dialogues). Pull from that lesson: the actual dialogue (for tone/situation inspiration, not to copy verbatim), and its vocabulary list (word/pinyin/POS/gloss) as the vocabulary pool the **easy** tier should stay within. Medium/hard can extend beyond it (see step 4) but should still favor this lesson's words where natural.

If no lesson was given, skip this step entirely — no need to open the PDF at all.

## 3. Pick the situation

If a free-text topic was given (alone or alongside a lesson), use it. If a lesson was given without a topic, base the situation on that lesson's actual dialogue/topic (see its title in the index) rather than inventing something unrelated. If neither was given, pick a fresh everyday situation a young person in Taiwan would realistically encounter — ordering food, asking directions, meeting a new roommate, buying a bus ticket, texting a friend to reschedule, returning an item at a shop, small talk at a night market, etc. Before picking, check the `stories/` folder (glob `stories/*.txt`) so you don't repeat a situation that's already there.

Favor situations with real conversational payoff: phrases the learner could actually reuse the same week. Avoid abstract or purely descriptive topics ("the four seasons") — the value here is rehearsing a real exchange, not reading a paragraph.

## 4. Decide the cast

Use **one narrator (monologue)** or **two characters (dialogue)** — whichever fits the situation more naturally. A transaction (ordering, buying, asking a stranger for directions) often reads better as dialogue; a personal recount (what I did this weekend, why I'm late) can work as monologue. Even in a dialogue story, it's fine for the opening and closing turns to be narrator lines that set or close the scene (see the example in step 5). Characters are always young people (students, young workers, roommates, friends) with real-sounding given names, following the book's convention (中明, 宜文, 友美, etc. — invent similar names, don't reuse the exact same pair every time, unless you're deliberately continuing the same cast from the source lesson).

## 5. Build the turn-by-turn scene plot once

Before writing any Chinese, outline the story as a fixed sequence of **4-6 turns**. Lock this count in now — all three difficulty levels below reuse exactly this many turns, because each turn is meant to eventually pair 1:1 with one image.

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

- **Easy (A1 low):** each turn is one short clause, highest-frequency ~150 words, only 是/很/叫/在/有 style patterns and present tense, no connectors. Sentence length matches the Lesson 1 example in the style reference. If a lesson was given, stay within that lesson's vocabulary list.
- **Medium (A1 high / A2 low):** each turn is a slightly longer single line, basic time words (今天/昨天/明天), at most one simple connector where it's natural (可是, 因為...所以...), a bit more vocabulary variety. If a lesson was given, you can pull in a modest number of words from earlier lessons in the index too, not just this one.
- **Hard (A2):** each turn can be one multi-clause line, comparison (比), aspect markers (了/過), more descriptive vocabulary — but still one short, spoken, natural line, not a paragraph. Don't drift into written/literary register or intermediate grammar (把, 被, complex complement structures) — that's past A2.

Write in **Traditional characters**. For each turn, give a short bracketed scene note (who/where/what's visually happening — this doubles as context for the future image) followed by three stacked lines: Chinese, pinyin, English. Label the speaker by name (or "Narrator") for every turn.

## 7. Add a vocabulary list per level

After each level's story text, list the new/level-appropriate words introduced in that version: number, word, pinyin, POS tag, English gloss — matching the book's annotation format. Keep each level's list focused on words that are new *for that level* (easy's list can be a subset of what appears in medium/hard).

## 8. Call out key phrases per level

For each level, pull out **at least 2 reusable phrases or applied grammar patterns** actually used in that level's story text — the takeaways a learner could lift straight into their own speech, distinct from the single-word vocabulary list in step 7. For each one give: the pattern (generalized with a blank where useful, e.g. "X 在哪裡？" or "因為...，所以..."), one example line pulled verbatim from that level's story, and a one-line usage note (when/why you'd reach for it). Draw these from the grammar toolkit each level is already scoped to in step 6 — 是/很/在/叫/有 patterns for easy, time words/connectors for medium, 比/了/過 for hard — rather than inventing patterns the story doesn't actually contain.

## 9. Assemble and save the file

One file, three sections, in this shape:

```
《[Story Title in Chinese]》[English title]
Situation: [one-line description of the real-life context]
[Source: Lesson N – 課名 (Dialogue C) — omit this line entirely if no lesson was specified]

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
...through Turn N (same N as every other level, 4-6 total)...

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

## 10. Generate an image prompt

Read `references/image-prompt-template.md` (the "one prompt, one page, N panels" method) and use it to write **two** AI image-generation prompts, both for **one image containing a grid of panels** — one panel per turn, comic-strip style, reusing the exact turns and scene notes locked in step 5 (don't invent new beats). Pick the grid shape from the turn count (2×2 for 4 turns, 2×3 for 5-6 turns — see the reference file). Write the cast/style/layout once at the top of each prompt, then one "Panel N:" line per turn expanding that turn's bracketed scene note into a full visual description, listing only the characters who actually appear in that panel and deliberately varying pose, shot framing, and camera angle panel to panel so they don't all look like the same picture — see the "Vary composition" rule in the reference file.

Write both modes into the same file, text-free first:

1. **Text-free** — no words anywhere in the image, safest since image models often garble Chinese text.
2. **Speech bubbles** — every panel gets somewhere to put its line, not just the speaking ones: a panel with a speaking character gets a bubble pointing at them, a narrator-only panel gets a rectangular caption box instead (no tail, along the bottom edge) — and this time **the real Chinese line is written directly into the prompt** for that bubble/box, so pasting the prompt into an image generator produces a finished page in one shot. Quote it exactly (Chinese only, no pinyin/English inside the bubble), default to the **medium** tier verbatim, but check the line actually matches that panel's visual scene note first — if a panel's note was drawn from a different tier's phrasing (turns can drift in wording between tiers), quote whichever tier's line actually matches what's depicted, so the bubble never describes something the panel doesn't show. Because AI image models render Chinese text inconsistently, add a caution note right above the prompt (proofread every bubble/box after generating; fall back to the text-free version + step 11's overlay scripts if a line comes out garbled) and append a consolidated **Caption Script** after the full prompt (Chinese/pinyin/English per panel, narrator panels included) as a proofreading reference.

Save this as `stories/<same-slug>-images.txt`, alongside the story file, with both prompts (and the speech-bubble version's Caption Script) clearly labeled and separated (see the file shape in `references/image-prompt-template.md`) so the user can copy whichever one they want to paste into an image generator without regenerating anything.

## 11. Optional: fill in the bubbles on a generated image

If a speech-bubble generation comes back with garbled or missing text (or the user generated from the text-free version and wants captions added after the fact), the Chinese can be placed in by hand with the two helper scripts in `scripts/`:

1. `python scripts/grid_panels.py IMAGE_PATH ROWS COLS OUT_DIR` — crops the image into its panels and saves a gridded, upscaled version of each (`panelN_grid.png`) with pixel-coordinate gridlines. Read a few of these (via the Read tool, they're images) to eyeball each bubble's safe interior box — comfortably inside the drawn outline, since the auto-fit still needs margin.
2. Write a small JSON config mapping panel number → `{"box": [left, top, right, bottom], "text": "..."}` (local coordinates within that panel, from step 1) — one entry per speaking panel, using the Caption Script's Chinese text (trim long lines slightly if a bubble is small; the full grammar/vocabulary point still lives in the story file, this is just the in-image caption).
3. `python scripts/overlay_captions.py IMAGE_PATH CONFIG_JSON OUT_PATH` — auto-shrinks and centers each caption to fit its box, saves the composed image.

Check the output (Read the saved PNG) before calling it done — text that touches or crosses a bubble's outline means the box needs tightening or the line needs trimming; iterate rather than accepting an overflowing result.

## Why this shape

The turn/level structure exists so a beginner can track real progress: reread the same story they enjoyed and notice they're ready for more complex language, rather than being handed unrelated stories at each level. Locking the turn count (4-6) across all three levels means the same beats — and eventually the same images — carry every difficulty version, so leveling up never means learning a new plot. Grounding word choice and sentence rhythm in the actual textbook (rather than generic "simple Chinese") keeps stories consistent with what the learner is used to seeing and makes new vocabulary land in a familiar voice.
