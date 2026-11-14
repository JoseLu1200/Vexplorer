from __future__ import annotations

import pytest

from backend.app.contratos.modelos import (
    GeneralAutoReviewArgs,
    GeneralAutoReviewDecisionArgs,
    GeneralComponentReview,
    GeneralConstructionConstraint,
    GeneralConstructionDecision,
    GeneralConstructionDetail,
    GeneralDimensionRange,
    GeneralFurnitureReviewRequest,
    GeneralPieceGeometry,
    GeneralPiecePlacement,
    GeneralQuantity,
    GeneralResolvedConstructionParameter,
    GeneralReviewOperation,
    GeneralTextValue,
    GeneralValue,
)
from backend.app.general_furniture.autonomous import (
    _effective_auto_status,
    _review_target_refs,
    _scenario_occurrences,
    _server_review_args,
    _validate_visual_checks,
)
from backend.app.general_furniture.review import apply_general_review
from backend.app.general_furniture.construction_validation import (
    validate_construction_scenario,
)
from backend.tests.test_general_furniture_derivations import _machine_review
from backend.tests.test_general_furniture_review import _draft


def test_review_preserves_estimated_construction_snapshot_without_physical_occurrences() -> None:
    parameter = GeneralResolvedConstructionParameter(
        id="panel_length", label="Largo provisional", nominal_mm=720,
        range_mm=GeneralDimensionRange(min_mm=700, max_mm=740),
        state="estimated", method="construction_assumption",
        dependency_refs=("premise:p1",), source_refs=("view:view-front",),
        assumption_refs=("premise:p1",), rationale="Proporción constructiva revisable.",
    )
    constraint = GeneralConstructionConstraint(
        id="closure", kind="equal", left_refs=("parameter:panel_length",),
        right_refs=("parameter:panel_length",), source_refs=("view:view-front",),
        rationale="Cierre del largo propuesto.",
    )
    detail = GeneralConstructionDetail(
        id="edge", kind="edge", component_ids=("panel-proposed",),
        parameter_refs=("parameter:panel_length",), state="estimated",
        source_refs=("view:view-front",), assumption_refs=("premise:p1",),
        rationale="Canto necesario para el escenario.",
    )
    decision = GeneralConstructionDecision(
        id="choose-length", category="dimension", summary="Adoptar largo provisional.",
        target_refs=("parameter:panel_length",), basis_refs=("view:view-front",),
        alternatives=("Mantener desconocido",), rationale="Permite plano provisional.",
        impact="high",
    )
    placement = GeneralPiecePlacement(
        occurrence_ref="provisional:scenario-main:panel-proposed:1",
        piece_id="panel-proposed", x_mm=0, y_mm=0, rotation_deg=0,
        state="estimated", source_refs=("view:view-front",),
        assumption_refs=("premise:p1",),
    )
    source = _draft().components[0].model_copy(update={
        "length": GeneralValue(
            value_mm=720, state="estimated", dependency_refs=("parameter:panel_length",),
            range_mm=GeneralDimensionRange(min_mm=700, max_mm=740),
            method="construction_assumption", assumption_refs=("premise:p1",),
        ),
        "quantity": GeneralQuantity(
            value=2, state="estimated", dependency_refs=("premise:p1",),
        ),
        "scenario_id": "scenario-main",
        "necessity": "estimated_required",
        "geometry": GeneralPieceGeometry(
            shape_kind="rectangle", source_contour_ids=(),
            basis_refs=("view:view-front",), rationale="Panel rectangular propuesto.",
        ),
        "construction_parameter_ids": ("panel_length",),
        "detail_ids": ("edge",),
        "quantity_basis_refs": ("premise:p1",),
    })
    draft = _draft().model_copy(update={
        "components": (source,),
        "construction_scenario_id": "scenario-main",
        "construction_parameters": (parameter,),
        "construction_constraints": (constraint,),
        "construction_details": (detail,),
        "construction_decisions": (decision,),
        "construction_placements": (placement,),
    })
    component = GeneralComponentReview(
        **source.model_dump(exclude={"premise_ids"}),
        material=GeneralTextValue(value=None, state="unknown"),
        finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=(source.id,),
    )
    request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1, base_review_revision=0,
        reviewer_name="reviewer", reason="Conserva estimación provisional.",
        operations=(GeneralReviewOperation(
            kind="replace", source_component_ids=(source.id,),
            result_component_ids=(source.id,), reason="Snapshot sin mutación.",
        ),),
        components=(component,),
    )

    review = apply_general_review(
        run_id="run-1", proposal_id=draft.proposal_id,
        proposal_revision=1, draft=draft, request=request,
    )

    assert review.construction_scenario_id == "scenario-main"
    assert review.construction_parameters == (parameter,)
    assert review.construction_constraints == (constraint,)
    assert review.construction_details == (detail,)
    assert review.construction_decisions == (decision,)
    assert review.construction_placements == (placement,)
    assert review.components[0].length.value_mm == 720
    assert review.components[0].length.state == "estimated"
    assert review.occurrences == ()


