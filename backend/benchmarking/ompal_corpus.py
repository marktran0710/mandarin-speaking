"""Load the OMPAL corpus of expert-rated Mandarin utterances.

OMPAL (https://github.com/phantomhsieh/OMPAL-corpus, CC BY 4.0) contains 1,850
utterances from 3 native speakers and 46 French-L1 learners, each rated by a
panel of experts. Every character carries a binary tone judgement per rater,
and every utterance carries 1-5 accuracy / fluency / prosody ratings per rater.

This module only acquires and parses the corpus. It computes no metrics and
runs no scoring, so it can be tested without audio or a network connection.

Note the population caveat that belongs with any result derived from it: these
are French-L1 learners reading prompted sentences. The corpus validates the
tone scorer itself; it does not directly predict behaviour on a different L1.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import httpx

from chinese_tones import word_tones

CORPUS_URL = "https://github.com/phantomhsieh/OMPAL-corpus/archive/refs/heads/main.zip"
CORPUS_CITATION = (
    "OMPAL corpus (phantomhsieh/OMPAL-corpus), licensed CC BY 4.0. "
    "82 native and 1,768 French-L1 learner Mandarin utterances with expert ratings."
)
NEUTRAL_TONE = 5

ProgressCallback = Callable[[int, int], None]


# How each utterance's annotations were joined to its audio. Carried on every
# record so any result can be split by provenance and the remap can be audited
# after the fact rather than taken on trust.
JOIN_EXACT = "original_exact_id_match"
JOIN_REMAP = "deterministic_remap"
JOIN_NATIVE_SCALAR = "native_scalar_only"


@dataclass(frozen=True)
class OmpalWord:
    """One rated unit: the characters it spans and each rater's verdicts.

    All three OMPAL word-level criteria are kept. Only tone has a machine
    counterpart today; consonant and vowel are retained so the report can state
    how many human labels exist for criteria the system cannot assess, rather
    than silently dropping them.
    """

    text: str
    expected_tones: tuple[int, ...]
    rater_tone_labels: tuple[bool, ...]
    rater_consonant_labels: tuple[bool, ...] = ()
    rater_vowel_labels: tuple[bool, ...] = ()

    @property
    def has_neutral_tone(self) -> bool:
        return NEUTRAL_TONE in self.expected_tones


@dataclass(frozen=True)
class OmpalUtterance:
    utterance_id: str
    speaker_id: str
    is_native: bool
    text: str
    wav_path: Path
    words: tuple[OmpalWord, ...]
    rater_accuracy: tuple[float, ...]
    rater_fluency: tuple[float, ...]
    rater_prosody: tuple[float, ...]
    #: One of JOIN_EXACT / JOIN_REMAP / JOIN_NATIVE_SCALAR.
    join_source: str = JOIN_EXACT
    #: The key this utterance's annotations were read under, when it differs
    #: from ``utterance_id``. Kept for audit trails.
    annotation_id: str | None = None

    @property
    def characters(self) -> str:
        return "".join(word.text for word in self.words)

    @property
    def has_per_rater_labels(self) -> bool:
        """Whether individual rater verdicts exist, or only an averaged score.

        False for every native utterance: native_scores.json publishes one
        scalar per rating with no per-rater breakdown, so those utterances can
        never contribute to inter-rater agreement. That is a property of the
        corpus, not of this join.
        """
        return self.join_source != JOIN_NATIVE_SCALAR

    def mean_rating(self, name: str) -> float | None:
        values = getattr(self, f"rater_{name}")
        return sum(values) / len(values) if values else None


def _as_sequence(value: Any) -> list[Any]:
    """Normalize a rating that may be a scalar or a per-rater list.

    native_scores.json stores a single value per rating while
    non-native_scores-detail.json stores one entry per rater. Both are valid
    panels; a scalar is simply a panel of one.
    """
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _as_bool_labels(value: Any) -> tuple[bool, ...]:
    """Coerce OMPAL's tone labels to booleans.

    Labels appear as ints in the native file and as strings in the detail
    file, so both shapes must be accepted.
    """
    labels: list[bool] = []
    for entry in _as_sequence(value):
        if isinstance(entry, bool):
            labels.append(entry)
        elif isinstance(entry, (int, float)):
            labels.append(bool(int(entry)))
        else:
            text = str(entry).strip()
            if text not in {"0", "1"}:
                raise ValueError(f"unrecognized tone label {entry!r}")
            labels.append(text == "1")
    return tuple(labels)


def _as_floats(value: Any) -> tuple[float, ...]:
    return tuple(float(entry) for entry in _as_sequence(value))


def corpus_status(root: str | Path) -> dict[str, Any]:
    """Report whether a usable corpus is already present on disk."""
    corpus_root = Path(root)
    wav_root = corpus_root / "wav"
    wav_count = sum(1 for _ in wav_root.rglob("*.wav")) if wav_root.is_dir() else 0
    scores_present = (corpus_root / "native_scores.json").is_file() and (
        corpus_root / "non-native_scores-detail.json"
    ).is_file()
    return {
        "root": str(corpus_root),
        "downloaded": wav_count > 0 and scores_present,
        "wav_count": wav_count,
        "scores_present": scores_present,
        "citation": CORPUS_CITATION,
    }


def download_corpus(
    root: str | Path,
    *,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    url: str = CORPUS_URL,
) -> dict[str, Any]:
    """Download and extract the corpus zipball into ``root``.

    A single zipball is used rather than 1,850 individual file requests, which
    would be far slower and would hit API rate limits. Extraction writes to a
    temporary directory first and only then moves into place, so a cancelled
    or failed download can never leave a half-populated corpus that later
    looks complete.
    """
    corpus_root = Path(root)
    corpus_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ompal-") as scratch:
        scratch_dir = Path(scratch)
        archive = scratch_dir / "ompal.zip"
        downloaded = 0
        with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            with archive.open("wb") as target:
                for chunk in response.iter_bytes(chunk_size=1 << 20):
                    if should_cancel and should_cancel():
                        raise RuntimeError("Corpus download cancelled.")
                    target.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)

        extract_dir = scratch_dir / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extract_dir)

        # The GitHub zipball nests everything under "<repo>-<branch>/".
        roots = [entry for entry in extract_dir.iterdir() if entry.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("Unexpected archive layout; expected one top-level directory.")
        _move_corpus_contents(roots[0], corpus_root)

    return corpus_status(corpus_root)


def _move_corpus_contents(source: Path, destination: Path) -> None:
    for entry in source.iterdir():
        target = destination / entry.name
        if target.exists():
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        shutil.move(str(entry), str(target))


def _load_scores(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _speaker_of(utterance_id: str) -> str:
    return utterance_id[3:6]


def _index_of(utterance_id: str) -> int:
    return int(utterance_id[6:])


def _majority(labels: Sequence[Any]) -> int:
    values = [int(bool(int(entry))) for entry in labels]
    return 1 if sum(values) * 2 > len(values) else 0


def _annotations_agree(detail: dict[str, Any], averaged: dict[str, Any]) -> str | None:
    """Return a failure reason, or None when the two entries describe the same rating.

    The averaged file is the same annotation at lower resolution: sentence
    ratings are the mean of the per-rater values, word labels are their
    majority (the file stores only 0 and 1, never a fraction). That makes it an
    ID-independent way to confirm a join, which is what the remap below relies
    on rather than trusting an inferred numbering rule.
    """
    if detail.get("text") != averaged.get("text"):
        return "text"
    for name in ("accuracy", "fluency", "prosody"):
        panel = _as_floats(detail.get(name))
        target = averaged.get(name)
        if not panel or target is None:
            return f"missing:{name}"
        # The averaged file is published rounded to two decimals.
        if abs(sum(panel) / len(panel) - float(target)) > 0.011:
            return f"sentence:{name}"
    detail_words = detail.get("words") or []
    averaged_words = averaged.get("words") or []
    if len(detail_words) != len(averaged_words):
        return "word_count"
    for left, right in zip(detail_words, averaged_words):
        if "".join(_as_sequence(left.get("text"))) != "".join(
            _as_sequence(right.get("text"))
        ):
            return "word_text"
        for key in ("phoneme_consonant", "phoneme_vowel", "tone"):
            panel = _as_sequence(left.get(key))
            target = right.get(key)
            if not panel or target is None:
                return f"missing:{key}"
            if _majority(panel) != int(target):
                return f"label:{key}"
    return None


def remap_detail_ids(
    detail: dict[str, Any],
    averaged: dict[str, Any],
    wav_ids: Iterable[str],
) -> dict[str, str]:
    """Map per-rater annotation IDs that address no audio onto the WAV they rate.

    OMPAL's per-rater file was written per annotation *session*, not per
    speaker: once a speaker passes 29 utterances the remainder is emitted under
    a fresh speaker number (047 upwards) with the utterance counter restarted
    at 01. 656 of 1,768 learner utterances are addressed that way, and a
    literal ID join silently drops all of them.

    Nothing here is assumed. The speaker pairing and the index offset are both
    derived from the data, and every resulting pair is then checked against the
    averaged file by ``_annotations_agree``. A pair that fails raises rather
    than being dropped or guessed at — a corpus revision that breaks this
    relation must fail loudly, not re-join itself incorrectly.

    See benchmarking/results/ompal_id_join_audit.md for the full evidence.
    Returns ``{annotation_id: wav_id}`` for remapped entries only.
    """
    wav_id_set = set(wav_ids)
    unmatched_detail = sorted(set(detail) - wav_id_set)
    if not unmatched_detail:
        return {}

    unmatched_wav = sorted(wav_id_set - set(detail) - set(averaged.keys() - set(detail)))
    # Learner audio that no annotation addresses directly.
    orphan_wav = sorted(wav for wav in wav_id_set if wav in averaged and wav not in detail)

    if not orphan_wav:
        # Annotations with no audio and no unannotated audio to pair them with.
        # That is simply missing audio, which the caller skips as it always
        # has — there is nothing here to remap.
        return {}

    phantom_speakers = sorted({_speaker_of(key) for key in unmatched_detail})
    overflow_speakers = sorted({_speaker_of(wav) for wav in orphan_wav})
    if len(phantom_speakers) != len(overflow_speakers):
        raise ValueError(
            "OMPAL join: cannot pair annotation speakers with audio speakers — "
            f"{len(phantom_speakers)} unaddressed annotation speakers "
            f"({phantom_speakers[:4]}…) vs {len(overflow_speakers)} audio "
            f"speakers with unannotated recordings ({overflow_speakers[:4]}…)."
        )
    speaker_map = dict(zip(phantom_speakers, overflow_speakers))

    # Offset per speaker, derived: the annotation block restarts at its own
    # lowest index, and fills the audio indices no direct match covered.
    by_annotation_speaker: dict[str, list[str]] = {}
    for key in unmatched_detail:
        by_annotation_speaker.setdefault(_speaker_of(key), []).append(key)
    by_audio_speaker: dict[str, list[str]] = {}
    for wav in orphan_wav:
        by_audio_speaker.setdefault(_speaker_of(wav), []).append(wav)

    mapping: dict[str, str] = {}
    for annotation_speaker, keys in by_annotation_speaker.items():
        audio_speaker = speaker_map[annotation_speaker]
        targets = by_audio_speaker[audio_speaker]
        if len(keys) != len(targets):
            raise ValueError(
                f"OMPAL join: annotation speaker {annotation_speaker} has "
                f"{len(keys)} entries but audio speaker {audio_speaker} has "
                f"{len(targets)} unannotated recordings."
            )
        offset = min(_index_of(wav) for wav in targets) - min(
            _index_of(key) for key in keys
        )
        for key in keys:
            mapping[key] = f"002{audio_speaker}{_index_of(key) + offset:02d}"

    if len(set(mapping.values())) != len(mapping):
        raise ValueError("OMPAL join: remap produced duplicate audio targets.")
    missing = sorted(set(mapping.values()) - wav_id_set)
    if missing:
        raise ValueError(f"OMPAL join: remap targets have no audio: {missing[:5]}")

    # The load-bearing check. Every remapped pair must describe the same rating
    # the averaged file already publishes for that audio.
    for annotation_id, wav_id in mapping.items():
        reason = _annotations_agree(detail[annotation_id], averaged.get(wav_id, {}))
        if reason is not None:
            raise ValueError(
                f"OMPAL join: remapped {annotation_id} -> {wav_id} disagrees with "
                f"the averaged annotation ({reason}). The published numbering "
                "may have changed; refusing to join on an unverified rule."
            )
    return mapping


def _build_words(entry: dict[str, Any]) -> tuple[OmpalWord, ...]:
    words: list[OmpalWord] = []
    for raw in entry.get("words") or []:
        text = "".join(_as_sequence(raw.get("text")))
        if not text:
            continue
        words.append(
            OmpalWord(
                text=text,
                expected_tones=tuple(word_tones(text)),
                rater_tone_labels=_as_bool_labels(raw.get("tone")),
                rater_consonant_labels=_as_bool_labels(raw.get("phoneme_consonant")),
                rater_vowel_labels=_as_bool_labels(raw.get("phoneme_vowel")),
            )
        )
    return tuple(words)


def load_utterances(root: str | Path) -> list[OmpalUtterance]:
    """Join the score JSONs to the WAV files actually present on disk.

    The WAV tree is treated as authoritative for speaker identity rather than
    decoding the utterance-ID digits, and utterances whose audio is missing are
    skipped rather than silently scored against absent input.
    """
    corpus_root = Path(root)
    wav_root = corpus_root / "wav"
    if not wav_root.is_dir():
        raise FileNotFoundError(f"No wav directory in corpus at {corpus_root}")

    wav_by_id: dict[str, Path] = {}
    speaker_by_id: dict[str, str] = {}
    for wav_path in wav_root.rglob("*.wav"):
        wav_by_id[wav_path.stem] = wav_path
        speaker_by_id[wav_path.stem] = wav_path.parent.name

    native = _load_scores(corpus_root / "native_scores.json")
    averaged = _load_scores(corpus_root / "non-native_scores.json")
    detail = _load_scores(corpus_root / "non-native_scores-detail.json")

    # 656 of the 1,768 learner utterances carry per-rater annotations under an
    # ID that addresses no audio, because the detail file was written per
    # annotation session rather than per speaker. `remap_detail_ids` derives
    # the correspondence and verifies every pair against the averaged file
    # before it is used; see ompal_id_join_audit.md. Without it those 656
    # utterances fall back to a one-rater panel and are then dropped from every
    # inter-rater analysis.
    remap = remap_detail_ids(detail, averaged, wav_by_id)

    # Per-rater annotations win wherever they exist, keyed by the audio they
    # actually describe. The averaged file fills any remainder.
    learner_entries: dict[str, tuple[dict[str, Any], str, str | None]] = {
        utterance_id: (entry, JOIN_EXACT, None)
        for utterance_id, entry in averaged.items()
    }
    for annotation_id, entry in detail.items():
        target = remap.get(annotation_id, annotation_id)
        if target not in wav_by_id:
            continue
        source = JOIN_REMAP if annotation_id in remap else JOIN_EXACT
        learner_entries[target] = (
            entry,
            source,
            annotation_id if source == JOIN_REMAP else None,
        )

    sources: list[tuple[dict[str, tuple[dict[str, Any], str, str | None]], bool]] = [
        (
            {
                # Native ratings are published as scalars with no per-rater
                # breakdown, so they can never enter an agreement calculation.
                # Marked rather than silently treated as a panel of one.
                utterance_id: (entry, JOIN_NATIVE_SCALAR, None)
                for utterance_id, entry in native.items()
            },
            True,
        ),
        (learner_entries, False),
    ]

    utterances: list[OmpalUtterance] = []
    for scores, is_native in sources:
        for utterance_id, (entry, join_source, annotation_id) in scores.items():
            wav_path = wav_by_id.get(utterance_id)
            if wav_path is None:
                continue
            utterances.append(
                OmpalUtterance(
                    utterance_id=utterance_id,
                    speaker_id=speaker_by_id[utterance_id],
                    is_native=is_native,
                    text=str(entry.get("text") or ""),
                    wav_path=wav_path,
                    words=_build_words(entry),
                    rater_accuracy=_as_floats(entry.get("accuracy")),
                    rater_fluency=_as_floats(entry.get("fluency")),
                    rater_prosody=_as_floats(entry.get("prosody")),
                    join_source=join_source,
                    annotation_id=annotation_id,
                )
            )
    utterances.sort(key=lambda item: item.utterance_id)
    return utterances


def join_summary(utterances: Sequence[OmpalUtterance]) -> dict[str, Any]:
    """Provenance counts, for the report and for splitting results by cohort."""
    counts: dict[str, int] = {}
    for utterance in utterances:
        counts[utterance.join_source] = counts.get(utterance.join_source, 0) + 1
    with_panel = [u for u in utterances if u.has_per_rater_labels]
    return {
        "total": len(utterances),
        "by_join_source": counts,
        "with_per_rater_labels": len(with_panel),
        "without_per_rater_labels": len(utterances) - len(with_panel),
    }


def align_system_characters(
    words: Sequence[OmpalWord], system_characters: Iterable[tuple[str, bool]]
) -> list[bool] | None:
    """Map per-character system verdicts onto OMPAL's rated word spans.

    Our analyzer tokenizes with jieba while OMPAL uses its own word units, so
    the two never agree on boundaries. Flattening our output to characters and
    regrouping it along OMPAL's spans is what makes the two comparable.

    A word spanning several characters passes only when every character in it
    passed, which is the same rule the application already applies to its own
    multi-syllable words.

    Returns None when the character sequences do not match. That guard matters:
    a silent misalignment would shift every label by one and quietly corrupt
    every metric downstream, which is far worse than dropping the utterance.
    """
    flattened = list(system_characters)
    if "".join(char for char, _ in flattened) != "".join(word.text for word in words):
        return None

    verdicts: list[bool] = []
    position = 0
    for word in words:
        span = flattened[position : position + len(word.text)]
        position += len(word.text)
        verdicts.append(all(passed for _, passed in span))
    return verdicts
