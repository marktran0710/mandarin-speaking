"""Contract checks for the speech-domain module migration."""

from pathlib import Path
import importlib

import chinese_tones
import praat_analyzer


def test_tone_facade_exports_semantic_modules():
    assert chinese_tones.calculate_tone_accuracy.__module__.endswith(
        "speech.tones.reference_contours"
    )
    assert chinese_tones.generate_comprehensive_feedback.__module__.endswith(
        "speech.tones.feedback"
    )


def test_acoustics_facade_exports_semantic_modules():
    assert praat_analyzer.analyze_all.__module__.endswith(
        "speech.acoustics.audio_features"
    )
    assert praat_analyzer.estimate_word_prosody.__module__.endswith(
        "speech.acoustics.word_prosody"
    )


def test_legacy_facades_no_longer_execute_part_files():
    backend_dir = Path(praat_analyzer.__file__).parent
    for facade in (backend_dir / "chinese_tones.py", backend_dir / "praat_analyzer.py"):
        assert "load_module_parts" not in facade.read_text(encoding="utf-8")


def test_feedback_and_asr_facades_alias_semantic_modules():
    assert importlib.import_module("services.ai_feedback") is importlib.import_module(
        "services.speech.feedback.pipeline"
    )
    assert importlib.import_module("services.asr") is importlib.import_module(
        "services.speech.asr.transcription"
    )