def test_accepted_estimated_quantity_creates_only_provisional_occurrences() -> None:
    source = _machine_review(length_status="accepted", quantity_status="accepted")
    component = source.components[0].model_copy(update={
        "quantity": GeneralQuantity(
            value=2, state="estimated", dependency_refs=("premise:two-sides",),
        ),
        "scenario_id": "construction-main",
    })
    args = GeneralAutoReviewArgs.model_validate({
        "scenario_id": "construction-main",
        "operations": [{
            "kind": "replace", "source_component_ids": [component.id],
            "result_component_ids": [component.id], "reason": "Snapshot estable.",
        }],
        "components": [component.model_dump(mode="json")],
        "checks": [item.model_dump(mode="json") for item in source.machine_checks],
        "field_reviews": [
            item.model_dump(mode="json") for item in source.machine_field_reviews
        ],
        "unresolved": ["material", "finish"],
        "status": "incomplete",
    })

    occurrences = _scenario_occurrences(args, args.checks)

    assert [item.id for item in occurrences] == [
        "provisional:construction-main:machine-side:1",
        "provisional:construction-main:machine-side:2",
    ]
    assert all(item.state == "provisional" for item in occurrences)


def test_autonomous_server_snapshot_preserves_piece_construction_metadata() -> None:
    geometry = GeneralPieceGeometry(
        shape_kind="rectangle", source_contour_ids=(),
        basis_refs=("view:view-front",), rationale="Panel rectangular propuesto.",
    )
    source = _draft().components[0].model_copy(update={
        "scenario_id": "construction-main",
        "necessity": "deduced_required",
        "geometry": geometry,
        "construction_parameter_ids": ("panel_length",),
        "detail_ids": ("edge",),
        "quantity_basis_refs": ("premise:p1",),
    })
    draft = _draft().model_copy(update={"components": (source,)})
    decision = GeneralAutoReviewDecisionArgs(
        scenario_id="construction-main", checks=(), field_reviews=(),
        unresolved=("quantity",), status="incomplete",
    )

    args = _server_review_args(decision, draft, None)

    reviewed = args.components[0]
    assert reviewed.scenario_id == "construction-main"
    assert reviewed.necessity == "deduced_required"
    assert reviewed.geometry == geometry
    assert reviewed.construction_parameter_ids == ("panel_length",)
    assert reviewed.detail_ids == ("edge",)
    assert reviewed.quantity_basis_refs == ("premise:p1",)


