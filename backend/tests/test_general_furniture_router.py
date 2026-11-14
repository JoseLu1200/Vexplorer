from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.router import GeneralFurnitureContext, create_general_furniture_router
from backend.tests.test_general_furniture_proposal import _extraction, _proposal


def test_router_persists_manual_proposal_and_returns_revision_wrapper(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    app = FastAPI()
    app.include_router(create_general_furniture_router(
        repository=repository,
        context_loader=lambda run_id: GeneralFurnitureContext(
            run_id=run_id, extraction=_extraction().model_copy(update={"input_kind": "general_furniture"}), ledger_revision="ledger-1"
        ),
    ))
    client = TestClient(app)

    proposal = _proposal().model_copy(update={"proposal_origin": "human"})
    response = client.post("/api/v1/runs/run-1/general/proposals", json={"mode": "manual", "base_proposal_revision": 0, "proposal": proposal.model_dump(mode="json")})

    assert response.status_code == 201
    assert response.json()["data"]["proposal_revision"] == 1
    assert response.json()["data"]["status"] == "needs_review"
    assert client.get("/api/v1/runs/run-1/general").status_code == 200


def test_direct_auto_review_is_disabled_without_durable_job_wiring(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    app = FastAPI()
    app.include_router(create_general_furniture_router(
        repository=repository,
        context_loader=lambda run_id: GeneralFurnitureContext(
            run_id=run_id, extraction=_extraction().model_copy(update={"input_kind": "general_furniture"}), ledger_revision="ledger-1"
        ),
    ))
    client = TestClient(app)
    proposal = _proposal().model_copy(update={"proposal_origin": "human"})
    client.post("/api/v1/runs/run-1/general/proposals", json={"mode": "manual", "base_proposal_revision": 0, "proposal": proposal.model_dump(mode="json")})

    response = client.post(
        "/api/v1/runs/run-1/general/auto-review",
        json={"base_proposal_revision": 1, "base_review_revision": 0},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "general_auto_review_requires_durable_job"
