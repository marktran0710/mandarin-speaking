import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from scripts.learning_engine_verification.runner import CheckResult, write_report
from scripts.verify_learning_engine import (
    FOCUSED_TEST_TIMEOUT_SECONDS,
    _analyze_voice_entry,
    _db_checks,
    _safe_url,
    _voice_checks,
    _voice_technical_result,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_documented_direct_entrypoint_imports_backend_packages(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND_ROOT / 'scripts' / 'verify_learning_engine.py'),
            '--engine',
            'voice',
            '--provider',
            'groq',
            '--output-dir',
            str(tmp_path),
        ],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    reports = list(tmp_path.glob('learning-engine-voice-*.json'))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding='utf-8'))['summary']['BLOCKED'] == 1


def test_bkt_mastery_authorization_subprocess_exits_cleanly():
    result = subprocess.run(
        [
            sys.executable,
            '-m',
            'pytest',
            '-q',
            'tests/test_bkt_mastery_api.py::test_student_cannot_read_another_students_mastery',
        ],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_focused_suite_timeout_is_fail_and_database_is_still_dropped():
    algorithm = CheckResult('algorithm', 'PASS', 1, 1)
    migration = subprocess.CompletedProcess(['alembic'], 0, '', '')
    timeout = subprocess.TimeoutExpired(
        ['pytest'],
        FOCUSED_TEST_TIMEOUT_SECONDS,
        output='partial test output',
    )

    with (
        patch('scripts.verify_learning_engine._algorithm_checks', return_value=[algorithm]),
        patch('scripts.verify_learning_engine._db_url', return_value='postgresql://user:secret@localhost/source'),
        patch('scripts.verify_learning_engine._create_database') as create_database,
        patch('scripts.verify_learning_engine._drop_database') as drop_database,
        patch('scripts.verify_learning_engine._run', side_effect=[migration, timeout]),
    ):
        results = _db_checks('bkt', keep=False)

    assert create_database.call_count == 1
    assert drop_database.call_count == 1
    focused = next(result for result in results if result.name == 'bkt focused pytest')
    assert focused.status == 'FAIL'
    assert focused.actual == 'timeout'
    assert 'partial test output' in (focused.detail or '')
    assert results[0] is algorithm


def test_cleanup_failure_keeps_prior_results_in_report():
    algorithm = CheckResult('algorithm', 'PASS', 1, 1)
    completed = subprocess.CompletedProcess(['command'], 0, '', '')

    with (
        patch('scripts.verify_learning_engine._algorithm_checks', return_value=[algorithm]),
        patch('scripts.verify_learning_engine._db_url', return_value='postgresql://user:secret@localhost/source'),
        patch('scripts.verify_learning_engine._create_database'),
        patch('scripts.verify_learning_engine._drop_database', side_effect=RuntimeError('cleanup failed')),
        patch('scripts.verify_learning_engine._run', side_effect=[completed, completed]),
    ):
        results = _db_checks('sm2', keep=False)

    assert [(result.name, result.status) for result in results] == [
        ('algorithm', 'PASS'),
        ('sm2 focused pytest', 'PASS'),
        ('sm2 database cleanup', 'FAIL'),
    ]

def test_safe_url_replaces_database_without_exposing_credentials():
    value = _safe_url('postgresql://user:secret@localhost:5432/app?sslmode=require', 'mandarin_verify_x')
    assert value == 'postgresql://user:secret@localhost:5432/mandarin_verify_x?sslmode=require'
    assert 'secret' in value  # URL remains usable; reports never serialize it.

def test_voice_missing_manifest_is_blocked(tmp_path):
    result = _voice_checks(str(tmp_path), 'groq')
    assert result[0].status == 'BLOCKED'

def test_voice_manifest_requires_real_files_and_metadata(tmp_path):
    (tmp_path / 'a.wav').write_bytes(b'RIFF')
    (tmp_path / 'manifest.json').write_text(json.dumps({'recordings': [{'file':'a.wav','target_text':'你好','pinyin':'ni3 hao3','context':'greeting'}]}), encoding='utf-8')
    result = _voice_checks(str(tmp_path), None)
    assert result[0].status == 'BLOCKED'

def test_report_contains_machine_and_human_outputs(tmp_path):
    md, js = write_report([CheckResult('x', 'PASS', 1, 1)], tmp_path, 'bkt')
    assert md.is_file() and js.is_file()
    assert json.loads(js.read_text())['summary']['PASS'] == 1
    assert '**PASS**' in md.read_text()


@pytest.mark.asyncio
async def test_voice_entry_never_supplies_a_transcript_and_uses_auto_asr(tmp_path):
    (tmp_path / 'human.wav').write_bytes(b'RIFF-real-recording-placeholder')
    item = {
        'file': 'human.wav',
        'target_text': '你好',
        'pinyin': 'ni3 hao3',
        'context': 'Greeting',
        'vocabulary': '你好',
    }
    with patch(
        'services.speech_analysis._do_analyze',
        new_callable=AsyncMock,
        return_value={'ok': True},
    ) as analyze:
        await _analyze_voice_entry(tmp_path, item, 'groq')

    args = analyze.await_args.args
    kwargs = analyze.await_args.kwargs
    assert args[1:3] == ('', 'auto')
    assert kwargs['ai_provider'] == 'groq'
    assert kwargs['scene_target_text'] == '你好'
    assert kwargs['scene_suggested_answer'] == '你好'


@pytest.mark.asyncio
async def test_cloud_coach_adapter_receives_each_praat_measurement(monkeypatch):
    import services.speech.feedback.pipeline as pipeline

    adapter = AsyncMock(return_value={'provider': 'groq'})
    monkeypatch.setattr(pipeline, 'GROQ_API_KEY', 'test-groq-key')
    monkeypatch.setattr(pipeline, '_feedback_with_groq', adapter)

    await pipeline.generate_language_feedback(
        '你好',
        provider='groq',
        praat_tone_accuracy=78.0,
        praat_fluency_score=72.0,
        praat_speech_rate=3.0,
        praat_vowel_quality='clear',
        praat_pause_analysis={'pause_count': 1},
        word_prosody=[{'token': '你', 'tone_accuracy': 82.0}],
    )

    passed = adapter.await_args.kwargs
    assert passed['praat_tone_accuracy'] == 78.0
    assert passed['praat_fluency_score'] == 72.0
    assert passed['praat_speech_rate'] == 3.0
    assert passed['praat_vowel_quality'] == 'clear'
    assert passed['praat_pause_analysis'] == {'pause_count': 1}
    assert passed['word_prosody'] == [{'token': '你', 'tone_accuracy': 82.0}]


def test_voice_technical_result_requires_cloud_trace_to_match_praat_response():
    response = {
        'tone_accuracy': 78.0,
        'fluency_score': 72.0,
        'speech_rate': 3.0,
        'pitch_contour': [[0.1, 210.0]],
        'word_prosody': [{'word': '你', 'passed': True}],
        'feedback_quality': {'can_score_pronunciation': True},
        'feedback_provenance': {
            'requested_provider': 'groq',
            'executed_provider': 'groq',
            'fallback_used': False,
            'acoustic_context_used': True,
            'acoustic_context_supplied': True,
            'pronunciation_source': 'praat_acoustic_measurements',
        },
        'processing_trace': {
            'stages': [{
                'stage': 'feedback',
                'status': 'passed',
                'input': {
                    'tone_accuracy': 78.0,
                    'fluency_score': 72.0,
                    'speech_rate': 3.0,
                    'word_prosody': [{'word': '你', 'passed': True}],
                },
            }],
        },
    }
    item = {'file': 'human.wav'}
    assert _voice_technical_result(item, response, 'groq').status == 'PASS'

    response['processing_trace']['stages'][0]['input']['tone_accuracy'] = 99.0
    assert _voice_technical_result(item, response, 'groq').status == 'FAIL'


def test_voice_technical_result_distinguishes_retry_audio_from_cloud_outage():
    item = {'file': 'silence.wav'}
    retry = {
        'feedback_quality': {'status': 'retry', 'can_score_pronunciation': False},
        'feedback_provenance': {
            'requested_provider': 'groq', 'executed_provider': 'local',
            'fallback_used': True, 'pronunciation_source': 'local_deterministic',
        },
        'processing_trace': {'stages': [{'stage': 'feedback', 'status': 'skipped'}]},
    }
    assert _voice_technical_result(item, retry, 'groq').status == 'PASS'

    outage = {
        **retry,
        'feedback_quality': {'status': 'reliable', 'can_score_pronunciation': True},
        'feedback_provenance': {
            'requested_provider': 'groq', 'executed_provider': 'local',
            'fallback_used': True, 'pronunciation_source': 'praat_acoustic_measurements',
        },
        'processing_trace': {'stages': [{'stage': 'feedback', 'status': 'failed'}]},
    }
    assert _voice_technical_result(item, outage, 'groq').status == 'BLOCKED'
