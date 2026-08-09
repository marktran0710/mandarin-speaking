# T3 surface-tone annotation queue

This is a **Train-only preannotation queue**, not a gold dataset. Dev and sealed Test are prohibited.

## Reviewer procedure

1. Open `token_audio_path`; use `source_audio_path` only when it is present.
2. Listen without treating the model prediction or lexical prompt as the answer.
3. Fill `human_perceived_tone` (T1–T4 or Unknown), `human_correctness`, `reviewer_id`, and `reviewed_at`.
4. Flag uncertain boundary/pitch cases in `review_notes`; do not infer missing context.
5. A second reviewer/adjudicator must set `adjudication_status`; only a separate gold-ingestion process may promote a reviewed row.

`T3_plus_T3_context` is a prioritization signal only. It never rewrites a lexical T3 target to T2.

Queued rows: 95
Reasons: `{"T3_error": 76, "low_margin_ambiguous": 32}`
