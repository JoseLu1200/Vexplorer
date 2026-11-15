from __future__ import annotations

from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.general_furniture.autonomous import AutoReviewLimits
from backend.tests.test_integral_api_integration import DXF_FIXTURE, _GeneralLiveProvider


class _InjectedProvider:
    def create_response(self, **kwargs):  # pragma: no cover - config tests never call it
        raise AssertionError("provider must not be called")


class _CapturingProvider(_GeneralLiveProvider):
    def __init__(self) -> None:
        super().__init__()
        self.timeouts: list[float] = []

    def create_response(self, **kwargs):
        self.timeouts.append(kwargs["timeout_s"])
        return super().create_response(**kwargs)


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(200):
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["state"] not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {job}")


def test_autonomous_extended_timeout_requires_explicit_internal_authorization() -> None:
    with pytest.raises(ValueError, match="general_auto_review_timeout_budget_invalid"):
        AutoReviewLimits(timeout_s=301)
    with pytest.raises(ValueError, match="general_auto_review_timeout_budget_invalid"):
        AutoReviewLimits(timeout_s=901, allow_extended_test_timeout=True)

    limits = AutoReviewLimits(timeout_s=900, allow_extended_test_timeout=True)

    assert limits.timeout_s == 900


def test_local_explicit_dual_provider_injection_advertises_1800_and_900(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    proposer = _InjectedProvider()
    reviewer = _InjectedProvider()

    with TestClient(
        create_app(
            data_dir=tmp_path,
            frontend_dir=tmp_path / "none",
            agent_provider=proposer,
            general_reviewer_provider=reviewer,
            general_test_job_timeout_s=1800,
        )
    ) as client:
        limits = client.get("/api/v1/config").json()["data"]["capabilities"][
            "general_furniture"
        ]["autonomous_review"]["limits"]

    assert limits["job_timeout_s"] == 1800
    assert limits["review_attempt_timeout_s"] == 900


def test_local_injected_job_passes_900_stage_budgets_to_both_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    proposer = _CapturingProvider()
    reviewer = _CapturingProvider()

    with TestClient(
        create_app(
            data_dir=tmp_path,
            frontend_dir=tmp_path / "none",
            agent_provider=proposer,
            general_reviewer_provider=reviewer,
            general_test_job_timeout_s=1800,
        )
    ) as client:
        document_id = client.post(
            "/api/v1/documents",
            files={"file": ("cabinet.dxf", DXF_FIXTURE.read_bytes(), "application/dxf")},
        ).json()["data"]["document_id"]
        submitted = client.post(
            "/api/v1/jobs",
            json={
                "document_id": document_id,
                "mode": "live",
                "input_kind": "general_furniture",
                "proposal_mode": "model_generated",
            },
        )
        terminal = _wait_job(client, submitted.json()["data"]["id"])

    assert terminal["state"] == "succeeded", terminal
    assert proposer.timeouts and 895 <= proposer.timeouts[0] <= 900
    assert reviewer.timeouts and 895 <= reviewer.timeouts[0] <= 900


def test_production_rejects_test_timeout_even_with_both_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "production")

    with pytest.raises(ValueError, match="general_test_job_timeout_local_only"):
        create_app(
            data_dir=tmp_path,
            agent_provider=_InjectedProvider(),
            general_reviewer_provider=_InjectedProvider(),
            general_test_job_timeout_s=1800,
        )


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 599, 3601])
def test_test_timeout_rejects_non_finite_or_out_of_range_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: float
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")

    with pytest.raises(ValueError, match="invalid_general_test_job_timeout"):
        create_app(
            data_dir=tmp_path,
            agent_provider=_InjectedProvider(),
            general_reviewer_provider=_InjectedProvider(),
            general_test_job_timeout_s=value,
        )


@pytest.mark.parametrize(
    ("proposer", "reviewer"),
    [(_InjectedProvider(), None), (None, _InjectedProvider()), (None, None)],
)
def test_test_timeout_requires_both_explicitly_injected_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    proposer: _InjectedProvider | None,
    reviewer: _InjectedProvider | None,
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")

    with pytest.raises(
        ValueError, match="general_test_job_timeout_requires_injected_providers"
    ):
        create_app(
            data_dir=tmp_path,
            agent_provider=proposer,
            general_reviewer_provider=reviewer,
            general_test_job_timeout_s=1800,
        )


def test_default_local_timeout_remains_300_without_test_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.delenv("VEXPLORER_GENERAL_JOB_TIMEOUT_SECONDS", raising=False)

    with TestClient(create_app(data_dir=tmp_path, frontend_dir=tmp_path / "none")) as client:
        limits = client.get("/api/v1/config").json()["data"]["capabilities"][
            "general_furniture"
        ]["autonomous_review"]["limits"]

    assert limits["job_timeout_s"] == 300
    assert limits["review_attempt_timeout_s"] == 300
