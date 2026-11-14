from __future__ import annotations

import pytest

from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.proposal import materialize_general_proposal
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
