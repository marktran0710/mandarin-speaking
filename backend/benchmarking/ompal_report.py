"""Turn scored OMPAL output into an auditable agreement report.

Kept separate from scoring so the pass threshold can be varied interactively:
scoring is minutes of Praat, this is milliseconds of arithmetic over stored
per-character scores.

Every exclusion is counted and reported rather than silently dropped. A metric
computed over an unstated subset is not auditable, and the excluded cases here
(neutral tones, alignment mismatches, unreadable audio) are exactly the ones a
reader would want to know about.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Sequence

from benchmarking.agreement import majority_label, rater_agreement_summary
from benchmarking.ompal_corpus import (
    CORPUS_CITATION,
    OmpalUtterance,
    align_system_characters,
)
from benchmarking.stats import binary_agreement, spearman
from benchmarking.tone_release_gate import evaluate_tone_release_gate

PRODUCTION_THRESHOLD = 58.0

POPULATION_CAVEAT = (
    "OMPAL speakers are French-L1 learners reading prompted sentences. These "
    "results validate the tone scorer itself; they do not directly predict "
    "behaviour for learners with a different first language or for "
    "free-speech scene prompts."
)
MAE_NOT_APPLICABLE = (
    "Not applicable: OMPAL rates utterances on a 1-5 rubric, which cannot be "
    "converted to the 0-100 scale this metric compares against without "
    "inventing an unvalidated mapping. Rank correlation is reported instead."
)


def _judgement_rows(
    utterances: Sequence[OmpalUtterance],
    scored_rows: Iterable[dict[str, Any]],
    threshold: float,
) -> tuple[list[dict[str, Any]], dict[str, int], list[list[bool]]]:
    """Pair every rated word with the system's verdict at ``threshold``."""
    by_id = {utterance.utterance_id: utterance for utterance in utterances}
    rows: list[dict[str, Any]] = []
    exclusions = Counter()
    rater_panels: list[tuple[bool, ...]] = []

    for scored in scored_rows:
        utterance = by_id.get(scored.get("utterance_id"))
        if utterance is None:
            exclusions["utterance_not_in_corpus"] += 1
            continue
        if scored.get("error"):
            exclusions["analyzer_error"] += 1
            continue

        characters = [
            (str(entry.get("char") or ""), float(entry.get("score") or 0.0) >= threshold)
            for entry in scored.get("characters") or []
        ]
        verdicts = align_system_characters(utterance.words, characters)
        if verdicts is None:
            exclusions["alignment_mismatch"] += 1
            continue

        for word, system_passed in zip(utterance.words, verdicts):
            if word.has_neutral_tone:
                exclusions["neutral_tone"] += 1
                continue
            teacher = majority_label(word.rater_tone_labels)
            if teacher is None:
                exclusions["no_rater_labels"] += 1
                continue
            rows.append({
                "utterance_id": utterance.utterance_id,
                "speaker_id": utterance.speaker_id,
                "is_native": utterance.is_native,
                "word": word.text,
                "expected_tone": (
                    word.expected_tones[0] if len(word.expected_tones) == 1 else None
                ),
                "system_passed": system_passed,
                "teacher_passed": teacher,
                "rater_labels": list(word.rater_tone_labels),
            })
            if not utterance.is_native:
                rater_panels.append(word.rater_tone_labels)

    return rows, dict(exclusions), _panel_matrix(rater_panels)


def _panel_matrix(panels: Sequence[tuple[bool, ...]]) -> list[list[bool]]:
    """Build a rater x item matrix from panels of the most common size.

    Inter-rater statistics require a fixed panel. Utterances rated by a
    differently sized panel are left out of the ceiling rather than padded,
    which would fabricate agreement that was never observed.
    """
    if not panels:
        return []
    sizes = Counter(len(panel) for panel in panels)
    modal_size, _ = sizes.most_common(1)[0]
    if modal_size < 2:
        return []
    usable = [panel for panel in panels if len(panel) == modal_size]
    return [[panel[index] for panel in usable] for index in range(modal_size)]


def _subset(rows: Sequence[dict[str, Any]], native: bool) -> list[dict[str, Any]]:
    return [row for row in rows if row["is_native"] is native]


