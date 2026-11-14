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
        response = client.post("/api/v1/documents", files={"file": ("estanteria.dxf", stream, "application/dxf")})
    assert response.status_code == 201
    return response.json()["data"]["document_id"]


def test_geometry_only_full_flow_uses_real_extractor_and_versioned_review(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"})

    assert created.status_code == 201
    run_id = created.json()["data"]["run"]["id"]
    initial = created.json()["data"]["result"]
    assert initial["result_revision"] == 1 and initial["state"] == "needs_review"
    assert len(initial["scenarios"]) == 2
    assert initial["scenarios"][0]["id"] in initial["scenarios"][1]["incompatible_with"]
    roles = {item["role"] for item in initial["scenarios"][0]["components"]}
    assert {"side_panel", "top_panel", "base_panel", "shelf"} <= roles
    assert all(item["thickness_mm"] is None for item in initial["scenarios"][0]["components"])

    reviewed = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Técnica demo",
            "scenario_id": "scenario-between-sides",
            "confirmed_thickness_mm": 18,
            "material": "tablero sintético",
            "finish": "melamina sintética",
            "notes": "Técnico confirma montaje y espesor",
        },
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["data"]["result_revision"] == 2
    assert reviewed.json()["data"]["state"] == "completed"
    shelf = next(item for item in reviewed.json()["data"]["pieces"] if item["role"] == "shelf")
    assert shelf["quantity"] == 2 and shelf["length_mm"] == 864

    snapshot = client.get(f"/api/v1/runs/{run_id}").json()["data"]
    assert snapshot["run"]["state"] == "needs_review"
    assert snapshot["result"]["result_revision"] == 2
    assert client.get(f"/api/v1/runs/{run_id}/ledger").json()["data"]["schema_version"] == "0.2.0"
    assert client.get(f"/api/v1/runs/{run_id}/drawing").json()["data"]["coordinate_unit"] == "mm"

    comparables = client.get(f"/api/v1/runs/{run_id}/comparables")
    assert comparables.status_code == 200 and comparables.json()["data"]
    estimated = client.post(f"/api/v1/runs/{run_id}/estimate", json={"result_revision": 2})
    assert estimated.status_code == 201
    estimate = estimated.json()["data"]
    assert estimate["result_revision"] == 2
    assert estimate["total"] == round(sum(item["amount"] for item in estimate["concepts"]), 2)

    exported = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"})
    assert exported.status_code == 200 and exported.json()["result_revision"] == 2
    events = client.get(f"/api/v1/runs/{run_id}/events")
    assert events.status_code == 200 and "event: run_finished" in events.text


def test_unavailable_live_and_unrecorded_replay_are_explicit_errors(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    live = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "live"})
    replay = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "recorded_replay"})

    assert live.status_code == 503
    assert live.json()["error"]["code"] == "live_provider_unavailable"
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "recorded_replay_unavailable"
    config = client.get("/api/v1/config").json()["data"]
    assert config["live_available"] is False
    assert config["unavailable_reason"]
    assert config["recorded_replay_available"] is False
    assert config["vision"]["enabled"] is False
    assert config["vision"]["authority"] == "context_only_not_measurement_source"
    assert all("path" not in str(tool).lower() for tool in config["tools"])


def test_document_id_cannot_escape_storage_and_export_is_audit_bundle(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    escaped = client.post("/api/v1/runs", json={"document_id": "../private", "mode": "geometry_only"})
    assert escaped.status_code == 422

    document_id = _upload(client)
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    client.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica demo", "scenario_id": "scenario-between-sides", "confirmed_thickness_mm": 18, "material": "tablero sintético", "finish": "melamina sintética", "notes": "Confirmado"})
    client.post(f"/api/v1/runs/{run_id}/estimate", json={"result_revision": 2})

    bundle = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"}).json()
    assert bundle["result_revision"] == 2
    assert bundle["result"]["review"]["reviewer_name"] == "Técnica demo"
    assert bundle["estimate"]["result_revision"] == 2
    assert bundle["comparables"] and bundle["events"]
