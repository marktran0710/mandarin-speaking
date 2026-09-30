"""Heavy per-sentence pitch data is split out of the story list.

`sentenceReferenceCurves` / `sentenceModelContour` are ~77% of the student's
story payload but only needed for the one lesson being practised, so the list
can omit them (`include_reference_data=false`) and the lesson fetches them
from `/api/custom-stories/{id}/reference-data`.
"""
import services.content.stories as story_service
from api.schemas.models import CustomStoryRequest

CURVES = '{"你": [0.5, 0.4, 0.3]}'
CONTOUR = '{"text": "你好", "tokens": [{"token": "你", "points": [[0.0, 1.0]]}]}'


def _story(story_id: str, *, published: bool = True) -> dict:
    return {
        "id": story_id,
        "title": "Reference data story",
        "published": published,
        "lessonNumber": 5,
        "frames": [
            {"imageUrl": "", "prompt": "frame zero", "sentenceReferenceCurves": CURVES, "sentenceModelContour": CONTOUR},
            {"imageUrl": "", "prompt": "frame one"},
        ],
    }


def _publish(story: dict) -> None:
    # Seed through the service: the student fixture's client has no staff cookie.
    story_service.create_story(CustomStoryRequest(**story))


def test_list_keeps_reference_data_by_default(admin_client):
    admin_client.post("/api/custom-stories", json=_story("ref-default"))
    saved = next(s for s in admin_client.get("/api/custom-stories").json() if s["id"] == "ref-default")
    assert saved["frames"][0]["sentenceReferenceCurves"] == CURVES
    assert saved["frames"][0]["sentenceModelContour"] == CONTOUR


def test_list_can_omit_reference_data_but_keeps_the_rest(admin_client):
    admin_client.post("/api/custom-stories", json=_story("ref-slim"))
    saved = next(
        s for s in admin_client.get("/api/custom-stories", params={"include_reference_data": "false"}).json()
        if s["id"] == "ref-slim"
    )
    for frame in saved["frames"]:
        assert not any(key.startswith(("sentenceReferenceCurves", "sentenceModelContour")) for key in frame)
    assert [frame["prompt"] for frame in saved["frames"]] == ["frame zero", "frame one"]
    assert saved["lessonNumber"] == 5


def test_reference_data_endpoint_returns_only_the_heavy_fields_per_frame(admin_client):
    admin_client.post("/api/custom-stories", json=_story("ref-endpoint"))
    body = admin_client.get("/api/custom-stories/ref-endpoint/reference-data").json()
    assert body["storyId"] == "ref-endpoint"
    assert len(body["frames"]) == 2
    assert body["frames"][0]["sentenceReferenceCurves"] == CURVES
    assert body["frames"][0]["sentenceModelContour"] == CONTOUR
    assert "prompt" not in body["frames"][0]
    assert not any(value for key, value in body["frames"][1].items() if value)


def test_reference_data_is_unknown_for_a_missing_story(admin_client):
    assert admin_client.get("/api/custom-stories/never-existed/reference-data").status_code == 404


def test_student_reads_reference_data_of_published_but_not_draft_stories(logged_in_student):
    client, _ = logged_in_student
    _publish(_story("ref-live"))
    _publish(_story("ref-draft", published=False))

    assert client.get("/api/custom-stories/ref-live/reference-data").status_code == 200
    assert client.get("/api/custom-stories/ref-draft/reference-data").status_code == 404
