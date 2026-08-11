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
    join_summary,
)
from benchmarking.stats import binary_agreement, pearson, spearman
from benchmarking.tone_release_gate import evaluate_tone_release_gate

PRODUCTION_THRESHOLD = 58.0

# The agreed evaluation contract (see the M0 protocol). Frozen deliberately:
# changing any of these silently would make results across runs incomparable.
RATER_PANEL_SIZE = 3
TARGET_KAPPA = 0.70
#: Marker for criteria OMPAL annotates but the analyzer cannot assess.
UNSUPPORTED = "unsupported"

# Protocol change, 2026-08-06, recorded rather than absorbed: the headline was
# agreement with each rater *individually*, which turned out to be bounded away
# from the target by construction. A perfect system -- one emitting the rater
# majority exactly -- scores only 0.606-0.744 against an individual rater,
# because each rater carries their own noise. A 0.70 target sat inside that
# band, so it demanded noise-free performance.
#
# The headline is now agreement with the 3-rater *majority*. Against that
# label a perfect system scores 1.0, so 0.70 is demanding but genuinely
# reachable rather than bounded away. Per-rater agreement is still computed
# and reported, now as context.
#
# Numbers before and after this change are NOT comparable: agreeing with a
# majority is an easier task than agreeing with one noisy individual.
HEADLINE_LABEL = "majority"

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
    """System agreement with each rater separately, averaged. Reported as context.

    This keeps both sides of the comparison "one judge vs one judge", which is
    what makes it directly comparable to the rater-vs-rater ceiling. It is
    systematically lower than the headline majority figure, because agreeing
    with one noisy individual is harder than agreeing with a panel's majority
    -- so a shortfall here is expected and is not the headline falling short.

    It also carries a hard bound the headline does not: a perfect system emits
    the majority, and even that scores only 0.606-0.744 against an individual
    rater. See ``oracle_bound``.
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
        # Deliberately no target/meets_target here: the headline target is
        # defined against the majority label, and applying it to the harder
        # per-rater task would report a failure that the contract never asked
        # for. The oracle bound is the reference for these numbers.
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
                # Secondary only: the two scales are not linearly comparable,
                # so rank correlation is the primary figure.
                "pearson_correlation": pearson(list(system_scores), list(teacher_scores)),
                "mean_human_rating": sum(teacher_scores) / len(teacher_scores),
                "mean_system_score": sum(system_scores) / len(system_scores),
                "human_scale": "OMPAL 1-5 rubric",
                "system_scale": "0-100",
            }
        else:
            result[name] = {"n": 0, "spearman_correlation": None}
    # OMPAL rates prosody 1-5, but nothing in the analyzer produces a prosody
    # score: the pipeline emits tone accuracy, fluency and per-word prosody
    # shape, none of which is the same construct. Reported as unsupported
    # rather than substituted with the nearest-looking number.
    result["prosody"] = {
        "n": 0,
        "status": UNSUPPORTED,
        "human_label_count": sum(
            1 for utterance in utterances if utterance.rater_prosody
        ),
        "reason": (
            "No system output corresponds to OMPAL's sentence-level prosody "
            "rating. Substituting tone accuracy or fluency would compare two "
            "different constructs."
        ),
    }
    result["spearman_correlation"] = result["accuracy"]["spearman_correlation"]
    return result


def _segmental_support(utterances: Sequence[OmpalUtterance]) -> dict[str, Any]:
    """State how many human consonant/vowel labels exist, and why none is used.

    The corpus rates three word-level criteria; the analyzer scores one. These
    entries exist so the count of unused human labels is visible in the report
    instead of the criteria simply being absent, which would read as though
    OMPAL had not annotated them.
    """
    consonant = sum(
        1 for u in utterances for w in u.words if w.rater_consonant_labels
    )
    vowel = sum(1 for u in utterances for w in u.words if w.rater_vowel_labels)
    return {
        "consonant": {
            "status": UNSUPPORTED,
            "human_label_count": consonant,
            "system_output": None,
            "reason": (
                "No consonant classifier exists. The pipeline has no "
                "phoneme-level forced alignment and no goodness-of-pronunciation "
                "measure, so there is nothing to compare these labels against."
            ),
        },
        "vowel": {
            "status": UNSUPPORTED,
            "human_label_count": vowel,
            "system_output": "F1/F2 per syllable (diagnostic measurement only)",
            "reason": (
                "Formants are measured per syllable but deliberately produce no "
                "correct/incorrect verdict: a short utterance does not contain "
                "enough distinct vowels to normalise a speaker reliably. "
                "Thresholding them here purely to obtain a number would "
                "manufacture the very verdict the analyzer declines to make."
            ),
        },
    }


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
        # The headline: system vs the 3-rater majority (see HEADLINE_LABEL).
        "pass_fail_agreement": overall,
        # Context. Agreeing with one noisy individual is a harder task than
        # agreeing with their majority, so these numbers are lower by nature
        # and must not be read as the headline falling short.
        "per_rater_agreement": primary,
        "oracle_bound": bound,
        "by_expected_tone": by_tone,
        "by_population": {
            "learners": _agreement(learners) if learners else {"n": 0},
            "natives": _agreement(natives) if natives else {"n": 0},
        },
        "human_ceiling": ceiling,
        "score_agreement": sentence,
        # Criteria OMPAL rates that the system cannot produce. Carried in the
        # report so "not measured" is never mistaken for "measured and fine".
        "segmental_support": _segmental_support(utterances),
        "join_provenance": join_summary(utterances),
        "exclusions": exclusions,
        "audit": {
            "disagreement_count": len(disagreements),
            "disagreements": disagreements[:audit_limit],
            "truncated": len(disagreements) > audit_limit,
        },
    }
    report["verdict"] = _build_verdict(overall, primary, ceiling, bound)
    report["release_gate"] = _build_gate(report)
    return report


def _build_verdict(
    overall: dict[str, Any],
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
    system_kappa = overall.get("cohen_kappa")
    per_rater_kappa = primary.get("mean_cohen_kappa")
    ceiling_kappa = ceiling.get("fleiss_kappa")
    low = bound.get("uncontaminated")
    high = bound.get("contaminated")

    meets = system_kappa is not None and system_kappa >= TARGET_KAPPA
    verdict: dict[str, Any] = {
        "system_kappa": system_kappa,
        "compared_against": HEADLINE_LABEL,
        "per_rater_kappa": per_rater_kappa,
        "target": TARGET_KAPPA,
        "meets_target": meets,
        "human_ceiling_kappa": ceiling_kappa,
        "attainable_max_low": low,
        "attainable_max_high": high,
    }

    if system_kappa is None:
        verdict["level"] = "unknown"
        verdict["summary"] = "Not enough judged data to measure agreement."
        return verdict

    if meets:
        verdict["level"] = "meets_target"
        verdict["summary"] = (
            f"The system agrees with the teacher panel's majority at kappa "
            f"{system_kappa:.3f}, meeting the {TARGET_KAPPA:g} target."
        )
        return verdict

    gap = TARGET_KAPPA - system_kappa
    verdict["level"] = "near_target" if gap <= 0.1 else "below_target"
    summary = (
        f"The system agrees with the teacher panel's majority at kappa "
        f"{system_kappa:.3f}, short of the {TARGET_KAPPA:g} target by {gap:.3f}."
    )
    # State plainly when the committed target sits at or above what a perfect
    # system could reach, rather than letting it read as ordinary underperformance.
    # Against the majority label a perfect system scores 1.0, so the oracle
    # bound that made the old target unreachable no longer applies. It is kept
    # in the report as context for the per-rater numbers.
    if HEADLINE_LABEL != "majority" and low is not None and TARGET_KAPPA > low:
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
