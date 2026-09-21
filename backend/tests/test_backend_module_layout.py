"""Contract tests for the backend's root-module migration.

The root aliases are intentional compatibility boundaries.  These checks make
sure a future cleanup does not silently remove them or fork module identity,
which would break existing imports and monkeypatch-based tests.
"""

from pathlib import Path


def test_backend_implementation_modules_have_canonical_locations():
    backend_root = Path(__file__).resolve().parents[1]
    for filename in (
        "auth.py",
        "models.py",
        "chinese_tones.py",
        "praat_analyzer.py",
        "reference_voice.py",
        "tone_decision.py",
        "tts_service.py",
        "vocab_assessment.py",
    ):
        assert not (backend_root / filename).exists(), filename


def test_test_loader_is_not_a_production_root_module():
    backend_root = Path(__file__).resolve().parents[1]
    assert not (backend_root / "_module_loader.py").exists()
    assert (backend_root / "tests" / "support" / "module_loader.py").exists()


def test_speech_and_database_assets_have_single_canonical_locations():
    backend_root = Path(__file__).resolve().parents[1]
    assert not (backend_root / "tone_scoring").exists()
    assert not (backend_root / "db_init").exists()
    assert (backend_root / "domain" / "speech" / "acoustics" / "alignment.py").exists()
    assert (backend_root / "pronunciation" / "embeddings.py").exists()
    assert (
        backend_root
        / "infrastructure"
        / "database"
        / "bootstrap"
        / "01-create-test-db.sql"
    ).exists()
