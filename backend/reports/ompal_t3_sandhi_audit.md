# OMPAL T3 sandhi audit

Scope: Train/Dev metadata and existing predictions only. The sealed Test set was not opened.

- T3 predictions audited: 157
- T3 mappings: `{"T3_correct": 50, "T3_to_T1": 25, "T3_to_T2": 52, "T3_to_T4": 30}`
- T3+T3 context: `{"T3_plus_T3": 13, "not_observed": 144}`
- Needs data: `needs_data_no_boundary_fields, needs_data_no_pitch_flags, needs_data_no_surface_label`

A T3→T2 row in T3+T3 context is a possible surface-sandhi observation only; it does not alter gold labels or metrics.
