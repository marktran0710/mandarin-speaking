# Learning Engine

What production actually runs for personalization, retention, and voice
feedback - the algorithms, their runtime parameters, and calibration
status. The admin **Learning Engine** page (`GET /api/admin/learning-engine`,
`services/learning_engine_service.py`) renders this same information live
from the modules listed below, so this document and that page can never
drift apart - if you change a threshold, both update automatically.

Provenance tags used throughout:

| Tag | Meaning |
|---|---|
| `STANDARD_ALGORITHM` | Textbook algorithm, unmodified |
| `MODIFIED_STANDARD_ALGORITHM` | A named algorithm with a documented project adaptation |
| `PUBLISHED_METHOD` | A published technique (not necessarily an academic "algorithm") |
| `PROJECT_HEURISTIC` | Project-specific logic with no external validation |
| `ENGINEERING_DEFAULT` | A runtime constant chosen for launch, not calibrated |

**Do not upgrade a tag without new evidence.** A runtime value being
"reasonable" or "working in practice" is not calibration. Source comments
throughout this code explicitly say so - see quotes below.

---

## 1. Personalized learning - Bayesian Knowledge Tracing

`analytics/bkt.py`. Provenance: `STANDARD_ALGORITHM` (the equations);
parameter values are `ENGINEERING_DEFAULT`.

**Purpose**: estimate per-word mastery from binary correct/incorrect
responses; rank weak words for personalized practice.

**Equations** (`analytics/bkt.py:136-164`, `update_bkt`):

```
P(L|correct)   = L(1-S) / [L(1-S) + (1-L)G]
P(L|incorrect) = LS / [LS + (1-L)(1-G)]
P(L_next)      = P(L|obs) + [1 - P(L|obs)] * T
```

**Runtime defaults** (`BktConfig`, `analytics/bkt.py:37-53`):

| Parameter | Value |
|---|---|
| `P(L0)` initial mastery | 0.20 |
| `P(T)` learning transition | 0.15 |
| `P(G)` guess, MCQ | 0.20 |
| `P(S)` slip, MCQ | 0.10 |
| `P(G)` guess, typed/free-text | 0.05 |
| `P(S)` slip, typed/free-text | 0.15 |
| Mastery threshold | 0.95 |
| Minimum observations | 3 |
| Required diagnostic rounds | 3 |
| Review count | 5 |

Format-aware guess/slip (`guess_slip_for()`, `analytics/bkt.py:116-124`):
typed free-text answers use the typed pair; everything else uses the MCQ
pair. A single global pair previously under-rewarded correct typed answers
and over-punished typos.

**Status, verbatim from source** (`analytics/bkt.py:1-6, 78-79`):
> "The defaults are engineering defaults for the first research version,
> not validated or calibrated cutoffs." ... "TODO: replace with
> pilot-calibrated/frozen BKT parameters before the main experiment. These
> transparent temporary defaults are not research-validated."

**Pipeline**: client response -> server resolves the authoritative
assessment answer (`analytics/bkt_assessment_resolver.py` - never trusts a
client-sent correct/incorrect boolean alone) -> BKT posterior update ->
learning transition -> mastery status (`UNASSESSED` / `DEVELOPING` /
`NEEDS_PRACTICE` / `STRONG`, `analytics/bkt.py:190-203`) -> weak-word
ranking (`analytics/weak_words.py`) for personalized practice.

**Reference**: Corbett, A. T., & Anderson, J. R. (1995). Knowledge
tracing: Modeling the acquisition of procedural knowledge. *User Modeling
and User-Adapted Interaction*, 4, 253-278. DOI: 10.1007/BF01099821. The
equations follow standard BKT; the parameter values above are this
project's own configuration, not values the paper recommends.

---

## 2. Retention - Modified SM-2

`analytics/srs.py`. Provenance: `MODIFIED_STANDARD_ALGORITHM`.

**Purpose**: schedule future review of vocabulary that has already reached
a `STRONG` BKT state - a separate concern from BKT mastery itself.
`analytics/srs.py` never touches `p_learned`; a review's correctness still
flows into BKT unchanged.

**Input mapping** (`quality_from_response()`, `analytics/srs.py:49-60`):
the UI grades binary correct/incorrect, mapped to the SM-2 0-5 quality
scale as `q=4` (correct) / `q=2` (incorrect) - a project adaptation of
SM-2's self-rating scale, not published SM-2 behavior.

