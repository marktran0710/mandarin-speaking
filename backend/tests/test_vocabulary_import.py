"""Admin quiz-vocabulary CSV import: preview (read-only) and confirm (write)."""
import csv
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import security.auth as auth
from db import connect_db
from routers import admin
from services.vocabulary_import import (
    _merge_assessment,
    apply_vocabulary_import,
    parse_csv_rows,
    preview_vocabulary_import,
    validate_import_rows,
)

COLUMNS = [
    "Question ID", "Word Key", "Source Type", "Chapter", "Section", "Item",
    "Traditional Chinese", "Pinyin", "POS", "English Meaning", "Round", "Tier",
    "Skill Label", "Question Type", "Input Mode", "Prompt", "Option A", "Option B",
    "Option C", "Option D", "Correct Option", "Correct Answer", "Accepted Answers",
    "Context Source", "Full Context Sentence", "PDF Page", "Book Page",
]


def word_rows(*, word_key="C99-1-I1-W001", chinese="錢包", pinyin="qiánbāo", meaning="wallet", section="99-1", suffix=""):
    common = {
        "Word Key": word_key, "Source Type": "Vocabulary", "Chapter": section.split("-")[0],
        "Section": section, "Item": "1", "Traditional Chinese": chinese, "Pinyin": pinyin,
        "POS": "N", "English Meaning": meaning, "Context Source": "", "Full Context Sentence": "",
        "PDF Page": "", "Book Page": "",
    }
    return [
        {**common, "Question ID": f"Q{word_key}1{suffix}", "Round": "Round 1", "Tier": "tier1",
         "Skill Label": "know it", "Question Type": "basic_meaning_mcq", "Input Mode": "click",
         "Prompt": f"Choose the correct English meaning of {chinese}", "Option A": "kitchen",
         "Option B": "the front; the front side; ahead; in front", "Option C": meaning, "Option D": "chair",
         "Correct Option": "C", "Correct Answer": meaning, "Accepted Answers": meaning},
        {**common, "Question ID": f"Q{word_key}2{suffix}", "Round": "Round 2", "Tier": "tier2",
         "Skill Label": "say it", "Question Type": "character_to_pinyin_typing", "Input Mode": "free_text",
         "Prompt": f"Type the pinyin for {chinese}.", "Option A": "", "Option B": "", "Option C": "", "Option D": "",
         "Correct Option": "", "Correct Answer": pinyin, "Accepted Answers": f"{pinyin} | {pinyin}1"},
        {**common, "Question ID": f"Q{word_key}3{suffix}", "Round": "Round 3", "Tier": "tier3",
         "Skill Label": "use it", "Question Type": "context_cloze_mcq", "Input Mode": "click",
         "Prompt": f"我的___不見了。", "Option A": chinese, "Option B": "書", "Option C": "門", "Option D": "床",
         "Correct Option": "A", "Correct Answer": chinese, "Accepted Answers": chinese},
    ]


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def test_parse_csv_rows_reports_missing_columns():
    bad = b"Question ID,Word Key\nQ1,W1\n"
    with pytest.raises(ValueError, match="missing required columns"):
        parse_csv_rows(bad)


def test_validate_import_rows_accepts_a_well_formed_word():
    rows = word_rows()
    assert validate_import_rows(rows) == []


def test_validate_import_rows_flags_wrong_question_type_for_round():
    rows = word_rows()
    rows[1]["Question Type"] = "context_cloze_mcq"  # should be character_to_pinyin_typing
    issues = validate_import_rows(rows)
    assert any("expected character_to_pinyin_typing" in issue for issue in issues)


def test_validate_import_rows_flags_missing_round():
    rows = word_rows()[:2]  # drop Round 3
    issues = validate_import_rows(rows)
    assert any("expected exactly one row for each round" in issue for issue in issues)


def test_merge_assessment_replaces_by_word_id_and_keeps_untouched_words():
    existing = [{"wordId": "W001", "targetWord": "old"}, {"wordId": "W002", "targetWord": "keep me"}]
    incoming = [{"wordId": "W001", "targetWord": "new"}]
    merged = _merge_assessment(existing, incoming)
    assert {q["wordId"]: q["targetWord"] for q in merged} == {"W001": "new", "W002": "keep me"}


def test_preview_reports_row_issues_without_touching_the_database(client):
    rows = word_rows()
    rows[1]["Question Type"] = "context_cloze_mcq"
    with connect_db() as db:
        report = preview_vocabulary_import(db, csv_bytes(rows))
    assert report["sections"] == []
    assert any("expected character_to_pinyin_typing" in issue for issue in report["rowIssues"])


