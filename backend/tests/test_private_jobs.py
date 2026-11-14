from __future__ import annotations

import time
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.operacion.auth import hash_password
from backend.app.operacion.public_access import PublicAdmissionStore
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
    assert job["error"]["retryable"] is True


def test_interrupted_job_retry_reuses_request_and_links_a_new_job(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "jobs-retry.sqlite3")
    request_json = '{"document_id":"doc-1","mode":"geometry_only"}'
    repository.create_job("job-source", request_json, actor="alice")
    repository.start_job("job-source")
    repository.interrupt_unfinished_jobs()

    retried, created = repository.reserve_job_retry(
        "job-source", "job-retry", actor="alice"
    )
    replay, replay_created = repository.reserve_job_retry(
        "job-source", "job-other", actor="alice"
    )

    assert created is True
    assert retried == replay
    assert replay_created is False
    assert retried["id"] == "job-retry"
    assert retried["retry_of_job_id"] == "job-source"
    assert repository.get_job_request("job-retry") == request_json


def test_job_retry_is_actor_scoped_and_rejects_nonretryable_states(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "jobs-retry-actor.sqlite3")
    repository.create_job("job-alice", '{"mode":"live"}', actor="alice")

    with pytest.raises(KeyError):
        repository.reserve_job_retry("job-alice", "job-bob", actor="bob")
    with pytest.raises(ValueError, match="job_not_retryable:queued"):
        repository.reserve_job_retry("job-alice", "job-retry", actor="alice")

    repository.start_job("job-alice")
    with pytest.raises(ValueError, match="job_not_retryable:running"):
        repository.reserve_job_retry("job-alice", "job-running", actor="alice")

    repository.finish_job("job-alice", run_id="run-success")
    with pytest.raises(ValueError, match="job_not_retryable:succeeded"):
        repository.reserve_job_retry("job-alice", "job-succeeded", actor="alice")

    repository.create_job("job-failed", '{"mode":"live"}', actor="alice")
    repository.start_job("job-failed")
    repository.finish_job(
        "job-failed",
        error={"code": "invalid_input", "message": "No reintentar.", "retryable": False},
    )
    with pytest.raises(ValueError, match="job_not_retryable:error"):
        repository.reserve_job_retry("job-failed", "job-failed-retry", actor="alice")


def test_public_live_quota_persists_and_does_not_charge_idempotent_replay(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs-public-quota.sqlite3"
    repository = DemoRepository(path)
    arguments = {
        "actor": None,
        "public_global_daily_limit": 2,
        "public_client_daily_limit": 1,
    }
    first, created = repository.reserve_job(
        "job-public-1", '{"mode":"live"}',
        idempotency_key="public-request", public_client_hash="client-a", **arguments,
    )
    replay, replay_created = repository.reserve_job(
        "job-public-replay", '{"mode":"live"}',
        idempotency_key="public-request", public_client_hash="client-a", **arguments,
    )
    assert created is True and replay_created is False and replay == first

    restarted = DemoRepository(path)
    with pytest.raises(ValueError, match="public_live_quota_exhausted"):
        restarted.reserve_job(
            "job-public-same-client", '{"mode":"live"}',
            public_client_hash="client-a", **arguments,
        )
    restarted.reserve_job(
        "job-public-2", '{"mode":"live"}',
        public_client_hash="client-b", **arguments,
    )
    with pytest.raises(ValueError, match="public_live_quota_exhausted"):
        restarted.reserve_job(
            "job-public-global", '{"mode":"live"}',
            public_client_hash="client-c", **arguments,
        )


def test_public_live_retry_consumes_quota_once(tmp_path: Path) -> None:
    path = tmp_path / "jobs-public-retry-quota.sqlite3"
    admission = PublicAdmissionStore(path)
    repository = DemoRepository(path)

    def callback(database) -> None:
        decision = admission.admit_mutation(
            "203.0.113.41", "job", database=database
        )
        if not decision.allowed:
            raise ValueError(decision.code or "public_job_admission_denied")

    for source in ("job-source-1", "job-source-2"):
        repository.create_job(source, '{"mode":"live"}', actor=None)
        repository.start_job(source)
    repository.interrupt_unfinished_jobs()
    arguments = {
        "actor": None,
        "public_client_hash": "client-a",
        "public_global_daily_limit": 1,
        "public_client_daily_limit": 1,
        "admission_callback": callback,
    }
    first, created = repository.reserve_job_retry(
        "job-source-1", "job-retry-1", **arguments
    )
    replay, replay_created = repository.reserve_job_retry(
        "job-source-1", "job-retry-replay", **arguments
    )
    assert created is True and replay_created is False and replay == first
    with pytest.raises(ValueError, match="public_live_quota_exhausted"):
        repository.reserve_job_retry("job-source-2", "job-retry-2", **arguments)
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM public_admission_events WHERE action='job'"
        ).fetchone()[0] == 1


