"""Tone scoring components: syllable alignment and per-syllable scoring.

Split out of praat_analyzer so alignment and scoring can be swapped and
measured independently against the OMPAL benchmark, instead of being fused
inline where neither could be attributed for a change in agreement.
"""
