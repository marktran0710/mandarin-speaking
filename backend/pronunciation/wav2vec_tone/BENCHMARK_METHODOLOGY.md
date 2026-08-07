# OMPAL tone-correctness benchmark — methodology and known limitations

Written when the preprocessing investigation closed, so the decisions and the
evidence behind them stay attached to the data. Every number here was measured
in this repository; the scripts that produced them are named alongside.

## The task

**Learner audio + expected Taiwan Mandarin tone → human correct/incorrect.**

Not tone identification, and not tone diagnosis. OMPAL records whether a rater
judged the tone right or wrong; it never records which wrong tone was produced,
so `T3 → T2` style analysis is impossible with this corpus as published.

## Why the original 0 ms boundaries were kept

The forced aligner's own boundaries are used with no adjustment.

Padding was tested twice and rejected twice.

The first test pre-registered ±40 ms against 0 ms on 44 tokens
(`analyze_binary_padding.py`) and it failed. In the same run ±20 ms looked
better as an exploratory condition, so it was retested properly on 72 fresh
tokens that had never been reviewed (`analyze_confirm_padding.py`). Adopting
20 ms on the strength of the first run would have meant selecting a winner from
the data that produced it.

The confirmation did not clear its pre-registered bar either, so **no padding
is applied**. Both thresholds were fixed in code and committed before the
judgments existed.

## Why no automatic QC rule was adopted

Three attempts, each ending in a measured limit rather than a guess.

**Alignment/acoustic indicators already in the pipeline**
(`segment_qc_diagnostic.py`). On 116 original-boundary tokens with binary human
judgments, duration was the best single indicator at AUC 0.760, and the
strongest pre-specified rule retained 65% of tokens at 88.0% human ACCEPT
against a 79.3% base rate. A post-hoc duration curve plateaued at 90–91% and
never approached 95%, so the shortfall was a ceiling rather than a missing
threshold.

**A failure-mode audit** (`analyze_failure_audit.py`) showed why. The confirmed
failures were only `LOW_AUDIO_QUALITY` (8) and `TOO_SHORT_OR_INCOMPLETE` (6) —
no wrong-token, no truncation, no adjacent speech. That retired the idea of a
constrained re-alignment check: there were no location errors to detect.

**Tone-specific acoustics** (`tone_qc_acoustics.py`). Absolute RMS separated
almost perfectly (AUC 0.946) but confounds a quiet token with a quietly
recorded speaker, so the same measure was recomputed relative to each token's
own utterance, where gain cancels. That survived at 0.807 in development.

It did not survive confirmation. On 100 fresh tokens
(`analyze_qc_confirmation.py`): `rms_relative_db` AUC **0.674**, `local_snr_db`
**0.672**, duration **0.727**. The frozen threshold (T = 3.1043 dB, derived
mechanically from development data and committed before the labels existed)
retained only **33%** at **90.9%** human ACCEPT — below the 95% precision and
50% retention it had to clear.

Development retention was 29%, and that was recorded in the preregistration
before the confirmation ran, so the retention failure repeated development
rather than contradicting it.

**Conclusion: no acoustic QC rule is validated, and none is applied.** The
descriptors are carried in the manifest as metadata so later analysis can
condition on them — knowing they were never shown to separate usable from
unusable segments.

## The headline limitation

A fresh blinded review put original-boundary human usability at **81/100**.

So roughly **one token in five is expected to be imperfect for tone analysis,
and the manifest cannot say which ones.** Any result computed on this benchmark
inherits that noise floor. It is not a defect to be filtered away — it is the
measured state of the data.

Two further cautions on the human labels themselves. The earlier three-level
boundary scale proved unusable, repeating itself on identical audio only 36% of
the time, which is why it was replaced by the binary usability question. Even
the binary question is not perfect: in the failure audit, 9 of 23 rejected
tokens were accepted on a second hearing, while all 24 accepted controls held —
instability concentrated on the marginal cases.

## Eligibility, and what is deliberately excluded

A token enters the manifest only when its audio and annotation genuinely match,
it carries an OMPAL correctness rating, and its expected Taiwan tone is verified
against the MoE dictionary (`moedict.tw`, tone read from bopomofo).

Three exclusions are policy, not oversight:

- **The 656 annotation/audio id mismatches are not repaired.** The counts pair
  20-for-20 across speakers and the numbering continues where the annotated
  utterances stop, so the release very likely splits two sessions per directory
  into two speaker ids. That is a strong hypothesis, not proof, and acting on it
  would attach labels to the wrong audio. Confirming it with the corpus authors
  would raise usable learner utterances from 1,112 to 1,768.
- **Polyphonic characters are not guessed.** Where MoE readings differ in tone
  (不, 上, 了, 們 …) the token is excluded. This costs real data and removes
  neutral tone from the benchmark entirely, since every neutral-capable
  character here is tone-ambiguous.
- **Multi-character words are out of scope**, and the alignment sequence is
  built from the full word list so their presence cannot shift the index of
  neighbouring tokens.

## Provenance

Every manifest row carries the aligner, boundary policy, manifest version, code
commit and target-pronunciation source, plus whether the token has been heard
in any human QC review and what the latest binary verdict was.

**Those QC fields are provenance only.** They record whether a clip is
*analysable*, never whether the learner pronounced it correctly, and must not
be used as a pronunciation label.

## Not done here

No train/dev/test split, no model, no threshold. Splits come next and need the
actual speaker and token distribution — especially the size of the minority
incorrect class — before they can be designed sensibly.

Human-verified evaluation data is handled separately. The tokens already
carrying binary usability judgments are a small, non-random subset, and using
them as a clean evaluation set would bias it toward material chosen for review.
