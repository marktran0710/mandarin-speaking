"""Score the OMPAL corpus under each aligner/scorer configuration.

The point is attribution. Shipping two changes at once and observing a better
number tells you nothing about which one earned it, so every configuration is
scored separately over the same corpus and reported in one table.

Each configuration writes its own results file, so a re-run resumes rather
than rescoring, and configurations can never contaminate each other.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarking.ompal_corpus import load_utterances
from benchmarking.ompal_report import build_report
from benchmarking.ompal_runner import load_scored, run_scoring

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "private-data" / "ompal"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "private-data" / "ablation"


def score_with(aligner: str, utterances, force: bool = False) -> list[dict]:
    """Score the corpus with one aligner, reusing prior results when present."""
    os.environ["TONE_ALIGNER"] = aligner
    # Imported here so the aligner selection is read fresh for this run.
    from praat_analyzer import analyze_all

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"scored-{aligner}.jsonl"
    if force and path.exists():
        path.unlink()

    summary = run_scoring(
        utterances,
        path,
        analyzer=lambda p, t: analyze_all(p, t),
        on_progress=lambda done, total, failed: (
            print(f"  [{aligner}] {done}/{total} (failed {failed})", end="\r")
            if done % 200 == 0 else None
        ),
    )
    print(f"  [{aligner}] scored={summary['scored']} failed={summary['failed']} "
          f"skipped={summary['skipped']}          ")
    return load_scored(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligners", nargs="+", default=["proportional", "energy"])
    parser.add_argument("--threshold", type=float, default=58.0)
    parser.add_argument("--force", action="store_true", help="rescore from scratch")
    args = parser.parse_args()

    utterances = load_utterances(CORPUS_ROOT)
    print(f"corpus: {len(utterances)} utterances\n")

    results = {}
    for aligner in args.aligners:
        print(f"scoring with aligner={aligner}")
        rows = score_with(aligner, utterances, force=args.force)
        results[aligner] = build_report(
            utterances, rows, threshold=args.threshold
        )

    print("\n=== ABLATION (scorer = heuristic in all rows) ===")
    header = f"{'aligner':<14}{'mean kappa':>12}{'vs majority':>13}{'raw agree':>11}{'n':>8}"
    print(header)
    print("-" * len(header))
    for aligner, report in results.items():
        primary = report["per_rater_agreement"]
        overall = report["pass_fail_agreement"]
        kappa = primary["mean_cohen_kappa"]
        print(
            f"{aligner:<14}"
            f"{(f'{kappa:.4f}' if kappa is not None else 'n/a'):>12}"
            f"{overall.get('cohen_kappa', 0):>13.4f}"
            f"{overall.get('accuracy', 0) * 100:>10.1f}%"
            f"{primary['n']:>8}"
        )

    baseline = results.get(args.aligners[0], {}).get("per_rater_agreement", {})
    base_kappa = baseline.get("mean_cohen_kappa")
    for aligner, report in results.items():
        kappa = report["per_rater_agreement"]["mean_cohen_kappa"]
        if base_kappa is not None and kappa is not None and aligner != args.aligners[0]:
            print(f"\ndelta {aligner} vs {args.aligners[0]}: {kappa - base_kappa:+.4f}")

    first = next(iter(results.values()))
    bound = first["oracle_bound"]
    print(
        f"\ntarget {first['per_rater_agreement']['target']} | "
        f"human ceiling {first['human_ceiling']['fleiss_kappa']:.4f} | "
        f"attainable max {bound['uncontaminated']:.4f}-{bound['contaminated']:.4f}"
    )
    for aligner, report in results.items():
        tones = {
            k: round(v.get("f1") or 0, 3)
            for k, v in report["by_expected_tone"].items()
        }
        print(f"  [{aligner}] per-tone F1: {tones}")
        print(f"  [{aligner}] exclusions: {report['exclusions']}")


if __name__ == "__main__":
    main()
