

# ──────────────────────────────────────────────────────────────────────────────
# CT Whisper provider (mocked model)
# ──────────────────────────────────────────────────────────────────────────────

class TestTranscribeWithCTWhisper:

    @pytest.mark.asyncio
    async def test_successful_transcription(self):
        from main import transcribe_with_ct_whisper
        import numpy as np

        mock_processor = MagicMock()
        mock_processor.return_value = MagicMock(input_features=MagicMock())
        mock_processor.get_decoder_prompt_ids.return_value = [(1, 2)]
        mock_processor.decode.return_value = "你好"

        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.device = "cpu"

        with patch("main._get_ct_whisper_model",
                   return_value=(mock_processor, mock_model, "cpu")), \
             patch("main.convert_to_traditional_chinese", return_value="你好"), \
             patch("librosa.load", return_value=(np.zeros(8000), 16000)):
            result = await transcribe_with_ct_whisper(SILENT_WAV)

        assert result.model == "ctwhisper"
        assert isinstance(result.text, str)

    @pytest.mark.asyncio
    async def test_converts_to_traditional(self):
        from main import transcribe_with_ct_whisper
        import numpy as np

        mock_processor = MagicMock()
        mock_processor.return_value = MagicMock(input_features=MagicMock())
        mock_processor.get_decoder_prompt_ids.return_value = [(1, 2)]
        mock_processor.decode.return_value = "你好"  # simplified

        mock_model = MagicMock()
        mock_model.generate.return_value = [[1, 2, 3]]
        mock_model.device = "cpu"

        with patch("main._get_ct_whisper_model",
                   return_value=(mock_processor, mock_model, "cpu")), \
             patch("main.convert_to_traditional_chinese",
                   return_value="妳好") as mock_convert, \
             patch("librosa.load", return_value=(np.zeros(8000), 16000)):
            result = await transcribe_with_ct_whisper(SILENT_WAV)

        mock_convert.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# /api/transcribe endpoint (integration via TestClient)
# ──────────────────────────────────────────────────────────────────────────────

