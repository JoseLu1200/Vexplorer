from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.servicios.repository import DemoRepository


FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"


def test_restart_marks_unfinished_paid_work_interrupted_without_reexecution(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "jobs.sqlite3")
    repository.create_job("job-1", '{"mode":"live"}', actor="alice")
    repository.start_job("job-1")

    restarted = DemoRepository(tmp_path / "jobs.sqlite3")
    assert restarted.interrupt_unfinished_jobs() == 1
    job = restarted.get_job("job-1")
    assert job["state"] == "interrupted"
    assert job["run_id"] is None
    assert job["error"]["code"] == "server_restarted"


def test_job_idempotency_is_scoped_by_actor_and_body(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "jobs-idempotency.sqlite3")
    first, created = repository.reserve_job(
        "job-1", '{"mode":"live"}', actor="alice", idempotency_key="submission-1"
    )
    replay, replay_created = repository.reserve_job(
        "job-2", '{"mode":"live"}', actor="alice", idempotency_key="submission-1"
    )

    assert created is True and replay_created is False
    assert replay == first
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        repository.reserve_job(
            "job-3", '{"mode":"geometry_only"}',
            actor="alice", idempotency_key="submission-1",
        )
    other_actor, other_created = repository.reserve_job(
        "job-4", '{"mode":"geometry_only"}',
        actor="bob", idempotency_key="submission-1",
    )
    assert other_created is True and other_actor["id"] == "job-4"


def test_job_api_persists_before_processing_and_can_be_polled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("fixture.dxf", FIXTURE.read_bytes(), "application/dxf")},
    )
    document_id = upload.json()["data"]["document_id"]

    submitted = client.post("/api/v1/jobs", json={
        "document_id": document_id,
        "mode": "geometry_only",
        "input_kind": "mounted_views_legacy",
    })

    assert submitted.status_code == 202
    initial = submitted.json()["data"]
    assert initial == {"id": initial["id"], "state": "queued", "run_id": None, "error": None}
    for _ in range(100):
        status = client.get(f"/api/v1/jobs/{initial['id']}")
        payload = status.json()["data"]
        if payload["state"] in {"succeeded", "failed", "interrupted"}:
            break
        time.sleep(0.02)
    assert payload["state"] == "succeeded"
    assert payload["run_id"].startswith("run-")
    assert client.get(f"/api/v1/runs/{payload['run_id']}").status_code == 200
