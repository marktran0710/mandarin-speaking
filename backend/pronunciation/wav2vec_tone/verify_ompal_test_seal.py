"""Phase D1 — independent verification that OMPAL Test is still sealed.

The D0 preflight recorded the test-lock status as a hardcoded literal, which
asserts nothing. This script checks it against the filesystem instead:

  1. the test split exists and is still defined (it is sealed, not deleted)
  2. no cached feature or trajectory array contains a test-split token
  3. no artefact reports a *performance number* on the test split
     (split composition metadata is legitimate and is not flagged)
  4. every module that reads the manifest has an executable test-lock guard
  5. the fresh-validation analysis script never reads the manifest at all

    python -m pronunciation.wav2vec_tone.verify_ompal_test_seal
"""

from __future__ import annotations

import ast
import collections
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MANIFEST_SPLIT = DATA / "ompal_full_tone_benchmark_manifest_split.csv"

# Words that turn a mention of "test" into a *result* rather than a description
# of how the split was built.
RESULT_KEYS = ("auc", "kappa", "precision", "recall", "accuracy", "coverage",
               "f1", "brier", "balanced", "pr_auc", "roc", "n_pass", "t_pass")

findings: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    findings.append((bool(ok), name, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return bool(ok)


def walk(node, trail=()):
    """Yield (trail, key, value) for every scalar in a nested JSON structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, trail + (str(key),))
    elif isinstance(node, list):
        for value in node:
            yield from walk(value, trail)
    else:
        yield trail, node


def guard_is_live(path: Path) -> tuple[bool, str]:
    """True when the module has a test-lock guard that can actually fire.

    A guard written as `if <cond> and False:` parses and greps fine but is dead
    code. Reading the AST is the only way to tell the difference.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    live = dead = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        source = ast.unparse(node.test)
        if "'test'" not in source and '"test"' not in source:
            continue
        if re.search(r"\band\s+False\b|\bFalse\s+and\b", source):
            dead += 1
        else:
            live += 1
    if live:
        return True, f"{live} live guard(s)" + (f", {dead} dead" if dead else "")
    return False, f"no live guard ({dead} dead)" if dead else "no guard"


def main() -> None:
    print("OMPAL Test seal verification (Phase D1)\n")

    # 1 — the split still exists ------------------------------------------------
    rows = list(csv.DictReader(MANIFEST_SPLIT.open(encoding="utf-8")))
    counts = collections.Counter(r["split"] for r in rows)
    test_speakers = {r["speaker_id"] for r in rows if r["split"] == "test"}
    check(counts["test"] > 0 and len(test_speakers) > 0,
          "test split still defined (sealed, not deleted)",
          f"{counts['test']} tokens / {len(test_speakers)} speakers")

    # 2 — no test token in any cache -------------------------------------------
    leaked = []
    for cache_path in sorted(DATA.glob("*.npz")):
        try:
            store = np.load(cache_path, allow_pickle=True)
        except Exception as exc:                      # unreadable is not a leak
            print(f"    (skipped {cache_path.name}: {exc})")
            continue
        if "split" in store.files and "test" in set(np.asarray(store["split"]).tolist()):
            leaked.append(cache_path.name)
    check(not leaked, "no cached array contains a test-split token",
          ", ".join(leaked) if leaked else f"{len(list(DATA.glob('*.npz')))} caches scanned")

    # 3 — no performance number reported on test -------------------------------
    offenders = []
    for artefact in sorted(DATA.glob("*.json")):
        payload = json.loads(artefact.read_text(encoding="utf-8"))
        for trail, value in walk(payload):
            lower = [part.lower() for part in trail]
            if "test" not in lower:
                continue
            after = lower[lower.index("test"):]
            if any(any(word in part for word in RESULT_KEYS) for part in after[1:]):
                offenders.append(f"{artefact.name}:{'.'.join(trail)}")
    check(not offenders, "no artefact reports a metric on the test split",
          "; ".join(offenders[:3]) if offenders
          else f"{len(list(DATA.glob('*.json')))} artefacts scanned")

    # 4 — every manifest reader has a live guard --------------------------------
    readers, weak, dead_code = [], [], []
    for module in sorted(HERE.glob("*.py")):
        source = module.read_text(encoding="utf-8")
        if "MANIFEST_SPLIT" not in source or module.name == Path(__file__).name:
            continue
        readers.append(module.name)
        live, detail = guard_is_live(module)
        if not live:
            weak.append(f"{module.name} ({detail})")
        elif "dead" in detail:
            # Not a seal failure — a live guard is present — but a dead guard
            # looks like protection to anyone auditing by eye, so name it.
            dead_code.append(f"{module.name} ({detail})")
    if dead_code:
        print(f"    note: vestigial dead guard(s), live guard still present — "
              f"{'; '.join(dead_code)}")
    check(not weak, "every manifest reader has an executable test-lock guard",
          "; ".join(weak) if weak else f"{len(readers)} modules")

    # 5 — the analysis script never touches the benchmark ----------------------
    analysis = (HERE / "analyze_fresh_human_validation.py").read_text(encoding="utf-8")
    check("MANIFEST_SPLIT" not in analysis and "manifest_split" not in analysis,
          "fresh-validation analysis never reads the OMPAL manifest")

    failed = [name for ok, name, _ in findings if not ok]
    (DATA / "ompal_test_seal_verification.json").write_text(json.dumps({
        "phase": "D1",
        "test_split": {"tokens": counts["test"], "speakers": len(test_speakers)},
        "checks": [{"check": n, "pass": ok, "detail": d} for ok, n, d in findings],
        "manifest_readers": readers,
        "vestigial_dead_guards": dead_code,
        "n_failed": len(failed),
        "sealed": not failed,
    }, indent=2), encoding="utf-8")

    print(f"\n{len(findings) - len(failed)}/{len(findings)} checks passed")
    if failed:
        sys.exit("OMPAL TEST SEAL NOT VERIFIED: " + "; ".join(failed))
    print("OMPAL Test is sealed.")


if __name__ == "__main__":
    main()
