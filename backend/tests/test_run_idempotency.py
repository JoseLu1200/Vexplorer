from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import create_app
from backend.app.servicios.repository import DemoRepository

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))


def _upload(client: TestClient, filename: str = "estanteria.dxf") -> str:
    with FIXTURE.open("rb") as stream:
        response = client.post("/api/v1/documents", files={"file": (filename, stream, "application/dxf")})
    assert response.status_code == 201
    return response.json()["data"]["document_id"]


def test_sqlite_wal_mode_enabled_and_repository_run_idempotency(tmp_path: Path) -> None:
    db_path = tmp_path / "wal-idempotency.sqlite3"
    repository = DemoRepository(db_path)

    with repository._connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    with sqlite3.connect(db_path) as raw_conn:
        raw_journal_mode = raw_conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert str(journal_mode).lower() == "wal"
    assert str(raw_journal_mode).lower() == "wal"
    assert synchronous == 1

    assert repository.get_idempotent_run(
        actor=None, idempotency_key="key-1", request_hash="hash-1"
    ) is None

    repository.save_idempotent_run(
        actor=None, idempotency_key="key-1", request_hash="hash-1", run_id="run-1"
    )
    assert (
        repository.get_idempotent_run(
            actor=None, idempotency_key="key-1", request_hash="hash-1"
        )
        == "run-1"
    )
    assert (
        repository.get_idempotent_run(
            actor="", idempotency_key="key-1", request_hash="hash-1"
        )
        == "run-1"
    )

    # Identical retry on concurrent save is a safe no-op.
    repository.save_idempotent_run(
        actor=None, idempotency_key="key-1", request_hash="hash-1", run_id="run-2"
    )
    assert (
        repository.get_idempotent_run(
            actor=None, idempotency_key="key-1", request_hash="hash-1"
        )
        == "run-1"
    )

    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        repository.get_idempotent_run(
            actor=None, idempotency_key="key-1", request_hash="hash-other"
        )
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        repository.save_idempotent_run(
            actor=None, idempotency_key="key-1", request_hash="hash-other", run_id="run-3"
        )

    # Actor scoping isolates identical keys across actors.
    repository.save_idempotent_run(
        actor="alice", idempotency_key="key-1", request_hash="hash-alice", run_id="run-alice"
    )
    repository.save_idempotent_run(
        actor="bob", idempotency_key="key-1", request_hash="hash-bob", run_id="run-bob"
    )
    assert (
        repository.get_idempotent_run(
            actor="alice", idempotency_key="key-1", request_hash="hash-alice"
        )
        == "run-alice"
    )
    assert (
        repository.get_idempotent_run(
            actor="bob", idempotency_key="key-1", request_hash="hash-bob"
        )
        == "run-bob"
    )


def test_create_run_same_idempotency_key_and_body_returns_same_run(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    body = {"document_id": document_id, "mode": "geometry_only"}
    headers = {"Idempotency-Key": "run-create-1"}

    first = client.post("/api/v1/runs", json=body, headers=headers)
    assert first.status_code == 201
    first_data = first.json()["data"]
    run_id = first_data["run"]["id"]

    # Advance run revision via a review to verify replay still serves revision 1 without creating another run.
    reviewed = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Técnica demo",
            "scenario_id": "scenario-between-sides",
            "confirmed_thickness_mm": 18,
            "material": "tablero sintético",
            "finish": "melamina sintética",
            "notes": "Revisión intermedia",
        },
    )
    assert reviewed.status_code == 201

    second = client.post("/api/v1/runs", json=body, headers=headers)
    assert second.status_code == 201
    second_data = second.json()["data"]
    assert second_data["run"]["id"] == run_id
    assert second_data["result"] == first_data["result"]
    assert second_data["result"]["result_revision"] == 1

    with sqlite3.connect(tmp_path / "data" / "vexplorer.sqlite3") as db:
        run_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        idem_count = db.execute("SELECT COUNT(*) FROM run_idempotency").fetchone()[0]
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    assert run_count == 1
    assert idem_count == 1
    assert str(journal_mode).lower() == "wal"


