"""Evaluate the current independent rubric against an official OMPAL test fold.

No cloud feedback, database writes, threshold fitting, or model substitution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import fmean

SOURCE = "https://github.com/phantomhsieh/OMPAL-corpus"
DIMENSIONS = {"accuracy": "pronunciation", "fluency": "fluency", "prosody": "prosody"}


def load_scores(path):
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, dict):
        raise ValueError("Expected an OMPAL score mapping")
    for uid, record in records.items():
        if not re.fullmatch(r"00[12]\d{5}", uid):
            raise ValueError(f"Invalid OMPAL audio id: {uid}")
        if not isinstance(record, dict) or not isinstance(record.get("text"), str) or not record["text"].strip():
            raise ValueError(f"Missing sentence: {uid}")
        for key in DIMENSIONS:
            score = record.get(key)
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 1 <= score <= 5:
                raise ValueError(f"Invalid {key} rating: {uid}")
    return records


def audio_path(corpus, uid):
    return Path(corpus) / "wav" / f"SPEAKER{uid[1:6]}" / f"{uid}.wav"


def build_pairs(corpus, fold):
    """Use only native anchors within the selected official test fold."""
    records = load_scores(Path(corpus) / "test" / f"test_{fold}_scores.json")
    anchors = {}
    for uid, record in sorted(records.items()):
        if uid.startswith("001"):
            anchors.setdefault(record["text"], uid)
    return [{"id": uid, "text": record["text"], "expert": {k: record[k] for k in DIMENSIONS},
             "audio": str(audio_path(corpus, uid)), "reference_id": anchors.get(record["text"]),
             "reference_audio": str(audio_path(corpus, anchors[record["text"]])) if record["text"] in anchors else None}
            for uid, record in sorted(records.items()) if uid.startswith("002")]


def score_pair(pair, policy):
    from domain.pronunciation.rubric import score_fluency, score_prosody
    from services.pronunciation.extraction import extract_utterance_features
    from services.pronunciation.wav2vec2_scoring import Wav2Vec2Unavailable, analyze_wav2vec2, score_wav2vec2_pronunciation

    result = dict(pair)
    result["dimensions"] = {}
    if not pair["reference_audio"]:
        return result | {"status": "skipped", "reason": "no_matching_native_reference"}
    if not all(Path(pair[k]).is_file() for k in ("audio", "reference_audio")):
        return result | {"status": "skipped", "reason": "audio_missing"}
    try:
        student = extract_utterance_features(pair["audio"], pair["text"])
        reference = extract_utterance_features(pair["reference_audio"], pair["text"])
        result["dimensions"] = {"fluency": score_fluency(student, reference, policy),
                                "prosody": score_prosody(student, reference, policy)}
        try:
            evidence = analyze_wav2vec2(student_audio_path=pair["audio"], reference_audio_path=pair["reference_audio"],
                                      student=student, reference=reference, policy=policy)
            result["dimensions"]["pronunciation"] = score_wav2vec2_pronunciation(evidence, policy)
        except Wav2Vec2Unavailable as exc:
            result["dimensions"]["pronunciation"] = {"score": None, "reason": str(exc), "source": "unavailable"}
        return result | {"status": "measured"}
    except Exception as exc:
        return result | {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}


def summarize(results):
    summary = {}
    for expert_key, system_key in DIMENSIONS.items():
        pairs = []
        degraded = 0
        for result in results:
            dimension = result.get("dimensions", {}).get(system_key, {})
            score = dimension.get("score")
            if result.get("status") != "measured" or score is None:
                continue
            if dimension.get("evidence_quality") == "degraded":
                degraded += 1
                continue
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 1 <= score <= 5:
                raise ValueError(f"Invalid predicted {system_key} score")
            pairs.append((float(score), float(result["expert"][expert_key])))
        correlation = None
        if len(pairs) > 1:
            xs, ys = zip(*pairs)
            mx, my = fmean(xs), fmean(ys)
            denominator = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
            if denominator:
                correlation = sum((x-mx)*(y-my) for x, y in pairs) / denominator
        summary[expert_key] = {"system_dimension": system_key, "scored": len(pairs), "total": len(results),
                               "degraded_excluded": degraded, "coverage": len(pairs)/len(results) if results else 0,
                               "mae": fmean(abs(x-y) for x, y in pairs) if pairs else None,
                               "pearson": correlation}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--fold", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--out", type=Path, default=Path("output/ompal/rubric.json"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--plan-only", action="store_true", help="Validate annotations and reference pairing without loading models")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    pairs = build_pairs(args.corpus.resolve(), args.fold)
    if args.limit:
        # A smoke run should exercise matched audio, even when the first
        # learner's script is absent from this fold's native recordings.
        pairs = sorted(pairs, key=lambda pair: pair["reference_id"] is None)[:args.limit]
    report = {"source": SOURCE, "license": "CC-BY-4.0", "fold": args.fold, "smoke_run": bool(args.limit),
              "annotation_sha256": hashlib.sha256((args.corpus / "test" / f"test_{args.fold}_scores.json").read_bytes()).hexdigest(),
              "validation_status": "benchmark_only_not_calibrated",
              "accuracy_mapping": "Current pronunciation similarity is a proxy, not the published OMPAL regression model."}
    if args.plan_only:
        report.update(mode="plan_only", pairs=pairs)
    else:
        from domain.pronunciation.rubric import RubricPolicy
        policy = RubricPolicy.from_env()
        results = [score_pair(pair, policy) for pair in pairs]
        report.update(mode="measured", policy=policy.to_dict(), results=results, summary=summarize(results))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"report": str(args.out), "utterances": len(pairs), "mode": report["mode"]}))


if __name__ == "__main__":
    main()
