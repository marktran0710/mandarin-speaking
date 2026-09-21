"""Contract tests for the backend's root-module migration.

The root aliases are intentional compatibility boundaries.  These checks make
sure a future cleanup does not silently remove them or fork module identity,
which would break existing imports and monkeypatch-based tests.
"""

from importlib import import_module
from pathlib import Path


def test_legacy_root_modules_resolve_to_their_layered_implementations():
    module_pairs = (
        ("auth", "security.auth"),
        ("models", "api.schemas.models"),
        ("tone_decision", "domain.speech.tone_decision"),
        ("vocab_assessment", "domain.vocabulary.assessment"),
        ("reference_voice", "services.speech.reference_voice"),
        ("tts_service", "infrastructure.speech.tts"),
    )

    for legacy_name, canonical_name in module_pairs:
        assert import_module(legacy_name) is import_module(canonical_name)


def test_test_loader_is_not_a_production_root_module():
    backend_root = Path(__file__).resolve().parents[1]
    assert not (backend_root / "_module_loader.py").exists()
    assert (backend_root / "tests" / "support" / "module_loader.py").exists()
