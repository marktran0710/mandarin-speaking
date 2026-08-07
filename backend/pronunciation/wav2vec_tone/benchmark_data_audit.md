# Benchmark data audit — which corpora can support a valid tone-error benchmark

Audited 2026-08-07. No corpus was downloaded for this audit; OMPAL was
inspected from the copy already in this repository at
`backend/private-data/ompal/`, everything else from public documentation.

## Why this audit exists

The 879-sample AISHELL-derived set is a development dataset only. A predictor
using **only `syllable_base` and no audio at all** scores 86.1% on it, against
57.8% for wav2vec2 and 59.0% for feature fusion (`syllable_diagnostic.py`,
commit `ad1d006`). 82.1% of its syllable bases occur with exactly one tone, so
the label is nearly a function of the word.

The decisive distinction for what follows:

- **Expected tone** — the tone the word is supposed to carry. Derivable from
  text plus a dictionary. Every corpus here can supply it.
- **Produced tone** — the tone the speaker actually made. Requires a human to
  listen and transcribe.
- **Tone correctness** — did produced match expected. Requires a human
  judgement, and is the label our application actually needs.

A corpus of native read speech gives expected tone and nothing else, so it
cannot measure error detection: every sample is correct by construction.

## 1. Corpus comparison table

| | **OMPAL** | **iCALL** | **LATIC** | **Sinica TMC / ILAS** | **NER-TRS / Formosa FSW** |
|---|---|---|---|---|---|
| Downloadable audio | **Yes** — 1,850 wav verified locally | **No** — "Open-source: No" | Yes — IEEE DataPort, login | Via ACLCLP academic licence | Partly; FSR challenge registration |
| speaker_id | Yes — 49 dirs, `SPEAKER01*` native / `SPEAKER02*` learner | Yes (305) | Yes (4) | Yes (170) | Yes |
| Native vs learner | **Both** — 3 native, 46 learner | Learner + ref | Learner only | Native only | Native only |
| Speaker L1 | **Yes** — French, all 46 | Yes — 24 languages | Yes — Russian, Korean, French, Arabic | n/a native | n/a native |
| Word/syllable transcript | Yes — per-word `text`, 19,766 of 19,775 are single characters | Yes | Yes | Yes (orthographic) | Yes |
| Pinyin | **No** | Yes (described) | Yes — `dict.txt`, 1,423 pinyin | Only MCDC8 subset manual | No |
| Expected lexical tone | **Derivable only** — no tone field; needs character→pinyin | Yes (described) | Yes | Derivable | Derivable |
| **Actual produced tone** | **No** | Described in publications | **Apparently yes** — "closest" transcript | No | No |
| **Tone correctness label** | **Yes** — binary per word, 19,775 annotations | Yes (described) | Unclear | **No** | **No** |
| Tone-confusion label (T3→T2) | **No** | Possibly | Possibly, via produced transcript | No | No |
| Word/syllable timestamps | **No** | Not stated | Not stated | MCDC8 signal-aligned IPU + word bounds; Phonological Development Corpus has verified syllable boundaries | No |
| Pronunciation score | Yes — sentence accuracy/fluency/prosody 1–5 | Fluency scores | Yes | No | No |
| Human raters | Yes | Yes | 2 experts | n/a | n/a |
| Number of raters | **3 per utterance, drawn from a panel of 4** | Not stated | 2 | n/a | n/a |
| Taiwan vs Mainland | **Taiwan** (see §2) | Singapore (I2R) | Not stated; presumed Mainland | **Taiwan** | **Taiwan** |
| Traditional vs Simplified | **Traditional** — 0 simplified chars found | Not stated | Not stated | Traditional | Traditional |
| Licence | **CC BY 4.0**, commercial use permitted | Not public | "Open Access", terms unverified | ACLCLP academic licence | Non-commercial (TAT-Vol1) |
| Access | Already in repo | Contact authors; no public route found | IEEE DataPort login | Application to ACLCLP | Challenge registration |
| **Class** | **B** | **D** (reclassify to B if access granted) | **C** | **C** | **C** |

Class key: A = direct tone-error benchmark as-is · B = suitable after
additional annotation/alignment · C = general pronunciation validation only ·
D = not suitable.

**No corpus qualifies as Class A.** None ships expected tone, produced tone
and syllable boundaries together.

## 2. OMPAL — inspected directly, not from the paper

Files inspected: `README.md`, `LICENSE`, `native_scores.json`,
`non-native_scores.json`, `non-native_scores-detail.json`, `wav/`, plus the
Interspeech 2025 PDF.

**Measured from the files:**

- 1,768 non-native + 82 native utterances; 1,850 wav files across 49 speakers.
- **19,775 word-level tone annotations**, each with exactly 3 rater values.
- Label values are only `"0"` and `"1"` — 51,281 ones, 8,044 zeros across all
  raters. **2,567 words (13.0%) judged tone-incorrect by majority.**