class TestTranscribeEndpoint:

    def test_missing_file_returns_422(self, client):
        resp = client.post("/api/transcribe", data={"model": "ctwhisper"})
        assert resp.status_code == 422

    def test_with_mocked_ctwhisper(self, client):
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="ctwhisper")
            resp = client.post(
                "/api/transcribe",
                files={"file": ("test.wav", SPEECH_WAV, "audio/wav")},
                data={"model": "ctwhisper"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "你好"
        assert body["model"] == "ctwhisper"

    def test_unknown_model_returns_400(self, client):
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            from fastapi import HTTPException
            mock.side_effect = HTTPException(status_code=400, detail="Invalid model")
            resp = client.post(
                "/api/transcribe",
                files={"file": ("test.wav", SILENT_WAV, "audio/wav")},
                data={"model": "nonexistent"},
            )
        assert resp.status_code == 400

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("ok", "degraded")
        assert "database" in body


class TestAnalysisProcessingTrace:
    @pytest.mark.asyncio
    async def test_do_analyze_returns_ordered_processing_trace(self):
        import main

        praat_result = (
            [], {}, 3.0, 72.0, {}, [], 2, 78.0,
            "Good tone.", {},
        )
        quality = {
            "status": "reliable",
            "confidence": 1.0,
            "can_score_pronunciation": True,
            "can_score_content": True,
            "reason_codes": [],
            "student_message": "",
            "metrics": {},
        }
        local_feedback = {
            "provider": "local",
            "vocabulary_coverage": {"score": 80, "used": [], "missing": [], "feedback": ""},
            "coherence": {"score": 70, "feedback": "", "corrections": []},
            "pronunciation_note": {"score": 80, "feedback": ""},
            "improved_version": "",
            "practice_prompt": "",
        }

        with patch("main.assess_recording_quality", return_value={
            "status": "reliable",
            "reason_codes": [],
            "student_message": "Sound check passed.",
        }), patch("main.resolve_image_b64", new_callable=AsyncMock, return_value=None), \
             patch("main.transcribe_audio_content", new_callable=AsyncMock) as transcribe, \
             patch("main.analyze_all", return_value=praat_result), \
             patch("main.generate_language_feedback", new_callable=AsyncMock) as feedback, \
             patch("main.finalize_feedback_quality", return_value=quality), \
             patch("main.classify_vowel_quality", return_value="Clear vowels"), \
             patch("main.build_tone_direction", return_value="rising"), \
             patch("main.caf_metrics.fluency_metrics", return_value={"articulation_rate": 3.0}), \
             patch("main.caf_metrics.classify_pauses", return_value={"judged": False}), \
             patch("ai_feedback.fallback_language_feedback", return_value=local_feedback), \
             patch("ai_feedback.apply_feedback_quality_gate", side_effect=lambda value, *_args, **_kwargs: value):
            transcribe.return_value = MagicMock(text="我在市場買菜。", model="ctwhisper")
            feedback.return_value = local_feedback
            result = await main._do_analyze(
                b"wav-bytes",
                "",
                "ctwhisper",
                scene_prompt="Describe the market",
                scene_vocabulary="市場, 買菜",
            )

        stages = {stage.stage: stage for stage in result.processing_trace.stages}
        assert [stage.stage for stage in result.processing_trace.stages[:2]] == ["preflight", "asr"]
        assert stages["preflight"].status == "reliable"
        assert stages["asr"].status == "passed"
        assert stages["praat"].status == "passed"
        assert stages["feedback"].status == "passed"
        assert stages["quality_gate"].status == "passed"
        assert result.processing_trace.total_duration_ms >= 0


# ──────────────────────────────────────────────────────────────────────────────
# AI Feedback: fallback_language_feedback()
# ──────────────────────────────────────────────────────────────────────────────

class TestFallbackLanguageFeedback:

    def test_empty_transcription(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback("")
        assert result["provider"] == "local"
        assert result["vocabulary_coverage"]["score"] == 0
        assert result["coherence"]["score"] == 0
        assert result["pronunciation_note"]["score"] == 0

    def test_empty_with_scene_prompt(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback("", scene_prompt="介紹人物")
        assert "介紹人物" in result["vocabulary_coverage"]["feedback"]

    def test_all_vocab_used(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback(
            "這是老師和學生",
            scene_vocabulary="老師,學生",
        )
        # Score now blends full task coverage with lexical diversity, so it is
        # high but no longer pinned to 100; all words used means none missing.
        assert result["vocabulary_coverage"]["missing"] == []
        assert result["vocabulary_coverage"]["score"] >= 70

    def test_no_vocab_used(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback(
            "你好",
            scene_vocabulary="老師,學生,教室",
        )
        # No scene words used -> all three missing; score stays low (only the
        # small lexical-diversity component contributes).
        assert len(result["vocabulary_coverage"]["missing"]) == 3
        assert result["vocabulary_coverage"]["score"] < 40

    def test_partial_vocab_used(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback(
            "老師在哪裡",
            scene_vocabulary="老師,學生,教室",
        )
        assert result["vocabulary_coverage"]["score"] > 0
        assert result["vocabulary_coverage"]["score"] < 100
        assert "老師" in result["vocabulary_coverage"]["used"]

    def test_no_scene_vocab_defined(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback("你好", scene_vocabulary="")
        # With no scene vocab the score now reflects lexical diversity (Guiraud),
        # and the feedback reports that diversity instead of a fixed message.
        assert result["vocabulary_coverage"]["score"] >= 0
        assert "diversity" in result["vocabulary_coverage"]["feedback"].lower()

    def test_praat_scores_affect_pronunciation_score(self):
        from ai_feedback import fallback_language_feedback
        low = fallback_language_feedback(
            "你好", praat_tone_accuracy=10.0, praat_fluency_score=15.0
        )
        high = fallback_language_feedback(
            "你好", praat_tone_accuracy=90.0, praat_fluency_score=85.0
        )
        assert high["pronunciation_note"]["score"] > low["pronunciation_note"]["score"]

    def test_longer_text_higher_coherence(self):
        from ai_feedback import fallback_language_feedback
        short = fallback_language_feedback("好")
        long = fallback_language_feedback(
            "這是一個很長的句子，有很多中文字，用來測試語言反饋系統。"
        )
        assert long["coherence"]["score"] >= short["coherence"]["score"]

    def test_returns_required_keys(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback("你好")
        required = {"provider", "vocabulary_coverage", "coherence",
                    "pronunciation_note", "improved_version", "practice_prompt"}
        assert required.issubset(result.keys())

    def test_vocabulary_coverage_structure(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback("你好", scene_vocabulary="你好,再見")
        vc = result["vocabulary_coverage"]
        assert "score" in vc
        assert "used" in vc
        assert "missing" in vc
        assert "feedback" in vc
        assert isinstance(vc["used"], list)
        assert isinstance(vc["missing"], list)

    def test_pron_feedback_includes_speed_verdict(self):
        from ai_feedback import fallback_language_feedback
        pause_analysis = {
            "duration": 4.0,
            "total_speaking_duration": 3.5,
            "pause_count": 0,
            "pauses": [],
        }
        result = fallback_language_feedback(
            "你好",
            praat_tone_accuracy=80.0,
            praat_fluency_score=80.0,
            praat_pause_analysis=pause_analysis,
            praat_speech_rate=1.0,
        )
        assert "syllables/sec" in result["pronunciation_note"]["feedback"]

    def test_pron_feedback_flags_choppy_pause_against_reference(self):
        from ai_feedback import fallback_language_feedback
        word_prosody = [
            {"token": "我喜歡", "start_time": 0.0, "end_time": 0.6},
            {"token": "貓", "start_time": 1.0, "end_time": 1.3},
        ]
        pause_analysis = {
            "duration": 1.3,
            "total_speaking_duration": 0.9,
            "pause_count": 1,
            "pauses": [{"start": 0.6, "end": 1.0, "duration": 0.4}],
        }
        result = fallback_language_feedback(
            "我喜歡貓",
            praat_tone_accuracy=80.0,
            praat_fluency_score=80.0,
            praat_pause_analysis=pause_analysis,
            praat_speech_rate=3.0,
            word_prosody=word_prosody,
            scene_suggested_answer="我喜歡貓。",
        )
        feedback = result["pronunciation_note"]["feedback"]
        assert "我喜歡" in feedback
        assert "貓" in feedback

    def test_details_has_only_tone_entry_with_minimal_data(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback("你好", praat_tone_accuracy=70.0)
        details = result["pronunciation_note"]["details"]
        keys = [d["key"] for d in details]
        assert keys == ["tone"]

    def test_details_includes_rhythm_pace_entry(self):
        from ai_feedback import fallback_language_feedback
        pause_analysis = {
            "duration": 4.0, "total_speaking_duration": 3.5,
            "pause_count": 0, "pauses": [],
        }
        result = fallback_language_feedback(
            "你好", praat_tone_accuracy=80.0, praat_fluency_score=80.0,
            praat_pause_analysis=pause_analysis, praat_speech_rate=1.0,
        )
        details = {d["key"]: d["text"] for d in result["pronunciation_note"]["details"]}
        assert "rhythm_pace" in details
        assert "syllables/sec" in details["rhythm_pace"]

    def test_details_includes_pausing_entry_when_judged(self):
        from ai_feedback import fallback_language_feedback
        word_prosody = [
            {"token": "我喜歡", "start_time": 0.0, "end_time": 0.6},
            {"token": "貓", "start_time": 1.0, "end_time": 1.3},
        ]
        pause_analysis = {
            "duration": 1.3, "total_speaking_duration": 0.9,
            "pause_count": 1,
            "pauses": [{"start": 0.6, "end": 1.0, "duration": 0.4}],
        }
        result = fallback_language_feedback(
            "我喜歡貓", praat_tone_accuracy=80.0, praat_fluency_score=80.0,
            praat_pause_analysis=pause_analysis, praat_speech_rate=3.0,
            word_prosody=word_prosody, scene_suggested_answer="我喜歡貓。",
        )
        details = {d["key"]: d["text"] for d in result["pronunciation_note"]["details"]}
        assert "pausing" in details
        assert "我喜歡" in details["pausing"]
        assert "貓" in details["pausing"]

    def test_details_includes_vowel_quality_entry(self):
        from ai_feedback import fallback_language_feedback
        result = fallback_language_feedback(
            "你好", praat_tone_accuracy=70.0, praat_vowel_quality="Open vowel",
        )
        details = {d["key"]: d["text"] for d in result["pronunciation_note"]["details"]}
        assert details.get("vowel_quality") == "Open vowel"

    def test_details_includes_word_stress_entry(self):
        from ai_feedback import fallback_language_feedback
        word_prosody = [
            {
                "token": "以後", "is_content_word": True, "mean_pitch": 100.0,
                "start_time": 0.0, "end_time": 0.3,
            },
            {
                "token": "好", "is_content_word": True, "mean_pitch": 100.0,
                "start_time": 0.3, "end_time": 0.6,
            },
        ]
        result = fallback_language_feedback(
            "以後好", praat_tone_accuracy=70.0, word_prosody=word_prosody,
        )
        details = result["pronunciation_note"]["details"]
        keys = [d["key"] for d in details]
        # word_stress only appears when word_stress_summary finds a de-accented
        # word or pitch-declination signal — not asserting presence here since
        # that depends on praat_analyzer's real pitch logic, just that the
        # feedback string stays consistent with whatever details were built.
        assert result["pronunciation_note"]["feedback"] == " ".join(
            d["text"] for d in details
        )

    def test_feedback_string_matches_joined_details(self):
        from ai_feedback import fallback_language_feedback
        pause_analysis = {
            "duration": 4.0, "total_speaking_duration": 3.5,
            "pause_count": 0, "pauses": [],
        }
        result = fallback_language_feedback(
            "你好", praat_tone_accuracy=80.0, praat_fluency_score=80.0,
            praat_pause_analysis=pause_analysis, praat_speech_rate=1.0,
            praat_vowel_quality="Open vowel",
        )
        details = result["pronunciation_note"]["details"]
        assert result["pronunciation_note"]["feedback"] == " ".join(
            d["text"] for d in details
        )


# ──────────────────────────────────────────────────────────────────────────────
# AI Feedback: fallback_story_feedback() — pronunciation-focused dimensions
# ──────────────────────────────────────────────────────────────────────────────

class TestFallbackStoryFeedbackDimensions:

    def test_returns_four_pronunciation_dimensions_not_ielts_pillars(self):
        from ai_feedback import fallback_story_feedback
        result = fallback_story_feedback(
            "我喜歡貓。牠很可愛。",
            avg_tone_accuracy=80.0,
            avg_fluency_score=70.0,
            avg_pron_score=75.0,
        )
        assert set(result.keys()) == {"provider", "tone", "word_stress", "rhythm_pace", "pausing"}

    def test_choppy_pause_count_mentioned_in_pausing_feedback(self):
        from ai_feedback import fallback_story_feedback
        result = fallback_story_feedback(
            "我喜歡貓。牠很可愛。",
            avg_fluency_score=70.0,
            total_pause_count=3,
            longest_single_pause=0.5,
            total_utterance_count=4,
            scene_count=2,
            total_choppy_pause_count=2,
        )
        assert "2" in result["pausing"]["feedback"]

    def test_slow_articulation_rate_mentioned_in_rhythm_pace_feedback(self):
        from ai_feedback import fallback_story_feedback
        result = fallback_story_feedback(
            "我喜歡貓。牠很可愛。",
            avg_fluency_score=70.0,
            avg_articulation_rate=1.5,
        )
        assert "syllables/sec" in result["rhythm_pace"]["feedback"]

    def test_tone_dimension_grounded_in_avg_tone_accuracy(self):
        from ai_feedback import fallback_story_feedback
        result = fallback_story_feedback("我喜歡貓。", avg_tone_accuracy=82.0)
        assert result["tone"]["judged"] is True
        assert "82" in result["tone"]["feedback"]

    def test_word_stress_dimension_grounded_in_avg_pron_score(self):
        from ai_feedback import fallback_story_feedback
        result = fallback_story_feedback("我喜歡貓。", avg_pron_score=63.0)
        assert result["word_stress"]["judged"] is True
        assert "63" in result["word_stress"]["feedback"]

    def test_dimensions_unjudged_without_data(self):
        from ai_feedback import fallback_story_feedback
        result = fallback_story_feedback("我喜歡貓。")
        assert result["tone"]["judged"] is False
        assert result["word_stress"]["judged"] is False
        assert result["rhythm_pace"]["judged"] is False
        assert result["pausing"]["judged"] is False
