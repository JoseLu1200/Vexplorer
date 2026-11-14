from __future__ import annotations

import json
import time
from base64 import urlsafe_b64encode
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderResponse
from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import create_app
from backend.app.operacion.auth import hash_password
from backend.app.servicios.repository import DemoRepository
from backend.tests.test_integral_api_integration import (
    DXF_FIXTURE,
    _GeneralLiveProvider,
)
from backend.tests.test_job_recovery import _CountingProposer, _TimeoutOnceReviewer
from backend.tests.test_security_ownership import _extraction, _scenario


def _repository(tmp_path: Path) -> DemoRepository:
    return DemoRepository(tmp_path / "jobs.sqlite3")


def test_queued_cancellation_is_terminal_idempotent_and_actor_scoped(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    repository.create_job("job-alice", '{"mode":"live"}', actor="alice")

    with pytest.raises(KeyError):
        repository.request_job_cancellation("job-alice", actor="bob")

    cancelled = repository.request_job_cancellation("job-alice", actor="alice")
    repeated = repository.request_job_cancellation("job-alice", actor="alice")

    assert cancelled == repeated
    assert cancelled["state"] == "cancelled"
    assert cancelled["error"] == {
        "code": "job_cancelled",
        "message": "El trabajo fue cancelado antes de comenzar.",
        "retryable": False,
    }
    assert repository.is_job_cancel_requested("job-alice") is True
    with pytest.raises(ValueError, match="job_not_queued"):
        repository.start_job("job-alice")


def test_running_cancellation_is_cooperative_and_terminal_states_reject_it(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    repository.create_job("job-running", '{"mode":"live"}', actor="alice")
    repository.start_job("job-running")

    requested = repository.request_job_cancellation("job-running", actor="alice")

    assert requested["state"] == "running"
    assert repository.is_job_cancel_requested("job-running") is True
    repository.finish_job(
        "job-running",
        error={"code": "job_cancelled", "message": "Cancelado.", "retryable": False},
        cancelled=True,
    )
    assert repository.get_job("job-running")["state"] == "cancelled"
    assert repository.request_job_cancellation("job-running", actor="alice")["state"] == "cancelled"

    repository.create_job("job-success", '{"mode":"geometry_only"}', actor="alice")
    repository.start_job("job-success")
    repository.finish_job("job-success", run_id="run-success")
    with pytest.raises(ValueError, match="job_not_cancellable:succeeded"):
        repository.request_job_cancellation("job-success", actor="alice")


def test_committed_cancellation_wins_race_with_successful_finish(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_job("job-race", "{}", actor="alice")
    repository.start_job("job-race")
    repository.request_job_cancellation("job-race", actor="alice")

    repository.finish_job("job-race", run_id="run-created-before-checkpoint")

    job = repository.get_job("job-race")
    assert job["state"] == "cancelled"
    assert job["run_id"] == "run-created-before-checkpoint"
    assert job["error"]["code"] == "job_cancelled"


def test_queue_position_counts_all_queued_work_without_exposing_foreign_jobs(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    repository.create_job("job-a", "{}", actor="alice")
    repository.create_job("job-b", "{}", actor="bob")
    repository.create_job("job-c", "{}", actor="alice")

    assert repository.get_job_queue_position("job-a", actor="alice") == 1
    assert repository.get_job_queue_position("job-c", actor="alice") == 3
    with pytest.raises(KeyError):
        repository.get_job_queue_position("job-b", actor="alice")

    repository.start_job("job-a")
    assert repository.get_job_queue_position("job-a", actor="alice") is None
    assert repository.get_job_queue_position("job-c", actor="alice") == 2


def test_queue_position_uses_admission_order_when_timestamps_tie(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("backend.app.servicios.repository._now", lambda: "2026-11-14T12:00:00+00:00")
    repository = _repository(tmp_path)
    repository.create_job("job-z", "{}", actor="alice")
    repository.create_job("job-a", "{}", actor="alice")

    assert repository.get_job_queue_position("job-z", actor="alice") == 1
    assert repository.get_job_queue_position("job-a", actor="alice") == 2


def test_recent_jobs_are_actor_scoped_and_cursor_stable(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_job("job-a1", '{"document_id":"doc-a","mode":"live","input_kind":"general_furniture"}', actor="alice")
    repository.create_job("job-b1", '{"document_id":"doc-b","mode":"live","input_kind":"general_furniture"}', actor="bob")
    repository.create_job("job-a2", '{"document_id":"doc-a","mode":"geometry_only","input_kind":"mounted_views_legacy"}', actor="alice")

    first, cursor = repository.list_recent_jobs_for_actor(actor="alice", limit=1)
    second, final_cursor = repository.list_recent_jobs_for_actor(
        actor="alice", limit=1, before_sequence=cursor
    )

    assert [item["id"] for item in first] == ["job-a2"]
    assert first[0]["document_id"] == "doc-a"
    assert first[0]["mode"] == "geometry_only"
    assert cursor is not None
    assert [item["id"] for item in second] == ["job-a1"]
    assert final_cursor is None


def test_job_cannot_link_run_owned_by_another_actor(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.create_run(
        "run-bob", "geometry_only", _extraction(), (_scenario(),), owner_actor="bob"
    )
    repository.create_job("job-alice", "{}", actor="alice")
    repository.start_job("job-alice")

    with pytest.raises(ValueError, match="job_run_owner_mismatch"):
        repository.link_job_run("job-alice", "run-bob")


def test_job_cancel_api_exposes_stable_lifecycle_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    )
    repository = client.app.state.repository
    queued_id = "job-" + "1" * 32
    running_id = "job-" + "2" * 32
    repository.create_job(queued_id, "{}", actor=None)
    repository.create_job(running_id, "{}", actor=None)
    repository.start_job(running_id)

    queued = client.post(f"/api/v1/jobs/{queued_id}/cancel")
    running = client.post(f"/api/v1/jobs/{running_id}/cancel")

    assert queued.status_code == 200
    assert queued.json()["data"] | {
        "state": "cancelled",
        "cancel_requested": True,
        "queue_position": None,
        "can_cancel": False,
    } == queued.json()["data"]
    assert running.status_code == 202
    assert running.json()["data"] | {
        "state": "running",
        "cancel_requested": True,
        "queue_position": None,
        "can_cancel": False,
    } == running.json()["data"]

    polled = client.get(f"/api/v1/jobs/{running_id}").json()["data"]
    assert polled["cancel_requested"] is True
    assert polled["can_cancel"] is False


def test_config_declares_bounded_worker_and_cancel_capabilities(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_JOB_MAX_WORKERS", "2")
    client = TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    )

    submission = client.get("/api/v1/config").json()["data"]["run_submission"]

    assert submission["cancel"] is True
    assert submission["queue_positions"] is True
    assert submission["max_workers"] == 2
    assert client.get("/api/v1/config").json()["data"]["capabilities"]["recent"] == {
        "available": True, "projects": True, "executions": True,
    }


def test_recent_projects_and_executions_have_frozen_paginated_envelopes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    with TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    ) as client:
        document_ids = []
        for filename in ("first.dxf", "second.dxf"):
            document_id = client.post(
                "/api/v1/documents",
                files={"file": (filename, DXF_FIXTURE.read_bytes(), "application/dxf")},
            ).json()["data"]["document_id"]
            document_ids.append(document_id)
            submitted = client.post("/api/v1/jobs", json={
                "document_id": document_id, "mode": "geometry_only",
                "input_kind": "mounted_views_legacy",
            })
            assert submitted.status_code == 202

        projects = client.get("/api/v1/projects", params={"limit": 1})
        executions = client.get("/api/v1/executions", params={"limit": 1})

        assert projects.status_code == executions.status_code == 200
        project_page = projects.json()["data"]
        execution_page = executions.json()["data"]
        assert set(project_page) == {"items", "next_cursor"}
        assert set(execution_page) == {"items", "next_cursor"}
        assert project_page["next_cursor"]
        assert execution_page["next_cursor"]
        project = project_page["items"][0]
        execution = execution_page["items"][0]
        assert project["document_id"] == document_ids[-1]
        assert project["filename"] == "second.dxf"
        assert set(project) == {"document_id", "filename", "created_at", "latest_execution"}
        assert set(project["latest_execution"]) == {"job_id", "run_id", "state", "updated_at"}
        assert set(execution) == {
            "job_id", "run_id", "document_id", "filename", "mode", "input_kind",
            "state", "created_at", "updated_at", "queue_position", "cancel_requested",
        }

        next_projects = client.get(
            "/api/v1/projects",
            params={"limit": 1, "cursor": project_page["next_cursor"]},
        ).json()["data"]
        next_executions = client.get(
            "/api/v1/executions",
            params={"limit": 1, "cursor": execution_page["next_cursor"]},
        ).json()["data"]
        assert next_projects["items"][0]["document_id"] == document_ids[0]
        assert next_executions["items"][0]["document_id"] == document_ids[0]


def test_recent_endpoints_reject_invalid_cursor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    client = TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    )

    for endpoint in ("projects", "executions"):
        response = client.get(f"/api/v1/{endpoint}", params={"cursor": "not-a-cursor"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_recent_cursor"

    malformed = (
        ("executions", {"kind": "executions", "sequence": True}),
        ("executions", {"kind": "executions", "sequence": 1.5}),
        ("executions", {"kind": "executions", "sequence": "1"}),
        ("projects", {"kind": "projects", "created_at": {}, "document_id": "doc-" + "1" * 32}),
        ("projects", {"kind": "projects", "created_at": "2026-11-14T12:00:00+00:00", "document_id": "foreign"}),
    )
    for endpoint, payload in malformed:
        cursor = urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        response = client.get(f"/api/v1/{endpoint}", params={"cursor": cursor})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_recent_cursor"


def test_recent_endpoints_never_list_another_authenticated_actor(
    tmp_path: Path, monkeypatch
) -> None:
    users = tmp_path / "users.json"
    users.write_text(json.dumps({
        "alice": hash_password("alice password"),
        "bob": hash_password("bob password"),
    }), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    headers = {"Origin": "https://vexplorer.example"}

    with TestClient(
        create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    ) as client:
        documents = {}
        for actor in ("alice", "bob"):
            auth = (actor, f"{actor} password")
            document = client.post(
                "/api/v1/documents", auth=auth, headers=headers,
                files={"file": (f"{actor}.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
            ).json()["data"]["document_id"]
            documents[actor] = document
            response = client.post(
                "/api/v1/jobs", auth=auth,
                headers={**headers, "Idempotency-Key": f"{actor}-job"},
                json={"document_id": document, "mode": "geometry_only", "input_kind": "mounted_views_legacy"},
            )
            assert response.status_code == 202

        for actor in ("alice", "bob"):
            auth = (actor, f"{actor} password")
            projects = client.get("/api/v1/projects", auth=auth).json()["data"]["items"]
            executions = client.get("/api/v1/executions", auth=auth).json()["data"]["items"]
            assert {item["document_id"] for item in projects} == {documents[actor]}
            assert {item["document_id"] for item in executions} == {documents[actor]}
            assert {item["filename"] for item in projects} == {f"{actor}.dxf"}


def test_running_job_observes_cancellation_after_in_flight_provider_call(
    tmp_path: Path, monkeypatch
) -> None:
    class BlockingProvider(_GeneralLiveProvider):
        def __init__(self) -> None:
            super().__init__()
            self.started = Event()
            self.release = Event()
            self.blocked = False

        def create_response(self, **kwargs):
            if not self.blocked:
                self.blocked = True
                self.started.set()
                assert self.release.wait(3)
            return super().create_response(**kwargs)

    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_JOB_MAX_WORKERS", "1")
    provider = BlockingProvider()
    app = create_app(
        data_dir=tmp_path / "data",
        frontend_dir=tmp_path / "none",
        agent_provider=provider,
        general_reviewer_provider=provider,
    )
    with TestClient(app) as client:
        document_id = client.post(
            "/api/v1/documents",
            files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
        ).json()["data"]["document_id"]
        job = client.post("/api/v1/jobs", json={
            "document_id": document_id,
            "mode": "live",
            "input_kind": "general_furniture",
            "proposal_mode": "model_generated",
        }).json()["data"]
        assert provider.started.wait(3)

        cancellation = client.post(f"/api/v1/jobs/{job['id']}/cancel")
        assert cancellation.status_code == 202
        provider.release.set()

        for _ in range(200):
            terminal = client.get(f"/api/v1/jobs/{job['id']}").json()["data"]
            if terminal["state"] not in {"queued", "running"}:
                break
            time.sleep(0.02)

        assert terminal["state"] == "cancelled"
        assert terminal["error"]["code"] == "job_cancelled"
        assert provider.review_visual_page_count == 0


def test_cancelled_general_proposer_does_not_make_a_follow_up_model_call(
    tmp_path: Path, monkeypatch
) -> None:
    class NoToolBlockingProvider(_GeneralLiveProvider):
        def __init__(self) -> None:
            super().__init__()
            self.started = Event()
            self.release = Event()
            self.calls = 0

        def create_response(self, **kwargs):
            self.calls += 1
            self.started.set()
            assert self.release.wait(3)
            return ProviderResponse(
                id=f"no-tool-{self.calls}", tool_calls=(), model="test",
                input_tokens=1, output_tokens=1,
            )

    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_JOB_MAX_WORKERS", "1")
    provider = NoToolBlockingProvider()
    app = create_app(
        data_dir=tmp_path / "data", frontend_dir=tmp_path / "none",
        agent_provider=provider, general_reviewer_provider=provider,
    )
    with TestClient(app) as client:
        document_id = client.post(
            "/api/v1/documents",
            files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
        ).json()["data"]["document_id"]
        job = client.post("/api/v1/jobs", json={
            "document_id": document_id, "mode": "live",
            "input_kind": "general_furniture", "proposal_mode": "model_generated",
        }).json()["data"]
        assert provider.started.wait(3)
        assert client.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 202
        provider.release.set()
        for _ in range(200):
            terminal = client.get(f"/api/v1/jobs/{job['id']}").json()["data"]
            if terminal["state"] not in {"queued", "running"}:
                break
            time.sleep(0.02)

        assert terminal["state"] == "cancelled"
        assert provider.calls == 1


def test_resumed_review_observes_cancellation_before_publishing_review(
    tmp_path: Path, monkeypatch
) -> None:
    class BlockingResumeReviewer(_TimeoutOnceReviewer):
        def __init__(self) -> None:
            super().__init__()
            self.resume_started = Event()
            self.resume_release = Event()

        def create_response(self, **kwargs):
            if self.review_calls == 1:
                self.resume_started.set()
                assert self.resume_release.wait(3)
            return super().create_response(**kwargs)

    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_JOB_MAX_WORKERS", "1")
    reviewer = BlockingResumeReviewer()
    app = create_app(
        data_dir=tmp_path / "data",
        frontend_dir=tmp_path / "none",
        agent_provider=_CountingProposer(),
        general_reviewer_provider=reviewer,
    )
    with TestClient(app) as client:
        document_id = client.post(
            "/api/v1/documents",
            files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
        ).json()["data"]["document_id"]
        source = client.post("/api/v1/jobs", json={
            "document_id": document_id,
            "mode": "live",
            "input_kind": "general_furniture",
            "proposal_mode": "model_generated",
        }).json()["data"]
        for _ in range(200):
            failed = client.get(f"/api/v1/jobs/{source['id']}").json()["data"]
            if failed["state"] == "failed":
                break
            time.sleep(0.02)
        assert failed["state"] == "failed"

        resumed = client.post(f"/api/v1/jobs/{source['id']}/resume").json()["data"]
        assert reviewer.resume_started.wait(3)
        assert client.post(f"/api/v1/jobs/{resumed['id']}/cancel").status_code == 202
        reviewer.resume_release.set()

        for _ in range(200):
            terminal = client.get(f"/api/v1/jobs/{resumed['id']}").json()["data"]
            if terminal["state"] not in {"queued", "running"}:
                break
            time.sleep(0.02)

        assert terminal["state"] == "cancelled"
        record = app.state.general_furniture_repository.get(failed["run_id"])
        assert record is not None and record.review is None
