from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.similarity.thresholds import (
    ABSTENTION_REASON_NO_PRECEDENTS,
    CALIBRATION_FILE_ENV_VAR,
    DEFAULT_GROUP_THRESHOLDS,
    DEFAULT_SIMILARITY_THRESHOLDS,
    NEAR_DUPLICATE_THRESHOLDS,
    evaluate_similarity_abstention,
    resolve_group_threshold,
    resolve_near_duplicate_threshold,
    resolve_similarity_threshold,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _reviewed_run(client: TestClient, label: str, *, material: str = "tablero", finish: str = "melamina") -> str:
    with FIXTURE.open("rb") as stream:
        document_id = client.post(
            "/api/v1/documents",
            files={"file": (f"{label}.dxf", stream, "application/dxf")},
        ).json()["data"]["document_id"]
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    scenario = created["result"]["scenarios"][0]["id"]
    response = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Técnica",
            "scenario_id": scenario,
            "confirmed_thickness_mm": 18,
            "material": material,
            "finish": finish,
            "notes": "Confirmado",
        },
    )
    assert response.status_code == 201
    return run_id


def test_default_calibrated_thresholds_differentiate_geometric_and_semantic() -> None:
    assert DEFAULT_SIMILARITY_THRESHOLDS == {"geometric": 0.78, "semantic": 0.90}
    assert DEFAULT_GROUP_THRESHOLDS == {"geometric": 0.85, "semantic": 0.92}
    assert NEAR_DUPLICATE_THRESHOLDS == {"geometric": 0.97, "semantic": 0.97}

    assert resolve_similarity_threshold("geometric") == 0.78
    assert resolve_similarity_threshold("semantic") == 0.90
    assert resolve_group_threshold("geometric") == 0.85
    assert resolve_group_threshold("semantic") == 0.92
    assert resolve_near_duplicate_threshold("geometric") == 0.97
    assert resolve_near_duplicate_threshold("semantic") == 0.97


