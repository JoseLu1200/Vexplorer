from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderError
from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import create_app
from backend.app.servicios.repository import DemoRepository
from backend.tests.test_integral_api_integration import DXF_FIXTURE, _GeneralLiveProvider


class _CountingProposer(_GeneralLiveProvider):
    def __init__(self) -> None:
        super().__init__()
        self.proposal_calls = 0

    def create_response(self, **kwargs):
        self.proposal_calls += 1
        return super().create_response(**kwargs)


class _TimeoutOnceReviewer(_GeneralLiveProvider):
    def __init__(self) -> None:
        super().__init__()
        self.review_calls = 0

    def create_response(self, **kwargs):
        self.review_calls += 1
        if self.review_calls == 1:
            raise ProviderError("provider_request_timeout")
        return super().create_response(**kwargs)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(150):
        payload = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if payload["state"] not in {"queued", "running"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {payload}")


def test_job_run_checkpoint_survives_restart_and_cannot_be_relinked(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    repository = DemoRepository(path)
    repository.create_job("job-source", '{"mode":"live"}', actor="alice")
    repository.start_job("job-source")

    repository.link_job_run("job-source", "run-original")
    with pytest.raises(ValueError, match="job_run_already_linked"):
        repository.link_job_run("job-source", "run-other")

    restarted = DemoRepository(path)
    assert restarted.interrupt_unfinished_jobs() == 1
    job = restarted.get_job("job-source")
    assert job["state"] == "interrupted"
    assert job["run_id"] == "run-original"


def test_resume_successor_reservation_is_atomic_and_keeps_typed_checkpoint(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "jobs.sqlite3")
    repository.create_job("job-source", '{"mode":"live"}', actor="alice")
    repository.start_job("job-source")
    repository.finish_job("job-source", error={"code": "provider_request_timeout", "retryable": True})
    checkpoint = {
        "attempt_kind": "review_from_saved_proposal", "run_id": "run-original",
        "proposal_revision": 1, "review_revision": 0, "document_sha256": "a" * 64,
    }

    def reserve(index: int):
        return repository.reserve_job_retry(
            "job-source", f"job-retry-{index}", actor="alice",
            resume_checkpoint=checkpoint,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, (1, 2)))

    assert sum(created for _, created in results) == 1
    assert len({job["id"] for job, _ in results}) == 1
    successor_id = results[0][0]["id"]
    assert repository.get_job_resume_checkpoint(successor_id) == checkpoint


def test_general_job_timeout_defaults_are_local_300_and_production_600(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("VEXPLORER_GENERAL_JOB_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    local = TestClient(create_app(data_dir=tmp_path / "local", frontend_dir=tmp_path / "none"))
    assert local.get("/api/v1/config").json()["data"]["capabilities"]["general_furniture"]["autonomous_review"]["limits"]["job_timeout_s"] == 300

    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    production = TestClient(create_app(data_dir=tmp_path / "production", frontend_dir=tmp_path / "none"))
    limits = production.get("/api/v1/config").json()["data"]["capabilities"]["general_furniture"]["autonomous_review"]["limits"]
    assert limits["job_timeout_s"] == 600
    assert limits["review_attempt_timeout_s"] == 300


def test_failed_review_restores_checkpoint_and_resume_does_not_repeat_proposer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    proposer = _CountingProposer()
    reviewer = _TimeoutOnceReviewer()
    app = create_app(
        data_dir=tmp_path / "data",
        frontend_dir=tmp_path / "none",
        agent_provider=proposer,
        general_reviewer_provider=reviewer,
    )
    client = TestClient(app)
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

    failed = _wait_job(client, source["id"])
    assert failed["state"] == "failed"
    assert failed["error"]["code"] == "provider_request_timeout"
    assert failed["error"]["phase"] == "autonomous_review"
    assert failed["checkpoint"] == {
        "phase": "autonomous_review",
        "proposal_saved": True,
        "proposal_id": failed["checkpoint"]["proposal_id"],
        "proposal_revision": 1,
        "review_revision": 0,
    }
    assert failed["recovery"]["safe_action"] == "resume_review"
    assert failed["recovery"]["endpoint"] == f"/api/v1/jobs/{source['id']}/resume"
    assert failed["recovery"]["attempt_kind"] == "review_from_saved_proposal"
    assert failed["recovery"]["repeats_proposer"] is False
    assert failed["recovery"]["continues_original_provider_call"] is False
    assert proposer.proposal_calls == 1
    restored_run = client.get(f"/api/v1/runs/{failed['run_id']}").json()["data"]
    assert restored_run["latest_job"]["id"] == source["id"]
    assert restored_run["latest_job"]["checkpoint"] == failed["checkpoint"]
    assert restored_run["latest_job"]["recovery"] == failed["recovery"]

    resumed_response = client.post(f"/api/v1/jobs/{source['id']}/resume")
    repeated_response = client.post(f"/api/v1/jobs/{source['id']}/resume")
    assert resumed_response.status_code == repeated_response.status_code == 202
    conflicting_retry = client.post(f"/api/v1/jobs/{source['id']}/retry")
    assert conflicting_retry.status_code == 409
    assert conflicting_retry.json()["error"]["code"] == "job_recovery_action_conflict"
    resumed = resumed_response.json()["data"]
    assert repeated_response.json()["data"]["id"] == resumed["id"]
    completed = _wait_job(client, resumed["id"])

    assert completed["state"] == "succeeded", completed.get("error")
    assert completed["run_id"] == failed["run_id"]
    assert completed["retry_of_job_id"] == source["id"]
    assert proposer.proposal_calls == 1
    record = app.state.general_furniture_repository.get(completed["run_id"])
    assert record is not None and record.review is not None
    assert record.review.auto_review_status == "incomplete"


def test_resume_rejects_failed_job_without_saved_proposal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    app = create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    client = TestClient(app)
    repository = app.state.repository
    job_id = "job-99999999999999999999999999999999"
    repository.create_job(job_id, json.dumps({"document_id": "doc-" + "1" * 32, "mode": "live", "input_kind": "general_furniture"}), actor=None)
    repository.start_job(job_id)
    repository.finish_job(job_id, error={"code": "provider_request_timeout", "phase": "proposal", "retryable": True})

    restored = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
    assert restored["checkpoint"]["proposal_saved"] is False
    assert restored["recovery"]["safe_action"] == "retry_from_start"
    assert restored["recovery"]["endpoint"] == f"/api/v1/jobs/{job_id}/retry"
    rejected = client.post(f"/api/v1/jobs/{job_id}/resume")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "job_resume_checkpoint_unavailable"


def test_resume_rejects_an_existing_full_retry_for_same_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    app = create_app(
        data_dir=tmp_path / "data", frontend_dir=tmp_path / "none",
        agent_provider=_CountingProposer(),
        general_reviewer_provider=_TimeoutOnceReviewer(),
    )
    client = TestClient(app)
    document_id = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    ).json()["data"]["document_id"]
    source = client.post("/api/v1/jobs", json={
        "document_id": document_id, "mode": "live",
        "input_kind": "general_furniture", "proposal_mode": "model_generated",
    }).json()["data"]
    failed = _wait_job(client, source["id"])
    assert failed["recovery"]["safe_action"] == "resume_review"

    retry_id = "job-" + "a" * 32
    _, created = app.state.repository.reserve_job_retry(
        source["id"], retry_id, actor=None,
    )
    assert created is True
    conflict = client.post(f"/api/v1/jobs/{source['id']}/resume")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "job_recovery_action_conflict"


def test_concurrent_retry_and_resume_choose_one_recovery_action(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    app = create_app(
        data_dir=tmp_path / "data", frontend_dir=tmp_path / "none",
        agent_provider=_CountingProposer(),
        general_reviewer_provider=_TimeoutOnceReviewer(),
    )
    client = TestClient(app)
    document_id = client.post(
        "/api/v1/documents",
        files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
    ).json()["data"]["document_id"]
    source = client.post("/api/v1/jobs", json={
        "document_id": document_id, "mode": "live",
        "input_kind": "general_furniture", "proposal_mode": "model_generated",
    }).json()["data"]
    assert _wait_job(client, source["id"])["recovery"]["safe_action"] == "resume_review"

    repository = app.state.repository
    original_get_retry = repository.get_job_retry
    precheck_barrier = Barrier(2)

    def synchronized_get_retry(*args, **kwargs):
        result = original_get_retry(*args, **kwargs)
        precheck_barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(repository, "get_job_retry", synchronized_get_retry)
    monkeypatch.setattr(
        app.state.job_executor, "submit_reserved",
        lambda _process: app.state.job_executor.release(),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (
            pool.submit(client.post, f"/api/v1/jobs/{source['id']}/retry"),
            pool.submit(client.post, f"/api/v1/jobs/{source['id']}/resume"),
        )
        responses = [future.result(timeout=10) for future in futures]

    assert sorted(response.status_code for response in responses) == [202, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "job_recovery_action_conflict"


def test_retry_conflicts_when_resume_wins_after_precheck(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    app = create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    client = TestClient(app)
    repository = app.state.repository
    source_id = "job-" + "b" * 32
    repository.create_job(source_id, json.dumps({
        "document_id": "doc-" + "1" * 32, "mode": "live",
        "input_kind": "general_furniture", "proposal_mode": "model_generated",
    }), actor=None)
    repository.start_job(source_id)
    repository.finish_job(source_id, error={"code": "provider_request_timeout", "retryable": True})
    original_reserve = repository.reserve_job_retry
    resume_id = "job-" + "c" * 32

    def resume_wins_before_retry_reserves(*args, **kwargs):
        _, created = original_reserve(source_id, resume_id, actor=None,
                                      resume_checkpoint={"run_id": "saved-run"})
        assert created is True
        return original_reserve(*args, **kwargs)

    monkeypatch.setattr(repository, "reserve_job_retry", resume_wins_before_retry_reserves)
    response = client.post(f"/api/v1/jobs/{source_id}/retry")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_recovery_action_conflict"
    assert repository.get_job_retry(source_id, actor=None)["id"] == resume_id
