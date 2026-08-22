"""Tone scoring components: syllable alignment and per-syllable scoring.

Split out of praat_analyzer so alignment and scoring can be swapped and
measured independently from the acoustic analyzer, instead of being fused
inline where each component would be harder to maintain and test.
"""
