"""Minimal production integration of the frozen ACCEPT/UNCERTAIN/NEEDS_PRACTICE
assistive feedback policy (Candidate F1 risk signal + Candidate E2 diagnostic).

Everything in this package is ADDITIVE and READ-ONLY with respect to the
existing scoring pipeline: it never modifies `word_prosody[].passed`,
`praat_analyzer.SYLLABLE_PASS_THRESHOLD`, `chinese_tones.py`, `tone_context.py`,
or any Candidate F1/E2 weights or formulas. See
`benchmarking/results/assistive_feedback_integration.md` for the full audit.
"""
