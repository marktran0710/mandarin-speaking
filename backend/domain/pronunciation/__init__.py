"""Known-script pronunciation evaluation: acoustic comparison against a
reference recording, scored by one deterministic, versioned policy.

Pure domain code - no IO, no HTTP, no persistence. Praat extraction and the
LLM feedback layer live in ``services.pronunciation`` and only ever consume or
produce the plain data types defined here.
"""
