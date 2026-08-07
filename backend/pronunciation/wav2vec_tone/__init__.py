"""Phase 1: frozen Mandarin wav2vec2 embeddings -> 4-way tone classifier.

Self-contained on purpose. It shares no code with ``tone_scoring`` (which is
wired into ``praat_analyzer`` and therefore live) or with any other production
module, so it can be changed, broken, or deleted without touching the app.
"""
