"""Export every human-vs-system tone judgement, and the disagreements alone.

The agreement report answers "how much do they agree". This answers "on what",
which is the only thing that can tell us *why* a false-rejection rate of ~44 %
happens. Nothing here scores anything or changes any verdict: it reads the
utterances and the already-scored rows and writes them out flat.

Availability is stated honestly. The cached scoring records per character only
``char``, ``score`` and ``judged`` (see ``ompal_runner.flatten_characters``),
so per-syllable duration, F0 summaries and alignment scores are written as
``NA`` rather than invented. Obtaining them means extending the scorer and
re-running Praat over 1,850 files, which is a separate decision — the columns
exist so that run can fill them without changing this schema.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from benchmarking.agreement import majority_label
from benchmarking.ompal_corpus import OmpalUtterance, align_system_characters
from benchmarking.stats import binary_agreement

NA = "NA"

#: Written for every row. Columns the cached scoring cannot fill are still
#: present, and always hold NA, so a later feature-carrying run drops straight
#: in without a schema change downstream.
FIELDNAMES = [
    "utterance_id",
    "speaker_id",
    "is_native",
    "join_source",
    "annotation_id",
    "text",
    "word",
    "expected_tone",
    "human_majority_tone_correct",
    "individual_rater_labels",
    "rater_panel_size",
    "system_tone_correct",
    "system_min_character_score",
    "system_character_scores",
    "system_all_characters_judged",
    "threshold",
    "error_type",
    "system_tone_accuracy",
    "system_fluency",
    "human_accuracy",
    "human_fluency",
    "human_prosody",
    "word_character_count",
    "duration_seconds",
    "f0_mean",
    "f0_min",
    "f0_max",
    "f0_range",
    "f0_slope",
    "alignment_score",
    "diagnostic_status",
    "audio_path",
]

FALSE_ACCEPTANCE = "false_acceptance"
FALSE_REJECTION = "false_rejection"


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_rows(
    utterances: Sequence[OmpalUtterance],
    scored_rows: Iterable[dict[str, Any]],
    *,
    threshold: float,
    panel_size: int = 3,
) -> list[dict[str, Any]]:
    """One row per rated word that both sides could judge.

    Deliberately mirrors ``ompal_report._judgement_rows`` exclusion for
    exclusion — neutral tones, words the analyzer declined to judge, incomplete
    panels and alignment mismatches are all left out — so the counts here add
    up to the counts in the report rather than telling a slightly different
    story about the same corpus.
    """
    by_id = {utterance.utterance_id: utterance for utterance in utterances}
    rows: list[dict[str, Any]] = []

    for scored in scored_rows:
        utterance = by_id.get(scored.get("utterance_id"))
        if utterance is None or scored.get("error"):
            continue

        entries = scored.get("characters") or []
        if any("judged" not in entry for entry in entries):
            continue
        characters = [
            (str(entry.get("char") or ""), float(entry.get("score") or 0.0) >= threshold)
            for entry in entries
        ]
        verdicts = align_system_characters(utterance.words, characters)
        if verdicts is None:
            continue

        position = 0
        for word, system_passed in zip(utterance.words, verdicts):
            span = slice(position, position + len(word.text))
            word_entries = entries[span]
            position += len(word.text)

            if word.has_neutral_tone:
                continue
            if not all(bool(entry.get("judged", True)) for entry in word_entries):
                continue
            if len(word.rater_tone_labels) != panel_size:
                continue
            teacher = majority_label(word.rater_tone_labels)
            if teacher is None:
                continue

            scores = [float(entry.get("score") or 0.0) for entry in word_entries]
            error_type = ""
            if teacher and not system_passed:
                error_type = FALSE_REJECTION
            elif system_passed and not teacher:
                error_type = FALSE_ACCEPTANCE

            rows.append({
                "utterance_id": utterance.utterance_id,
                "speaker_id": utterance.speaker_id,
                "is_native": utterance.is_native,
                "join_source": utterance.join_source,
                "annotation_id": utterance.annotation_id or NA,
                "text": utterance.text,
                "word": word.text,
                "expected_tone": (
                    word.expected_tones[0] if len(word.expected_tones) == 1 else NA
                ),
                "human_majority_tone_correct": int(teacher),
                "individual_rater_labels": "".join(
                    str(int(label)) for label in word.rater_tone_labels
                ),
                "rater_panel_size": len(word.rater_tone_labels),
                "system_tone_correct": int(system_passed),
                # The word verdict is the minimum character score against the
                # threshold, so the minimum is the number that decided it.
                "system_min_character_score": round(min(scores), 2) if scores else NA,
                "system_character_scores": "|".join(f"{value:.1f}" for value in scores),
                "system_all_characters_judged": 1,
                "threshold": threshold,
                "error_type": error_type,
                "system_tone_accuracy": scored.get("system_tone_accuracy", NA),
                "system_fluency": scored.get("system_fluency", NA),
                "human_accuracy": utterance.mean_rating("accuracy") or NA,
                "human_fluency": utterance.mean_rating("fluency") or NA,
                "human_prosody": utterance.mean_rating("prosody") or NA,
                "word_character_count": len(word.text),
                # Not carried by the cached scoring. See the module docstring.
                "duration_seconds": NA,
                "f0_mean": NA,
                "f0_min": NA,
                "f0_max": NA,
                "f0_range": NA,
                "f0_slope": NA,
                "alignment_score": NA,
                "diagnostic_status": NA,
                "audio_path": str(utterance.wav_path),
            })
    return rows


def _score_bin(value: Any, threshold: float) -> str:
    """Where a word's deciding score sits relative to the pass bar.

    A false rejection at 57 and one at 5 are different failures: the first is a
    borderline call, the second means the contour was read as moving the wrong
    way entirely.
    """
    if not isinstance(value, (int, float)):
        return NA
    distance = float(value) - threshold
    if distance >= 0:
        return "pass"
    for edge, label in ((-5, "just below (0-5)"), (-15, "below (5-15)"), (-30, "well below (15-30)")):
        if distance > edge:
            return label
    return "far below (30+)"


def summarize(rows: Sequence[dict[str, Any]], threshold: float) -> dict[str, Any]:
    """Break the disagreements down by every dimension the data supports."""
    def agreement(subset: Sequence[dict[str, Any]]) -> dict[str, Any]:
        if not subset:
            return {"n": 0}
        return binary_agreement(
            [bool(row["system_tone_correct"]) for row in subset],
            [bool(row["human_majority_tone_correct"]) for row in subset],
        )

    def group(key: str) -> dict[str, Any]:
        buckets: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            buckets[row[key]].append(row)
        return {
            str(name): agreement(subset)
            for name, subset in sorted(buckets.items(), key=lambda item: str(item[0]))
        }

    errors = [row for row in rows if row["error_type"]]
    by_score_bin = Counter(
        _score_bin(row["system_min_character_score"], threshold)
        for row in rows
        if row["error_type"] == FALSE_REJECTION
    )
    worst_words = Counter(
        row["word"] for row in rows if row["error_type"] == FALSE_REJECTION
    )
    worst_speakers = Counter(
        row["speaker_id"] for row in rows if row["error_type"] == FALSE_REJECTION
    )

    return {
        "n": len(rows),
        "overall": agreement(rows),
        "by_expected_tone": group("expected_tone"),
        "by_population": group("is_native"),
        "by_join_source": group("join_source"),
        "by_word_character_count": group("word_character_count"),
        "false_rejection_by_score_distance": dict(by_score_bin.most_common()),
        "most_false_rejected_words": worst_words.most_common(20),
        "speakers_with_most_false_rejections": worst_speakers.most_common(10),
        "error_counts": Counter(row["error_type"] for row in errors),
        "unavailable_dimensions": {
            "duration_bin": "duration is not stored by the cached scoring",
            "alignment_quality": "no alignment score is stored per syllable",
            "diagnostic_status": "cached rows predate the four-state diagnosis",
        },
    }


def write_csv(rows: Sequence[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export(
    rows: Sequence[dict[str, Any]], results_dir: Path
) -> dict[str, int]:
    """Write the full table and the two disagreement tables."""
    written = {
        "human_vs_system.csv": write_csv(rows, results_dir / "human_vs_system.csv"),
        "tone_false_acceptance.csv": write_csv(
            [row for row in rows if row["error_type"] == FALSE_ACCEPTANCE],
            results_dir / "tone_false_acceptance.csv",
        ),
        "tone_false_rejection.csv": write_csv(
            [row for row in rows if row["error_type"] == FALSE_REJECTION],
            results_dir / "tone_false_rejection.csv",
        ),
    }
    return written
