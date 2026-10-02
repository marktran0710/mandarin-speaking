# Vocabulary system pilot

The existing 40-account cohort is the user's operational pilot for trying the
learning system. Preserve its accounts, imported placement responses, quiz
attempts, response ledger, BKT state and SM-2 schedules. Removing the dormant
2x2 experiment does not reset this cohort or require experimental assignment.

The pilot exercises one flow: placement/diagnostics, pooled word-level BKT,
server-selected corrective practice per unresolved dimension, and ordinary
modified SM-2 maintenance. PFA remains an admin analysis tool; it does not
select practice or decide mastery. There are no 2x2 participants, conditions,
treatment-state projections or participant-only delayed probes.

The developer database was inspected on 2026-10-02 (Asia/Taipei): 40 accounts
were marked `is_test_account=true`, and all ten `vocab_research_*` tables were
empty. These account and evidence-source labels remain intact. Calling the
cohort a pilot describes how it is being used; it does not change the origin
of imported or simulated responses. The user has not run calibration.

This pilot can validate system behavior, persistence, progression, corrective
completion and scheduling. Its existing source labels must remain available
when analyzing results. Synthetic/system-test responses do not by themselves
validate human learning assumptions or calibrate production BKT for people.

Migration 0062 removes only the empty experiment tables and experiment-only
columns. It refuses to proceed if any experiment table contains rows or any
ordinary quiz evidence is experiment-linked. It updates the lesson-reset
trigger and preserves historical response fingerprints for safe retries.
Historical migrations 0043-0049 remain so older databases can upgrade and the
empty experiment structures can be reconstructed on downgrade.

Removal verification on the local developer database: revision 0062 is applied,
no experiment tables remain, and all 40 pilot accounts and their 4,480 response
rows are retained. Counts and checksums of 17 production tables match before
and after migration (excluding only the removed experiment metadata columns).
The frontend production build, 81 frontend tests and 242 backend regression
tests passed, including migration guards and pilot-evidence preservation.
