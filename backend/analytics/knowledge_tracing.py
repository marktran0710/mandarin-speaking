"""Small, dependency-free PFA/BKT pilot utilities for vocabulary quizzes.

The module deliberately consumes plain database/API dictionaries so a router can
call it without coupling the pilot to SQLAlchemy, Pydantic, or a new schema.
It is not a grading or recommendation policy: it only exposes probability and
model state derived from historical quiz responses.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import exp, isfinite, log
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
import unicodedata

from scipy.optimize import minimize


EPSILON = 1e-9


@dataclass(frozen=True)
class ResponseRecord:
    """One valid, ordered student response suitable for knowledge tracing."""

    student_id: str
    concept_id: str
    correct: bool
    occurred_at: Optional[datetime]
    attempt_id: str
    question_index: int
    story_id: Optional[str] = None
    item_id: Optional[str] = None
    question_kind: Optional[str] = None
    level: Optional[str] = None
    mode: Optional[str] = None
    item_version: Optional[str] = None
    identity_source: str = "concept_id"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["occurred_at"] = self.occurred_at.isoformat() if self.occurred_at else None
        return data


@dataclass
class NormalizationResult:
    records: list[ResponseRecord]
    counters: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {"records": [record.to_dict() for record in self.records], "counters": dict(self.counters)}


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _normalise_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    return value.casefold() or None


def _parse_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            parsed = datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def normalize_vocab_attempts(attempts: Iterable[Any]) -> NormalizationResult:
    """Convert vocab attempt dictionaries (or Pydantic-like objects) to records.

    ``conceptId`` is preferred. Older payloads use normalized ``word`` as their
    concept key. Invalid attempts/items are skipped and reflected in counters
    rather than silently being interpreted as incorrect answers.
    """
    counters = {
        "attempts_seen": 0, "attempts_without_student": 0, "attempts_without_results": 0,
        "attempts_without_id": 0,
        "items_seen": 0, "records_emitted": 0, "duplicate_responses": 0, "skipped_missing_concept": 0,
        "skipped_invalid_correct": 0, "legacy_word_fallback": 0, "invalid_timestamp": 0,
    }
    sortable: list[tuple[tuple[Any, ...], ResponseRecord]] = []
    seen_response_keys: set[tuple[str, str, int]] = set()
    for attempt_position, attempt in enumerate(attempts):
        counters["attempts_seen"] += 1
        student_id = _normalise_text(_field(attempt, "studentId", _field(attempt, "student_id")))
        if student_id is None:
            student_id = _normalise_text(_field(attempt, "studentName", _field(attempt, "student_name")))
        if student_id is None:
            counters["attempts_without_student"] += 1
            continue
        attempt_id = _normalise_text(_field(attempt, "id"))
        if attempt_id is None:
            # Do not fingerprint an id-less attempt from its contents: two
            # legitimate retries can have identical answers. Without a stable
            # identity we keep both observations and report the limitation.
            counters["attempts_without_id"] += 1
            attempt_id = f"legacy-attempt-{attempt_position}"
        raw_time = _field(attempt, "completedAt", _field(attempt, "completed_at"))
        occurred_at = _parse_time(raw_time)
        if raw_time is not None and occurred_at is None:
            counters["invalid_timestamp"] += 1
        results = _field(attempt, "questionResults", _field(attempt, "question_results", []))
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)) or not results:
            counters["attempts_without_results"] += 1
            continue
        for question_index, result in enumerate(results):
            counters["items_seen"] += 1
            concept_id = _normalise_text(_field(result, "conceptId", _field(result, "concept_id")))
            identity_source = "concept_id"
            if concept_id is None:
                concept_id = _normalise_text(_field(result, "word"))
                if concept_id is None:
                    counters["skipped_missing_concept"] += 1
                    continue
                counters["legacy_word_fallback"] += 1
                identity_source = "word_fallback"
            correct = _field(result, "correct")
            if not isinstance(correct, bool):
                counters["skipped_invalid_correct"] += 1
                continue
            response_key = (student_id, attempt_id, question_index)
            if response_key in seen_response_keys:
                counters["duplicate_responses"] += 1
                continue
            seen_response_keys.add(response_key)
            record = ResponseRecord(
                student_id=student_id,
                concept_id=concept_id,
                correct=correct,
                occurred_at=occurred_at,
                attempt_id=attempt_id,
                question_index=question_index,
                story_id=_normalise_text(_field(attempt, "baseStoryId", _field(attempt, "storyId", _field(attempt, "story_id")))),
                item_id=_normalise_text(_field(result, "itemId", _field(result, "item_id"))),
                question_kind=_normalise_text(_field(result, "questionKind", _field(result, "question_kind"))),
                level=_normalise_text(_field(result, "level")),
                mode=_normalise_text(_field(attempt, "mode")),
                item_version=_normalise_text(_field(result, "itemVersion", _field(result, "item_version"))),
                identity_source=identity_source,
            )
            # Timestamp-less legacy attempts retain incoming order and sort after dated records.
            timestamp = occurred_at.timestamp() if occurred_at else float("inf")
            sortable.append(((timestamp, attempt_position, question_index), record))
            counters["records_emitted"] += 1
    sortable.sort(key=lambda item: item[0])
    return NormalizationResult([record for _, record in sortable], counters)


def _clamp_probability(value: float) -> float:
    return min(1.0 - EPSILON, max(EPSILON, value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return _clamp_probability(1.0 / (1.0 + exp(-value)))
    positive = exp(value)
    return _clamp_probability(positive / (1.0 + positive))


@dataclass(frozen=True)
class PFAParameters:
    intercept: float = 0.0
    success_weight: float = 0.35
    failure_weight: float = -0.55
    l2: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class PFAState:
    successes: int = 0
    failures: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class PFA:
    """Online Performance Factors Analysis with per-student/concept counts."""

    def __init__(self, parameters: PFAParameters = PFAParameters()) -> None:
        self.parameters = parameters
        self._states: dict[tuple[str, str], PFAState] = {}

    def state_for(self, student_id: str, concept_id: str) -> PFAState:
        state = self._states.get((student_id, concept_id), PFAState())
        return PFAState(state.successes, state.failures)

    def predict(self, student_id: str, concept_id: str) -> float:
        state = self.state_for(student_id, concept_id)
        p = self.parameters
        return _sigmoid(p.intercept + p.success_weight * state.successes + p.failure_weight * state.failures)

    def update(self, record: ResponseRecord) -> PFAState:
        key = (record.student_id, record.concept_id)
        state = self._states.setdefault(key, PFAState())
        if record.correct:
            state.successes += 1
        else:
            state.failures += 1
        return self.state_for(*key)

    def observe(self, record: ResponseRecord) -> dict[str, Any]:
        prediction = self.predict(record.student_id, record.concept_id)
        state = self.update(record)
        return {"prediction": prediction, "state": state.to_dict()}

    def states(self) -> dict[str, dict[str, int]]:
        return {f"{student}\u001f{concept}": state.to_dict() for (student, concept), state in self._states.items()}


def fit_pfa_parameters(
    records: Iterable[ResponseRecord], *, initial: PFAParameters = PFAParameters(),
    iterations: int = 200, learning_rate: float = 0.08,
) -> PFAParameters:
    """Fit global PFA coefficients by L2-regularized batch gradient descent.

    Histories are generated sequentially, so each row only sees earlier events
    for the same student and concept. The supplied ``l2`` applies to fitted
    coefficients; a non-positive value disables regularization intentionally.
    """
    ordered = list(records)
    if not ordered:
        return initial
    counts: dict[tuple[str, str], PFAState] = {}
    rows: list[tuple[tuple[float, float, float], float]] = []
    for record in ordered:
        state = counts.setdefault((record.student_id, record.concept_id), PFAState())
        rows.append(((1.0, float(state.successes), float(state.failures)), float(record.correct)))
        if record.correct:
            state.successes += 1
        else:
            state.failures += 1
    weights = [initial.intercept, initial.success_weight, initial.failure_weight]
    penalty = max(0.0, initial.l2)
    for _ in range(max(0, iterations)):
        gradient = [0.0, 0.0, 0.0]
        for features, outcome in rows:
            probability = _sigmoid(sum(weight * feature for weight, feature in zip(weights, features)))
            for index, feature in enumerate(features):
                gradient[index] += (probability - outcome) * feature
        for index in range(3):
            gradient[index] = gradient[index] / len(rows) + penalty * weights[index] / len(rows)
            weights[index] -= learning_rate * gradient[index]
    return PFAParameters(*weights, l2=initial.l2)


@dataclass(frozen=True)
class BKTParameters:
    prior: float = 0.2
    learn: float = 0.15
    guess: float = 0.2
    slip: float = 0.1

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite probability in [0, 1]")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


class BKT:
    """Global-parameter Bayesian Knowledge Tracing with per-learner concepts."""

    def __init__(self, parameters: BKTParameters = BKTParameters()) -> None:
        self.parameters = parameters
        self._mastery: dict[tuple[str, str], float] = {}

    def mastery_for(self, student_id: str, concept_id: str) -> float:
        return self._mastery.get((student_id, concept_id), self.parameters.prior)

    def predict(self, student_id: str, concept_id: str) -> float:
        mastery = self.mastery_for(student_id, concept_id)
        p = mastery * (1.0 - self.parameters.slip) + (1.0 - mastery) * self.parameters.guess
        return _clamp_probability(p)

    def update(self, record: ResponseRecord) -> dict[str, float]:
        key = (record.student_id, record.concept_id)
        prior = self.mastery_for(*key)
        probability = self.predict(*key)
        if record.correct:
            posterior = prior * (1.0 - self.parameters.slip) / probability
        else:
            posterior = prior * self.parameters.slip / (1.0 - probability)
        mastery = posterior + (1.0 - posterior) * self.parameters.learn
        self._mastery[key] = _clamp_probability(mastery)
        return {"prior_mastery": prior, "posterior_mastery": _clamp_probability(posterior), "mastery": self._mastery[key]}

    def observe(self, record: ResponseRecord) -> dict[str, Any]:
        prediction = self.predict(record.student_id, record.concept_id)
        state = self.update(record)
        return {"prediction": prediction, "state": state}

    def states(self) -> dict[str, float]:
        return {f"{student}\u001f{concept}": mastery for (student, concept), mastery in self._mastery.items()}


def fit_bkt_parameters(
    records: Iterable[ResponseRecord], *, initial: BKTParameters = BKTParameters(),
    iterations: int = 80,
) -> BKTParameters:
    """Fit one global BKT parameter set on an ordered training prefix.

    BKT parameters are shared across skills in this pilot because individual
    words are too sparse for reliable per-skill estimates. The objective is
    the same pre-response likelihood later used for evaluation, with a small
    prior penalty that keeps a small prefix near the transparent defaults.
    """
    ordered = list(records)
    if not ordered:
        return initial

    initial_values = [initial.prior, initial.learn, initial.guess, initial.slip]

    def objective(values: Sequence[float]) -> float:
        parameters = BKTParameters(*values)
        tracer = BKT(parameters)
        loss = 0.0
        for record in ordered:
            probability = tracer.predict(record.student_id, record.concept_id)
            loss -= log(probability if record.correct else 1.0 - probability)
            tracer.update(record)
        penalty = 0.05 * sum((value - base) ** 2 for value, base in zip(values, initial_values))
        return loss / len(ordered) + penalty

    result = minimize(
        objective,
        initial_values,
        method="L-BFGS-B",
        bounds=[(0.001, 0.999)] * 4,
        options={"maxiter": max(1, iterations)},
    )
    return BKTParameters(*[float(value) for value in result.x])


def _auc(outcomes: list[bool], predictions: list[float]) -> Optional[float]:
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    if not positives or not negatives:
        return None
    ranked = sorted(zip(predictions, outcomes), key=lambda pair: pair[0])
    rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][0] == ranked[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum += average_rank * sum(outcome for _, outcome in ranked[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _calibration_error(outcomes: list[bool], predictions: list[float], bins: int) -> float:
    total = len(outcomes)
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [offset for offset, probability in enumerate(predictions) if low <= probability < high or (index == bins - 1 and probability == 1.0)]
        if members:
            observed = sum(outcomes[offset] for offset in members) / len(members)
            expected = sum(predictions[offset] for offset in members) / len(members)
            error += len(members) / total * abs(observed - expected)
    return error


def evaluate_prequential(
    records: Iterable[ResponseRecord], *, model: str = "pfa", train_fraction: float = 0.5,
    pfa_parameters: PFAParameters = PFAParameters(), bkt_parameters: BKTParameters = BKTParameters(),
    calibration_bins: int = 10, include_auc: bool = True,
) -> dict[str, Any]:
    """Evaluate ordered responses on the later time split, prequentially.

    The first fraction establishes each learner's model state. For PFA, it
    additionally estimates global regularized coefficients on that prefix.
    Every evaluation prediction is made before its outcome updates the state.
    """
    ordered = list(records)
    if model not in {"pfa", "bkt"}:
        raise ValueError("model must be 'pfa' or 'bkt'")
    if not 0.0 <= train_fraction < 1.0:
        raise ValueError("train_fraction must be in [0, 1)")
    if calibration_bins < 1:
        raise ValueError("calibration_bins must be at least 1")
    split = min(len(ordered), int(len(ordered) * train_fraction))
    prefix, evaluation = ordered[:split], ordered[split:]
    if model == "pfa":
        fitted = fit_pfa_parameters(prefix, initial=pfa_parameters) if prefix else pfa_parameters
        tracer: Any = PFA(fitted)
        parameters = fitted.to_dict()
    else:
        fitted = fit_bkt_parameters(prefix, initial=bkt_parameters) if prefix else bkt_parameters
        tracer = BKT(fitted)
        parameters = fitted.to_dict()
    for record in prefix:
        tracer.update(record)
    predictions: list[float] = []
    outcomes: list[bool] = []
    for record in evaluation:
        predictions.append(tracer.predict(record.student_id, record.concept_id))
        outcomes.append(record.correct)
        tracer.update(record)
    if not outcomes:
        metrics = {
            "n": 0,
            "positive_count": 0,
            "negative_count": 0,
            "log_loss": None,
            "brier": None,
            "calibration_error": None,
            "auc": None,
        }
    else:
        metrics = {
            "n": len(outcomes),
            "positive_count": sum(outcomes),
            "negative_count": len(outcomes) - sum(outcomes),
            "log_loss": -sum((log(probability) if outcome else log(1.0 - probability)) for probability, outcome in zip(predictions, outcomes)) / len(outcomes),
            "brier": sum((probability - float(outcome)) ** 2 for probability, outcome in zip(predictions, outcomes)) / len(outcomes),
            "calibration_error": _calibration_error(outcomes, predictions, calibration_bins),
            "auc": _auc(outcomes, predictions) if include_auc else None,
        }
    return {"model": model, "train_n": len(prefix), "parameters": parameters, "metrics": metrics, "final_state": tracer.states()}


def evaluate_vocab_attempts(
    attempts: Iterable[Any], *, model: str = "pfa", train_fraction: float = 0.5,
    pfa_parameters: PFAParameters = PFAParameters(), bkt_parameters: BKTParameters = BKTParameters(),
    calibration_bins: int = 10, include_auc: bool = True,
) -> dict[str, Any]:
    """Dict-friendly router entry point for a collection of stored attempts."""
    normalized = normalize_vocab_attempts(attempts)
    result = evaluate_prequential(
        normalized.records, model=model, train_fraction=train_fraction,
        pfa_parameters=pfa_parameters, bkt_parameters=bkt_parameters,
        calibration_bins=calibration_bins, include_auc=include_auc,
    )
    result["data_quality"] = normalized.counters
    return result
