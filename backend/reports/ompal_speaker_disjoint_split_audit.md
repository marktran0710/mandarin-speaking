# OMPAL speaker-disjoint split audit — `ompal_speaker_split_v1`

seed `20260808` · algorithm: random restarts + pairwise/relocation hill-climbing, whole speakers · objective 1.1237 · hash `853aa9d0a2c3a449`

## Split summary

| | Train | Dev | Test |
|---|---|---|---|
| Speakers | 32 | 6 | 7 |
| Tokens | 1424 | 322 | 322 |
| % of tokens | 68.9% | 15.6% | 15.6% |
| Correct | 1183 | 267 | 267 |
| Incorrect | 241 | 55 | 55 |
| Incorrect % | 16.9% | 17.1% | 17.1% |
| T1 | 384 | 82 | 87 |
| T2 | 320 | 74 | 74 |
| T3 | 192 | 40 | 40 |
| T4 | 528 | 126 | 121 |

## Minority-class adequacy

351 Incorrect tokens are the entire statistical budget for this
benchmark, so held-out minority counts matter more than exact token
proportions.

- Train Incorrect = **241**
- Dev Incorrect = **55**
- Test Incorrect = **55**

## Tone x correctness by split

### Train

| tone | Correct | Incorrect |
|---|---|---|
| T1 | 319 | 65 |
| T2 | 268 | 52 |
| T3 | 157 | 35 |
| T4 | 439 | 89 |

### Dev

| tone | Correct | Incorrect |
|---|---|---|
| T1 | 71 | 11 |
| T2 | 64 | 10 |
| T3 | 30 | 10 |
| T4 | 102 | 24 |

### Test

| tone | Correct | Incorrect |
|---|---|---|
| T1 | 74 | 13 |
| T2 | 65 | 9 |
| T3 | 33 | 7 |
| T4 | 95 | 26 |

## Lexical coverage

Train covers 59 characters and 53 syllable bases.

| | Dev | Test |
|---|---|---|
| characters | 59 | 59 |
| syllables | 53 | 53 |
| characters unseen in Train | 0 | 0 |
| syllables unseen in Train | 0 | 0 |
| % tokens w/ unseen character | 0.0% | 0.0% |
| % tokens w/ unseen syllable | 0.0% | 0.0% |

Lexical novelty is quantified, not eliminated — some is useful for
measuring generalisation.

## Speaker difficulty

Speaker Incorrect rate, per split:

| | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|
| train | 0.0% | 5.9% | 15.3% | 28.5% | 56.9% |
| dev | 2.8% | 11.9% | 15.1% | 21.1% | 31.9% |
| test | 2.8% | 10.2% | 15.3% | 20.6% | 36.1% |

## Speaker assignment

- **train** (32): 02002, 02003, 02005, 02006, 02007, 02009, 02010, 02011, 02012, 02013, 02016, 02018, 02019, 02020, 02021, 02022, 02024, 02028, 02029, 02030, 02031, 02033, 02034, 02035, 02038, 02039, 02041, 02042, 02043, 02044, 02045, 02046
- **dev** (6): 02004, 02014, 02023, 02027, 02036, 02040
- **test** (7): 02001, 02008, 02015, 02025, 02026, 02032, 02037

## Leakage checks

All passed:
- train ∩ dev = ∅, train ∩ test = ∅, dev ∩ test = ∅
- 45 unique learner speakers assigned, each to exactly one split
- tokens 2068 = train + dev + test; correct 1717; incorrect 351
- no token id in more than one split, no duplicate token ids
- no utterance straddles two splits
- every segment file referenced by the manifest exists on disk

## Native reference data

The 108 native tokens (speakers 01001-01003) are outside the primary split. They appear in the split manifest only as `split = native_reference`, and are not to be used as training examples for the learner classifier without an explicit later research decision.

## Metrics planning

Majority-class accuracy is 83.0%, so Accuracy alone is not informative. Later comparison must report Balanced Accuracy, Macro-F1, Incorrect-class precision/recall/F1, ROC-AUC and PR-AUC; Accuracy is secondary and descriptive only.

## Freeze

Split `ompal_speaker_split_v1` is frozen. SHA-256 of the sorted speaker→split mapping:

`853aa9d0a2c3a449900f8797f8aabd780b7505d0cdbacce250b131058a532468`

Do not regenerate this split because model results are disappointing.
The Test set must not influence any modelling decision.
