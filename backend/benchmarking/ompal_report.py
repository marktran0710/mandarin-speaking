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

# The agreed evaluation contract (see the M0 protocol). Frozen deliberately:
# changing any of these silently would make results across runs incomparable.
RATER_PANEL_SIZE = 3
TARGET_KAPPA = 0.61  # Landis-Koch "substantial agreement"

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
    panel_size: int = RATER_PANEL_SIZE,
) -> tuple[list[dict[str, Any]], dict[str, int], list[list[bool]]]:
    """Pair every rated word with the system's verdict at ``threshold``.

    Restricted to words carrying a full ``panel_size`` rater panel. Mixing
    panel sizes would make the per-rater agreement mean an average over
    different-sized panels, which is not a single interpretable quantity.
    """
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

        entries = scored.get("characters") or []
        # A record predating the judged flag cannot be interpreted safely: its
        # placeholder zeros are indistinguishable from real failing scores.
        legacy = any("judged" not in entry for entry in entries)
        characters = [
            (str(entry.get("char") or ""), float(entry.get("score") or 0.0) >= threshold)
            for entry in entries
        ]
        judged_flags = [bool(entry.get("judged", True)) for entry in entries]
        verdicts = align_system_characters(utterance.words, characters)
        if verdicts is None:
            exclusions["alignment_mismatch"] += 1
            continue
        if legacy:
            exclusions["legacy_record_without_judged_flag"] += 1
            continue

        position = 0
        for word, system_passed in zip(utterance.words, verdicts):
            span = slice(position, position + len(word.text))
            word_judged = all(judged_flags[span])
            position += len(word.text)

            if word.has_neutral_tone:
                exclusions["neutral_tone"] += 1
                continue
            if not word_judged:
                # The analyzer withheld a verdict here; counting it as a
                # failure would penalise the system for declining to guess.
                exclusions["unjudged_by_analyzer"] += 1
                continue
            if len(word.rater_tone_labels) != panel_size:
                exclusions["incomplete_rater_panel"] += 1
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


