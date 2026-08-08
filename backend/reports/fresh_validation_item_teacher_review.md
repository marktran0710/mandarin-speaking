# Fresh validation — item review for teacher sign-off

**Automated dictionary checking does not replace expert review.** Every item
below passed a mechanical MoE single-reading check, which only establishes that
the dictionary lists one reading. It says nothing about whether the item is
appropriate for CFL learners, natural in isolation, or unambiguous as presented.

**No item is recommended KEEP on automated grounds alone.** All 16 are marked
TEACHER REVIEW REQUIRED. Sign-off sheet:
`data/fresh_validation_item_teacher_review_TEMPLATE.csv`.

| item | char | expected pinyin | tone | MoE evidence | possible alternative reading | isolated-prompt safety | learner suitability note | recommendation |
|---|---|---|---|---|---|---|---|---|
| I01 | 貓 | māo | T1 | māo only in MoE | — | SAFE AS ISOLATED CHARACTER | free noun, high frequency | TEACHER REVIEW REQUIRED |
| I02 | 高 | gāo | T1 | gāo only | also a surname, same reading | SAFE AS ISOLATED CHARACTER | free adjective | TEACHER REVIEW REQUIRED |
| I03 | 天 | tiān | T1 | tiān only | — | SAFE AS ISOLATED CHARACTER | free noun (day/sky) | TEACHER REVIEW REQUIRED |
| I04 | 花 | huā | T1 | huā only | verb 'to spend' shares the reading | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I05 | 人 | rén | T2 | rén only | — | SAFE AS ISOLATED CHARACTER | very high frequency | TEACHER REVIEW REQUIRED |
| I06 | 門 | mén | T2 | mén only | — | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I07 | 茶 | chá | T2 | chá only | — | SAFE AS ISOLATED CHARACTER | free noun, beginner vocabulary | TEACHER REVIEW REQUIRED |
| I08 | 魚 | yú | T2 | yú only | — | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I09 | 狗 | gǒu | T3 | gǒu only | — | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I10 | 水 | shuǐ | T3 | shuǐ only | — | SAFE AS ISOLATED CHARACTER | very high frequency | TEACHER REVIEW REQUIRED |
| I11 | 馬 | mǎ | T3 | mǎ only | also a surname, same reading | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I12 | 筆 | bǐ | T3 | bǐ only | — | SAFE AS ISOLATED CHARACTER | free noun, usually counted (一枝筆) | TEACHER REVIEW REQUIRED |
| I13 | 飯 | fàn | T4 | fàn only | — | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I14 | 話 | huà | T4 | huà only | — | CONTEXT RECOMMENDED | largely bound: 說話 / 電話 | TEACHER REVIEW REQUIRED |
| I15 | 菜 | cài | T4 | cài only | — | SAFE AS ISOLATED CHARACTER | free noun | TEACHER REVIEW REQUIRED |
| I16 | 電 | diàn | T4 | diàn only | — | CONTEXT RECOMMENDED | bound morpheme: 電話 / 電腦 / 電視 | TEACHER REVIEW REQUIRED |

## What the automated check did and did not do

It queried the Taiwan MoE dictionary (moedict.tw) and kept only characters with
a **single reading**, reading the tone from the bopomofo. That check rejected
several otherwise attractive CFL items — 錢 (jiǎn/qián), 雨 (yǔ/yù), 頭, 來, 紅,
女 — because a polyphonic target would make "the expected tone" undefined.

It did **not** assess frequency for CFL learners, naturalness in isolation,
regional preference in Taiwan Mandarin, or whether a learner at the target level
would recognise the character.

## Items flagged for prompt context

Two items are marked **CONTEXT RECOMMENDED**, not because the reading is
ambiguous but because the character is largely **bound** and may be unnatural to
produce alone:

- **話 huà** — normally appears in 說話 / 電話. Asking a learner to say 話 in
  isolation may produce hesitation or a citation-style reading unlike natural
  speech.
- **電 diàn** — a bound morpheme in modern usage (電話 / 電腦 / 電視). Saying 電
  alone is unusual.

If the teacher agrees, the recommended fix is a **fixed disyllabic word whose
target syllable is the intended one**, with the analysis window on that syllable
— for example 電話 with 電 as target. That preserves one known expected tone
while making the prompt natural. **The item manifest was not changed
automatically**; any substitution must be recorded on the sign-off sheet and the
frozen manifest reissued before recruitment.

## A separate issue the teacher should rule on: T3 citation form

Four items are T3. In isolation the citation form is the full dipping tone, but
many speakers produce a low-falling "half-third" variant, and both are commonly
accepted. Because the study's criterion is *acceptability*, raters need to know
whether a half-third counts as acceptable. **This should be settled in the rater
instructions before rating begins**, not left to individual raters, or T3
disagreement will inflate for reasons unrelated to the system.

## Gate

No participant recruitment may begin until all 16 rows carry
`teacher_decision = APPROVE`. Any REPLACE requires a new MoE verification of the
substitute and a reissued item manifest.