**Ease update** (`_updated_ease()`, `analytics/srs.py:63-65`):

```
EF' = EF + [0.1 - (5-q) * (0.08 + (5-q) * 0.02)]
EF' = max(EF', 1.3)
```

**Interval sequence** (`review()`, `analytics/srs.py:68-97`): first
success -> 1 day; second success -> 6 days; thereafter
`round(previous_interval * ease)`. Any failure (`q < PASS_QUALITY=3`)
resets repetitions to 0 and the interval to 1 day.

**Runtime constants**: `INITIAL_EASE = 2.5`, `MIN_EASE = 1.3`,
`FIRST_INTERVAL_DAYS = 1`, `SECOND_INTERVAL_DAYS = 6`,
`DAY_SECONDS = 86400.0` (overridable via a dev-only env var to compress a
"day" for live testing - never in production; see
`routers/vocab_quiz_attempts.py`'s `_effective_srs_day_seconds`).

**Idempotency**: `should_advance()` (`analytics/srs.py:100-109`) requires a
full `day_seconds` to have elapsed since the last graded review before a
new answer can advance the schedule - repeated practice within one cycle
doesn't keep pushing the due date out.

**Conceptual separation**: BKT asks "how well is this word currently
learned?"; SRS asks "when should this word be reviewed again?" A word can
be BKT-weak, SRS-due, both, or neither. The review queue
(`analytics/review_queue.py`) tags each entry `weak` or `due` rather than
merging the two - a mastered-but-due word is never shown as weak merely
because it needs a maintenance review.

**Reference**: Wozniak, P. A. (1990). *Optimization of learning.*
SuperMemo / SM-2 family. This project's binary-response scheduler is a
modified SM-2 implementation - not the original algorithm unchanged.

---

## 3. Voice feedback pipeline

```
Audio upload
  -> Recording quality control (duration / loudness / speech presence / clipping / format)
  -> ASR transcription
  -> Praat/Parselmouth acoustic (pitch contour) extraction
  -> Deterministic shape + directional tone scoring
  -> Feedback-quality gate (poor evidence -> UNCERTAIN/INVALID_AUDIO, never a confident bad score)
  -> AI/local coaching feedback
  -> Pronunciation mastery + sentence-level verdict
  -> Speaking-progress persistence
```

Code: `domain/speech/tone_decision.py`, `domain/speech/tones/`,
`domain/speech/acoustics/`, `services/pronunciation_scoring.py`,
`services/content_verification.py`, `services/speech/asr/`,
`services/speech/feedback/pipeline.py`.

### 3.1 Acoustic analysis

**Technology**: Praat via `python-parselmouth`
(`domain/speech/acoustics/audio_features.py`). Provenance:
`PUBLISHED_METHOD`.

Pitch extraction: `sound.to_pitch(time_step=0.010, pitch_floor=75,
pitch_ceiling=500)` - Praat's standard autocorrelation-based pitch
tracker. The 10ms step (rather than Praat's own convention) was chosen
after finding a coarser step gave too few voiced frames per syllable to
resolve tone contours. Formants: `sound.to_formant_burg(...)` - Praat's
Burg-method formant tracker. A project-specific `_correct_octave_jumps()`
post-processing heuristic fixes 2x/0.5x pitch-tracker errors on top of
Praat's raw output.

**Reference**: Boersma, P. (1993). Accurate short-term analysis of the
fundamental frequency and the harmonics-to-noise ratio of a sampled sound.
*Proceedings of the Institute of Phonetic Sciences*, 17, 97-110. This
supports the acoustic pitch-extraction technique only - the tone
shape/direction scoring formulas built on top of the extracted contour
(below) are project-specific and are **not** defined by this paper.

### 3.2 Tone scoring formulas

Provenance: `PROJECT_HEURISTIC` throughout this section.

**Shape similarity** (`_shape_match_score()`,
`domain/speech/tones/reference_contours.py:121-159`):

```
correlation_score = (correlation + 1.0) / 2.0
distance_score     = max(0, 1 - distance / sqrt(N))
accuracy            = (correlation_score * 0.65 + distance_score * 0.35) * 100
```

`distance` is the Euclidean distance between the two **mean-centered**
curves (so absolute pitch level isn't penalized, only shape); dividing by
`sqrt(N)` rather than `N` is deliberate - a past bug used `N` and made the
distance term nearly inert.

**Tone 1 / flat-reference special case**: when the reference has near-zero
variance (Tone 1, or an all-neutral phrase), Pearson correlation is
undefined, so the code scores the *user's own* contour flatness instead:
`flatness = max(0, 1 - user_variance / 0.015) * 100`.

**Directional scoring** (`_score_segment()`,
`domain/speech/tones/scoring.py:180-227`; curves are median-filtered
first, kernel=5): segment split into quarters, `s_mean`/`e_mean` = first/
last quarter means, `mid_min` = min of the middle 50%, `variance` = whole-
segment variance.

| Tone | Formula |
|---|---|
| 1 (flat) | `max(0, 1 - variance/0.12) * 100` |
| 2 (rising) | `rise = e_mean - s_mean`; `clamp01((rise+0.5)/1.0) * 100` |
| 3 (dip) | `dip = (s_mean+e_mean)/2 - mid_min`; `clamp01((dip+0.25)/0.55) * 100` |
| 4 (falling) | `fall = s_mean - e_mean`; `clamp01((fall+0.5)/1.0) * 100` |
| 5 (neutral) | not measured; flat constant `75.0` |
| segment < 4 frames | not measured; flat constant `65.0` |

The two flat-constant cases carry a `"not measured"` provenance tag
internally and sit above the legacy pass bar (58.0) by design, so an
unmeasurable syllable doesn't get penalized for being unmeasurable.

**Tone sandhi**: only third-tone sandhi (T3+T3 -> T2+T3) is implemented
(`apply_tone_sandhi()`, `reference_contours.py:277-287`) - the one pattern
common enough in short student phrases to be worth correcting for; other
sandhi (e.g. 一/不) is explicitly out of scope.

### 3.3 Three separate weighted combinations - do not confuse them

1. **Legacy pass-path composite** (`calculate_phrase_tone_accuracy`,
   `domain/speech/tones/scoring.py:324-375`): `PHRASE_SHAPE_WEIGHT = 0.50`,
   `PHRASE_DIRECTIONAL_WEIGHT = 0.50`. This score does feed the legacy
   per-word pass path (see 3.4).
2. **Display-only composite** (`domain/speech/tone_decision.py:134-135`):
   `DISPLAY_SHAPE_WEIGHT = 0.70`, `DISPLAY_DIRECTION_WEIGHT = 0.30`.
   Explicitly commented as not a verdict input - shown only so a learner's
   progress history has one number.
3. **The actual diagnostic verdict is not a blend at all.**
   `decide_word_tone()` (`domain/speech/tone_decision.py:340-423`) is
   rule/branch logic over `shape_score` and `direction_score` as separate
   signals (shape is primary evidence, direction is a consistency check).

### 3.4 What actually gates lesson progression

**This is the single most important distinction on this page.** The
diagnostic states (`CORRECT`/`UNCERTAIN`/`INCORRECT`/`INVALID_AUDIO`) are
shown to students as feedback but explicitly do **not** drive progression -
verbatim from `domain/speech/tone_decision.py:1-34`:

> "None of these states drive lesson progression. Progression still runs
> on the legacy `score >= SYLLABLE_PASS_THRESHOLD` path, unchanged."

| Threshold | Value | Gates progression? | Purpose |
|---|---|---|---|
| `SYLLABLE_PASS_THRESHOLD` | 58.0 | **Yes - the only one that does** | Legacy per-syllable pass bar |
| `SENTENCE_SYLLABLE_PASS_RATIO` | 0.80 | Yes | Fraction of judged syllables that must pass for a sentence to pass |
| `PHRASE_SHAPE_WEIGHT` / `PHRASE_DIRECTIONAL_WEIGHT` | 0.50 / 0.50 | Yes (feeds the score `SYLLABLE_PASS_THRESHOLD` gates) | Legacy composite |
| `TONE_CONFIRM_THRESHOLD` | 50.0 | No - diagnostic only | Score at/above which a tone is confirmed CORRECT |
| `TONE_ERROR_THRESHOLD` | 45.0 | No - diagnostic only | Score at/below which a tone is confirmed INCORRECT |
| `SHAPE_STRONG` / `SHAPE_WEAK` | 70.0 / 60.0 | No - diagnostic only | Shape-evidence strength bands |
| `DIRECTION_SUPPORT` / `DIRECTION_BAD` | 60.0 / 45.0 | No - diagnostic only | Direction-evidence bands |
| `PHRASE_RESCUE_SHAPE_STRONG` / `_DIRECTION_SUPPORT` | 78.0 / 65.0 | No - diagnostic only | Stricter bar letting strong phrase evidence override a borderline syllable verdict |
| `DISPLAY_SHAPE_WEIGHT` / `_DIRECTION_WEIGHT` | 0.70 / 0.30 | No - cosmetic only | Progress-history composite |

All are `os.getenv(...)`-overridable at these coded defaults, and every
`ToneDiagnosis`/`WordToneDiagnosis` payload the API returns carries
`"threshold_validated": False` explicitly
(`domain/speech/tone_decision.py:213, 325`).

### 3.5 Quality gate

`services/content_verification.py:80-201`. Deterministic, pre-ASR checks
on the raw decoded audio, each producing a specific reason code (not a
generic failure):

| Check | Default | Reason code |
|---|---|---|
| Minimum duration | 0.45s | `recording_too_short` |
| Silence RMS floor | 0.02 | `signal_too_quiet` |
| Minimum voiced seconds | 0.4s (0.25s for a 1-syllable target) | `insufficient_speech` |
| Max clipping ratio | 0.08 | `audio_clipping` |
| WAV decode failure | - | `audio_format_unverified` |
| Minimum pitch points | 8 | `insufficient_voiced_pitch` |
| Near-constant signal (hum/held tone) | voiced_ratio >= 0.85 and energy_variation < 0.03 | `low_signal_variation` |

Any failing check sets `can_score_pronunciation=False`, which becomes
`INVALID_AUDIO` rather than a confident bad score - poor evidence is never
treated as bad pronunciation.

### 3.6 Word/syllable -> sentence rollup

- **Syllable -> word** (`aggregate_word()`,
  `domain/speech/tone_decision.py:426-441`): any `INCORRECT` -> word
  `INCORRECT`; else any `INVALID_AUDIO` -> word `INVALID_AUDIO`; else any
  `UNCERTAIN` -> `UNCERTAIN`; else `CORRECT`.
- **Phrase/word rescue** (`domain/speech/acoustics/phrase_rescue.py`,
  `domain/speech/acoustics/verdicts.py`): can promote a verdict toward
  `CORRECT` - including overriding an individually-measured `INCORRECT` -
  only when combined evidence clears the stricter `PHRASE_RESCUE_*` bars.
  It never demotes.
- **Word -> sentence** (`build_pronunciation_mastery()`,
  `services/pronunciation_scoring.py:76-227`): excludes placeholder
  (unmeasured) syllables from both numerator and denominator; sentence
  passes when `pass_rate >= SENTENCE_SYLLABLE_PASS_RATIO (0.80)` and
  `content_match is not False`.

### 3.7 Speech recognition

Adapters actually wired in `services/speech/asr/transcription.py`:
`openai`, `groq`, `gemini` (cloud), `ctwhisper`, `vibevoice` (local).
Fallback order defaults to `groq,ctwhisper`
(`ASR_FALLBACK_ORDER` env var). The admin Learning Engine page reports
which are configured (a key is present) - never the key value itself.

### 3.8 AI coaching feedback

`services/speech/feedback/pipeline.py`. Default provider: `local` (an
offline deterministic CAF-style engine) unless `AI_FEEDBACK_PROVIDER` is
set. When a cloud provider is requested, on a missing key or a failed call
it degrades to the next configured cloud provider, then to the local
engine - a student always gets feedback even if every cloud provider is
unavailable. AI feedback is coaching/explanation; it is not the source of
truth for whether pronunciation or required vocabulary was produced -
those are the deterministic tone-scoring and transcript-matching steps
above.

---

## Calibration status summary

| Engine | Algorithm status | Parameter status |
|---|---|---|
| BKT | Standard BKT equations | Engineering defaults; needs pilot/human-rater calibration |
| Retention | Modified SM-2 | Standard ease/interval constants; the q=4/q=2 binary mapping is an unvalidated project adaptation |
| Voice/tone scoring | Praat extraction is a published method; the scoring formulas on top are project heuristics | Every named threshold is an engineering default; the code ships `threshold_validated: False` in every verdict |

None of these should be described as validated or calibrated in any
external-facing report until an actual human-rater calibration study has
run against them.
