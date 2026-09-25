"""Structure linter for backend/ — enforces the R1/R5/R7 folder-splitting rules.

Usage: python scripts/check_structure.py [--layer routers,services,...]
Exits non-zero if any violation is found.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Layers this check applies to (top-level packages under backend/).
LAYERS = [
    "routers", "services", "repositories", "application",
    "analytics", "domain", "scripts",
]

SKIP_DIR_NAMES = {"__pycache__", "data", "__init__.py"}

SIZE_THRESHOLD = 8       # R1(b): >8 source files (excl. __init__.py) in one folder
PREFIX_THRESHOLD = 3     # R1(a): >=3 files sharing a domain-ish prefix
TEST_FLAT_THRESHOLD = 25  # R1(c): >25 test files flat in one folder
MAX_DEPTH_UNDER_LAYER = 2  # R5: <layer>/<domain>/<subdomain>/file at most

# R7 — canonical backend domain names, and keywords that indicate a file
# belongs to that domain even when its folder name doesn't say so.
CANONICAL_DOMAINS = {
    "accounts", "content", "vocabulary_quiz", "learner_model",
    "research", "speech", "speaking", "classroom", "platform",
}
DOMAIN_KEYWORDS: dict[str, str] = {
    "bkt": "learner_model",
    "srs": "learner_model",
    "knowledge_analytics": "learner_model",
    "knowledge_tracing": "learner_model",
    "weak_words": "learner_model",
    "review_queue": "learner_model",
    "vocabulary_state": "learner_model",
    "vocab_quiz": "vocabulary_quiz",
    "quiz_review": "vocabulary_quiz",
    "quiz_attempt": "vocabulary_quiz",
    "research": "research",
    "vocabulary_research": "research",
    "placement_test": "research",
    "story": "content",
    "stories": "content",
    "vocabulary_import": "content",
    "vocabulary_audio_import": "content",
    "content_reset": "content",
    "content_verification": "content",
    "help_request": "classroom",
    "speaking_progress": "speaking",
    "submission": "speaking",
    "verified_speech": "speaking",
    "verified_speaking": "speaking",
    "audio_record": "speaking",
    "media": "platform",
    "health": "platform",
    "admin": "accounts",
    "student": "accounts",
    "teacher": "accounts",
}


def stem_prefix(stem: str) -> str:
    return stem.split("_")[0]


def find_prefix_clusters(stems: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for stem in stems:
        groups[stem_prefix(stem)].append(stem)
    return {prefix: members for prefix, members in groups.items()
            if len(members) >= PREFIX_THRESHOLD}


def domain_keyword_hits(stem: str) -> set[str]:
    hits = set()
    for keyword, domain in DOMAIN_KEYWORDS.items():
        if keyword in stem:
            hits.add(domain)
    return hits


def iter_py_files(directory: Path):
    for entry in directory.iterdir():
        if entry.is_file() and entry.suffix == ".py":
            yield entry


def check_folder_size_and_prefix(directory: Path, violations: list[str]) -> None:
    source_files = [
        f for f in iter_py_files(directory)
        if f.name != "__init__.py" and not f.name.startswith("test_")
    ]
    if len(source_files) > SIZE_THRESHOLD:
        violations.append(
            f"R1(b) size: {rel(directory)} has {len(source_files)} source files "
            f"(threshold {SIZE_THRESHOLD}): "
            + ", ".join(sorted(f.name for f in source_files))
        )

    stems = [f.stem for f in source_files]
    for prefix, members in find_prefix_clusters(stems).items():
        violations.append(
            f"R1(a) prefix: {rel(directory)} has {len(members)} files sharing "
            f"prefix '{prefix}': {', '.join(sorted(members))}"
        )


def check_test_folder_flat(directory: Path, violations: list[str]) -> None:
    test_files = [f for f in iter_py_files(directory) if f.name.startswith("test_")]
    subdirs = [d for d in directory.iterdir() if d.is_dir() and d.name not in SKIP_DIR_NAMES]
    if len(test_files) > TEST_FLAT_THRESHOLD and not subdirs:
        violations.append(
            f"R1(c) flat tests: {rel(directory)} has {len(test_files)} test files "
            f"flat with no domain subfolders (threshold {TEST_FLAT_THRESHOLD})"
        )


def check_depth(layer_dir: Path, violations: list[str]) -> None:
    for dirpath, dirnames, _filenames in os.walk(layer_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        depth = len(Path(dirpath).relative_to(layer_dir).parts)
        if depth > MAX_DEPTH_UNDER_LAYER:
            violations.append(
                f"R5 depth: {rel(Path(dirpath))} is {depth} levels under "
                f"{layer_dir.name}/ (max {MAX_DEPTH_UNDER_LAYER})"
            )


def check_domain_naming(directory: Path, violations: list[str]) -> None:
    top_level_name = directory.name
    if top_level_name in CANONICAL_DOMAINS:
        return
    hits: dict[str, list[str]] = defaultdict(list)
    for f in iter_py_files(directory):
        if f.name == "__init__.py":
            continue
        for domain in domain_keyword_hits(f.stem):
            hits[domain].append(f.name)
    for domain, files in hits.items():
        violations.append(
            f"R7 naming: {rel(directory)} holds {len(files)} file(s) matching "
            f"domain '{domain}' but the folder isn't named for a canonical "
            f"domain: {', '.join(sorted(files))}"
        )


def rel(path: Path) -> str:
    return str(path.relative_to(BACKEND_ROOT)).replace("\\", "/")


def walk_layer(layer_dir: Path, violations: list[str]) -> None:
    if not layer_dir.is_dir():
        return
    check_depth(layer_dir, violations)
    for dirpath, dirnames, _filenames in os.walk(layer_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        current = Path(dirpath)
        if current.name == "tests" or "test" in current.name:
            check_test_folder_flat(current, violations)
            continue
        check_folder_size_and_prefix(current, violations)
        check_domain_naming(current, violations)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", help="comma-separated subset of layers to check")
    args = parser.parse_args()

    layers = args.layer.split(",") if args.layer else LAYERS
    violations: list[str] = []

    for layer in layers:
        walk_layer(BACKEND_ROOT / layer, violations)

    tests_dir = BACKEND_ROOT / "tests"
    if tests_dir.is_dir():
        check_test_folder_flat(tests_dir, violations)

    if not violations:
        print("check_structure: no violations found.")
        return 0

    print(f"check_structure: {len(violations)} violation(s) found:\n")
    for v in sorted(violations):
        print(f"  - {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
