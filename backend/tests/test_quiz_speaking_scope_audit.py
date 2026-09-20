"""Synthetic, offline tests; run with pytest --noconftest to bypass DB fixtures."""

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_quiz_speaking_scope.py"
SPEC = importlib.util.spec_from_file_location("quiz_speaking_scope_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

TEA, WATER = "\u8336", "\u6c34"
SENTENCE = "\u6211\u559d\u8336\u3002"


def question(kind="translation", **changes):
    answer = {"translation": "tea", "pinyin": "cha", "pos": "N"}.get(kind, TEA)
    options = [answer, WATER] if kind in audit.ANSWER_POOL_TYPES else ["water", "coffee"]
    if kind == "pos":
        options = []
    row = dict.fromkeys(audit.QUESTION_COLUMNS, "")
    row.update(story_id="story", story_title="Tea", published="True", lesson_number="5",
               lesson_sub_order="1", tier="easy", frame_index="0", word_index="0", word=TEA,
               question_type=kind, prompt="Choose", correct_answer=answer, translation="tea",
               pinyin="cha", part_of_speech="N", options_from_source=json.dumps(options),
               context_sentence="\u6211\u559d____\u3002" if kind == "cloze" else SENTENCE,
               source="verified_v3_book_locked", validation_status="ok")
    row.update(changes)
    return row


def speaking(*, frame=None, **changes):
    payload = {"vocabulary": TEA + ", " + WATER, "vocabularyTranslation": "tea, water",
               "vocabularyPinyin": "cha, shui", "vocabularyPos": "N, N", "suggestedAnswer": SENTENCE,
               "listenScript": SENTENCE}
    payload.update(frame or {})
    row = {"story_id": "story", "story_title": "Tea", "published": "True", "lesson_number": "5",
           "lesson_sub_order": "1", "frame_index": "0", "frame_json": json.dumps(payload)}
    row.update(changes)
    return row


def write_csv(path, rows):
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_audit(tmp_path, questions, sources=None, evidence=None):
    quiz = write_csv(tmp_path / "questions.csv", questions)
    source = write_csv(tmp_path / "speaking.csv", sources or [speaking()])
    return audit.audit(quiz, source, root=tmp_path, evidence=evidence)


@pytest.mark.parametrize("kind", sorted(audit.QUESTION_TYPES))
def test_valid_option_conventions(tmp_path, kind):
    summary, ledger, _ = run_audit(tmp_path, [question(kind)])
    assert summary["by_code"] == {}
    assert ledger[0]["semantic_review"] == "not_reviewed"
    assert ledger[0]["cefr"] == "unverified"


@pytest.mark.parametrize("kind,options,code", [
    ("translation", ["tea", "water"], "correct_answer_in_distractors"),
    ("cloze", [TEA, WATER], "correct_answer_in_distractors"),
    ("synonym", [TEA, WATER], "correct_answer_in_distractors"),
    ("reverse", [WATER], "correct_answer_missing_from_options"),
    ("listening", [WATER], "correct_answer_missing_from_options"),
    ("pinyin", ["shui"], "correct_answer_missing_from_options"),
])
def test_invalid_answer_presence_by_convention(tmp_path, kind, options, code):
    _, ledger, _ = run_audit(tmp_path, [question(kind, options_from_source=json.dumps(options))])
    assert code in ledger[0]["finding_codes"]


def test_exhaustive_bad_rows_and_precise_multiline_locations(tmp_path):
    questions = [question(prompt="Choose\ncarefully", options_from_source="{broken"),
                 question("synonym", correct_answer="\u8317", story_title="Wrong"),
                 question("cloze", context_sentence="____\u559d____", options_from_source='["x","x",7]'),
                 question("reverse", story_id="broken"), question("listening")]
    summary, ledger, findings = run_audit(tmp_path, questions, [speaking(), speaking(story_id="broken", frame_json="{bad")])
    assert len(ledger) == 5
    assert [row["record_number"] for row in ledger] == [1, 2, 3, 4, 5]
    assert [row["physical_start_line"] for row in ledger] == [2, 4, 5, 6, 7]
    assert ledger[0]["physical_end_line"] == 3
    assert ledger[1]["composite_identity"] == ["story", "easy", 0, 0, "synonym"]
    assert {"metadata_mismatch", "synonym_answer_not_found"} <= set(ledger[1]["finding_codes"])
    assert {"cloze_blank_count", "duplicate_options", "malformed_options"} <= set(ledger[2]["finding_codes"])
    assert "malformed_frame_json" in ledger[3]["finding_codes"]
    assert ledger[4]["finding_codes"] == []
    assert summary["unique_affected_rows"] == 4
    assert summary["total_findings"] == sum(row["finding_count"] for row in ledger)
    assert sum(item["rows"] for item in summary["by_type"].values()) == 5
    assert any(f["entity"] == "speaking_source" and f["code"] == "malformed_frame_json" for f in findings)


def test_csv_width_error_does_not_discard_later_records(tmp_path):
    quiz = tmp_path / "questions.csv"
    with quiz.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(audit.QUESTION_COLUMNS)
        writer.writerow(["too", "short"])
        writer.writerow([question()[key] for key in audit.QUESTION_COLUMNS])
    source = write_csv(tmp_path / "speaking.csv", [speaking()])
    summary, ledger, _ = audit.audit(quiz, source, root=tmp_path)
    assert summary["total_rows"] == 2
    assert "csv_row_width" in ledger[0]["finding_codes"]
    assert ledger[1]["finding_codes"] == []


def test_source_normalization_scopes_and_no_generated_or_cross_field_matches(tmp_path):
    source = write_csv(tmp_path / "speaking.csv", [
        speaking(frame={"phrases": "alpha", "phrasesHard": "left, right", "grammarPatternMedium": "\uff21\u3000\uff22",
                        "grammarExampleHard": "beta", "vocabularySynonym": "forbidden",
                        "vocabularyDistractors": "forbidden", "vocabularyCloze": "forbidden",
                        "vocabularyLookalike": "forbidden", "quiz_approved_snapshot": {"text": "forbidden"}}),
        speaking(frame_index="1", frame={"phrasesMedium": "nearby"}),
        speaking(story_id="other", frame={"listenScriptHard": "distant"}),
    ])
    records, _, _ = audit.read_csv(source, set())
    index = audit.SpeakingSources(records)
    assert index.search("A\n B", "story", 0)["scope"] == "same_frame"
    assert index.search("nearby", "story", 0)["scope"] == "same_story"
    assert index.search("distant", "story", 0)["scope"] == "other_speaking_story"
    for text in ("alphabeta", "alpha beta", "left, right", "leftright", "forbidden", "a b"):
        assert index.search(text, "story", 0)["scope"] == "not_found"
    assert index.search("beta", "story", 0)["evidence"]["field"] == "frame_json.grammarExampleHard"


def test_cloze_repeated_word_preserved_or_altered_not_grammar_error(tmp_path):
    repeated = "\u8336\u5c31\u662f\u8336\u3002"
    summary, ledger, _ = run_audit(tmp_path, [
        question("cloze", context_sentence="____\u5c31\u662f\u8336\u3002"),
        question("cloze", tier="medium", context_sentence="____\u5f88\u597d\u3002"),
        question("cloze", tier="hard", context_sentence="____\u3002"),
    ], [speaking(frame={"suggestedAnswer": repeated, "listenScript": repeated,
                        "vocabularyCloze": [{"sentence": "\u8336\u5f88\u597d\u3002"}]})])
    assert ledger[0]["finding_codes"] == []
    assert ledger[0]["reconstructed_context"] == repeated
    assert ledger[1]["finding_codes"] == ["altered_context"]
    assert ledger[2]["finding_codes"] == ["altered_context"]  # A sentence suffix is not a source sentence.
    assert not any("grammar" in code for code in summary["by_code"])


def test_target_tier_fallback_and_source_metadata_alignment(tmp_path):
    summary, ledger, _ = run_audit(tmp_path, [question(tier="medium"), question(tier="hard"),
                                           question("reverse", word_index="1")],
                                 [speaking(frame={"vocabularyMedium": "", "vocabularyHard": WATER,
                                                  "vocabularyTranslationHard": "water"})])
    assert ledger[0]["target_alignment"]["resolution"] == "base_fallback"
    assert ledger[0]["finding_codes"] == []
    assert {"target_word_mismatch", "target_metadata_mismatch"} <= set(ledger[1]["finding_codes"])
    assert "target_word_mismatch" in ledger[2]["finding_codes"]
    assert summary["unique_affected_rows"] == 2


def test_mirrors_and_missing_json_still_search_csv_sources(tmp_path):
    _, ledger, _ = run_audit(tmp_path, [question(), question("listening", story_id="broken")], [
        speaking(vocabulary="wrong"),
        speaking(story_id="broken", frame_json="[]", vocabulary=TEA, vocabulary_translation="tea",
                 vocabulary_pinyin="cha", vocabulary_pos="N", suggested_answer=SENTENCE)])
    assert "source_field_mismatch" in ledger[0]["finding_codes"]
    assert ledger[0]["target_alignment"]["expected_word"] == TEA
    assert ledger[1]["word_source_scope"] == "same_frame"
    assert "malformed_frame_json" in ledger[1]["finding_codes"]


def test_chinese_distractor_coverage_and_synonym_other_story(tmp_path):
    elsewhere, missing = "\u5496\u5561", "\u8317"
    _, ledger, _ = run_audit(tmp_path, [question("reverse", options_from_source=json.dumps([TEA, elsewhere, missing])),
                                      question("synonym", correct_answer=elsewhere)],
                            [speaking(), speaking(story_id="other", frame={"phrasesHard": elsewhere})])
    assert {"chinese_distractor_other_story", "chinese_distractor_not_found"} <= set(ledger[0]["finding_codes"])
    assert [m["scope"] for m in ledger[0]["chinese_distractor_matches"]] == ["other_speaking_story", "not_found"]
    assert ledger[1]["finding_codes"] == ["synonym_answer_other_story"]


def test_cli_reports_hashes_historical_inventory_and_unchanged_inputs(tmp_path):
    quiz = write_csv(tmp_path / "questions.csv", [question(), question("cloze")])
    source = write_csv(tmp_path / "speaking.csv", [speaking()])
    history = write_csv(tmp_path / "old_quiz_questions.csv", [question()] * 3)
    before = {path: path.read_bytes() for path in (quiz, source, history)}
    output = tmp_path / "reports"
    output.mkdir()
    reference = output / "tocfl-reference.json"
    reference.write_text('{"parent":"owned"}', encoding="utf-8")
    result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--questions", str(quiz), "--speaking", str(source),
                             "--inventory-root", str(tmp_path), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["rows"] == 2
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    with (output / "row_ledger.csv").open(encoding="utf-8-sig", newline="") as handle:
        ledger = list(csv.DictReader(handle))
    assert len(ledger) == summary["total_rows"] == 2
    assert {row["semantic_review"] for row in ledger} == {"not_reviewed"}
    assert {row["cefr"] for row in ledger} == {"unverified"}
    assert summary["input_manifest"]["questions"]["sha256"] == hashlib.sha256(before[quiz]).hexdigest()
    assert summary["historical_quiz_inventory"][0]["records"] == 3
    assert summary["historical_quiz_inventory"][0]["included_in_totals"] is False
    assert (output / "findings.csv").is_file()
    assert reference.read_text(encoding="utf-8") == '{"parent":"owned"}'
    assert all(path.read_bytes() == data for path, data in before.items())


def test_duplicate_identities_mark_every_affected_record(tmp_path):
    summary, ledger, _ = run_audit(tmp_path, [question(), question()])
    assert summary["by_code"] == {"duplicate_question_identity": 2}
    assert summary["unique_affected_rows"] == 2
    assert all(row["finding_codes"] == ["duplicate_question_identity"] for row in ledger)


def test_optional_evidence_requires_input_hash_and_identity(tmp_path):
    quiz = write_csv(tmp_path / "questions.csv", [question()])
    source = write_csv(tmp_path / "speaking.csv", [speaking()])
    evidence = tmp_path / "review.json"
    record = {"record_number": 1, "composite_identity": audit.identity(question()), "reviewer": "Human",
              "reference": "Local review note", "semantic_review": "reviewed", "cefr": "A2"}
    evidence.write_text(json.dumps({"questions_sha256": "wrong", "rows": [record]}), encoding="utf-8")
    summary, ledger, _ = audit.audit(quiz, source, root=tmp_path, evidence=evidence)
    assert ledger[0]["cefr"] == "unverified"
    assert summary["input_issues"][0]["code"] == "invalid_review_evidence"
    evidence.write_text(json.dumps({"questions_sha256": hashlib.sha256(quiz.read_bytes()).hexdigest(), "rows": [record]}), encoding="utf-8")
    _, ledger, _ = audit.audit(quiz, source, root=tmp_path, evidence=evidence)
    assert ledger[0]["cefr"] == "A2"
    assert ledger[0]["review_evidence"]["reference"] == "Local review note"


def test_report_writer_refuses_input_alias(tmp_path):
    summary, ledger, findings = run_audit(tmp_path, [question()])
    source = tmp_path / "speaking.csv"
    before = source.read_bytes()
    output = tmp_path / "reports"
    output.mkdir()
    (output / "row_ledger.csv").hardlink_to(source)
    with pytest.raises(ValueError, match="aliases an input"):
        audit.write_reports(output, summary, ledger, findings)
    assert source.read_bytes() == before
    assert not (output / "summary.json").exists()
