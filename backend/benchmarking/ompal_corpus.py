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


@dataclass(frozen=True)
class OmpalWord:
    """One rated unit: the characters it spans and each rater's tone verdict."""

    text: str
    expected_tones: tuple[int, ...]
    rater_tone_labels: tuple[bool, ...]

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

    @property
    def characters(self) -> str:
        return "".join(word.text for word in self.words)

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
    # The two learner files cover different subsets of the published audio:
    # the per-rater detail file matches only 1,112 of the 1,768 WAVs, while the
    # averaged file matches all of them. Preferring detail and falling back to
    # the averaged file keeps the per-rater disagreement needed for the human
    # ceiling wherever it exists, without discarding a third of the corpus.
    # An averaged entry parses as a one-rater panel, which the ceiling
    # calculation then excludes on its own (it uses the modal panel size).
    non_native = {
        **_load_scores(corpus_root / "non-native_scores.json"),
        **_load_scores(corpus_root / "non-native_scores-detail.json"),
    }

    utterances: list[OmpalUtterance] = []
    for scores, is_native in ((native, True), (non_native, False)):
        for utterance_id, entry in scores.items():
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
                )
            )
    utterances.sort(key=lambda item: item.utterance_id)
    return utterances


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
