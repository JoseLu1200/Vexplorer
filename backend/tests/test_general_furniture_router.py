from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.router import GeneralFurnitureContext, create_general_furniture_router
from backend.app.general_furniture.derivations import derive_general_package
from backend.tests.test_general_furniture_derivations import _review
from backend.tests.test_general_furniture_repository import _assembly_attempt
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


def test_get_assembly_is_read_only_and_revision_exact(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    from backend.app.general_furniture.proposal import materialize_general_proposal
    draft = materialize_general_proposal(_extraction(), proposal)
    repository.save_proposal("run-1", proposal, draft, base_proposal_revision=0)
    review = _review()
    repository.save_review("run-1", review, derive_general_package(review))
    repository.save_assembly_attempt(
        "run-1", _assembly_attempt(review_revision=1, assembly_revision=1),
        base_assembly_revision=0,
    )
    app = FastAPI()
    app.include_router(create_general_furniture_router(
        repository=repository,
        context_loader=lambda run_id: GeneralFurnitureContext(
            run_id=run_id,
            extraction=_extraction().model_copy(update={"input_kind": "general_furniture"}),
            ledger_revision="ledger-1",
        ),
    ))

    exact = TestClient(app).get(
        "/api/v1/runs/run-1/general/assembly?proposal_revision=1&review_revision=1"
    )
    missing = TestClient(app).get(
        "/api/v1/runs/run-1/general/assembly?proposal_revision=1&review_revision=2"
    )

    assert exact.status_code == 200
    assert exact.json()["assembly_revision"] == 1
    assert exact.json()["current"]["report"]["status"] == "incomplete"
    assert missing.status_code == 404