def test_preview_and_confirm_against_a_real_story(client):
    story = {
        "id": "vocab-import-story-99-1", "title": "Import test story", "frames": [],
        "published": True, "lessonNumber": 99, "lessonSubOrder": 1,
    }
    assert client.post("/api/custom-stories", json=story).status_code == 200

    rows = word_rows()
    content = csv_bytes(rows)
    with connect_db() as db:
        preview = preview_vocabulary_import(db, content)
    assert preview["rowIssues"] == []
    assert len(preview["sections"]) == 1
    section = preview["sections"][0]
    assert section["found"] is True
    assert section["storyId"] == "vocab-import-story-99-1"
    assert section["newWords"] == 1
    assert section["updatedWords"] == 0
    assert section["issues"] == []

    with connect_db() as db:
        result = apply_vocabulary_import(db, content)
    assert result["published"] == [
        {"section": "99-1", "storyId": "vocab-import-story-99-1", "storyTitle": "Import test story", "questionCount": 3}
    ]

    saved = next(s for s in client.get("/api/custom-stories").json() if s["id"] == "vocab-import-story-99-1")
    assert len(saved["vocabAssessment"]) == 3
    assert {q["wordId"] for q in saved["vocabAssessment"]} == {"C99-1-I1-W001"}

    # Re-importing the same word updates it in place rather than duplicating it.
    updated_rows = word_rows(meaning="coin purse")
    with connect_db() as db:
        preview_again = preview_vocabulary_import(db, csv_bytes(updated_rows))
    assert preview_again["sections"][0]["newWords"] == 0
    assert preview_again["sections"][0]["updatedWords"] == 1

    with connect_db() as db:
        apply_vocabulary_import(db, csv_bytes(updated_rows))
    saved_again = next(s for s in client.get("/api/custom-stories").json() if s["id"] == "vocab-import-story-99-1")
    assert len(saved_again["vocabAssessment"]) == 3
    assert saved_again["vocabAssessment"][0]["simpleEnglishMeaning"] == "coin purse"


def test_preview_reports_when_no_story_matches_the_section(client):
    rows = word_rows(section="97-9")
    with connect_db() as db:
        report = preview_vocabulary_import(db, csv_bytes(rows))
    assert report["sections"][0]["found"] is False
    assert "No existing story" in report["sections"][0]["error"]


def test_confirm_raises_when_no_story_matches_the_section(client):
    rows = word_rows(section="97-9")
    with connect_db() as db, pytest.raises(LookupError):
        apply_vocabulary_import(db, csv_bytes(rows))


@pytest.fixture()
def import_endpoint_api(monkeypatch):
    app = FastAPI()
    app.include_router(admin.router)
    with TestClient(app) as test_client:
        yield test_client


def test_import_endpoints_are_admin_only(import_endpoint_api, monkeypatch):
    test_client = import_endpoint_api
    monkeypatch.setattr(admin, "preview_vocabulary_import", lambda db, content: {"rows": 0, "rowIssues": [], "sections": []})
    files = {"file": ("bank.csv", b"Question ID\n", "text/csv")}

    response = test_client.post("/api/admin/vocabulary-import/preview", files=files)
    assert response.status_code == 401

    test_client.cookies.set(auth.ROLE_COOKIE_NAMES["teacher"], auth.issue_token("teacher", "teacher-1"))
    assert test_client.post("/api/admin/vocabulary-import/preview", files=files).status_code in (401, 403)

    test_client.cookies.clear()
    test_client.cookies.set(auth.ROLE_COOKIE_NAMES["admin"], auth.issue_token("admin", "admin"))
    response = test_client.post("/api/admin/vocabulary-import/preview", files=files)
    assert response.status_code == 200
    assert response.json() == {"rows": 0, "rowIssues": [], "sections": []}


def test_preview_endpoint_returns_422_on_bad_file(import_endpoint_api):
    test_client = import_endpoint_api
    test_client.cookies.set(auth.ROLE_COOKIE_NAMES["admin"], auth.issue_token("admin", "admin"))
    files = {"file": ("bank.csv", b"not,a,valid,header\n", "text/csv")}
    response = test_client.post("/api/admin/vocabulary-import/preview", files=files)
    assert response.status_code == 422
    assert "missing required columns" in response.json()["detail"]
