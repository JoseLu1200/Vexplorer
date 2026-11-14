from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import create_app


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _prepare_run(data_dir: Path, monkeypatch, *, content: bytes, reviewed: bool, label: str) -> str:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.delenv("VEXPLORER_AUTH_ENABLED", raising=False)
    with TestClient(create_app(data_dir=data_dir, frontend_dir=data_dir / "missing-frontend")) as client:
        uploaded = client.post("/api/v1/documents", files={"file": (f"{label}.dxf", content, "application/dxf")})
        assert uploaded.status_code == 201
        document_id = uploaded.json()["data"]["document_id"]
        created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"})
        assert created.status_code == 201
        run_id = created.json()["data"]["run"]["id"]
        if reviewed:
            scenario_id = created.json()["data"]["result"]["scenarios"][0]["id"]
            response = client.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica responsable", "scenario_id": scenario_id, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "Revisión de fuente real controlada"})
            assert response.status_code == 201
        return run_id


def _production_client(data_dir: Path, tmp_path: Path, monkeypatch) -> TestClient:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    return TestClient(create_app(data_dir=data_dir, frontend_dir=tmp_path / "missing-frontend"))


def _mark_extraction_synthetic(data_dir: Path, run_id: str) -> None:
    with sqlite3.connect(data_dir / "vexplorer.sqlite3") as database:
        payload = json.loads(database.execute("SELECT extraction_json FROM runs WHERE id=?", (run_id,)).fetchone()[0])
        payload["synthetic"] = True
        database.execute("UPDATE runs SET extraction_json=? WHERE id=?", (json.dumps(payload), run_id))


def _keep_only_nested_source_hash(data_dir: Path, run_id: str) -> None:
    with sqlite3.connect(data_dir / "vexplorer.sqlite3") as database:
        document_id = database.execute("SELECT document_id FROM runs WHERE id=?", (run_id,)).fetchone()[0]
    path = data_dir / "documents" / f"{document_id}.manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["source"]["sha256"]
    manifest.pop("sha256", None)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _publish(client: TestClient, run_id: str, revision: int, publication: dict | None):
    payload = {"result_revision": revision, "label": run_id, "embedding_mode": "offline"}
    if publication is not None:
        payload["publication"] = publication
    return client.post(f"/api/v1/runs/{run_id}/library", json=payload, headers={"Origin": "https://vexplorer.example"})


def test_production_library_requires_declared_real_reviewed_attestation_and_rejects_known_sources(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    fixture_bytes = FIXTURE.read_bytes()
    unreviewed = _prepare_run(data_dir, monkeypatch, content=fixture_bytes + b"\n", reviewed=False, label="unreviewed-real-control")
    known_demo = _prepare_run(data_dir, monkeypatch, content=fixture_bytes, reviewed=True, label="known-demo")
    declared_real = _prepare_run(data_dir, monkeypatch, content=fixture_bytes + b"\n", reviewed=True, label="declared-real-control")
    _keep_only_nested_source_hash(data_dir, declared_real)
    synthetic = _prepare_run(data_dir, monkeypatch, content=fixture_bytes + b"\n\n", reviewed=True, label="synthetic-control")
    _mark_extraction_synthetic(data_dir, synthetic)
    publication = {"source_kind": "real_furniture", "source_reference": "work-order:controlled-real-001", "approved_for_public_library": True}

    with _production_client(data_dir, tmp_path, monkeypatch) as client:
        config = client.get("/api/v1/config").json()["data"]
        assert config["library_requires_real_reviewed"] is True

        missing_review = _publish(client, unreviewed, 1, publication)
        assert missing_review.status_code == 409
        assert missing_review.json()["error"]["code"] == "public_library_review_required"

        missing_attestation = _publish(client, declared_real, 2, None)
        assert missing_attestation.status_code == 422
        assert missing_attestation.json()["error"]["code"] == "public_library_attestation_required"

        blank_reference = _publish(client, declared_real, 2, {**publication, "source_reference": "   "})
        assert blank_reference.status_code == 422

        demo = _publish(client, known_demo, 2, publication)
        assert demo.status_code == 409
        assert demo.json()["error"]["code"] == "public_library_fixture_forbidden"

        synthetic_response = _publish(client, synthetic, 2, publication)
        assert synthetic_response.status_code == 409
        assert synthetic_response.json()["error"]["code"] == "public_library_synthetic_forbidden"

        accepted = _publish(client, declared_real, 2, publication)
        assert accepted.status_code == 201
        stored = accepted.json()["data"]["publication"]
        assert stored["source_kind"] == "real_furniture"
        assert stored["source_reference"] == "work-order:controlled-real-001"
        assert stored["approved_for_public_library"] is True
        assert stored["attested_by"] == "Técnica responsable"
        assert stored["attested_at"]
