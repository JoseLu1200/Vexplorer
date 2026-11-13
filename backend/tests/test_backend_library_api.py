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


def _reviewed_run(client: TestClient, label: str) -> str:
    with FIXTURE.open("rb") as stream:
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

    listed = client.get("/api/v1/library")
    assert listed.status_code == 200 and len(listed.json()["data"]) == 2
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

    first = client.post("/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.9}).json()["data"]
    second = client.post("/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.9}).json()["data"]
    assert first == second
    assert len(first) == 1 and len(first[0]["member_ids"]) == 3
    assert first[0]["threshold"] == 0.9
    assert first[0]["method"] == "geometric"
