"""Run focused BKT, SM-2 and voice verification checks safely."""
from __future__ import annotations
import argparse, asyncio, json, os, secrets, subprocess, sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Running ``python scripts/verify_learning_engine.py`` puts only the
    # scripts directory on sys.path. Add the backend root so the documented
    # direct entrypoint can import production packages such as services and
    # analytics just like ``python -m scripts.verify_learning_engine`` does.
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
try:
    from learning_engine_verification.runner import CheckResult, write_report
except ModuleNotFoundError:  # imported as scripts.verify_learning_engine by pytest
    from scripts.learning_engine_verification.runner import CheckResult, write_report

DEFAULT_OUT = ROOT / 'verification_reports'
DB_PREFIX = 'mandarin_verify_'
MIGRATION_TIMEOUT_SECONDS = 180
FOCUSED_TEST_TIMEOUT_SECONDS = 300

# Match the backend's normal configuration loading when this file is launched
# directly from the repository root. Values are never written to reports.
load_dotenv(ROOT / '.env')
load_dotenv(ROOT.parent / '.env.local')

def _safe_url(url: str, database: str | None = None) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, database or p.path.lstrip('/'), p.query, p.fragment))


def _redact(value: object) -> str:
    text = str(value)
    secrets_to_hide = [
        os.getenv(name)
        for name in ('DATABASE_URL', 'TEST_DATABASE_URL', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'GROQ_API_KEY')
    ]
    for secret in secrets_to_hide:
        if secret:
            text = text.replace(secret, '[redacted]')
            try:
                password = urlsplit(secret).password
            except ValueError:
                password = None
            if password:
                text = text.replace(password, '[redacted]')
    return text


def _db_url() -> str | None: return os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')
def _run(
    cmd: list[str],
    env: dict[str, str],
    *,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def _timeout_detail(exc: subprocess.TimeoutExpired) -> str:
    stdout = exc.stdout or ''
    stderr = exc.stderr or ''
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors='replace')
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors='replace')
    tail = _redact((stdout + stderr)[-1500:])
    return f'Timed out after {exc.timeout} seconds.' + (f' Last output: {tail}' if tail else '')


def _create_database(admin_url: str, name: str) -> None:
    import psycopg
    with psycopg.connect(_safe_url(admin_url, 'postgres'), autocommit=True) as conn:
        with conn.cursor() as cur: cur.execute(f'CREATE DATABASE "{name}"')
def _drop_database(admin_url: str, name: str) -> None:
    if not name.startswith(DB_PREFIX) or not name.replace('_','').isalnum(): raise ValueError('unsafe database name')
    import psycopg
    with psycopg.connect(_safe_url(admin_url, 'postgres'), autocommit=True) as conn:
        with conn.cursor() as cur: cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _algorithm_checks(engine: str) -> list[CheckResult]:
    """Run small independent reference checks before touching PostgreSQL."""
    if engine == 'bkt':
        from services.bkt_verification_golden import build_golden_report

        report = build_golden_report()
        results = []
        for check in report['checks']:
            expected = check['expected']
            actual = check['actual']
            results.append(CheckResult(
                f"BKT golden: {check['scenario']}",
                'PASS' if check['result'] == 'PASS' else 'FAIL',
                {'pLearned': expected['pLearned'], 'observationCount': expected['observationCount'], 'status': expected['status']},
                {'pLearned': actual['pLearned'], 'observationCount': actual['observationCount'], 'status': actual['status']},
                f"fixture={report['fixtureVersion']}; contract={report['contractStatus']}",
            ))
        return results
    from datetime import datetime, timezone
    from analytics.learner_model.srs import SrsState, review

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = SrsState()
    actual = []
    for moment in (now, datetime(2026, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 8, tzinfo=timezone.utc)):
        state = review(state, 4, moment)
        actual.append({'reps': state.reps, 'intervalDays': state.interval_days, 'ease': state.ease})
    expected = [
        {'reps': 1, 'intervalDays': 1, 'ease': 2.5},
        {'reps': 2, 'intervalDays': 6, 'ease': 2.5},
        {'reps': 3, 'intervalDays': 15, 'ease': 2.5},
    ]
    passed = actual == expected
    failed = review(state, 2, datetime(2026, 1, 23, tzinfo=timezone.utc))
    reset_actual = {'reps': failed.reps, 'intervalDays': failed.interval_days, 'ease': round(failed.ease, 2)}
    reset_expected = {'reps': 0, 'intervalDays': 1, 'ease': 2.18}
    return [
        CheckResult('SM-2 interval sequence', 'PASS' if passed else 'FAIL', expected, actual, 'Modified binary policy q=4.'),
        CheckResult('SM-2 failure reset', 'PASS' if reset_actual == reset_expected else 'FAIL', reset_expected, reset_actual, 'q=2 resets repetitions and interval.'),
    ]


