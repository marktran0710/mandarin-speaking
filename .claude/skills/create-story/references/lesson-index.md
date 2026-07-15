# 時代華語 1 (Modern Chinese 1) — lesson index

Source file: `D:\hautran\Chinese\book refer\時代華語 1 課程.pdf` (322-page scanned PDF, no text layer — pages must be rendered as images to read, see `scripts/render_pages.py`).

Every boundary below was confirmed by directly rendering and reading that lesson's title/divider page (each lesson opens with a page showing a large "Lesson 第N課" circle badge plus the lesson title, combined with the start of Dialogue 1 on the same page). This table went through two corrections before landing here — the first pass (thumbnail sampling) had several pages wrong because a divider's tall circle graphic visually bled into the neighboring grid cell when pages were cropped to just their header strip. If you ever need to re-derive or double check a boundary, render the **full page, uncropped**, and look for the circle — don't rely on a cropped header strip.

The book has **15 lessons**.

| # | Title (Chinese) | Title (English) | Page range |
|---|---|---|---|
| 1 | 新同學 | The New Classmate | 1–22 |
| 2 | 你幾點去學校？ | What Time Do You Go to School? | 23–36 |
| 3 | 買生日禮物 | Buying Birthday Gifts | 37–58 |
| 4 | 你要咖啡還是茶？ | Would You Like to Have Coffee or Tea? | 59–79 |
| 5 | 我的錢包在哪裡？ | Where Is My Wallet? | 80–98 |
| 6 | 週末去打網球吧！ | Let's Play Tennis This Weekend! | 99–124 |
| 7 | 怎麼到飯店去？ | How Do We Get to the Hotel? | 125–147 |
| 8 | 這條裙子真好看 | This Skirt is Very Beautiful | 148–169 |
| 9 | 我的中文課 | My Chinese Class | 170–189 |
| 10 | 最近感冒的人很多 | Many People Got Colds Recently | 190–209 |
| 11 | 你們是怎麼認識的？ | How Did You Meet Each Other? | 210–234 |
| 12 | 你想做什麼工作？ | What Job Do You Want to Do? | 235–257 |
| 13 | 用手機上網 | Get on the Internet with a Cell Phone | 258–280 |
| 14 | 跨年活動 | New Year's Eve Celebration | 281–310 |
| 15 | 十二生肖 | The Chinese Animal Zodiac | 311–322 |

Each lesson generally contains, in this order: a title/divider page (with Dialogue 1 starting on the same page), a Simplified-characters/Pinyin/English companion spread for that dialogue, a vocabulary list (生詞, numbered word/pinyin/POS/gloss/example), Dialogue 2 (對話二) partway through, more vocabulary, grammar notes (語法), and exercises. The source text lives in the two dialogues and their vocabulary lists — skip exercises/grammar-drill pages when extracting story material.

## Referencing a specific dialogue ("chapter")

A lesson number alone (e.g. `5`) means "use this lesson generally." A lesson-chapter pair (e.g. `5-2`) means "use dialogue 2 specifically" — 對話一 = chapter 1, 對話二 = chapter 2.

This index does not pre-map dialogue-level page numbers (that would mean scanning every page of every lesson up front for a fairly small benefit). Instead, resolve a chapter reference on demand: render the full page range for that lesson (it's only 20-25 pages), scan the rendered images for the "對話一 Dialogue 1" / "對話二 Dialogue 2" section headers, and read from the requested one until the next section header (usually a vocabulary list) begins.
