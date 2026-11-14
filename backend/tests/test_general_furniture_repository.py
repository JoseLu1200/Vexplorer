from __future__ import annotations
from backend.app.contratos.modelos import (
    GeneralAssemblyAttempt,
    GeneralAssemblyValidationIssue,
    GeneralAssemblyValidationReport,
    GeneralScene,
)
from backend.app.general_furniture.assembly import validate_assembly
from backend.tests.test_general_furniture_assembly import (
    _candidate as _assembly_candidate,
    _extraction as _assembly_extraction,
    _review as _assembly_review,
)

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

def _assembly_attempt(*, review_revision: int, assembly_revision: int) -> GeneralAssemblyAttempt:
    return GeneralAssemblyAttempt(
        run_id="run-1", proposal_revision=1, review_revision=review_revision,
        assembly_revision=assembly_revision, attempt_index=assembly_revision,
        candidate=None,
        report=GeneralAssemblyValidationReport(
            status="incomplete",
            issues=(GeneralAssemblyValidationIssue(
                code="insufficient_evidence", severity="error",
                message="No hay evidencia suficiente.",
            ),),
            placements=(), scene=None,
        ),
        model="test-assembly", policy_version="general-assembly-v1",
        sources=("drawing:drawing-1",), trace=(),
    )

def test_repository_persists_assembly_attempts_and_rejects_stale_review_writer(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    repository.save_proposal("run-1", proposal, draft, base_proposal_revision=0)
    review = _review()
    repository.save_review("run-1", review, derive_general_package(review))

    repository.save_assembly_attempt(
        "run-1", _assembly_attempt(review_revision=1, assembly_revision=1),
        base_assembly_revision=0,
    )
    assert repository.get_assembly_attempt("run-1", proposal_revision=1, review_revision=1).assembly_revision == 1

    second = review.model_copy(update={"review_revision": 2})
    repository.save_review("run-1", second, derive_general_package(second))
    with pytest.raises(ValueError, match="assembly_revision_conflict"):
        repository.save_assembly_attempt(
            "run-1", _assembly_attempt(review_revision=1, assembly_revision=2),
            base_assembly_revision=1,
        )

def test_repository_exposes_distinct_accepted_assembly_alternatives(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    repository.save_proposal("run-1", proposal, draft, base_proposal_revision=0)
    review = _review()
    repository.save_review("run-1", review, derive_general_package(review))
    candidate = _assembly_candidate(_assembly_extraction(), _assembly_review()).model_copy(
        update={"run_id": "run-1", "proposal_revision": 1, "review_revision": 1}
    )
    for revision, alternative in ((1, "alternative-a"), (2, "alternative-b")):
        selected = candidate.model_copy(update={
            "assembly_revision": revision,
            "candidate_id": f"candidate-{revision}",
            "alternative_id": alternative,
        })
        repository.save_assembly_attempt(
            "run-1",
            GeneralAssemblyAttempt(
                run_id="run-1", proposal_revision=1, review_revision=1,
                assembly_revision=revision, attempt_index=revision,
                candidate=selected,
                report=GeneralAssemblyValidationReport(
                    status="accepted", issues=(), placements=(),
                    scene=GeneralScene(
                        status="mounted_hypothesis", items=(), warnings=(),
                    ),
                ),
                model="test-assembly", policy_version="general-assembly-v1",
                sources=("drawing:drawing-1",), trace=(),
            ),
            base_assembly_revision=revision - 1,
        )

    state = repository.get_assembly_state(
        "run-1", proposal_revision=1, review_revision=1,
    )
    assert state.status == "ambiguous"
    assert state.ambiguous is True
    assert [item.candidate.alternative_id for item in state.accepted_alternatives] == [
        "alternative-a", "alternative-b",
    ]
    package = repository.get_derived(
        "run-1", proposal_revision=1, review_revision=1,
    )
    assert "multiple_compatible_assembly_hypotheses" in package.scene.warnings

    diagnostic_report = validate_assembly(
        _assembly_extraction(), _assembly_review(),
        _assembly_candidate(_assembly_extraction(), _assembly_review()),
    )
    diagnostic_candidate = candidate.model_copy(update={
        "assembly_revision": 3,
        "candidate_id": "candidate-diagnostic",
        "alternative_id": "alternative-b",
    })
    repository.save_assembly_attempt(
        "run-1",
        GeneralAssemblyAttempt(
            run_id="run-1", proposal_revision=1, review_revision=1,
            assembly_revision=3, attempt_index=3,
            candidate=diagnostic_candidate,
            report=diagnostic_report.model_copy(update={
                "status": "incomplete", "scene": None,
            }),
            model="test-assembly", policy_version="general-assembly-v1",
            sources=diagnostic_candidate.sources, trace=(),
        ),
        base_assembly_revision=2,
    )
    terminal_state = repository.get_assembly_state(
        "run-1", proposal_revision=1, review_revision=1,
    )
    terminal_package = repository.get_derived(
        "run-1", proposal_revision=1, review_revision=1,
    )
    assert terminal_state.current.report.placements == diagnostic_report.placements
    assert terminal_state.current.report.scene is None
    assert terminal_package.scene.status != "mounted_hypothesis"

def test_repository_persists_assembly_cancellation_flag(tmp_path) -> None:
    path = tmp_path / "general.sqlite3"
    GeneralFurnitureRepository(path).request_assembly_cancellation(
        "job-1", "run-1", "2026-11-14T12:00:00+00:00"
    )

    restarted = GeneralFurnitureRepository(path)
    assert restarted.is_assembly_cancelled("job-1", "run-1") is True
    assert restarted.is_assembly_cancelled("job-1", "other-run") is False

    proposal = _proposal()
    draft = materialize_general_proposal(_extraction(), proposal)
    restarted.save_proposal("run-1", proposal, draft, base_proposal_revision=0)
    review = _review()
    restarted.save_review("run-1", review, derive_general_package(review))
    candidate = _assembly_candidate(_assembly_extraction(), _assembly_review()).model_copy(
        update={
            "run_id": "run-1", "proposal_revision": 1,
            "review_revision": 1, "assembly_revision": 1,
        }
    )
    accepted = GeneralAssemblyAttempt(
        run_id="run-1", proposal_revision=1, review_revision=1,
        assembly_revision=1, attempt_index=1, candidate=candidate,
        report=GeneralAssemblyValidationReport(
            status="accepted", issues=(), placements=(),
            scene=GeneralScene(status="mounted_hypothesis", items=(), warnings=()),
        ),
        model="test", policy_version="general-assembly-v1",
        sources=("drawing:drawing",), trace=(),
    )
    with pytest.raises(ValueError, match="assembly_cancelled"):
        restarted.save_assembly_attempt(
            "run-1", accepted, base_assembly_revision=0,
            cancellation_job_id="job-1",
        )
    assert restarted.get_assembly_attempt(
        "run-1", proposal_revision=1, review_revision=1,
    ) is None
