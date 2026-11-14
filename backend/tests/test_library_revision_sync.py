from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.semantic.descriptor import build_descriptor, semantic_text
from backend.app.semantic.embeddings import EmbeddingProviderError, EmbeddingResult, embedding_cache_key

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SHELF = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"
FIXTURE_VARIANT = ROOT / "data" / "planos_demo" / "mueble_demo_002.dxf"


class _HashEmbeddingProvider:
    model = "text-embedding-3-small"
    dimensions = 4

    def __init__(self, *, fail_after_calls: int | None = None) -> None:
        self.calls = 0
        self.fail_after_calls = fail_after_calls

    def embed(self, text: str) -> EmbeddingResult:
        self.calls += 1
        if self.fail_after_calls is not None and self.calls > self.fail_after_calls:
            raise EmbeddingProviderError("semantic_provider_failed")
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = tuple(1.0 + digest[index] / 255.0 for index in range(self.dimensions))
        return EmbeddingResult(vector=vector, model=self.model, dimensions=self.dimensions)


def _client(tmp_path: Path, monkeypatch, embedding_provider=None) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    app = create_app(data_dir=tmp_path, embedding_provider=embedding_provider)
    return TestClient(app)


def _create_run(client: TestClient, fixture: Path, label: str) -> tuple[str, str]:
    with fixture.open("rb") as stream:
        upload = client.post(
            "/api/v1/documents",
            files={"file": (f"{label}.dxf", stream, "application/dxf")},
        )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["data"]["document_id"]
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"})
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    return data["run"]["id"], data["result"]["scenarios"][0]["id"]


def _review_payload(scenario_id: str) -> dict:
    return {
        "base_result_revision": 1,
        "reviewer_name": "Técnica",
        "scenario_id": scenario_id,
        "confirmed_thickness_mm": 18,
        "material": "tablero",
        "finish": "melamina",
        "notes": "Confirmación en revisión",
    }


