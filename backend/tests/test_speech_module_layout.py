"""Contract checks for the speech-domain module migration."""

from pathlib import Path
import importlib

import domain.speech.tones as chinese_tones
import domain.speech.acoustics as praat_analyzer


def test_tone_package_exports_semantic_modules():
    assert chinese_tones.calculate_tone_accuracy.__module__.endswith(
        "speech.tones.reference_contours"
    )
    assert chinese_tones.generate_comprehensive_feedback.__module__.endswith(
        "speech.tones.feedback"
    )


def test_acoustics_package_exports_semantic_modules():
    assert praat_analyzer.analyze_all.__module__.endswith(
        "speech.acoustics.audio_features"
    )
    assert praat_analyzer.estimate_word_prosody.__module__.endswith(
        "speech.acoustics.word_prosody"
    )


def test_legacy_root_speech_modules_are_removed():
    backend_dir = Path(__file__).parents[1]
    assert not (backend_dir / "chinese_tones.py").exists()
    assert not (backend_dir / "praat_analyzer.py").exists()


def test_feedback_and_asr_facades_alias_semantic_modules():
    assert importlib.import_module("services.ai_feedback") is importlib.import_module(
        "services.speech.feedback.pipeline"
    )
    assert importlib.import_module("services.asr") is importlib.import_module(
        "services.speech.asr.transcription"
    )


def test_domain_and_repository_boundaries_are_explicit():
    assert chinese_tones.calculate_tone_accuracy.__module__.startswith("domain.")
    assert praat_analyzer.analyze_all.__module__.startswith("domain.")
    assert importlib.import_module("db") is importlib.import_module(
        "repositories.database"
    )


def test_domain_modules_do_not_depend_on_http_or_persistence_layers():
    domain_root = Path(__file__).parents[1] / "domain"
    forbidden = (
        "from routers",
        "import routers",
        "from db",
        "import db",
        "from repositories",
    )
    for module in domain_root.rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert not any(statement in source for statement in forbidden), module


def test_legacy_speech_submodules_are_true_aliases(monkeypatch):
    module_groups = {
        "tones": ("feedback", "reference_contours", "scoring"),
        "acoustics": (
            "audio_features",
            "pause_fluency",
            "phrase_rescue",
            "prosody_feedback",
            "verdicts",
            "word_prosody",
        ),
    }
    for package, modules in module_groups.items():
        for module_name in modules:
            legacy = importlib.import_module(f"services.speech.{package}.{module_name}")
            canonical = importlib.import_module(f"domain.speech.{package}.{module_name}")
            assert legacy is canonical

            marker = object()
            monkeypatch.setattr(legacy, "_compatibility_probe", marker, raising=False)
            assert canonical._compatibility_probe is marker