- **19,766 of 19,775 "words" are a single character**, so word-level is
  effectively syllable-level. This is the key structural fact: OMPAL's tone
  annotations already sit at the granularity we need.
- Only 84 unique sentences (82 for native), i.e. a small script inventory.
- Per-utterance keys: `accuracy`, `fluency`, `prosody`, `text`, `words`.
  Per-word keys: `phoneme_consonant`, `phoneme_vowel`, `tone`, `text`.
  **There is no pinyin field, no tone-number field, and no timestamp field.**
- Script: Traditional throughout — 們, 沒, 麼, 這, 說, 個, 學, 國, 時, 來, 對,
  開, 會, 後, 點 all present; **zero simplified characters found**.
- `LICENSE` is Creative Commons Attribution 4.0 International.

**Two corrections to the documentation, both verified:**

1. The README says "annotated by **four** experts". The data has 3 values per
   item. The paper resolves it: *"Each utterance is evaluated by three out of
   four experts."* So the panel is 4, the panel size per utterance is 3 — which
   matches this project's existing `RATER_PANEL_SIZE = 3`. It also means rater
   position is **not** a stable identity across utterances, so per-rater
   agreement cannot be attributed to a named individual (Fleiss, not per-pair
   Cohen).
2. Neither README nor GitHub page states the Mandarin variety. The paper's
   affiliations settle it: *"Graduate Institute of Communication Engineering,
   National Taiwan University, Taiwan"*, *"Graduate Program of Teaching Chinese
   as a Second Language, National Taiwan University, Taiwan"*, *"Department of
   Communication Engineering, National Taipei University, Taiwan"*. Combined
   with exclusively Traditional transcripts and NTU-based CSL instructors as
   raters, **OMPAL is Taiwan Mandarin (國語)**.

### Answers to the specific questions

- **Can we identify tone errors at word/syllable level?** **Yes.** 19,775
  annotations, effectively one per syllable, 3 raters each.
- **Can we know expected tone?** **Not directly.** No tone or pinyin field. It
  must be derived from the Traditional characters via a dictionary — and per
  `schema.py`, for a Taiwan target that must be the MoE dictionary, not a
  Mainland lexicon.
- **Can we know the produced/diagnosed tone?** **No.** The label is binary
  correct/incorrect. When a learner mispronounces T3, nothing records whether
  they produced T2, T1 or something between. **No tone-confusion analysis is
  possible with OMPAL as published.**
- **Are audio and annotations downloadable?** **Yes**, CC BY 4.0, commercial
  use permitted. Already present in this repo.
- **Can it be mapped safely to Taiwan pronunciation targets?** **Yes, and it is
  the only audited learner corpus for which this is true.** Traditional script
  and Taiwan-based raters mean the annotations already encode Taiwan
  judgements. The expected-tone lookup must still go through the MoE
  dictionary, and `schema.assert_label_usable` will enforce
  `pinyin_source="moe_dict"`.

**Why OMPAL escapes the syllable confound:** its label is *correctness*, not
*identity*. Knowing the word is 忙 tells you the expected tone is T2 but says
nothing about whether this learner produced it. A lexical lookup cannot score
above the 87% base rate of "correct", and would have zero recall on the 13%
that matter.

## 3. iCALL — annotations are described, not distributed

The OMPAL paper's Table 1 lists iCALL as **Open-source: No**. Developed at the
Institute for Infocomm Research, Singapore; 90,841 utterances, 305 speakers,
142 hours, 24 L1s. Literature states the corpus carries phonetic, tonal and
fluency annotation, and that lexical tone errors outnumber phonetic errors by
more than six to one — a useful finding, but a claim about data we cannot
obtain.

**No public download route was found.** The ISCA page documents no licence,
download URL or request procedure. **The exact tonal annotation format could
not be established from any accessible source**, so it cannot be documented
here as requested — that itself is the finding. Access would require
contacting I2R directly.

Also relevant: I2R is Singapore, and Singapore Mandarin follows the Mainland
standard with local lexical variation. Even with access it would need the same
variety scrutiny as any non-Taiwan source.

## 4. LATIC — produced transcription, but only 4 speakers

IEEE DataPort, open access with login. 2,579 samples, ~4 hours, 4 speakers
(2M/2F, 19–30), L1 Russian/Korean/French/Arabic, 2 expert annotators.
Annotators recorded the **"closest" transcript**, which implies transcription
of what was actually produced rather than only the target — the one audited
corpus that may supply **produced tone** and therefore tone-confusion pairs.

Disqualifying for benchmarking: **4 speakers cannot support speaker-disjoint
cross-validation.** Every fold would hold out 25% of the speaker population,
and no result would generalise. Variety and script are unstated; presumed
Mainland. Useful as a pilot for confusion-pair annotation format, not as a
benchmark.

## 5. Taiwan resources — native only, no learner errors