def test_job_admission_callback_is_replay_safe_and_rolls_back_with_paid_quota(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs-shared-admission.sqlite3"
    admission = PublicAdmissionStore(path)
    repository = DemoRepository(path)

    def callback(database) -> None:
        decision = admission.admit_mutation(
            "203.0.113.40", "job", database=database
        )
        if not decision.allowed:
            raise ValueError(decision.code or "public_job_admission_denied")

    arguments = {
        "actor": None,
        "idempotency_key": "shared-job",
        "admission_callback": callback,
        "public_client_hash": "paid-client-a",
        "public_global_daily_limit": 1,
        "public_client_daily_limit": 1,
    }
    first, created = repository.reserve_job(
        "job-shared-1", '{"mode":"live"}', **arguments
    )
    replay, replay_created = repository.reserve_job(
        "job-shared-replay", '{"mode":"live"}', **arguments
    )
    assert created is True and replay_created is False and replay == first

    with pytest.raises(ValueError, match="public_live_quota_exhausted"):
        repository.reserve_job(
            "job-paid-denied",
            '{"mode":"live"}',
            actor=None,
            idempotency_key="different-job",
            admission_callback=callback,
            public_client_hash="paid-client-a",
            public_global_daily_limit=1,
            public_client_daily_limit=1,
        )

    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM public_admission_events WHERE action='job'"
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM jobs WHERE id='job-paid-denied'"
        ).fetchone()[0] == 0


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


def test_interrupted_job_api_retry_creates_one_linked_successor(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    )
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("fixture.dxf", FIXTURE.read_bytes(), "application/dxf")},
    )
    request_json = json.dumps({
        "document_id": upload.json()["data"]["document_id"],
        "mode": "geometry_only",
        "input_kind": "mounted_views_legacy",
    })
    source_id = "job-11111111111111111111111111111111"
    repository = client.app.state.repository
    repository.create_job(source_id, request_json, actor=None)
    repository.start_job(source_id)
    repository.interrupt_unfinished_jobs()

    first = client.post(f"/api/v1/jobs/{source_id}/retry")
    second = client.post(
        f"/api/v1/jobs/{source_id}/retry",
        headers={"Idempotency-Key": "same-retry"},
    )

    assert first.status_code == second.status_code == 202
    first_job = first.json()["data"]
    assert second.json()["data"]["id"] == first_job["id"]
    assert first_job["retry_of_job_id"] == source_id
    for _ in range(100):
        retried = client.get(f"/api/v1/jobs/{first_job['id']}").json()["data"]
        if retried["state"] not in {"queued", "running"}:
            break
        time.sleep(0.02)
    assert retried["state"] == "succeeded"
    assert retried["run_id"].startswith("run-")


def test_public_live_api_quota_survives_restart_and_replay_is_free(
    tmp_path: Path, monkeypatch
) -> None:
    catalog = tmp_path / "public-catalog.json"
    catalog.write_text(
        get_table_cost_catalog().model_dump_json(), encoding="utf-8"
    )
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_PUBLIC_LIVE_DAILY_LIMIT", "2")
    monkeypatch.setenv("VEXPLORER_PUBLIC_LIVE_CLIENT_DAILY_LIMIT", "1")
    data_dir = tmp_path / "public-data"
    headers = {
        "Origin": "https://vexplorer.example",
        "Idempotency-Key": "public-live-1",
    }
    with TestClient(create_app(data_dir=data_dir, frontend_dir=tmp_path / "none")) as client:
        upload = client.post(
            "/api/v1/documents",
            files={"file": ("fixture.dxf", FIXTURE.read_bytes(), "application/dxf")},
            headers={"Origin": "https://vexplorer.example"},
        )
        body = {
            "document_id": upload.json()["data"]["document_id"],
            "mode": "live",
            "input_kind": "mounted_views_legacy",
        }
        first = client.post("/api/v1/jobs", json=body, headers=headers)
        replay = client.post("/api/v1/jobs", json=body, headers=headers)
        exhausted = client.post(
            "/api/v1/jobs",
            json=body,
            headers={**headers, "Idempotency-Key": "public-live-2"},
        )
        assert first.status_code == replay.status_code == 202
        assert first.json()["data"]["id"] == replay.json()["data"]["id"]
        assert exhausted.status_code == 429
        assert exhausted.json()["error"]["code"] == "public_live_quota_exhausted"
        assert exhausted.json()["error"]["retryable"] is False
        assert int(exhausted.headers["Retry-After"]) > 0
        assert int(exhausted.headers["X-RateLimit-Reset"]) > int(time.time())

    with TestClient(create_app(data_dir=data_dir, frontend_dir=tmp_path / "none")) as restarted:
        exhausted = restarted.post(
            "/api/v1/jobs",
            json=body,
            headers={**headers, "Idempotency-Key": "public-live-after-restart"},
        )
        assert exhausted.status_code == 429
        assert exhausted.json()["error"]["code"] == "public_live_quota_exhausted"