def test_offline_review_refreshes_library_item_and_json_export(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    run_id, scenario_id = _create_run(client, FIXTURE_SHELF, "offline-sync")

    saved_resp = client.post(
        f"/api/v1/runs/{run_id}/library",
        json={"result_revision": 1, "label": "Estantería inicial", "embedding_mode": "offline"},
    )
    assert saved_resp.status_code == 201, saved_resp.text
    saved = saved_resp.json()["data"]
    assert saved["result_revision"] == 1
    assert saved["descriptor"]["structure"] == "unknown"
    assert "structure" in saved["descriptor"]["unknown_fields"]
    assert "confirmed_components" in saved["descriptor"]["unknown_fields"]
    assert saved["embedding"] is None

    review_resp = client.post(f"/api/v1/runs/{run_id}/reviews", json=_review_payload(scenario_id))
    assert review_resp.status_code == 201, review_resp.text
    assert review_resp.json()["data"]["result_revision"] == 2

    listed_resp = client.get("/api/v1/library")
    assert listed_resp.status_code == 200, listed_resp.text
    items = listed_resp.json()["data"]
    assert len(items) == 1
    refreshed = items[0]
    assert refreshed["id"] == saved["id"]
    assert refreshed["label"] == "Estantería inicial"
    assert refreshed["created_at"] == saved["created_at"]
    assert refreshed["result_revision"] == 2
    assert refreshed["embedding"] is None
    assert refreshed["descriptor_fingerprint"] != saved["descriptor_fingerprint"]
    assert refreshed["descriptor"]["structure"] == "top_base_between_sides"
    assert refreshed["descriptor"]["material"] == "tablero"
    assert refreshed["descriptor"]["finish"] == "melamina"
    assert "structure" not in refreshed["descriptor"]["unknown_fields"]
    assert "confirmed_components" not in refreshed["descriptor"]["unknown_fields"]
    assert "material" not in refreshed["descriptor"]["unknown_fields"]
    assert "finish" not in refreshed["descriptor"]["unknown_fields"]

    export_resp = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"})
    assert export_resp.status_code == 200, export_resp.text
    bundle = export_resp.json()
    assert bundle["result_revision"] == 2
    assert all(piece["thickness_mm"] == 18 for piece in bundle["result"]["pieces"])
    assert bundle["library_item"] is not None
    assert bundle["library_item"]["result_revision"] == 2
    assert bundle["library_item"]["descriptor"] == bundle["descriptor"]

    events = client.app.state.repository.get_events(run_id)
    refreshed_events = [item for item in events if item["event_type"] == "library_item_refreshed"]
    assert len(refreshed_events) == 1
    assert refreshed_events[0]["data"]["library_item_id"] == saved["id"]
    assert refreshed_events[0]["data"]["result_revision"] == 2
    assert refreshed_events[0]["data"]["embedding_refreshed"] is False


def test_semantic_review_regenerates_embedding_and_unblocks_similarity(tmp_path: Path, monkeypatch) -> None:
    provider = _HashEmbeddingProvider()
    client = _client(tmp_path, monkeypatch, embedding_provider=provider)
    run_a, scenario_a = _create_run(client, FIXTURE_SHELF, "semantic-a")
    run_b, _ = _create_run(client, FIXTURE_VARIANT, "semantic-b")
    run_c, scenario_c = _create_run(client, FIXTURE_SHELF, "semantic-c")

    save_a = client.post(
        f"/api/v1/runs/{run_a}/library",
        json={"result_revision": 1, "label": "Estantería A", "embedding_mode": "openai"},
    )
    save_b = client.post(
        f"/api/v1/runs/{run_b}/library",
        json={"result_revision": 1, "label": "Variante B", "embedding_mode": "openai"},
    )
    assert save_a.status_code == 201 and save_b.status_code == 201
    rev1_cache_key = save_a.json()["data"]["embedding"]["cache_key"]
    assert provider.calls == 2

    review_a = client.post(f"/api/v1/runs/{run_a}/reviews", json=_review_payload(scenario_a))
    assert review_a.status_code == 201, review_a.text
    assert provider.calls == 3

    item_a = client.app.state.repository.get_library_item(run_a)
    assert item_a.result_revision == 2
    assert item_a.embedding is not None
    assert item_a.embedding.status == "generated"
    assert item_a.embedding.cache_key != rev1_cache_key

    events_a = client.app.state.repository.get_events(run_a)
    refreshed_a = [item for item in events_a if item["event_type"] == "library_item_refreshed"]
    assert len(refreshed_a) == 1
    assert refreshed_a[0]["data"]["library_item_id"] == item_a.id
    assert refreshed_a[0]["data"]["result_revision"] == 2
    assert refreshed_a[0]["data"]["embedding_refreshed"] is True

    similarity = client.post(
        f"/api/v1/runs/{run_a}/similarity",
        json={"result_revision": 2, "mode": "semantic", "limit": 5},
    )
    assert similarity.status_code == 200, similarity.text
    matches = similarity.json()["data"]
    assert len(matches) == 1
    assert matches[0]["run_id"] == run_b
    assert matches[0]["method"] == "semantic"
    assert matches[0]["score_kind"] == "cosine_similarity"

    # A second identical shelf reuses both Rev 1 and Rev 2 cached embeddings without extra provider calls.
    save_c = client.post(
        f"/api/v1/runs/{run_c}/library",
        json={"result_revision": 1, "label": "Estantería C", "embedding_mode": "openai"},
    )
    assert save_c.status_code == 201
    assert save_c.json()["data"]["embedding"]["status"] == "cache"
    review_c = client.post(f"/api/v1/runs/{run_c}/reviews", json=_review_payload(scenario_c))
    assert review_c.status_code == 201
    assert provider.calls == 3
    item_c = client.app.state.repository.get_library_item(run_c)
    assert item_c.result_revision == 2
    assert item_c.embedding is not None and item_c.embedding.status == "cache"


def test_review_degrades_gracefully_when_provider_raises_during_refresh(tmp_path: Path, monkeypatch) -> None:
    provider = _HashEmbeddingProvider(fail_after_calls=1)
    client = _client(tmp_path, monkeypatch, embedding_provider=provider)
    run_id, scenario_id = _create_run(client, FIXTURE_SHELF, "failing-provider")

    saved = client.post(
        f"/api/v1/runs/{run_id}/library",
        json={"result_revision": 1, "label": "Con embedding inicial", "embedding_mode": "openai"},
    )
    assert saved.status_code == 201
    assert saved.json()["data"]["embedding"] is not None

    review = client.post(f"/api/v1/runs/{run_id}/reviews", json=_review_payload(scenario_id))
    assert review.status_code == 201, review.text
    assert review.json()["data"]["result_revision"] == 2

    item = client.app.state.repository.get_library_item(run_id)
    assert item.result_revision == 2
    assert item.descriptor.structure == "top_base_between_sides"
    assert item.embedding is None

    events = client.app.state.repository.get_events(run_id)
    [refreshed_event] = [item for item in events if item["event_type"] == "library_item_refreshed"]
    assert refreshed_event["data"]["library_item_id"] == item.id
    assert refreshed_event["data"]["result_revision"] == 2
    assert refreshed_event["data"]["embedding_refreshed"] is False


def test_review_degrades_gracefully_when_provider_unavailable_or_cache_incompatible(tmp_path: Path, monkeypatch) -> None:
    dir_unavailable = tmp_path / "unavailable"
    client_with_provider = _client(dir_unavailable, monkeypatch, embedding_provider=_HashEmbeddingProvider())
    run_unavailable, scenario_unavailable = _create_run(client_with_provider, FIXTURE_SHELF, "no-provider")
    assert client_with_provider.post(
        f"/api/v1/runs/{run_unavailable}/library",
        json={"result_revision": 1, "label": "Guardado con proveedor", "embedding_mode": "openai"},
    ).status_code == 201

    client_without_provider = _client(dir_unavailable, monkeypatch, embedding_provider=None)
    review_unavailable = client_without_provider.post(
        f"/api/v1/runs/{run_unavailable}/reviews",
        json=_review_payload(scenario_unavailable),
    )
    assert review_unavailable.status_code == 201, review_unavailable.text
    updated_unavailable = client_without_provider.app.state.repository.get_library_item(run_unavailable)
    assert updated_unavailable.result_revision == 2
    assert updated_unavailable.embedding is None

    # Corrupt/incompatible cache entry under the Rev 2 cache key triggers ValueError in repository.get_embedding.
    dir_cache_conflict = tmp_path / "cache-conflict"
    provider = _HashEmbeddingProvider()
    client_conflict = _client(dir_cache_conflict, monkeypatch, embedding_provider=provider)
    run_seed, scenario_seed = _create_run(client_conflict, FIXTURE_SHELF, "seed-rev2")
    assert client_conflict.post(
        f"/api/v1/runs/{run_seed}/reviews",
        json=_review_payload(scenario_seed),
    ).status_code == 201
    rev2_result = client_conflict.app.state.repository.get_result(run_seed, 2)
    rev2_descriptor = build_descriptor(rev2_result)
    rev2_cache_key = embedding_cache_key(
        rev2_descriptor.descriptor_version,
        provider.model,
        provider.dimensions,
        semantic_text(rev2_descriptor),
    )

    run_target, scenario_target = _create_run(client_conflict, FIXTURE_SHELF, "target-rev1")
    assert client_conflict.post(
        f"/api/v1/runs/{run_target}/library",
        json={"result_revision": 1, "label": "Conflicto caché", "embedding_mode": "openai"},
    ).status_code == 201
    with sqlite3.connect(dir_cache_conflict / "vexplorer.sqlite3") as db:
        db.execute(
            "INSERT OR REPLACE INTO embedding_cache VALUES (?, ?, ?, ?, ?, ?)",
            (rev2_cache_key, "other-model", provider.dimensions, rev2_descriptor.descriptor_version, "[1.0,1.0,1.0,1.0]", "2026-11-14T00:00:00Z"),
        )

    review_conflict = client_conflict.post(
        f"/api/v1/runs/{run_target}/reviews",
        json=_review_payload(scenario_target),
    )
    assert review_conflict.status_code == 201, review_conflict.text
    updated_conflict = client_conflict.app.state.repository.get_library_item(run_target)
    assert updated_conflict.result_revision == 2
    assert updated_conflict.embedding is None


def test_review_without_library_entry_creates_no_item_or_refresh_event(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    run_id, scenario_id = _create_run(client, FIXTURE_SHELF, "not-in-library")

    review = client.post(f"/api/v1/runs/{run_id}/reviews", json=_review_payload(scenario_id))
    assert review.status_code == 201, review.text

    listed = client.get("/api/v1/library")
    assert listed.status_code == 200
    assert listed.json()["data"] == []

    event_types = [item["event_type"] for item in client.app.state.repository.get_events(run_id)]
    assert "human_review_committed" in event_types
    assert "library_item_refreshed" not in event_types
    assert "library_item_saved" not in event_types


def test_idempotent_review_replay_does_not_emit_duplicate_refresh_events(tmp_path: Path, monkeypatch) -> None:
    provider = _HashEmbeddingProvider()
    client = _client(tmp_path, monkeypatch, embedding_provider=provider)
    run_id, scenario_id = _create_run(client, FIXTURE_SHELF, "idempotent-replay")

    assert client.post(
        f"/api/v1/runs/{run_id}/library",
        json={"result_revision": 1, "label": "Idempotente", "embedding_mode": "openai"},
    ).status_code == 201
    assert provider.calls == 1

    payload = _review_payload(scenario_id)
    headers = {"Idempotency-Key": "sync-idem-key-1"}
    first = client.post(f"/api/v1/runs/{run_id}/reviews", json=payload, headers=headers)
    second = client.post(f"/api/v1/runs/{run_id}/reviews", json=payload, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["data"]["result_revision"] == 2
    assert second.json()["data"]["result_revision"] == 2
    assert provider.calls == 2

    events = client.app.state.repository.get_events(run_id)
    refreshed_events = [item for item in events if item["event_type"] == "library_item_refreshed"]
    saved_events = [item for item in events if item["event_type"] == "library_item_saved"]
    assert len(refreshed_events) == 1
    assert len(saved_events) == 2