**Sinica / ILAS** (`tmc.ling.sinica.edu.tw`): TMC Corpus 43 h, 170 speakers,
Traditional orthographic transcription; only the MCDC8 subset has manual
pinyin and POS, the rest is automatically processed. Also a Sociophonetic
Corpus (1,402 speakers), a Child Speech Corpus, and a **Phonological
Development Corpus** — the last processed with the ILAS phone aligner with
**manually verified syllable boundaries**, plus pinyin and IPA. Access via
ACLCLP academic licence.

**NER-TRS / Formosa FSW**: ~300 h Taiwan Mandarin from National Education
Radio; TAT-Vol1 free for non-commercial use. Note TAT is Taiwanese Hokkien,
not Mandarin — do not conflate them.

**All are native speech.** Per the brief's own warning, this is exactly the
case where a Taiwan-native corpus must not be assumed suitable: it establishes
what correct Taiwan tones sound like, and contains no errors to detect. Class C
for that reason alone, not because of any quality issue.

**MoE 重編國語辭典修訂本** — not a corpus, but the authoritative Taiwan
pronunciation source needed for expected-tone lookup. Downloadable from
`language.moe.gov.tw`. **Licence is CC BY-ND 3.0 Taiwan — No Derivatives**,
and the ministry explicitly does not authorise API interfaces or page parsing.
The ND clause is a genuine constraint on redistributing a derived
pronunciation table and needs checking before any such table ships.
`g0v/moedict-data` mirrors the data in other formats under separate terms.

## 6. Missing information and access barriers

1. **iCALL annotation format is undocumented publicly** — the single biggest
   gap. It is the only large corpus that may already have tone-confusion labels.
2. **OMPAL has no syllable timestamps.** Forced alignment must be run and its
   accuracy validated; this project has already found alignment quality to be a
   real risk (anchored boundaries scored *worse* than guessed ones, AUC 0.527
   vs 0.570, in earlier work).
3. **OMPAL has no produced tone.** No amount of alignment recovers it — it
   requires new listening annotation.
4. **MoE dictionary ND licence** unresolved for derived redistribution.
5. **LATIC terms unverified** behind the IEEE DataPort login.
6. **Sinica/ACLCLP licence terms and cost** not established; requires
   application.
7. **No Taiwan-native L2 learner corpus was found at all.** Learner corpora are
   French-in-Taiwan (OMPAL), Singapore (iCALL), or mixed-L1 Mainland (LATIC).

## 7. Recommendations

**Native tone reference:** Sinica Phonological Development Corpus for
syllable-aligned Taiwan pinyin/IPA; NER-TRS for volume. Both need ACLCLP
application. Neither is required to start.

**L2 tone-error validation:** OMPAL. It is the only accessible corpus with
per-syllable tone-correctness judgements from multiple raters.

**Taiwan Mandarin adaptation:** OMPAL again — Taiwan-rated and Traditional —
with the MoE dictionary for expected-tone lookup.

---

**Best immediate dataset:** OMPAL.

**Reason:** It is the only audited corpus that is downloadable, permissively
licensed (CC BY 4.0, commercial use allowed), carries per-syllable tone
correctness from 3 raters, and is Taiwan Mandarin in Traditional script. It is
already in this repository. Critically, its label is correctness rather than
identity, so the syllable confound that invalidates the AISHELL set does not
apply.

**Best Taiwan-native dataset:** Sinica Phonological Development Corpus
(ILAS/ACLCLP).

**Reason:** The only audited Taiwan-native resource with manually verified
syllable boundaries plus pinyin and IPA — the alignment reference OMPAL lacks.
Caveat: it is child speech, so its F0 range will not transfer directly to adult
learners.

**Best L2 error-annotated dataset:** OMPAL, for binary tone correctness.
For tone *confusion* pairs, none is currently available; LATIC is the only
candidate and it has 4 speakers.

**Can we build a valid tone-error benchmark without collecting new data?**
**Partially.**

Yes for the question the application actually asks — *did this learner produce
the target tone correctly?* OMPAL supports that today: 19,775 syllable
judgements, 13.0% errors, 46 learners, speaker-disjoint splits, Taiwan targets.

No for tone *diagnosis* — *which wrong tone did they produce?* No accessible
corpus labels produced tone at usable scale. That needs either new annotation
over existing OMPAL audio (listening only, no new recording) or iCALL access.

Also no for Taiwan-native *learner* speech: OMPAL's learners are French L1
recorded on a French curriculum. Fine for Taiwan tone targets, not
representative of the app's Vietnamese and other-L1 users.

**Next recommended action:**

Re-target evaluation onto OMPAL as the primary benchmark and demote the
AISHELL 879 to a development set, then build the expected-tone layer:
character → MoE pinyin → expected tone, stored with
`pinyin_source="moe_dict"` so `schema.assert_label_usable` passes. That
converts OMPAL from Class B to usable without any new recording, and reuses the
existing `benchmarking/ompal_*` code path.

Defer forced alignment until after that lookup exists — expected tone is
needed to evaluate alignment quality, so doing it in the other order provides
nothing to check against.
