from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "piezas_completo.dxf"


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _upload(client: TestClient) -> str:
    with FIXTURE.open("rb") as stream:
        response = client.post(
            "/api/v1/documents",
            files={"file": (FIXTURE.name, stream, "application/dxf")},
        )
    assert response.status_code == 201
    return response.json()["data"]["document_id"]


def test_parts_only_run_persists_observations_and_candidates(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    drawing = client.get(
        f"/api/v1/documents/{document_id}/drawing",
        params={"input_kind": "separated_part_views"},
    )
    created = client.post(
        "/api/v1/runs",
        json={
            "document_id": document_id,
            "mode": "geometry_only",
            "input_kind": "separated_part_views",
        },
    )

    assert drawing.status_code == 200
    assert drawing.json()["data"]["input_kind"] == "separated_part_views"
    assert created.status_code == 201
    payload = created.json()["data"]
    assert payload["run"]["input_kind"] == "separated_part_views"
    assert payload["result"]["scenarios"] == []
    assert len(payload["result"]["part_analysis"]["observations"]) == 3
    assert payload["result"]["assembly_candidates"]

    run_id = payload["run"]["id"]
    parts = client.get(
        f"/api/v1/runs/{run_id}/parts", params={"result_revision": 1}
    )
    assert parts.status_code == 200
    assert parts.json()["data"]["part_analysis"]["candidate_revision"]
    assert parts.json()["data"]["selected_assembly_candidate_id"] is None


def test_parts_only_requires_explicit_input_kind(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    drawing = client.get(f"/api/v1/documents/{document_id}/drawing")

    assert drawing.status_code == 200
    assert drawing.json()["data"]["input_kind"] == "mounted_views_legacy"