def test_autonomous_critic_can_review_construction_and_piece_identity_targets() -> None:
    proposal, draft = __import__(
        "backend.tests.test_general_furniture_construction_validation",
        fromlist=["_proposal_and_draft"],
    )._proposal_and_draft()
    targets = _review_target_refs(proposal, draft)

    assert {
        "component:sides.existence",
        "component:sides.kind",
        "component:sides.role",
        "component:sides.geometry",
        "parameter:thickness",
        "constraint:width-closure",
    } <= targets

    source = _machine_review(length_status="accepted", quantity_status="accepted")
    component = source.components[0]
    args = GeneralAutoReviewArgs.model_validate({
        "scenario_id": "cabinet",
        "operations": [{
            "kind": "replace", "source_component_ids": [component.id],
            "result_component_ids": [component.id], "reason": "Snapshot estable.",
        }],
        "components": [component.model_dump(mode="json")],
        "checks": [{
            "id": "parameter-plausibility", "kind": "visual_consistency",
            "outcome": "pass", "method": "model_visual",
            "target_refs": ["parameter:thickness"],
            "source_refs": ["visual:overview"],
            "summary": "El rango estimado es visualmente plausible.",
        }],
        "field_reviews": [{
            "target_ref": "parameter:thickness", "status": "accepted",
            "check_ids": ["parameter-plausibility"],
        }],
        "unresolved": ["material"], "status": "incomplete",
    })

    _validate_visual_checks(
        args,
        allowed_source_refs={"visual:overview"},
        visual_refs={"visual:overview"},
        allowed_target_refs=targets,
    )
    assert _effective_auto_status(args) == "incomplete"


def test_rejected_construction_dependency_forces_semantic_conflict() -> None:
    source = _machine_review(length_status="accepted", quantity_status="accepted")
    component = source.components[0]
    args = GeneralAutoReviewArgs.model_validate({
        "scenario_id": "cabinet",
        "operations": [{
            "kind": "replace", "source_component_ids": [component.id],
            "result_component_ids": [component.id], "reason": "Snapshot estable.",
        }],
        "components": [component.model_dump(mode="json")],
        "checks": [{
            "id": "bad-thickness", "kind": "visual_consistency",
            "outcome": "fail", "method": "model_visual",
            "target_refs": ["parameter:thickness"],
            "source_refs": ["visual:overview"],
            "summary": "El espesor contradice las vistas.",
        }],
        "field_reviews": [{
            "target_ref": "parameter:thickness", "status": "rejected",
            "check_ids": ["bad-thickness"],
        }],
        "unresolved": [], "status": "incomplete",
    })

    assert _effective_auto_status(args) == "conflict"


def test_deterministic_construction_conflict_forces_semantic_repair_status() -> None:
    proposal, draft = __import__(
        "backend.tests.test_general_furniture_construction_validation",
        fromlist=["_proposal_and_draft"],
    )._proposal_and_draft()
    opening = draft.construction_parameters[2].model_copy(
        update={"nominal_mm": 500, "range_mm": GeneralDimensionRange(
            min_mm=500, max_mm=500
        )}
    )
    invalid_draft = draft.model_copy(update={
        "construction_parameters": (*draft.construction_parameters[:2], opening),
    })
    validation = validate_construction_scenario(proposal, invalid_draft)
    source = _machine_review(length_status="accepted", quantity_status="accepted")

    assert validation.status == "invalid"
    assert _effective_auto_status(source, validation) == "conflict"


def test_accepted_estimated_quantity_requires_basis_and_duplicate_checks() -> None:
    source = _machine_review(length_status="accepted", quantity_status="accepted")
    component = source.components[0].model_copy(update={
        "quantity": GeneralQuantity(
            value=2, state="estimated", dependency_refs=("premise:two-sides",),
        ),
    })
    args = GeneralAutoReviewArgs.model_validate({
        "scenario_id": "cabinet",
        "operations": [{
            "kind": "replace", "source_component_ids": [component.id],
            "result_component_ids": [component.id], "reason": "Snapshot estable.",
        }],
        "components": [component.model_dump(mode="json")],
        "checks": [{
            "id": "looks-plausible", "kind": "visual_consistency",
            "outcome": "pass", "method": "model_visual",
            "target_refs": [f"component:{component.id}.quantity"],
            "source_refs": ["visual:overview"],
            "summary": "La cantidad parece plausible.",
        }],
        "field_reviews": [{
            "target_ref": f"component:{component.id}.quantity",
            "status": "accepted", "check_ids": ["looks-plausible"],
        }],
        "unresolved": [], "status": "accepted",
    })

    with pytest.raises(
        ValueError, match="accepted_provisional_quantity_requires_closed_checks"
    ):
        _validate_visual_checks(
            args,
            {"visual:overview"},
            {"visual:overview"},
            {f"component:{component.id}.quantity"},
        )
