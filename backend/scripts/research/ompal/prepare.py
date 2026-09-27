"""Clean the OMPAL corpus into one analysis manifest (read-only on the corpus).

OMPAL (Hsieh et al., Interspeech 2025, CC BY 4.0) ships two score files that
disagree on utterance ids:

* ``non-native_scores.json`` (rater-aggregated) - its 1,768 ids match the
  1,768 learner ``.wav`` files exactly.
* ``non-native_scores-detail.json`` (one value per rater) - 656 of its ids
  renumber a second recording session as new speakers (02047-02066) and so
  point at no audio file.

This script keys everything on the aggregated file, then recovers the
per-rater votes for the renumbered records (see ``recover_rater_votes``).
Every recovered pair must also match on content (text, mean sentence
scores, per-character majority labels), so no rater vote is ever guessed.
Utterances whose annotation
units do not spell the reference text (the learner substituted or dropped
words, so the scored characters and the prompt disagree) are excluded.

Every decision is written to ``cleaning_log.json`` next to the manifest.

Example, from ``backend/``::

    python -m scripts.research.ompal.prepare --corpus ../../phantomhsieh/ompal-corpus --out output/ompal
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from helpers.pinyin_service import canonical_pinyin_tone3  # noqa: E402


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2)


def _majority(votes: list[str]) -> int:
    return int(sum(int(v) for v in votes) * 2 > len(votes))


def _aggregated_signature(record: dict) -> tuple:
    words = record["words"]
    return (
        record["text"],
        round(float(record["accuracy"]), 2),
        round(float(record["fluency"]), 2),
        round(float(record["prosody"]), 2),
        tuple(w["tone"] for w in words),
        tuple(w["phoneme_vowel"] for w in words),
        tuple(w["phoneme_consonant"] for w in words),
    )


def _detail_signature(record: dict) -> tuple:
    words = record["words"]
    return (
        record["text"],
        _mean(record["accuracy"]),
        _mean(record["fluency"]),
        _mean(record["prosody"]),
        tuple(_majority(w["tone"]) for w in words),
        tuple(_majority(w["phoneme_vowel"]) for w in words),
        tuple(_majority(w["phoneme_consonant"]) for w in words),
    )


def _speaker(uid: str) -> str:
    return uid[2:6]


def _utterance(uid: str) -> int:
    return int(uid[6:])


def recover_rater_votes(aggregated: dict, detail: dict) -> tuple[dict, dict]:
    """Map every aggregated id to its per-rater detail record where provable.

    The detail file's renumbered speakers (sorted) correspond one-to-one, in
    order, to the aggregated speakers that own the unmatched ids (sorted),
    and each renumbered utterance ``n`` is aggregated utterance ``n + offset``
    where ``offset`` is the renumbered speaker's first aggregated utterance
    minus one. That rule is only a candidate: a pair is accepted solely when
    the content signature (text, mean sentence scores, per-character
    majority labels) agrees, so a wrong rule shows up as unverified pairs.
    """
    mapping = {uid: detail[uid] for uid in aggregated if uid in detail}
    log: dict = {"direct_id_match": len(mapping)}
    orphan_detail = sorted(uid for uid in detail if uid not in aggregated)
    orphan_aggregated = sorted(uid for uid in aggregated if uid not in detail)
    detail_speakers = sorted({_speaker(uid) for uid in orphan_detail})
    aggregated_speakers = sorted({_speaker(uid) for uid in orphan_aggregated})
    speaker_map = dict(zip(detail_speakers, aggregated_speakers))
    first_utterance = {
        speaker: min(_utterance(uid) for uid in orphan_aggregated if _speaker(uid) == speaker)
        for speaker in aggregated_speakers
    }
    verified = unverified = 0
    for uid in orphan_detail:
        target_speaker = speaker_map.get(_speaker(uid))
        if target_speaker is None:
            unverified += 1
            continue
        offset = first_utterance[target_speaker] - 1
        target = f"{uid[:2]}{target_speaker}{_utterance(uid) + offset:02d}"
        if target in aggregated and target not in mapping and (
            _aggregated_signature(aggregated[target]) == _detail_signature(detail[uid])
        ):
            mapping[target] = detail[uid]
            verified += 1
        else:
            unverified += 1
    log.update({
        "renumbered_detail_records": len(orphan_detail),
        "renumbered_speaker_map": speaker_map,
        "recovered_and_content_verified": verified,
        "rater_votes_unavailable": unverified,
    })
    return mapping, log


def build_manifest(corpus: Path) -> tuple[list[dict], dict]:
    aggregated = json.loads((corpus / "non-native_scores.json").read_text(encoding="utf-8"))
    detail = json.loads((corpus / "non-native_scores-detail.json").read_text(encoding="utf-8"))
    native = json.loads((corpus / "native_scores.json").read_text(encoding="utf-8"))
    wavs = {Path(p).stem: p for p in glob.glob(str(corpus / "wav" / "*" / "*.wav"))}
    native_by_text = {record["text"]: uid for uid, record in native.items() if uid in wavs}

    rater_detail, log = recover_rater_votes(aggregated, detail)
    excluded: dict[str, list[str]] = collections.defaultdict(list)
    manifest: list[dict] = []
    for uid, record in sorted(aggregated.items()):
        units = ["".join(w["text"]) for w in record["words"]]
        if uid not in wavs:
            excluded["no_audio"].append(uid)
            continue
        if "".join(units) != record["text"] or any(len(u) != 1 for u in units):
            excluded["units_do_not_spell_reference_text"].append(uid)
            continue
        tones = canonical_pinyin_tone3(record["text"]).split()
        detail_record = rater_detail.get(uid)
        characters = []
        for index, word in enumerate(record["words"]):
            rater = detail_record["words"][index] if detail_record else None
            characters.append({
                "char": units[index],
                "expected_tone": int(tones[index][-1]) if index < len(tones) and tones[index][-1].isdigit() else None,
                "tone_ok": int(word["tone"]),
                "tone_votes": [int(v) for v in rater["tone"]] if rater else None,
            })
        manifest.append({
            "id": uid,
            "speaker": Path(wavs[uid]).parent.name,
            "wav": wavs[uid],
            "text": record["text"],
            "native_reference_wav": wavs.get(native_by_text.get(record["text"], "")),
            "accuracy": float(record["accuracy"]),
            "fluency": float(record["fluency"]),
            "prosody": float(record["prosody"]),
            "rater_accuracy": detail_record["accuracy"] if detail_record else None,
            "rater_fluency": detail_record["fluency"] if detail_record else None,
            "rater_prosody": detail_record["prosody"] if detail_record else None,
            "characters": characters,
        })
    log.update({
        "aggregated_utterances": len(aggregated),
        "kept_utterances": len(manifest),
        "kept_with_rater_votes": sum(1 for m in manifest if m["rater_accuracy"] is not None),
        "kept_with_native_reference": sum(1 for m in manifest if m["native_reference_wav"]),
        "excluded": {reason: {"count": len(ids), "ids": ids} for reason, ids in excluded.items()},
        "raters_per_item_in_detail_file": sorted({len(v["accuracy"]) for v in detail.values()}),
    })
    return manifest, log


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, type=Path, help="Path to a checkout of the OMPAL corpus.")
    parser.add_argument("--out", default=Path("output/ompal"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest, log = build_manifest(args.corpus.resolve())
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (args.out / "cleaning_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: (v if k != "excluded" else {r: e["count"] for r, e in v.items()}) for k, v in log.items()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