def per_rater_agreement(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The headline: system agreement with each rater separately, then averaged.

    This is the framing chosen for the target. Scoring against a rater panel's
    majority is an easier task, because averaging cancels individual rater
    noise, so a majority-based figure must never be compared against a
    rater-vs-rater ceiling. Measuring against each individual keeps both sides
    of the comparison "one judge vs one judge".
    """
    if not rows:
        return {"n": 0, "mean_cohen_kappa": None, "per_rater": [], "meets_target": False}
    panel = len(rows[0]["rater_labels"])
    system = [row["system_passed"] for row in rows]
    per_rater = []
    for index in range(panel):
        result = binary_agreement(system, [row["rater_labels"][index] for row in rows])
        per_rater.append({
            "rater": index + 1,
            "cohen_kappa": result["cohen_kappa"],
            "accuracy": result["accuracy"],
        })
    kappas = [entry["cohen_kappa"] for entry in per_rater if entry["cohen_kappa"] is not None]
    mean_kappa = sum(kappas) / len(kappas) if kappas else None
    return {
        "n": len(rows),
        "rater_count": panel,
        "mean_cohen_kappa": mean_kappa,
        "per_rater": per_rater,
        "target": TARGET_KAPPA,
        "meets_target": mean_kappa is not None and mean_kappa >= TARGET_KAPPA,
    }


def oracle_bound(panel: Sequence[Sequence[bool]]) -> dict[str, Any]:
    """How well a *perfect* system could agree with an individual rater.

    The rater-vs-rater ceiling is not an upper bound for a machine: two noisy
    judges agreeing at 0.49 is consistent with a noise-free judge agreeing far
    better with either of them. This measures that directly by treating the
    rater majority as a perfect system.

    ``contaminated`` is optimistic because each rater helps define the majority
    it is scored against. ``uncontaminated`` removes that by using only the
    other raters, but is undefined when they disagree, so it drops those items
    and is therefore optimistic in a different way. The true bound lies
    between them, and both are reported rather than picking one.
    """
    rows = [list(rater) for rater in panel]
    if len(rows) < 2 or not rows[0]:
        return {"contaminated": None, "uncontaminated": None, "dropped_for_ties": None}
    count = len(rows[0])
    majority = [sum(rater[i] for rater in rows) * 2 > len(rows) for i in range(count)]
    contaminated = [
        value
        for rater in rows
        if (value := binary_agreement(majority, rater)["cohen_kappa"]) is not None
    ]

    clean: list[float] = []
    dropped = 0
    for index, rater in enumerate(rows):
        others = [other for position, other in enumerate(rows) if position != index]
        predicted, actual = [], []
        for i in range(count):
            values = {other[i] for other in others}
            if len(values) != 1:
                continue
            predicted.append(values.pop())
            actual.append(rater[i])
        dropped = count - len(actual)
        value = binary_agreement(predicted, actual)["cohen_kappa"] if actual else None
        if value is not None:
            clean.append(value)

    return {
        "contaminated": sum(contaminated) / len(contaminated) if contaminated else None,
        "uncontaminated": sum(clean) / len(clean) if clean else None,
        "dropped_for_ties": dropped,
    }


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
    primary = per_rater_agreement(rows)
    bound = oracle_bound(panel)

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
        # The agreed headline: system vs each rater individually.
        "per_rater_agreement": primary,
        # Context only. Scoring against the majority is an easier task, so this
        # must never be quoted against a rater-vs-rater ceiling.
        "pass_fail_agreement": overall,
        "oracle_bound": bound,
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
    report["verdict"] = _build_verdict(primary, ceiling, bound)
    report["release_gate"] = _build_gate(report)
    return report


def _build_verdict(
    primary: dict[str, Any],
    ceiling: dict[str, Any],
    bound: dict[str, Any],
) -> dict[str, Any]:
    """Judge the headline kappa against the agreed target and what is attainable.

    Three numbers are needed to read a kappa honestly, so all three are carried
    here: the target that was committed to, how well the raters agreed with
    each other, and how well a perfect system could possibly do. Reporting the
    target alone would hide the case where the target sits above the attainable
    maximum -- which is a real risk for this corpus.
    """
    system_kappa = primary.get("mean_cohen_kappa")
    ceiling_kappa = ceiling.get("fleiss_kappa")
    low = bound.get("uncontaminated")
    high = bound.get("contaminated")

    verdict: dict[str, Any] = {
        "system_kappa": system_kappa,
        "target": TARGET_KAPPA,
        "meets_target": bool(primary.get("meets_target")),
        "human_ceiling_kappa": ceiling_kappa,
        "attainable_max_low": low,
        "attainable_max_high": high,
    }

    if system_kappa is None:
        verdict["level"] = "unknown"
        verdict["summary"] = "Not enough judged data to measure agreement."
        return verdict

    if primary.get("meets_target"):
        verdict["level"] = "meets_target"
        verdict["summary"] = (
            f"The system agrees with an individual teacher at kappa "
            f"{system_kappa:.3f}, meeting the {TARGET_KAPPA:g} target."
        )
        return verdict

    gap = TARGET_KAPPA - system_kappa
    verdict["level"] = "near_target" if gap <= 0.1 else "below_target"
    summary = (
        f"The system agrees with an individual teacher at kappa "
        f"{system_kappa:.3f}, short of the {TARGET_KAPPA:g} target by {gap:.3f}."
    )
    # State plainly when the committed target sits at or above what a perfect
    # system could reach, rather than letting it read as ordinary underperformance.
    if low is not None and TARGET_KAPPA > low:
        limit = f"{low:.2f}" if high is None else f"{low:.2f}-{high:.2f}"
        summary += (
            f" Note: a perfect system scores only about {limit} against an "
            f"individual rater here, so the target sits at or above the "
            f"attainable maximum."
        )
    verdict["summary"] = summary
    return verdict


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