def _db_checks(engine: str, keep: bool) -> list[CheckResult]:
    results = list(_algorithm_checks(engine))
    source = _db_url()
    if not source:
        return results + [CheckResult('database configuration','BLOCKED','TEST_DATABASE_URL or DATABASE_URL',None,'Set a PostgreSQL connection URL.')]
    name = DB_PREFIX + secrets.token_hex(8); target = _safe_url(source, name)
    env = os.environ.copy(); env['TEST_DATABASE_URL'] = target; env['DATABASE_URL'] = target
    created = False
    try:
        _create_database(source, name)
        created = True
        try:
            migration = _run(
                [sys.executable,'-m','alembic','upgrade','head'],
                env,
                timeout_seconds=MIGRATION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            results.append(CheckResult(
                'alembic upgrade head',
                'FAIL',
                f'completed within {MIGRATION_TIMEOUT_SECONDS} seconds',
                'timeout',
                _timeout_detail(exc),
            ))
        else:
            if migration.returncode:
                results.append(CheckResult(
                    'alembic upgrade head',
                    'FAIL',
                    0,
                    migration.returncode,
                    _redact(migration.stderr[-1000:]),
                ))
            else:
                selections = {
                    'bkt': [
                        'tests/test_bkt.py',
                        'tests/test_placement_prior.py',
                        'tests/test_bkt_integrity.py',
                        'tests/test_bkt_mastery_api.py',
                        'tests/test_vocab_quiz_attempts.py',
                        'tests/test_vocab_quiz_progression.py',
                        'tests/test_manual_bkt_smoke.py',
                        'tests/test_bkt_verification.py',
                    ],
                    'sm2': [
                        'tests/test_srs.py',
                        'tests/test_review_queue.py',
                        'tests/test_srs_verification.py',
                        'tests/test_srs_today_override_api.py',
                        'tests/test_bkt_mastery_api.py',
                    ],
                }[engine]
                # A broken integration fixture must become a reportable FAIL
                # instead of holding the verification command forever.
                try:
                    test = _run(
                        [sys.executable,'-m','pytest','-q','--timeout=60',*selections],
                        env,
                        timeout_seconds=FOCUSED_TEST_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired as exc:
                    results.append(CheckResult(
                        f'{engine} focused pytest',
                        'FAIL',
                        f'completed within {FOCUSED_TEST_TIMEOUT_SECONDS} seconds',
                        'timeout',
                        _timeout_detail(exc),
                    ))
                else:
                    results.append(CheckResult(
                        f'{engine} focused pytest',
                        'PASS' if test.returncode == 0 else 'FAIL',
                        0,
                        test.returncode,
                        _redact((test.stdout+test.stderr)[-2000:]),
                    ))
    except Exception as exc:
        results.append(CheckResult(
            f'{engine} database setup',
            'BLOCKED',
            'temporary PostgreSQL database',
            None,
            _redact(exc),
        ))
    finally:
        if created and not keep:
            try: _drop_database(source, name)
            except Exception as exc:
                # Cleanup failures are surfaced in the report without leaking
                # connection details and must not discard prior check results.
                results.append(CheckResult(f'{engine} database cleanup', 'FAIL', 'dropped', None, _redact(f'{type(exc).__name__}: {exc}')))
    return results
async def _analyze_voice_entry(root: Path, item: dict, provider: str):
    # Keep production imports lazy: `--help` and DB checks remain usable when
    # optional speech dependencies are unavailable.
    from services.speech_analysis import _do_analyze
    content = (root / item['file']).read_bytes()
    return await _do_analyze(
        content,
        '',
        'auto',
        scene_target_text=item['target_text'],
        pinyin_hint=item['pinyin'],
        scene_prompt=item['context'],
        scene_vocabulary=item.get('vocabulary', ''),
        scene_phrases=item.get('scene_phrases', ''),
        scene_suggested_answer=item.get('suggested_answer', item['target_text']),
        ai_provider=provider,
    )


def _feedback_trace(response: dict[str, Any]) -> dict[str, Any]:
    trace = response.get('processing_trace') or {}
    stages = trace.get('stages') or []
    return next((stage for stage in stages if stage.get('stage') == 'feedback'), {})


def _voice_technical_result(item: dict[str, Any], response: dict[str, Any], provider: str) -> CheckResult:
    provenance = response.get('feedback_provenance') or {}
    quality = response.get('feedback_quality') or {}
    feedback_trace = _feedback_trace(response)
    trace_input = feedback_trace.get('input') or {}
    pitch_contour = response.get('pitch_contour') or []
    word_prosody = response.get('word_prosody') or []
    measured_evidence = bool(pitch_contour) and bool(word_prosody)
    trace_matches_response = (
        trace_input.get('tone_accuracy') == response.get('tone_accuracy')
        and trace_input.get('fluency_score') == response.get('fluency_score')
        and trace_input.get('speech_rate') == response.get('speech_rate')
        and trace_input.get('word_prosody') == word_prosody
    )
    quality_status = str(quality.get('status') or '').lower()
    retry_expected = (
        quality.get('can_score_pronunciation') is False
        and quality_status == 'retry'
        and feedback_trace.get('status') == 'skipped'
        and provenance.get('executed_provider') == 'local'
        and provenance.get('fallback_used') is True
        and provenance.get('pronunciation_source') == 'local_deterministic'
    )
    technical = (
        quality.get('can_score_pronunciation') is True
        and measured_evidence
        and trace_matches_response
        and feedback_trace.get('status') == 'passed'
        and provenance.get('acoustic_context_used') is True
        and provenance.get('acoustic_context_supplied') is True
        and str(provenance.get('executed_provider', '')).lower() == provider.lower()
        and not provenance.get('fallback_used', True)
    )
    if retry_expected:
        status = 'PASS'
    elif provenance.get('fallback_used') and str(provenance.get('requested_provider', '')).lower() == provider.lower():
        # The pipeline intentionally returns local coaching when a cloud call
        # fails or times out. That is safe for a student, but cloud acceptance
        # is blocked because the requested provider did not actually run.
        status = 'BLOCKED'
    else:
        status = 'PASS' if technical else 'FAIL'
    return CheckResult(
        f"voice analysis: {item['file']}",
        status,
        {'praat_measurements': True, 'provider': provider, 'asr_input': 'empty'},
        {
            'quality_status': quality_status,
            'retry_expected': retry_expected,
            'can_score_pronunciation': quality.get('can_score_pronunciation'),
            'pitch_points': len(pitch_contour),
            'word_prosody_items': len(word_prosody),
            'feedback_trace_matches_response': trace_matches_response,
            'feedback_provenance': provenance,
        },
        'No transcript was supplied by the runner; production ASR used auto selection.',
    )

def _voice_checks(audio_dir: str | None, provider: str | None) -> list[CheckResult]:
    if not audio_dir: return [CheckResult('voice manifest','BLOCKED','audio directory and manifest.json',None,'Pass --audio-dir containing manifest.json and real audio files.')]
    root = Path(audio_dir); manifest_path = root / 'manifest.json'
    if not manifest_path.is_file(): return [CheckResult('voice manifest','BLOCKED','manifest.json',None,f'Missing {manifest_path}')]
    try: data = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc: return [CheckResult('voice manifest','FAIL','valid JSON',None,str(exc))]
    entries = data.get('recordings', data) if isinstance(data,dict) else data
    if not isinstance(entries,list) or not entries: return [CheckResult('voice manifest','FAIL','non-empty recordings list',entries,'Manifest needs file, target_text, pinyin and context.')]
    missing=[]; calibration_missing=[]
    for item in entries:
        if not isinstance(item,dict) or not all(item.get(k) for k in ('file','target_text','pinyin','context')): missing.append(str(item)); continue
        if not item.get('speaker_confirmed_human'): missing.append(item.get('file')); continue
        if item.get('human_rating') not in ('passed', 'needs_practice', 'not_judged'): calibration_missing.append(item.get('file'))
        path=(root/item['file']).resolve()
        if root.resolve() not in path.parents or not path.is_file(): missing.append(item.get('file'))
    if missing: return [CheckResult('voice manifest','BLOCKED','all files and target metadata present',missing,'No cloud call was made.')]
    if not provider: return [CheckResult('voice provider','BLOCKED','--provider plus configured API key',None,'Choose a provider and configure its key.')]
    if provider.lower() not in {'groq', 'openai', 'gemini'}:
        return [CheckResult('voice provider','FAIL','groq, openai, or gemini',provider,'Unsupported cloud provider.')]
    key={'groq':'GROQ_API_KEY','openai':'OPENAI_API_KEY','gemini':'GEMINI_API_KEY'}.get(provider.lower())
    if key and not os.getenv(key): return [CheckResult('voice provider','BLOCKED',key,None,'Provider credentials are not configured.')]
    results=[]
    if calibration_missing:
        results.append(CheckResult('voice human calibration','BLOCKED','human_rating on every recording',calibration_missing,'Technical analysis can run, but agreement cannot be claimed.'))
    async def run_all():
        responses = []
        # Run recordings one by one so acceptance checks do not create a burst
        # of paid/rate-limited cloud calls and report order stays deterministic.
        for item in entries:
            responses.append(await _analyze_voice_entry(root, item, provider))
        return responses
    try:
        responses = asyncio.run(run_all())
    except Exception as exc:
        return results + [CheckResult('voice real pipeline','BLOCKED','Praat + ASR + cloud feedback',None,_redact(f'{type(exc).__name__}: {exc}'))]
    disagreements=[]
    for item, response in zip(entries, responses):
        data = response.model_dump() if hasattr(response, 'model_dump') else (response.dict() if hasattr(response, 'dict') else response)
        results.append(_voice_technical_result(item, data, provider))
        rating=item.get('human_rating')
        if rating and rating != 'not_judged':
            predicted = (data.get('pronunciation_mastery') or {}).get('status')
            if predicted != rating: disagreements.append({'file':item['file'],'human':rating,'system':predicted})
    if disagreements: results.append(CheckResult('voice human agreement','FAIL','all ratings agree',disagreements,'Review disagreements before deployment.'))
    elif not calibration_missing: results.append(CheckResult('voice human agreement','PASS','all ratings agree',True))
    return results
def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--engine',choices=('bkt','sm2','voice','all'),required=True); p.add_argument('--provider'); p.add_argument('--audio-dir'); p.add_argument('--output-dir',default=str(DEFAULT_OUT)); p.add_argument('--keep-database',action='store_true'); args=p.parse_args(argv)
    engines=('bkt','sm2','voice') if args.engine=='all' else (args.engine,); results=[]
    for engine in engines: results.extend(_voice_checks(args.audio_dir,args.provider) if engine=='voice' else _db_checks(engine,args.keep_database))
    md,js=write_report(results,Path(args.output_dir),args.engine); print(f'Report: {md}\nJSON: {js}')
    if any(r.status == 'FAIL' for r in results): return 1
    if any(r.status == 'BLOCKED' for r in results): return 2
    return 0
if __name__ == '__main__': raise SystemExit(main())
