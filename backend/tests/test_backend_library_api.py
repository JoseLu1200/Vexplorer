from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _reviewed_run(client: TestClient, label: str, fixture: Path = FIXTURE) -> str:
    with fixture.open("rb") as stream:
        document_id = client.post("/api/v1/documents", files={"file": (f"{label}.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    scenario = created["result"]["scenarios"][0]["id"]
    response = client.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": scenario, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "Confirmado"})
    assert response.status_code == 201
    return run_id


def test_offline_library_save_list_and_similarity_are_explicit_and_read_only(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    first = _reviewed_run(client, "first")
    second = _reviewed_run(client, "second")
    for run_id, label in ((first, "Original"), (second, "Variante")):
        response = client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": label, "embedding_mode": "offline"})
        assert response.status_code == 201
        assert response.json()["data"]["embedding"] is None

    listed = client.get("/api/v1/library", params={"include_summary": "true"})
    assert listed.status_code == 200
    library = listed.json()["data"]
    assert len(library["items"]) == 2
    assert library["record_count"] == 2
    assert library["design_count"] == 1
    assert library["duplicate_record_count"] == 1
    match = client.post(f"/api/v1/runs/{first}/similarity", json={"result_revision": 2, "mode": "geometric", "limit": 5})
    assert match.status_code == 200
    assert len(match.json()["data"]) == 1
    assert match.json()["data"][0]["run_id"] == second
    assert match.json()["data"][0]["method"] == "geometric"
    assert match.json()["data"][0]["score_kind"] == "geometric_similarity"
    assert "probability" not in str(match.json()).lower()
    assert len(client.get("/api/v1/library").json()["data"]) == 2


def test_library_keeps_only_latest_revision_per_run(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    run_id = _reviewed_run(client, "latest")
    first = client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 1, "label": "Borrador", "embedding_mode": "offline"})
    second = client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": "Revisado", "embedding_mode": "offline"})
    assert first.status_code == 201 and second.status_code == 201
    items = client.get("/api/v1/library").json()["data"]
    assert len(items) == 1
    assert items[0]["result_revision"] == 2 and items[0]["label"] == "Revisado"


def test_offline_groups_are_reproducible_and_explain_threshold(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    for label in ("a", "b", "c"):
        run_id = _reviewed_run(client, label)
        client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": label, "embedding_mode": "offline"})

    first_payload = client.post("/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.9, "include_summary": True}).json()["data"]
    second_payload = client.post("/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.9, "include_summary": True}).json()["data"]
    first, second = first_payload["groups"], second_payload["groups"]
    assert first == second
    assert len(first) == 1 and len(first[0]["member_ids"]) == 3
    assert first[0]["threshold"] == 0.9
    assert first[0]["method"] == "geometric"
    assert first[0]["linkage"] == "complete"
    assert first[0]["minimum_pair_score"] >= 0.9
    assert first_payload["record_count"] == 3
    assert first_payload["design_count"] == 1
    assert first_payload["duplicate_record_count"] == 2


def test_semantic_groups_use_compatible_cached_embeddings_without_fallback(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult

    class FakeEmbeddingProvider:
        model = "text-embedding-3-small"
        dimensions = 2

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(vector=(0.8, 0.6), model=self.model, dimensions=self.dimensions)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, embedding_provider=FakeEmbeddingProvider()))
    for label in ("semantic-a", "semantic-b"):
        run_id = _reviewed_run(client, label)
        saved = client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": label, "embedding_mode": "embeddinggemma2"})
        assert saved.status_code == 201

    response = client.post("/api/v1/library/groups", json={"mode": "semantic", "threshold": 0.99, "include_summary": True})
    assert response.status_code == 200
    groups = response.json()["data"]["groups"]
    assert len(groups) == 1 and len(groups[0]["member_ids"]) == 2
    assert groups[0]["method"] == "semantic"
    assert groups[0]["score_kind"] == "cosine_similarity"


def test_semantic_groups_reject_missing_embeddings_explicitly(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    run_id = _reviewed_run(client, "offline")
    client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": "Offline", "embedding_mode": "offline"})
    response = client.post("/api/v1/library/groups", json={"mode": "semantic", "threshold": 0.8})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "semantic_embedding_missing"


def test_library_version_filter_keeps_table_space_separate_from_legacy(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    for label in ("legacy-a", "legacy-b"):
        run_id = _reviewed_run(client, label)
        client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": label, "embedding_mode": "offline"})

    listed = client.get("/api/v1/library", params={"descriptor_version": "furniture-v3"})
    assert listed.status_code == 200
    assert listed.json()["data"] == {"items": [], "descriptor_version": "furniture-v3", "excluded_count": 2}
    grouped = client.post("/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.8, "descriptor_version": "furniture-v3"})
    assert grouped.status_code == 200
    assert grouped.json()["data"] == {"groups": [], "descriptor_version": "furniture-v3", "excluded_count": 2}


def test_similarity_deduplicates_equivalent_designs_before_limit_and_reports_counts(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    query = _reviewed_run(client, "query")
    duplicate_a = _reviewed_run(client, "duplicate-a")
    duplicate_b = _reviewed_run(client, "duplicate-b", ROOT / "data" / "planos_demo" / "mueble_demo_004.dxf")
    distinct = _reviewed_run(client, "distinct", ROOT / "data" / "planos_demo" / "mueble_demo_002.dxf")
    for run_id in (query, duplicate_a, duplicate_b, distinct):
        saved = client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": run_id, "embedding_mode": "offline"})
        assert saved.status_code == 201

    response = client.post(f"/api/v1/runs/{query}/similarity", json={"result_revision": 2, "mode": "geometric", "limit": 2, "include_summary": True})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["record_count"] == 3
    assert payload["design_count"] == 2
    assert payload["duplicate_record_count"] == 1
    assert len(payload["matches"]) == 2
    assert distinct in {item["run_id"] for item in payload["matches"]}
    repeated = next(item for item in payload["matches"] if item["run_id"] != distinct)
    assert set(repeated["equivalent_record_ids"]) == {f"library-{duplicate_a}", f"library-{duplicate_b}"}
    assert repeated["duplicate_record_count"] == 1
    distinct_match = next(item for item in payload["matches"] if item["run_id"] == distinct)
    assert distinct_match["equivalent_record_ids"] == [f"library-{distinct}"]
    assert distinct_match["duplicate_record_count"] == 0


def test_semantic_similarity_preserves_cosine_and_reranks_by_technical_evidence(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult

    class FlatEmbeddingProvider:
        model = "text-embedding-3-small"
        dimensions = 2

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(vector=(1.0, 0.0), model=self.model, dimensions=self.dimensions)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, embedding_provider=FlatEmbeddingProvider()))
    query = _reviewed_run(client, "query-semantic")
    exact = _reviewed_run(client, "exact-semantic", ROOT / "data" / "planos_demo" / "mueble_demo_004.dxf")
    changed = _reviewed_run(client, "changed-semantic", ROOT / "data" / "planos_demo" / "mueble_demo_002.dxf")
    for run_id in (query, exact, changed):
        saved = client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": run_id, "embedding_mode": "embeddinggemma2"})
        assert saved.status_code == 201

    response = client.post(f"/api/v1/runs/{query}/similarity", json={"result_revision": 2, "mode": "semantic", "limit": 2, "include_summary": True})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert [item["run_id"] for item in payload["matches"]] == [exact, changed]
    assert [item["score"] for item in payload["matches"]] == [1.0, 1.0]
    assert all(item["score_kind"] == "cosine_similarity" for item in payload["matches"])
    assert payload["matches"][0]["technical_score"] > payload["matches"][1]["technical_score"]
    assert all(item["technical_score_kind"] == "technical_similarity" for item in payload["matches"])
    assert all(item["compatibility_warnings"] for item in payload["matches"])


def test_similarity_rejects_requested_descriptor_space_different_from_query(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    run_id = _reviewed_run(client, "legacy-query")

    response = client.post(f"/api/v1/runs/{run_id}/similarity", json={"result_revision": 2, "mode": "geometric", "descriptor_version": "furniture-v3", "include_summary": True})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "descriptor_space_incompatible"


def test_semantic_similarity_excludes_candidate_without_embedding_instead_of_failing_query(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult

    class FakeEmbeddingProvider:
        model = "text-embedding-3-small"
        dimensions = 2

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(vector=(1.0, 0.0), model=self.model, dimensions=self.dimensions)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, embedding_provider=FakeEmbeddingProvider()))
    query = _reviewed_run(client, "embedded-query")
    offline = _reviewed_run(client, "offline-candidate")
    assert client.post(f"/api/v1/runs/{query}/library", json={"result_revision": 2, "label": query, "embedding_mode": "embeddinggemma2"}).status_code == 201
    assert client.post(f"/api/v1/runs/{offline}/library", json={"result_revision": 2, "label": offline, "embedding_mode": "offline"}).status_code == 201

    response = client.post(f"/api/v1/runs/{query}/similarity", json={"result_revision": 2, "mode": "semantic", "include_summary": True})

    assert response.status_code == 200
    assert response.json()["data"] == {"matches": [], "descriptor_version": "furniture-v1", "excluded_count": 1, "record_count": 0, "design_count": 0, "duplicate_record_count": 0}


def test_embeddinggemma2_automatic_thresholds_fail_closed_until_calibrated(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult, EmbeddingSpaceIdentity

    class Provider:
        identity = EmbeddingSpaceIdentity.embeddinggemma2_text("revision-a")
        model = identity.model
        dimensions = identity.dimensions

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(tuple([1.0] + [0.0] * 767), self.model, self.dimensions)

    client = TestClient(create_app(data_dir=tmp_path, embedding_provider=Provider()))
    run_id = _reviewed_run(client, "eg2-threshold")
    assert client.post(
        f"/api/v1/runs/{run_id}/library",
        json={"result_revision": 2, "label": run_id, "embedding_mode": "embeddinggemma2"},
    ).status_code == 201

    automatic = client.post(
        f"/api/v1/runs/{run_id}/similarity",
        json={"result_revision": 2, "mode": "semantic", "include_abstention": True},
    )
    assert automatic.status_code == 409
    assert automatic.json()["error"]["code"] == "semantic_threshold_uncalibrated"
    assert client.post(
        f"/api/v1/runs/{run_id}/similarity",
        json={"result_revision": 2, "mode": "semantic", "include_abstention": True, "min_score": 0.5},
    ).status_code == 200

    groups = client.post("/api/v1/library/groups", json={"mode": "semantic"})
    assert groups.status_code == 409
    assert groups.json()["error"]["code"] == "semantic_threshold_uncalibrated"
    assert client.post(
        "/api/v1/library/groups", json={"mode": "semantic", "threshold": 0.5}
    ).status_code == 200


def test_embeddinggemma2_groups_infer_single_descriptor_for_exact_calibration(tmp_path: Path, monkeypatch) -> None:
    from backend.app.semantic.embeddings import EmbeddingResult, EmbeddingSpaceIdentity

    class Provider:
        identity = EmbeddingSpaceIdentity.embeddinggemma2_text("revision-a")
        model = identity.model
        dimensions = identity.dimensions

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(tuple([1.0] + [0.0] * 767), self.model, self.dimensions)

    calibration = tmp_path / "thresholds.json"
    calibration.write_text(
        __import__("json").dumps({
            "group": {
                f"semantic:furniture-v1:embeddinggemma2:{Provider.identity.space_id}": 0.9
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("VEXPLORER_SIMILARITY_THRESHOLDS_FILE", str(calibration))
    client = TestClient(create_app(data_dir=tmp_path / "data", embedding_provider=Provider()))
    run_id = _reviewed_run(client, "eg2-calibrated")
    assert client.post(
        f"/api/v1/runs/{run_id}/library",
        json={"result_revision": 2, "label": run_id, "embedding_mode": "embeddinggemma2"},
    ).status_code == 201

    response = client.post("/api/v1/library/groups", json={"mode": "semantic"})

    assert response.status_code == 200