def test_create_run_same_idempotency_key_different_body_returns_409(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    doc_a = _upload(client, "a.dxf")
    doc_b = _upload(client, "b.dxf")
    headers = {"Idempotency-Key": "shared-run-key"}

    first = client.post("/api/v1/runs", json={"document_id": doc_a, "mode": "geometry_only"}, headers=headers)
    assert first.status_code == 201

    conflict = client.post("/api/v1/runs", json={"document_id": doc_b, "mode": "geometry_only"}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"

    with sqlite3.connect(tmp_path / "data" / "vexplorer.sqlite3") as db:
        run_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    assert run_count == 1


@pytest.mark.parametrize("bad_key", ["", "   ", "k" * 129])
def test_create_run_invalid_idempotency_key_returns_422(
    tmp_path: Path, monkeypatch, bad_key: str
) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    response = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
        headers={"Idempotency-Key": bad_key},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_create_run_max_valid_idempotency_key_length_succeeds(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    max_key = "k" * 128

    first = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
        headers={"Idempotency-Key": max_key},
    )
    second = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
        headers={"Idempotency-Key": max_key},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["run"]["id"] == first.json()["data"]["run"]["id"]


def test_create_run_without_idempotency_key_creates_distinct_runs(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    body = {"document_id": document_id, "mode": "geometry_only"}

    first = client.post("/api/v1/runs", json=body)
    second = client.post("/api/v1/runs", json=body)

    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["data"]["run"]["id"]
    second_id = second.json()["data"]["run"]["id"]
    assert first_id != second_id

    with sqlite3.connect(tmp_path / "data" / "vexplorer.sqlite3") as db:
        run_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    assert run_count == 2


def test_create_run_failed_attempt_does_not_consume_idempotency_key(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    headers = {"Idempotency-Key": "retry-after-404"}

    missing = client.post(
        "/api/v1/runs",
        json={"document_id": "doc-" + "0" * 32, "mode": "geometry_only"},
        headers=headers,
    )
    assert missing.status_code == 404

    recovered = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
        headers=headers,
    )
    assert recovered.status_code == 201


def test_create_run_concurrent_save_conflict_returns_409(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    repository: DemoRepository = client.app.state.repository
    key = "race-key"
    repository.save_idempotent_run(
        actor=None,
        idempotency_key=key,
        request_hash=hashlib.sha256(b"other-payload").hexdigest(),
        run_id="run-existing",
    )
    # Force the pre-execution lookup to return None, simulating an interleaved insert before save.
    monkeypatch.setattr(repository, "get_idempotent_run", lambda **kwargs: None)

    conflict = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
        headers={"Idempotency-Key": key},
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"


def test_create_run_in_production_checks_use_jobs_endpoint_first(tmp_path: Path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/runs",
        json={"document_id": "doc-" + "0" * 32, "mode": "geometry_only"},
        headers={"Origin": "https://vexplorer.example", "Idempotency-Key": ""},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "use_jobs_endpoint"


@pytest.mark.parametrize("same_payload", [True, False])
def test_concurrent_request_reserved_before_execution(tmp_path, monkeypatch, same_payload):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    first_client = _client(tmp_path, monkeypatch)
    second_client = _client(tmp_path, monkeypatch)
    document = _upload(first_client)
    other_document = document if same_payload else _upload(first_client, "other.dxf")
    repository = first_client.app.state.repository
    entered, release = Event(), Event()
    original_create = repository.create_run

    def delayed_create(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(repository, "create_run", delayed_create)
    headers = {"Idempotency-Key": "overlapping-requests"}
    body = {"document_id": document, "mode": "geometry_only"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_client.post, "/api/v1/runs", json=body, headers=headers)
        try:
            assert entered.wait(10)
            second = second_client.post("/api/v1/runs", json={**body, "document_id": other_document}, headers=headers)
            assert second.status_code == 409
            assert second.json()["error"]["code"] == (
                "idempotency_key_in_progress" if same_payload else "idempotency_key_conflict"
            )
        finally:
            release.set()
        completed = first.result(timeout=10)
    assert completed.status_code == 201
    replay = second_client.post("/api/v1/runs", json=body, headers=headers)
    assert replay.status_code == 201
    assert replay.json()["data"]["run"]["id"] == completed.json()["data"]["run"]["id"]
    with repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