def test_calibrated_thresholds_load_from_json_with_precedence_and_fallback(tmp_path: Path, monkeypatch) -> None:
    calibration_file = tmp_path / "thresholds.json"
    calibration_file.write_text(
        json.dumps(
            {
                "similarity": {
                    "semantic": 0.88,
                    "semantic:furniture-v2": 0.91,
                    "semantic:furniture-v2:text-embedding-3-small": 0.93,
                    "geometric": True,
                },
                "group": {
                    "geometric:furniture-v3": 0.87,
                    "semantic": 1.5,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(CALIBRATION_FILE_ENV_VAR, str(calibration_file))

    assert resolve_similarity_threshold("semantic", "furniture-v2", "text-embedding-3-small") == 0.93
    assert resolve_similarity_threshold("semantic", "furniture-v2", "other-model") == 0.91
    assert resolve_similarity_threshold("semantic", "furniture-v1", "other-model") == 0.88
    # Invalid boolean/out-of-range values fall back deterministically to defaults.
    assert resolve_similarity_threshold("geometric") == 0.78
    assert resolve_group_threshold("geometric", "furniture-v3") == 0.87
    assert resolve_group_threshold("semantic") == 0.92

    # Missing or malformed calibration file falls back deterministically.
    missing_file = tmp_path / "missing.json"
    assert resolve_similarity_threshold("semantic", config_path=missing_file) == 0.90
    malformed_file = tmp_path / "bad.json"
    malformed_file.write_text("{not-valid-json", encoding="utf-8")
    assert resolve_group_threshold("geometric", config_path=malformed_file) == 0.85


def test_evaluate_similarity_abstention_handles_empty_below_and_passing_matches() -> None:
    empty_res = evaluate_similarity_abstention([], 0.90)
    assert empty_res.abstained is True
    assert empty_res.abstention_reason == ABSTENTION_REASON_NO_PRECEDENTS
    assert empty_res.threshold_used == 0.90
    assert empty_res.filtered_matches == ()

    below_res = evaluate_similarity_abstention([{"score": 0.89}, {"score": 0.50}], 0.90)
    assert below_res.abstained is True
    assert below_res.abstention_reason == "sin_precedentes_suficientes"
    assert below_res.filtered_matches == ()

    passing_res = evaluate_similarity_abstention(
        [{"id": "a", "score": 0.95}, {"id": "b", "score": 0.90}, {"id": "c", "score": 0.89}],
        0.90,
    )
    assert passing_res.abstained is False
    assert passing_res.abstention_reason is None
    assert passing_res.threshold_used == 0.90
    assert [item["id"] for item in passing_res.filtered_matches] == ["a", "b"]


def test_similarity_endpoint_abstention_and_backward_compatibility(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = TestClient(create_app(data_dir=tmp_path))

    first = _reviewed_run(client, "first")
    second = _reviewed_run(client, "second")
    for run_id, label in ((first, "Original"), (second, "Copia")):
        saved = client.post(
            f"/api/v1/runs/{run_id}/library",
            json={"result_revision": 2, "label": label, "embedding_mode": "offline"},
        )
        assert saved.status_code == 201

    # Default include_abstention=False preserves legacy list response shape.
    legacy = client.post(
        f"/api/v1/runs/{first}/similarity",
        json={"result_revision": 2, "mode": "geometric", "limit": 5},
    )
    assert legacy.status_code == 200
    assert isinstance(legacy.json()["data"], list)
    assert len(legacy.json()["data"]) == 1

    # include_abstention=True with passing geometric match uses 0.78 threshold and does not abstain.
    passing = client.post(
        f"/api/v1/runs/{first}/similarity",
        json={"result_revision": 2, "mode": "geometric", "limit": 5, "include_abstention": True},
    )
    assert passing.status_code == 200
    data = passing.json()["data"]
    assert data["abstained"] is False
    assert data["abstention_reason"] is None
    assert data["threshold_used"] == pytest.approx(0.78)
    assert data["descriptor_version"] == "furniture-v1"
    assert data["excluded_count"] == 0
    assert len(data["matches"]) == 1


def test_similarity_endpoint_abstains_sin_precedentes_when_below_semantic_threshold(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult

    class OrthogonalishEmbeddingProvider:
        model = "text-embedding-3-small"
        dimensions = 2

        def embed(self, text: str) -> EmbeddingResult:
            # First call vs second call: cosine similarity = 0.80 (below semantic 0.90).
            if not hasattr(self, "_count"):
                self._count = 0
            self._count += 1
            if self._count == 1:
                return EmbeddingResult(vector=(1.0, 0.0), model=self.model, dimensions=self.dimensions)
            return EmbeddingResult(vector=(0.8, 0.6), model=self.model, dimensions=self.dimensions)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, embedding_provider=OrthogonalishEmbeddingProvider()))

    first = _reviewed_run(client, "sem-a", material="tablero", finish="melamina")
    second = _reviewed_run(client, "sem-b", material="madera_maciza", finish="barniz_mate")
    for run_id, label in ((first, "A"), (second, "B")):
        saved = client.post(
            f"/api/v1/runs/{run_id}/library",
            json={"result_revision": 2, "label": label, "embedding_mode": "openai"},
        )
        assert saved.status_code == 201

    abstained = client.post(
        f"/api/v1/runs/{first}/similarity",
        json={"result_revision": 2, "mode": "semantic", "limit": 5, "include_abstention": True},
    )
    assert abstained.status_code == 200
    payload = abstained.json()["data"]
    assert payload["abstained"] is True
    assert payload["abstention_reason"] == "sin_precedentes_suficientes"
    assert payload["threshold_used"] == pytest.approx(0.90)
    assert payload["matches"] == []

    # Explicit min_score below 0.80 recovers the match and does not abstain.
    recovered = client.post(
        f"/api/v1/runs/{first}/similarity",
        json={"result_revision": 2, "mode": "semantic", "limit": 5, "min_score": 0.75, "include_abstention": True},
    )
    assert recovered.status_code == 200
    rec_payload = recovered.json()["data"]
    assert rec_payload["abstained"] is False
    assert rec_payload["abstention_reason"] is None
    assert rec_payload["threshold_used"] == pytest.approx(0.75)
    assert len(rec_payload["matches"]) == 1


def test_group_request_uses_calibrated_default_threshold_per_mode(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult

    class PairEmbeddingProvider:
        model = "text-embedding-3-small"
        dimensions = 2

        def embed(self, text: str) -> EmbeddingResult:
            # Cosine similarity between (1, 0) and (0.88, 0.47497...) is 0.88:
            # above geometric default (0.85) but below semantic default (0.92).
            if not hasattr(self, "_count"):
                self._count = 0
            self._count += 1
            if self._count == 1:
                return EmbeddingResult(vector=(1.0, 0.0), model=self.model, dimensions=self.dimensions)
            return EmbeddingResult(vector=(0.88, 0.4749736834815167), model=self.model, dimensions=self.dimensions)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, embedding_provider=PairEmbeddingProvider()))

    for label, material, finish in (("g-a", "tablero", "melamina"), ("g-b", "madera_maciza", "barniz_mate")):
        run_id = _reviewed_run(client, label, material=material, finish=finish)
        saved = client.post(
            f"/api/v1/runs/{run_id}/library",
            json={"result_revision": 2, "label": label, "embedding_mode": "openai"},
        )
        assert saved.status_code == 201

    geo_groups = client.post("/api/v1/library/groups", json={"mode": "geometric"})
    assert geo_groups.status_code == 200
    geo_data = geo_groups.json()["data"]
    assert len(geo_data) == 1
    assert geo_data[0]["threshold"] == pytest.approx(0.85)

    sem_groups = client.post("/api/v1/library/groups", json={"mode": "semantic"})
    assert sem_groups.status_code == 200
    # Cosine 0.88 < semantic calibrated default 0.92, so items are not merged into a group.
    assert sem_groups.json()["data"] == []

    # Explicit threshold 0.85 merges them as expected.
    sem_explicit = client.post("/api/v1/library/groups", json={"mode": "semantic", "threshold": 0.85})
    assert sem_explicit.status_code == 200
    assert len(sem_explicit.json()["data"]) == 1
    assert sem_explicit.json()["data"][0]["threshold"] == pytest.approx(0.85)


def test_near_duplicate_threshold_uses_calibration_and_preserves_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calibration = tmp_path / "thresholds.json"
    calibration.write_text(json.dumps({"near_duplicate": {"geometric:furniture-v1": 0.995}}), encoding="utf-8")
    monkeypatch.setenv(CALIBRATION_FILE_ENV_VAR, str(calibration))
    client = TestClient(create_app(data_dir=tmp_path / "data"))
    first = _reviewed_run(client, "query")
    second = _reviewed_run(client, "precedent")
    saved = client.post(f"/api/v1/runs/{second}/library", json={"result_revision": 2, "label": "Precedente", "embedding_mode": "offline"})
    assert saved.status_code == 201
    response = client.post(f"/api/v1/runs/{first}/similarity", json={
        "result_revision": 2, "mode": "geometric", "include_abstention": True,
        "include_summary": True, "threshold_kind": "near_duplicate",
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["threshold_used"] == pytest.approx(0.995)
    assert data["record_count"] == data["design_count"] == 1
    assert data["duplicate_record_count"] == 0
    assert data["abstained"] is False
    assert data["matches"][0]["run_id"] == second
