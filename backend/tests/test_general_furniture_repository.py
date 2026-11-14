from __future__ import annotations

import pytest

from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.derivations import derive_general_package
from backend.tests.test_general_furniture_derivations import _review
from backend.tests.test_general_furniture_proposal import _extraction, _proposal


def test_repository_persists_proposal_revision_and_returns_exact_snapshot(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    revision = repository.save_proposal("run-1", proposal, draft, base_proposal_revision=0)
    record = repository.get("run-1")
    assert revision == 1
    assert record is not None
    assert record.proposal_revision == 1
    assert record.proposal == proposal
    assert record.draft == draft
    assert record.review is None


def test_repository_keeps_immutable_proposal_history_and_rejects_stale_writer(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    repository.save_proposal("run-1", proposal, draft, base_proposal_revision=0)
    second = proposal.model_copy(update={"id": "proposal-2"})
    second_draft = draft.model_copy(update={"proposal_id": "proposal-2"})
    repository.save_proposal("run-1", second, second_draft, base_proposal_revision=1)

    assert repository.get("run-1", proposal_revision=1).proposal.id == "proposal-1"
    assert repository.get("run-1").proposal.id == "proposal-2"
    with pytest.raises(ValueError, match="proposal_revision_conflict"):
        repository.save_proposal("run-1", second, second_draft, base_proposal_revision=1)


def test_repository_bounds_proposal_revisions_per_run(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3", max_proposals_per_run=1)
    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    repository.save_proposal("run-1", proposal, draft, base_proposal_revision=0)

    with pytest.raises(ValueError, match="proposal_quota_exceeded"):
        repository.save_proposal("run-1", proposal, draft, base_proposal_revision=1)


def test_repository_rejects_derived_snapshot_with_mismatched_exact_revision(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    repository.save_proposal(
        "run-1", proposal, materialize_general_proposal(_extraction(), proposal),
        base_proposal_revision=0,
    )
    review = _review()
    mismatched = derive_general_package(review).model_copy(
        update={"proposal_revision": 2}
    )

    with pytest.raises(ValueError, match="general_derived_revision_mismatch"):
        repository.save_review("run-1", review, mismatched)


def test_repository_rejects_construction_plan_from_another_exact_snapshot(tmp_path) -> None:
    from backend.tests.test_general_furniture_construction_planner import (
        _review as construction_review,
        _validation as construction_validation,
    )

    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    repository.save_proposal(
        "run-cabinet", proposal, draft, base_proposal_revision=0
    )
    proposal_2 = proposal.model_copy(update={"id": "proposal-cabinet"})
    draft_2 = draft.model_copy(update={"proposal_id": "proposal-cabinet"})
    repository.save_proposal(
        "run-cabinet", proposal_2, draft_2, base_proposal_revision=1
    )
    review = construction_review().model_copy(update={
        "construction_validation": construction_validation(),
    })
    package = derive_general_package(review)
    assert package.construction is not None
    wrong_plan = package.construction.model_copy(update={
        "basis_revision": "run:other:proposal:2:review:1:scenario:cabinet-main"
    })

    with pytest.raises(
        ValueError, match="general_construction_snapshot_revision_mismatch"
    ):
        repository.save_review(
            "run-cabinet", review,
            package.model_copy(update={"construction": wrong_plan}),
        )
