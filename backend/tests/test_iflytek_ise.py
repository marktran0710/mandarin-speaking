"""Candidate D's guard rails and mapping logic. This adapter never sends
real audio anywhere in this test suite -- every test here either exercises
pure functions (auth-URL construction, frame chunking, response parsing,
tone-correctness mapping) or the dry-run path, which by construction opens
no network connection and needs no credentials.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.candidates.praat_logistic import FinalTestLockedError
from benchmarking.external.iflytek_ise import (
    AUDIO_FRAME_BYTES,
    IflytekCredentials,
    IsePhoneResult,
    IseRequest,
    IseSyllableResult,
    build_audio_frames,
    build_authorized_url,
    dry_run_summary,
    evaluate_utterance,
    map_tone_correctness,
    parse_ise_response,
)


class TestFinalTestGuard:
    def test_dry_run_summary_raises_for_final_test(self):
        with pytest.raises(FinalTestLockedError):
            dry_run_summary("final_test")

    def test_dry_run_summary_raises_for_final_test_even_with_a_large_sample_size(self):
        """A caller can't work around the guard by tweaking unrelated
        parameters -- the split name alone decides."""
        with pytest.raises(FinalTestLockedError):
            dry_run_summary("final_test", sample_size=10_000)

    def test_module_never_passes_unlock_final_test(self):
        """AST-based, not a text search -- the module's own docstrings
        explain the guard using the literal string "unlock_final_test=True"
        as prose, which would make a plain substring search trip on the
        documentation instead of on real call sites."""
        import ast

        from benchmarking.external import iflytek_ise

        tree = ast.parse(Path(iflytek_ise.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "unlock_final_test":
                assert not (isinstance(node.value, ast.Constant) and node.value.value is True)


class TestDryRunNeverTouchesTheNetwork:
    def test_evaluate_utterance_dry_run_needs_no_credentials(self, tmp_path):
        """The default call path -- no IFLYTEK_* environment variables set
        at all -- must still succeed, because dry_run=True is the default."""
        for key in ("IFLYTEK_APP_ID", "IFLYTEK_API_KEY", "IFLYTEK_API_SECRET"):
            os.environ.pop(key, None)
        result = evaluate_utterance(tmp_path / "nonexistent.wav", "你好")
        assert result.n_unique_utterances == 1
        assert result.sample_requests[0]["audio_exists"] is False

    def test_evaluate_utterance_dry_run_does_not_import_websocket_at_module_load(self):
        """`websocket` is only imported inside the real-call branch, so a
        machine without it installed can still run every dry-run path."""
        import ast

        from benchmarking.external import iflytek_ise

        tree = ast.parse(Path(iflytek_ise.__file__).read_text(encoding="utf-8"))
        top_level_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "websocket" not in top_level_imports


class TestAuthUrlConstruction:
    def test_url_contains_the_required_query_parameters(self):
        creds = IflytekCredentials(app_id="appid", api_key="key123", api_secret="secret456")
        url = build_authorized_url(creds, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert url.startswith("wss://ise-api.xfyun.cn/v2/open-ise?")
        assert "authorization=" in url
        assert "date=" in url
        assert "host=" in url

    def test_signature_is_deterministic_for_the_same_inputs(self):
        creds = IflytekCredentials(app_id="appid", api_key="key123", api_secret="secret456")
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert build_authorized_url(creds, now=now) == build_authorized_url(creds, now=now)

    def test_a_different_secret_changes_the_signature(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        url_a = build_authorized_url(IflytekCredentials("id", "key", "secret-a"), now=now)
        url_b = build_authorized_url(IflytekCredentials("id", "key", "secret-b"), now=now)
        assert url_a != url_b

    def test_credentials_from_env_reports_exactly_whats_missing(self, monkeypatch):
        monkeypatch.delenv("IFLYTEK_APP_ID", raising=False)
        monkeypatch.delenv("IFLYTEK_API_KEY", raising=False)
        monkeypatch.delenv("IFLYTEK_API_SECRET", raising=False)
        monkeypatch.setenv("IFLYTEK_APP_ID", "x")
        with pytest.raises(RuntimeError) as excinfo:
            IflytekCredentials.from_env()
        assert "IFLYTEK_API_KEY" in str(excinfo.value)
        assert "IFLYTEK_API_SECRET" in str(excinfo.value)
        assert "IFLYTEK_APP_ID" not in str(excinfo.value)  # was set, shouldn't be reported missing


class TestAudioFrameChunking:
    def test_chunks_respect_the_frame_size_limit(self):
        pcm = bytes(range(256)) * 20  # 5120 bytes
        frames = build_audio_frames(pcm)
        for frame in frames[:-1]:
            import base64
            decoded = base64.b64decode(frame["data"]["data"])
            assert len(decoded) <= AUDIO_FRAME_BYTES

    def test_first_frame_is_marked_aus_1_status_1(self):
        frames = build_audio_frames(b"x" * 100)
        assert frames[0]["business"]["aus"] == 1
        assert frames[0]["data"]["status"] == 1

    def test_last_frame_is_marked_aus_4_status_2(self):
        frames = build_audio_frames(b"x" * (AUDIO_FRAME_BYTES * 3))
        assert frames[-1]["business"]["aus"] == 4
        assert frames[-1]["data"]["status"] == 2

    def test_empty_audio_still_produces_one_terminal_frame(self):
        frames = build_audio_frames(b"")
        assert len(frames) == 1
        assert frames[0]["business"]["aus"] == 4


class TestResponseParsingExtractsOnlyDocumentedFields:
    SAMPLE_XML = """<?xml version="1.0"?>
    <xml_result>
      <read_sentence total_score="85.0" phone_score="80.0" tone_score="70.0"
                      fluency_score="90.0" integrity_score="100.0">
        <sentence>
          <word>
            <syll symbol="ta1" mono_tone="1" content="他" dp_message="0" beg_pos="0" end_pos="50">
              <phone perr_msg="0" perr_level_msg="1" is_yun="0" dp_message="0" beg_pos="0" end_pos="20"/>
              <phone perr_msg="0" perr_level_msg="1" is_yun="1" dp_message="0" beg_pos="20" end_pos="50"/>
            </syll>
          </word>
        </sentence>
      </read_sentence>
    </xml_result>
    """

    def test_extracts_sentence_level_scores(self):
        result = parse_ise_response(self.SAMPLE_XML)
        assert result.total_score == 85.0
        assert result.tone_score == 70.0
        assert result.fluency_score == 90.0

    def test_extracts_syllable_and_phone_fields(self):
        result = parse_ise_response(self.SAMPLE_XML)
        assert len(result.syllables) == 1
        syll = result.syllables[0]
        assert syll.mono_tone == "1"
        assert len(syll.phones) == 2
        assert syll.phones[0].is_yun == "0"
        assert syll.phones[1].is_yun == "1"

    def test_raw_response_is_preserved_verbatim(self):
        result = parse_ise_response(self.SAMPLE_XML)
        assert result.raw_response == self.SAMPLE_XML

    def test_malformed_xml_does_not_raise_and_notes_the_failure(self):
        result = parse_ise_response("not xml at all <<<")
        assert result.total_score is None
        assert any("parse error" in note.lower() for note in result.parse_notes)

    def test_missing_sentence_level_field_is_noted_not_invented(self):
        xml = '<xml_result><read_sentence total_score="50.0"></read_sentence></xml_result>'
        result = parse_ise_response(xml)
        assert result.total_score == 50.0
        assert result.tone_score is None
        assert any("tone_score" in note for note in result.parse_notes)


class TestToneCorrectnessMapping:
    """Rule, confirmed and restated by the task: tone lives on the
    final/rime (`is_yun == "1"`), so only that phone entry's `perr_msg`
    decides -- 0=vowel+tone correct, 1=vowel error only (NA for tone),
    2=tone error, 3=vowel+tone error."""

    def _phone(self, **kwargs):
        return IsePhoneResult(**kwargs)

    def _syll_with_yun_perr(self, perr_msg, *, include_initial=True):
        phones = []
        if include_initial:
            phones.append(self._phone(perr_msg="0", dp_message="0", is_yun="0"))
        phones.append(self._phone(perr_msg=perr_msg, dp_message="0", is_yun="1"))
        return IseSyllableResult(phones=tuple(phones))

    def test_perr_msg_zero_on_the_yun_phone_maps_to_one(self):
        assert map_tone_correctness(self._syll_with_yun_perr("0")) == 1

    def test_perr_msg_two_on_the_yun_phone_maps_to_zero(self):
        assert map_tone_correctness(self._syll_with_yun_perr("2")) == 0

    def test_perr_msg_three_on_the_yun_phone_maps_to_zero(self):
        assert map_tone_correctness(self._syll_with_yun_perr("3")) == 0

    def test_perr_msg_one_on_the_yun_phone_is_ambiguous_for_tone_and_marked_na(self):
        """perr_msg == "1" is documented as a vowel error only, making NO
        claim about tone -- must not be silently treated as tone-correct."""
        assert map_tone_correctness(self._syll_with_yun_perr("1")) is None

    def test_initial_phone_errors_are_irrelevant_to_the_tone_verdict(self):
        """An error on the is_yun=="0" (initial/consonant) phone must not
        influence the tone verdict -- only the yun phone's perr_msg counts."""
        syll = IseSyllableResult(phones=(
            self._phone(perr_msg="2", dp_message="0", is_yun="0"),  # would be wrong if it counted
            self._phone(perr_msg="0", dp_message="0", is_yun="1"),
        ))
        assert map_tone_correctness(syll) == 1

    def test_no_yun_phone_present_is_na(self):
        syll = IseSyllableResult(phones=(self._phone(perr_msg="0", dp_message="0", is_yun="0"),))
        assert map_tone_correctness(syll) is None

    def test_missed_syllable_with_no_phone_breakdown_is_na(self):
        """dp_message indicating the syllable was missed/added/replaced, with
        no phone-level breakdown at all, means no tone was ever evaluated."""
        syll = IseSyllableResult(dp_message="16", phones=())
        assert map_tone_correctness(syll) is None

    def test_no_phone_entries_at_all_is_na(self):
        syll = IseSyllableResult(phones=())
        assert map_tone_correctness(syll) is None

    def test_more_than_one_yun_phone_is_na_rather_than_guessed(self):
        syll = IseSyllableResult(phones=(
            self._phone(perr_msg="0", dp_message="0", is_yun="1"),
            self._phone(perr_msg="2", dp_message="0", is_yun="1"),
        ))
        assert map_tone_correctness(syll) is None

    def test_never_falls_back_to_a_tone_score_threshold(self):
        """Structural guard: the function's signature takes only the parsed
        syllable, never a raw tone_score or a threshold -- there is no way
        for it to fall back to score-thresholding even by accident."""
        import inspect

        params = list(inspect.signature(map_tone_correctness).parameters)
        assert params == ["syllable"]


class TestIseRequest:
    def test_estimated_frame_count_matches_manual_chunking(self, tmp_path):
        import wave

        path = tmp_path / "sample.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b"\x00\x00" * 16000)  # 1 second of silence

        request = IseRequest(audio_path=path, reference_text="你好")
        assert request.audio_duration_seconds() == pytest.approx(1.0)
        manual = len(build_audio_frames(b"\x00\x00" * 16000))
        assert request.estimated_frame_count() == manual

    def test_first_frame_payload_includes_bom_prefixed_text(self):
        request = IseRequest(audio_path=Path("x.wav"), reference_text="你好")
        payload = request.first_frame_payload(app_id="appid123")
        assert payload["business"]["text"] == "﻿你好"
        assert payload["common"]["app_id"] == "appid123"
        assert payload["business"]["auf"] == "audio/L16;rate=16000"