def test_public_reconstruction_uses_shared_job_and_paid_daily_admission(
    tmp_path: Path, monkeypatch
) -> None:
    import backend.app.reconstruction3d.router as reconstruction_router

    catalog = tmp_path / "public-catalog.json"
    catalog.write_text(
        get_table_cost_catalog().model_dump_json(), encoding="utf-8"
    )
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_PUBLIC_LIVE_DAILY_LIMIT", "1")
    monkeypatch.setenv("VEXPLORER_PUBLIC_LIVE_CLIENT_DAILY_LIMIT", "1")
    sequence = iter(("reconstruction-one", "reconstruction-two"))

    def fake_router(**kwargs):
        admission = kwargs["admission_callback"]
        assert admission is not None
        router = APIRouter()

        @router.post("/api/v1/test-reconstruction-admission")
        def submit(http_request: Request):
            job_id = next(sequence)
            admission(http_request, "submit", job_id)
            return {"job_id": job_id}

        return router

    monkeypatch.setattr(
        reconstruction_router, "create_reconstruction_router", fake_router
    )
    data_dir = tmp_path / "public-data"
    with TestClient(
        create_app(data_dir=data_dir, frontend_dir=tmp_path / "none")
    ) as client:
        first = client.post("/api/v1/test-reconstruction-admission")
        exhausted = client.post("/api/v1/test-reconstruction-admission")

    assert first.status_code == 200
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == "public_live_quota_exhausted"
    assert int(exhausted.headers["Retry-After"]) > 0
    with sqlite3.connect(data_dir / "vexplorer.sqlite3") as database:
        assert database.execute(
            "SELECT job_id,kind FROM job_admission"
        ).fetchall() == [("reconstruction-one", "reconstruction_submit")]
        assert database.execute(
            "SELECT COUNT(*) FROM public_admission_events WHERE action='job'"
        ).fetchone() == (1,)


def test_job_retry_api_rejects_nonretryable_and_foreign_jobs(
    tmp_path: Path, monkeypatch
) -> None:
    users = tmp_path / "users.json"
    users.write_text(json.dumps({
        "alice": hash_password("alice password"),
        "bob": hash_password("bob password"),
    }), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        get_table_cost_catalog().model_dump_json(), encoding="utf-8"
    )
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    client = TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    )
    repository = client.app.state.repository
    queued_id = "job-22222222222222222222222222222222"
    interrupted_id = "job-33333333333333333333333333333333"
    request_json = json.dumps({
        "document_id": "doc-11111111111111111111111111111111",
        "mode": "live",
    })
    repository.create_job(interrupted_id, request_json, actor="alice")
    repository.start_job(interrupted_id)
    repository.interrupt_unfinished_jobs()
    repository.create_job(queued_id, request_json, actor="alice")
    headers = {"Origin": "https://vexplorer.example"}

    queued = client.post(
        f"/api/v1/jobs/{queued_id}/retry",
        auth=("alice", "alice password"), headers=headers,
    )
    foreign = client.post(
        f"/api/v1/jobs/{interrupted_id}/retry",
        auth=("bob", "bob password"), headers=headers,
    )

    assert queued.status_code == 409
    assert queued.json()["error"] == {
        "code": "job_not_retryable:queued",
        "message": "El trabajo no admite reintento.",
        "retryable": False,
    }
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "job_not_found"
