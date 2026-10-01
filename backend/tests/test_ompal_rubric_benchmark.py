import json

import pytest

from scripts.research.ompal.run_rubric import build_pairs, load_scores, score_pair, summarize


def record(text="你好", **kwargs):
    return {"text": text, "accuracy": 4.33, "fluency": 4.67, "prosody": 4, **kwargs}


def test_official_fold_pairs_by_text_not_utterance_number(tmp_path):
    (tmp_path / "test").mkdir()
    (tmp_path / "test/test_1_scores.json").write_text(json.dumps({
        "00100201": record(), "00200109": record(), "00200101": record("再見"),
    }), encoding="utf-8")
    pairs = build_pairs(tmp_path, 1)
    assert len(pairs) == 2
    assert pairs[0]["reference_audio"] is None
    assert pairs[1]["reference_id"] == "00100201"
    assert pairs[1]["reference_audio"] == str(tmp_path / "wav/SPEAKER01002/00100201.wav")
    assert pairs[1]["audio"] == str(tmp_path / "wav/SPEAKER02001/00200109.wav")


@pytest.mark.parametrize("uid,score", [("../evil", 4), ("00200101", float("nan")), ("00200101", 0), ("00200101", True)])
def test_reject_invalid_annotations(tmp_path, uid, score):
    path = tmp_path / "scores.json"
    path.write_text(json.dumps({uid: record(accuracy=score)}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_scores(path)


def test_coverage_excludes_missing_and_degraded_evidence():
    results = [
        {"status": "measured", "expert": record(), "dimensions": {"pronunciation": {"score": 4}, "fluency": {"score": 5}}},
        {"status": "measured", "expert": record(), "dimensions": {"pronunciation": {"score": None}, "fluency": {"score": 1, "evidence_quality": "degraded"}}},
        {"status": "error", "expert": record(), "dimensions": {"fluency": {"score": 1}}},
    ]
    summary = summarize(results)
    assert summary["accuracy"]["scored"] == 1
    assert summary["accuracy"]["mae"] == pytest.approx(.33)
    assert summary["fluency"]["coverage"] == pytest.approx(1/3)
    assert summary["fluency"]["degraded_excluded"] == 1
    assert summary["prosody"]["mae"] is None
    assert summary["accuracy"]["pearson"] is None


def test_perfect_correlation():
    rows = [{"status": "measured", "expert": record(accuracy=n), "dimensions": {"pronunciation": {"score": n}}} for n in (1, 3, 5)]
    assert summarize(rows)["accuracy"]["pearson"] == pytest.approx(1)


def test_unavailable_model_preserves_acoustic_dimensions(tmp_path, monkeypatch):
    import domain.pronunciation.rubric as rubric
    import services.pronunciation.extraction as extraction
    import services.pronunciation.wav2vec2_scoring as wav2vec

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fixture")
    monkeypatch.setattr(extraction, "extract_utterance_features", lambda *args: object())
    monkeypatch.setattr(rubric, "score_fluency", lambda *args: {"score": 4})
    monkeypatch.setattr(rubric, "score_prosody", lambda *args: {"score": 3})
    def unavailable(**kwargs):
        raise wav2vec.Wav2Vec2Unavailable("model missing")
    monkeypatch.setattr(wav2vec, "analyze_wav2vec2", unavailable)
    result = score_pair({"audio": str(audio), "reference_audio": str(audio), "text": "你好"}, None)
    assert result["status"] == "measured"
    assert result["dimensions"]["pronunciation"]["score"] is None
    assert result["dimensions"]["fluency"]["score"] == 4
    assert result["dimensions"]["prosody"]["score"] == 3