def _agreement(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return binary_agreement(
        [row["system_passed"] for row in rows],
        [row["teacher_passed"] for row in rows],
    )


def _sentence_correlations(
    utterances: Sequence[OmpalUtterance], scored_rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Rank correlation between system scores and mean teacher ratings.

    Deliberately no mean-absolute-error: a 1-5 rubric and a 0-100 score share
    no common unit, so an "average error" between them would be a fabricated
    number that looks more precise than the data supports.
    """
    by_id = {utterance.utterance_id: utterance for utterance in utterances}
    pairs: dict[str, list[tuple[float, float]]] = {"accuracy": [], "fluency": []}
    for scored in scored_rows:
        utterance = by_id.get(scored.get("utterance_id"))
        if utterance is None or scored.get("error"):
            continue
        for name, system_key in (
            ("accuracy", "system_tone_accuracy"),
            ("fluency", "system_fluency"),
        ):
            system_value = scored.get(system_key)
            teacher_value = utterance.mean_rating(name)
            if system_value is not None and teacher_value is not None:
                pairs[name].append((float(system_value), teacher_value))

    result: dict[str, Any] = {"mean_absolute_error": None, "note": MAE_NOT_APPLICABLE}
    for name, values in pairs.items():
        if values:
            system_scores, teacher_scores = zip(*values)
            result[name] = {
                "n": len(values),
                "spearman_correlation": spearman(list(system_scores), list(teacher_scores)),
            }
        else:
            result[name] = {"n": 0, "spearman_correlation": None}
    result["spearman_correlation"] = result["accuracy"]["spearman_correlation"]
    return result


def build_report(
    utterances: Sequence[OmpalUtterance],
    scored_rows: Sequence[dict[str, Any]],
    *,
    threshold: float = PRODUCTION_THRESHOLD,
    audit_limit: int = 50,
) -> dict[str, Any]:
    """Build the full agreement report at a given pass threshold."""
    rows, exclusions, panel = _judgement_rows(utterances, scored_rows, threshold)
    learners = _subset(rows, native=False)
    natives = _subset(rows, native=True)

    by_tone: dict[str, Any] = {}
    for tone in range(1, 5):
        tone_rows = [row for row in rows if row["expected_tone"] == tone]
        by_tone[str(tone)] = _agreement(tone_rows) if tone_rows else {"n": 0}

    ceiling = rater_agreement_summary(panel)
    overall = _agreement(rows) if rows else {"n": 0}
    sentence = _sentence_correlations(utterances, scored_rows)

    disagreements = [
        {
            "utterance_id": row["utterance_id"],
            "speaker_id": row["speaker_id"],
            "word": row["word"],
            "expected_tone": row["expected_tone"],
            "system_passed": row["system_passed"],
            "teacher_passed": row["teacher_passed"],
            "rater_labels": row["rater_labels"],
        }
        for row in rows
        if row["system_passed"] != row["teacher_passed"]
    ]

    scored_utterance_ids = {
        scored.get("utterance_id") for scored in scored_rows if not scored.get("error")
    }
    speaker_count = len({
        utterance.speaker_id
        for utterance in utterances
        if utterance.utterance_id in scored_utterance_ids
    })

    report = {
        "benchmark_protocol": {
            "threshold": threshold,
            "production_threshold": PRODUCTION_THRESHOLD,
            "recording_count": len(scored_utterance_ids),
            "speaker_count": speaker_count,
            "rated_word_count": len(rows),
            "rule": (
                "A system pass is character score >= threshold for every character "
                "in the rated word; the teacher label is the rater-panel majority."
            ),
            "citation": CORPUS_CITATION,
            "population_caveat": POPULATION_CAVEAT,
            "threshold_warning": (
                "The shipped threshold is "
                f"{PRODUCTION_THRESHOLD:g} and was not chosen using this corpus. "
                "Moving this slider is for diagnosis only; shipping a threshold "
                "picked here would be test-set leakage."
            ),
        },
        "pass_fail_agreement": overall,
        "by_expected_tone": by_tone,
        "by_population": {
            "learners": _agreement(learners) if learners else {"n": 0},
            "natives": _agreement(natives) if natives else {"n": 0},
        },
        "human_ceiling": ceiling,
        "score_agreement": sentence,
        "exclusions": exclusions,
        "audit": {
            "disagreement_count": len(disagreements),
            "disagreements": disagreements[:audit_limit],
            "truncated": len(disagreements) > audit_limit,
        },
    }
    report["verdict"] = _build_verdict(overall, ceiling)
    report["release_gate"] = _build_gate(report)
    return report


def _build_verdict(
    overall: dict[str, Any], ceiling: dict[str, Any]
) -> dict[str, Any]:
    """Compare the system's agreement against the human ceiling.

    This is the only number that answers "is the system good", because a kappa
    means nothing without knowing how well the experts agreed with each other.
    """
    system_kappa = overall.get("cohen_kappa")
    ceiling_kappa = ceiling.get("mean_pairwise_cohen_kappa")
    if system_kappa is None or ceiling_kappa is None:
        return {
            "system_kappa": system_kappa,
            "human_ceiling_kappa": ceiling_kappa,
            "ratio": None,
            "level": "unknown",
            "summary": "Not enough data to compare the system against the human ceiling.",
        }

    # A non-positive ceiling is a measured result, not a missing one: the
    # raters agreed no better than chance. Reporting it as "could not be
    # computed" would blame the tooling for what the data actually says, and
    # a ratio against it would be meaningless.
    if ceiling_kappa <= 0:
        return {
            "system_kappa": system_kappa,
            "human_ceiling_kappa": ceiling_kappa,
            "ratio": None,
            "level": "no_reliable_ceiling",
            "summary": (
                f"The teacher panel did not agree with each other beyond chance "
                f"(kappa {ceiling_kappa:.2f}), so there is no meaningful human "
                f"ceiling to compare the system's kappa ({system_kappa:.2f}) against."
            ),
        }

    ratio = system_kappa / ceiling_kappa
    if ratio >= 0.9:
        level = "at_human_level"
    elif ratio >= 0.7:
        level = "approaching_human"
    else:
        level = "below_human"

    summaries = {
        "at_human_level": (
            f"The system agrees with the teacher panel (kappa {system_kappa:.2f}) "
            f"about as well as the teachers agree with each other "
            f"(kappa {ceiling_kappa:.2f})."
        ),
        "approaching_human": (
            f"The system agrees with the teacher panel (kappa {system_kappa:.2f}), "
            f"below but within reach of how well the teachers agree with each "
            f"other (kappa {ceiling_kappa:.2f})."
        ),
        "below_human": (
            f"The system agrees with the teacher panel (kappa {system_kappa:.2f}), "
            f"clearly below how well the teachers agree with each other "
            f"(kappa {ceiling_kappa:.2f})."
        ),
    }
    return {
        "system_kappa": system_kappa,
        "human_ceiling_kappa": ceiling_kappa,
        "ratio": ratio,
        "level": level,
        "summary": summaries[level],
    }


def _build_gate(report: dict[str, Any]) -> dict[str, Any]:
    """Run the existing student-release gate over this report.

    The gate also requires a mean-absolute-error ceiling, which this corpus
    cannot supply (see MAE_NOT_APPLICABLE). Rather than invent a value or
    quietly drop the criterion, that single check is reported as not
    applicable and the overall verdict is marked incomplete.
    """
    result = evaluate_tone_release_gate(report)
    checks = []
    for check in result.checks:
        applicable = check.name != "mean_absolute_error"
        checks.append({
            "name": check.name,
            "passed": check.passed,
            "actual": check.actual,
            "operator": check.operator,
            "threshold": check.threshold,
            "detail": MAE_NOT_APPLICABLE if not applicable else check.detail,
            "applicable": applicable,
        })
    applicable_checks = [check for check in checks if check["applicable"]]
    return {
        "checks": checks,
        "applicable_passed": all(check["passed"] for check in applicable_checks),
        "complete": False,
        "note": (
            "Incomplete: this corpus cannot supply an absolute-scale score error, "
            "so the mean-absolute-error criterion is not applicable here."
        ),
    }
