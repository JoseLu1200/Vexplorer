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


def _upload(client: TestClient) -> str:
    with FIXTURE.open("rb") as stream:
        response = client.post("/api/v1/documents", files={"file": ("drawing.dxf", stream, "application/dxf")})
    return response.json()["data"]["document_id"]


def test_document_drawing_is_available_before_any_run(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    response = client.get(f"/api/v1/documents/{document_id}/drawing")

    assert response.status_code == 200
    assert response.json()["data"]["drawing_id"]
    assert response.json()["data"]["views"]

    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"})
    assert created.json()["data"]["run"]["document_id"] == document_id


def test_document_drawing_rejects_invalid_identifier_and_missing_document(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    assert client.get("/api/v1/documents/..%2Fprivate/drawing").status_code in (404, 422)
    missing = client.get(f"/api/v1/documents/doc-{'0' * 32}/drawing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "document_not_found"


def test_document_preview_is_svg_with_restrictive_headers(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    response = client.get(f"/api/v1/documents/{document_id}/preview.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_result_revisions_are_listed_in_order(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    scenario_id = created["result"]["scenarios"][0]["id"]
    client.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": scenario_id, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "Confirmado"})

    response = client.get(f"/api/v1/runs/{run_id}/revisions")

    assert response.status_code == 200
    assert [item["result_revision"] for item in response.json()["data"]] == [1, 2]


def test_scene_is_bound_to_requested_revision(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    before = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 1})
    assert before.status_code == 200
    assert before.json()["data"]["state"] == "unavailable"

    scenario_id = created["result"]["scenarios"][0]["id"]
    client.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": scenario_id, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "Confirmado"})
    after = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
    assert after.status_code == 200
    assert after.json()["data"]["result_revision"] == 2
    assert after.json()["data"]["objects"]
    client.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": "Ficha", "embedding_mode": "offline"})
    bundle = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"}).json()
    assert bundle["scene"]["result_revision"] == 2
    assert bundle["explanations"]["result_revision"] == 2
    assert bundle["descriptor"]["descriptor_version"] == "furniture-v1"
    assert bundle["library_item"]["result_revision"] == 2
