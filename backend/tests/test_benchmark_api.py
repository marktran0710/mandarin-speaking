"""API tests for the OMPAL benchmark endpoints."""
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main
from benchmarking import ompal_runner
from routers import benchmark as benchmark_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_router, "CORPUS_ROOT", tmp_path / "ompal")
    monkeypatch.setattr(benchmark_router, "RESULTS_PATH", tmp_path / "scored.jsonl")
    ompal_runner.reset_for_tests()
    yield TestClient(main.app)
    ompal_runner.reset_for_tests()


class TestStatus:
    def test_reports_a_missing_corpus_and_no_results(self, client):
        body = client.get("/api/benchmark/ompal/status").json()
        assert body["corpus"]["downloaded"] is False
        assert body["has_results"] is False
        assert body["job"]["phase"] == "idle"
        assert body["production_threshold"] == 58.0

    def test_counts_existing_scored_rows(self, client, tmp_path):
        (tmp_path / "scored.jsonl").write_text(
            json.dumps({"utterance_id": "001", "characters": [], "error": None}) + "\n",
            encoding="utf-8",
        )
        body = client.get("/api/benchmark/ompal/status").json()
        assert body["scored_count"] == 1
        assert body["has_results"] is True


class TestCancel:
    def test_rejects_cancelling_when_nothing_is_running(self, client):
        response = client.post("/api/benchmark/ompal/cancel")
        assert response.status_code == 409


class TestRunConcurrency:
    def test_rejects_a_second_concurrent_run(self, client, monkeypatch):
        """Two jobs appending to one results file would interleave output."""
        monkeypatch.setattr(ompal_runner, "is_running", lambda: True)
        monkeypatch.setattr(ompal_runner, "start", lambda *a, **k: False)
        response = client.post("/api/benchmark/ompal/run")
        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]


class TestReport:
    def test_returns_404_before_any_run(self, client):
        response = client.get("/api/benchmark/ompal/report")
        assert response.status_code == 404
        assert "Run the benchmark first" in response.json()["detail"]

    def test_refuses_to_interpret_results_without_the_corpus(self, client, tmp_path):
        """Scored rows carry no teacher labels; without the corpus they cannot
        be turned into an agreement report at all."""
        (tmp_path / "scored.jsonl").write_text(
            json.dumps({"utterance_id": "001", "characters": [], "error": None}) + "\n",
            encoding="utf-8",
        )
        response = client.get("/api/benchmark/ompal/report")
        assert response.status_code == 409
        assert "corpus is missing" in response.json()["detail"]

    def test_rejects_an_out_of_range_threshold(self, client):
        assert client.get("/api/benchmark/ompal/report?threshold=250").status_code == 422
        assert client.get("/api/benchmark/ompal/report?threshold=-5").status_code == 422
