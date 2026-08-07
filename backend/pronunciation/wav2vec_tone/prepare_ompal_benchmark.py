"""Turn OMPAL into a syllable-level Taiwan Mandarin tone-correctness benchmark.

The task changes here. AISHELL asked "which tone is this?", which that corpus
could not pose honestly -- syllable identity predicted the answer 86% of the
time. OMPAL asks "did this learner produce the expected tone correctly?", and
its label is a human judgement of correctness rather than of identity, so no
lexical lookup can shortcut it.

Expected tones come from the Taiwan MoE dictionary via moedict.tw, never from
a Mainland resource and never from the AISHELL labels. Tone is read from the
bopomofo, which marks it unambiguously.

Polyphonic characters are not guessed. A character with several readings that
all carry the same tone is still usable -- this benchmark needs the tone, not
the full reading -- but one whose readings differ in tone is marked ambiguous
and excluded from the first benchmark while staying in the metadata.

    python -m pronunciation.wav2vec_tone.prepare_ompal_benchmark
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone import schema

DATA_DIR = Path(__file__).resolve().parent / "data"
OMPAL_DIR = Path(__file__).resolve().parents[2] / "private-data" / "ompal"
MOE_ENDPOINT = "https://www.moedict.tw/uni/"
MOE_CACHE = DATA_DIR / "moe_pronunciations.csv"

# Bopomofo tone marks. The neutral mark leads the syllable; the rest trail it,
# and an unmarked syllable is tone 1.
TONE_MARKS = {"ˊ": 2, "ˇ": 3, "ˋ": 4}
NEUTRAL_MARK = "˙"

# OMPAL's own encoding, recorded before any transformation (see README §3).
OMPAL_TONE_CORRECT = "1"
OMPAL_TONE_INCORRECT = "0"


def tone_from_bopomofo(bopomofo: str) -> int | None:
    """Tone number from a bopomofo syllable, or None if unreadable."""
    text = (bopomofo or "").strip()
    if not text:
        return None
    if text.startswith(NEUTRAL_MARK):
        return 5
    for mark, tone in TONE_MARKS.items():
        if text.endswith(mark):
            return tone
    return 1


def fetch_moe(character: str) -> list[dict]:
    """All Taiwan MoE readings for one character."""
    url = MOE_ENDPOINT + urllib.parse.quote(character)
    with urllib.request.urlopen(url, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    readings = []
    for heteronym in payload.get("heteronyms", []):
        bopomofo = heteronym.get("bopomofo") or ""
        tone = tone_from_bopomofo(bopomofo)
        if tone is None:
            continue
        readings.append({
            "pinyin": heteronym.get("pinyin") or "",
            "bopomofo": bopomofo,
            "tone": tone,
        })
    return readings


def build_pronunciation_table(characters, cache_path: Path, pause: float) -> dict:
    """Look up every character once and cache it as a reusable mapping table.

    Cached so the benchmark can be rebuilt without hitting the dictionary
    again, and so the exact pronunciations used are inspectable rather than
    implicit.
    """
    table: dict[str, dict] = {}
    if cache_path.exists():
        for row in csv.DictReader(cache_path.open(encoding="utf-8")):
            table[row["word"]] = {
                "expected_pinyin": row["expected_pinyin"],
                "expected_tone": row["expected_tone"],
                "source": row["source"],
                "source_status": row["source_status"],
                "all_readings": row["all_readings"],
                "reading_count": int(row["reading_count"]),
                "tones_seen": row["tones_seen"],
            }

    missing = [c for c in characters if c not in table]
    if missing:
        print(f"    looking up {len(missing)} characters at moedict.tw…")
    for position, character in enumerate(missing, start=1):
        try:
            readings = fetch_moe(character)
        except Exception as error:  # noqa: BLE001 - recorded, not fatal
            table[character] = {
                "expected_pinyin": "", "expected_tone": "",
                "source": "moe_dict", "source_status": f"lookup_failed:{type(error).__name__}",
                "all_readings": "", "reading_count": 0, "tones_seen": "",
            }
            continue

        tones = sorted({r["tone"] for r in readings})
        if not readings:
            status, pinyin, tone = "not_found", "", ""
        elif len(tones) == 1:
            # One tone across every reading: the tone is determined even when
            # the full pronunciation is not, which is all this benchmark needs.
            status = "verified" if len(readings) == 1 else "verified_tone_only"
            pinyin = readings[0]["pinyin"] if len(readings) == 1 else ""
            tone = str(tones[0])
        else:
            # Readings disagree on tone. Resolving this needs the intended
            # word, not the character, so it is left for a human rather than
            # guessed.
            status, pinyin, tone = "ambiguous_polyphone", "", ""

        table[character] = {
            "expected_pinyin": pinyin,
            "expected_tone": tone,
            "source": "moe_dict",
            "source_status": status,
            "all_readings": "|".join(f"{r['pinyin']}({r['bopomofo']})={r['tone']}"
                                     for r in readings),
            "reading_count": len(readings),
            "tones_seen": ",".join(str(t) for t in tones),
        }
        if position % 25 == 0:
            print(f"      {position}/{len(missing)}")
        time.sleep(pause)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["word", "expected_pinyin", "expected_tone", "source",
                         "source_status", "all_readings", "reading_count",
                         "tones_seen"])
        for word in sorted(table):
            entry = table[word]
            writer.writerow([word, entry["expected_pinyin"], entry["expected_tone"],
                             entry["source"], entry["source_status"],
                             entry["all_readings"], entry["reading_count"],
                             entry["tones_seen"]])
    return table


def load_ompal(root: Path):
    """Read OMPAL, returning learner rows, native rows and integrity findings."""
    learner = json.loads((root / "non-native_scores-detail.json").read_text(encoding="utf-8"))
    native = json.loads((root / "native_scores.json").read_text(encoding="utf-8"))

    on_disk = {
        file.stem
        for speaker in (root / "wav").iterdir() if speaker.is_dir()
        for file in speaker.iterdir() if file.suffix == ".wav"
    }
    keys = set(learner) | set(native)
    return learner, native, on_disk, {
        "audio_files": len(on_disk),
        "annotation_keys": len(keys),
        "matched": len(on_disk & keys),
        "keys_without_audio": sorted(keys - on_disk),
        "audio_without_keys": sorted(on_disk - keys),
    }


def audio_path(utterance_id: str) -> str:
    """OMPAL stores 00204601.wav under wav/SPEAKER02046/ -- speaker is chars 1-6."""
    return f"wav/SPEAKER{utterance_id[1:6]}/{utterance_id}.wav"


def build_rows(learner, native, on_disk, table) -> list[dict]:
    rows = []
    for source, speech_type in ((native, schema.NATIVE), (learner, schema.L2)):
        for utterance_id, record in sorted(source.items()):
            has_audio = utterance_id in on_disk
            for position, word in enumerate(record["words"]):
                text = "".join(word["text"])
                if len(text) != 1:
                    continue          # 18 multi-character tokens, out of scope

                raw = word["tone"]
                ratings = [str(v) for v in (raw if isinstance(raw, list) else [raw])]
                correct = sum(1 for v in ratings if v == OMPAL_TONE_CORRECT)
                entry = table.get(text, {})
                status = entry.get("source_status", "not_looked_up")
                usable_tone = status in ("verified", "verified_tone_only")

                rows.append({
                    "corpus": "OMPAL",
                    "audio_path": audio_path(utterance_id),
                    "audio_present": int(has_audio),
                    "utterance_id": utterance_id,
                    "token_index": position,
                    "speaker_id": utterance_id[1:6],
                    "speech_type": speech_type,
                    "speaker_variety": schema.TAIWAN,
                    "word": text,
                    "word_script": schema.TRADITIONAL,
                    "expected_pinyin": entry.get("expected_pinyin", ""),
                    "expected_tone": entry.get("expected_tone", ""),
                    "pinyin_variety": schema.TAIWAN,
                    "pinyin_source": schema.SOURCE_MOE_DICT,
                    "pinyin_source_status": status,
                    "pronunciation_ambiguous": int(not usable_tone),
                    "rater_1_tone": ratings[0] if len(ratings) > 0 else "",
                    "rater_2_tone": ratings[1] if len(ratings) > 1 else "",
                    "rater_3_tone": ratings[2] if len(ratings) > 2 else "",
                    "n_ratings": len(ratings),
                    # Majority of the raters present. Native rows carry a
                    # single consensus value, so "majority" there is that value.
                    "majority_tone_correct": int(correct * 2 >= len(ratings)),
                    "agreement_count": correct,
                    "usable": int(usable_tone and has_audio),
                })
    return rows


def report(rows, integrity, table) -> tuple[str, dict]:
    learner = [r for r in rows if r["speech_type"] == schema.L2]
    usable = [r for r in rows if r["usable"]]
    usable_learner = [r for r in usable if r["speech_type"] == schema.L2]

    correct = sum(r["majority_tone_correct"] for r in usable)
    ambiguous = sum(1 for r in rows if r["pronunciation_ambiguous"])
    missing_audio = sum(1 for r in rows if not r["audio_present"])

    by_tone = defaultdict(lambda: [0, 0])
    for row in usable:
        bucket = by_tone[row["expected_tone"]]
        bucket[0 if row["majority_tone_correct"] else 1] += 1

    # The diagnostic the AISHELL set failed: does a lexical item appear both
    # correct and incorrect, so identity alone cannot decide?
    per_word = defaultdict(lambda: [0, 0])
    for row in usable_learner:
        per_word[row["word"]][0 if row["majority_tone_correct"] else 1] += 1
    both = {w for w, (c, i) in per_word.items() if c and i}
    covered = sum(c + i for w, (c, i) in per_word.items() if w in both)

    status_counts = Counter(r["pinyin_source_status"] for r in rows)

    lines = [
        "=" * 76,
        "OMPAL TAIWAN MANDARIN TONE-CORRECTNESS BENCHMARK",
        "=" * 76,
        "",
        "Original OMPAL tone encoding, before any transformation:",
        f'  learner: JSON strings "1"=correct, "0"=incorrect, 3 values per token',
        f"  native : JSON integers 1=correct, 0=incorrect, 1 value per token",
        f"  no rater identifier field exists in any file -- rater position is",
        f"  not a stable identity (3 of a 4-expert panel rate each utterance)",
        "",
        f"Total rated tokens: {len(rows)}",
        f"Usable verified tokens: {len(usable)}",
        f"  (usable = MoE-verified expected tone AND audio present)",
        "",
        f"Learner speakers: {len({r['speaker_id'] for r in learner})}",
        f"Native speakers: {len({r['speaker_id'] for r in rows if r['speech_type'] == schema.NATIVE})}",
        "",
        f"Tone correct: {correct} ({correct / max(len(usable), 1) * 100:.1f}%)",
        f"Tone incorrect: {len(usable) - correct} "
        f"({(len(usable) - correct) / max(len(usable), 1) * 100:.1f}%)",
        "",
        "Correct/incorrect by expected tone (usable tokens):",
        f"  {'tone':<8}{'correct':>10}{'incorrect':>11}{'total':>9}{'% incorrect':>13}",
    ]
    for tone in ("1", "2", "3", "4", "5"):
        good, bad = by_tone.get(tone, [0, 0])
        total = good + bad
        label = "neutral" if tone == "5" else f"T{tone}"
        lines.append(f"  {label:<8}{good:>10}{bad:>11}{total:>9}"
                     + (f"{bad / total * 100:>12.1f}%" if total else f"{'--':>13}"))

    lines += [
        "",
        f"Ambiguous pronunciations: {ambiguous} tokens "
        f"({ambiguous / len(rows) * 100:.1f}%) -- kept in metadata, excluded from benchmark",
        f"Missing audio: {missing_audio} tokens "
        f"({missing_audio / len(rows) * 100:.1f}%)",
        "",
        "MoE lookup status by token:",
    ]
    for status, count in status_counts.most_common():
        lines.append(f"  {status:<28}{count:>7}  ({count / len(rows) * 100:5.1f}%)")

    lines += [
        "",
        "-" * 76,
        "TRIVIALITY CHECK -- can syllable identity alone solve this?",
        "-" * 76,
        f"Lexical items among usable learner tokens: {len(per_word)}",
        f"Items with BOTH correct and incorrect productions: {len(both)} "
        f"({len(both) / max(len(per_word), 1) * 100:.1f}%)",
        f"Learner samples covered by those items: {covered} "
        f"({covered / max(len(usable_learner), 1) * 100:.1f}%)",
        "",
        "  On AISHELL, syllable identity predicted the label 86.1% of the time.",
        "  Here the label is correctness, so a lexical lookup can only predict",
        "  the majority outcome and scores the base rate with zero recall on",
        "  errors -- the class that matters.",
        "",
        "-" * 76,
        "CORPUS INTEGRITY",
        "-" * 76,
        f"  audio files on disk      : {integrity['audio_files']}",
        f"  annotation keys          : {integrity['annotation_keys']}",
        f"  matched                  : {integrity['matched']}",
        f"  keys with no audio       : {len(integrity['keys_without_audio'])}",
        f"  audio with no annotation : {len(integrity['audio_without_keys'])}",
    ]
    return "\n".join(lines), {
        "total_rated_tokens": len(rows),
        "usable_tokens": len(usable),
        "learner_speakers": len({r["speaker_id"] for r in learner}),
        "native_speakers": len({r["speaker_id"] for r in rows
                                if r["speech_type"] == schema.NATIVE}),
        "tone_correct": correct,
        "tone_incorrect": len(usable) - correct,
        "by_expected_tone": {t: by_tone.get(t, [0, 0]) for t in ("1", "2", "3", "4", "5")},
        "ambiguous_tokens": ambiguous,
        "missing_audio_tokens": missing_audio,
        "lexical_items": len(per_word),
        "items_both_outcomes": len(both),
        "samples_covered_by_both": covered,
        "moe_status_counts": dict(status_counts),
        "integrity": {k: (v if not isinstance(v, list) else len(v))
                      for k, v in integrity.items()},
        "integrity_keys_without_audio_speakers":
            sorted({u[1:6] for u in integrity["keys_without_audio"]}),
        "integrity_audio_without_keys_speakers":
            sorted({u[1:6] for u in integrity["audio_without_keys"]}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ompal", default=str(OMPAL_DIR))
    parser.add_argument("--out", default=str(DATA_DIR / "ompal_tone_benchmark_metadata.csv"))
    parser.add_argument("--pause", type=float, default=0.15,
                        help="seconds between dictionary lookups")
    args = parser.parse_args()

    root = Path(args.ompal)
    print("[1] reading OMPAL…")
    learner, native, on_disk, integrity = load_ompal(root)
    print(f"    {len(learner)} learner + {len(native)} native utterances, "
          f"{len(on_disk)} wav files")

    characters = sorted({
        "".join(w["text"])
        for source in (learner, native)
        for record in source.values()
        for w in record["words"]
        if len("".join(w["text"])) == 1
    })
    print(f"[2] Taiwan MoE pronunciation table for {len(characters)} characters")
    table = build_pronunciation_table(characters, MOE_CACHE, args.pause)
    print(f"    mapping table -> {MOE_CACHE}")

    print("[3] building rows…")
    rows = build_rows(learner, native, on_disk, table)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    text, summary = report(rows, integrity, table)
    print(text)
    summary_path = DATA_DIR / "ompal_tone_benchmark_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    print(f"\nmetadata : {path}")
    print(f"summary  : {summary_path}")
    print(f"mapping  : {MOE_CACHE}")
    print("\nMetadata only. No audio copied, no alignment, no model run.")


if __name__ == "__main__":
    main()
