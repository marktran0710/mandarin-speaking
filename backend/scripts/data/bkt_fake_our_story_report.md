# Synthetic BKT pilot — 我們去喝下午茶

> Synthetic data only. This report is for UI and analytics pipeline testing; it is not human-rated evidence and must not silently replace production defaults.

- Students: **25** (`fake-student-01` … `fake-student-25`)
- Easy diagnostic questions per student: **67** (20 + 22 + 25)
- Total response records: **1675**
- Unique vocabulary concepts: **31**
- Random seed: **20260902**

## BKT parameters

| Parameter | Generating value | Estimated from all responses |
|---|---:|---:|
| Prior mastery (`prior`) | 0.2500 | 0.1910 |
| Learn rate (`learn`) | 0.1800 | 0.2055 |
| Guess rate (`guess`) | 0.1800 | 0.1904 |
| Slip rate (`slip`) | 0.0800 | 0.0464 |

## Validation

- BKT-eligible responses after the repository validation gate: **1675 / 1675**
- Full-data sequential fit accuracy: **0.410**
- Full-data log loss: **0.6366**
- Full-data Brier score: **0.2226**
- Prequential evaluation responses: **838** after a 837-response training prefix
- Prequential log loss: **0.6316**
- Prequential Brier score: **0.2201**

## Interpretation

The fitted values are a recovery check against the synthetic generator, not a calibrated recommendation. The production implementation currently uses engineering defaults of prior=0.20, learn=0.15, guess=0.20, and slip=0.10. Keep those values unchanged until real, approved student responses are collected and evaluated with the same eligibility gates.
