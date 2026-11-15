from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    GeneralBinding,
    GeneralComponentProposal,
    GeneralConstructionConstraint,
    GeneralConstructionDetail,
    GeneralEvidenceDisposition,
    GeneralFurnitureProposal,
    GeneralPremise,
    GeneralQuantity,
    GeneralValue,
    GeneralFurnitureReviewRequest,
    GeneralReviewOperation,
    RunRequest,
)


def test_shared_projection_support_requires_distinct_support_components_without_owner() -> None:
    disposition = GeneralEvidenceDisposition(
        candidate_region_id="evidence-candidate:shared-side",
        kind="shared_projection_support",
        support_component_ids=("left-panel", "right-panel"),
        source_refs=("contour:side-shared",),
        rationale="El contorno lateral apoya dos candidatos ortogonales anclados por separado.",
    )

    assert disposition.component_id is None
    assert disposition.support_component_ids == ("left-panel", "right-panel")

    for support_component_ids in ((), ("left-panel",), ("left-panel", "left-panel")):
        with pytest.raises(ValidationError, match="distinct support components"):
            GeneralEvidenceDisposition(
                candidate_region_id="evidence-candidate:shared-side",
                kind="shared_projection_support",
                support_component_ids=support_component_ids,
                source_refs=("contour:side-shared",),
                rationale="Fixture inválido.",
            )


def test_evidence_disposition_rejects_support_components_for_other_kinds() -> None:
    with pytest.raises(ValidationError, match="support_component_ids is only valid"):
        GeneralEvidenceDisposition(
            candidate_region_id="evidence-candidate:owned-front",
            kind="assigned",
            component_id="left-panel",
            support_component_ids=("left-panel", "right-panel"),
            source_refs=("contour:front-left",),
            rationale="Fixture inválido.",
        )


def _proposal() -> GeneralFurnitureProposal:
    return GeneralFurnitureProposal(
        id="general-proposal-1",
        drawing_id="drawing-1",
        ledger_revision="ledger-1",
        proposal_origin="native_tool",
        bindings=(GeneralBinding(id="copy-width", operation="copy", operand_refs=("dimension:dim-width",)),),
        premises=(GeneralPremise(id="premise-panel", description="El contorno puede representar un panel rectangular."),),
        components=(GeneralComponentProposal(
            id="component-1", label="Panel sin rol confirmado", kind="panel", role="unknown",
            length_binding_id="copy-width", width_binding_id=None, thickness_binding_id=None,
            quantity=GeneralQuantity(value=None, state="unknown"), premise_ids=("premise-panel",),
            source_view_ids=("view-front",), source_observation_ids=("observation-front",),
            source_evidence_ids=("evidence-width",), source_dimension_ids=("dim-width",),
            assumptions=("La identidad entre vistas no está confirmada.",),
            unknown_fields=("width", "thickness", "quantity", "placement"),
        ),),
        assumptions=("Propuesta para revisión; no es un despiece de fabricación.",),
    )


def test_general_proposal_uses_only_referenced_bindings_and_keeps_quantity_unknown() -> None:
    proposal = _proposal()
    assert proposal.components[0].quantity.value is None
    assert proposal.components[0].source_view_ids == ("view-front",)


def test_general_proposal_rejects_observed_numeric_value_without_ledger_provenance() -> None:
    with pytest.raises(ValidationError, match="observed value requires drawing provenance"):
        GeneralValue(value_mm=600, state="observed")


def test_general_proposal_rejects_unknown_binding_reference() -> None:
    component = _proposal().components[0].model_copy(update={"length_binding_id": "missing-binding"})
    with pytest.raises(ValidationError, match="unknown binding"):
        GeneralFurnitureProposal(**(_proposal().model_dump() | {"components": (component,)}))


def test_general_proposal_reports_all_unknown_constraint_and_detail_references() -> None:
    proposal = _proposal()
    constraint = GeneralConstructionConstraint(
        id="bad-closure", kind="sum_equals",
        left_refs=("parameter:missing-constraint",),
        right_refs=("binding:copy-width",), tolerance_mm=0.1,
        severity="error", source_refs=("dimension:dim-width",),
        rationale="Fixture referencial inválido.",
    )
    detail = GeneralConstructionDetail(
        id="bad-detail", kind="other", component_ids=("component-1",),
        parameter_refs=("parameter:missing-detail",), state="deduced",
        source_refs=("dimension:dim-width",), assumption_refs=(),
        rationale="Fixture referencial inválido.",
    )

    with pytest.raises(ValidationError) as caught:
        GeneralFurnitureProposal(**(
            proposal.model_dump()
            | {
                "construction_constraints": (constraint,),
                "construction_details": (detail,),
            }
        ))

    message = str(caught.value)
    assert "construction constraint references an unknown parameter or binding" in message
    assert "construction_constraints[0].left_refs" in message
    assert "parameter:missing-constraint" in message
    assert "construction detail references an unknown parameter" in message
    assert "construction_details[0].parameter_refs" in message
    assert "parameter:missing-detail" in message
    assert "expected=parameter:<id>|binding:<id>" in message


def test_general_binding_enforces_operation_arity() -> None:
    with pytest.raises(ValidationError, match="subtract requires at least two operands"):
        GeneralBinding(id="bad", operation="subtract", operand_refs=("dimension:dim-width",))


def test_run_request_admits_general_furniture_without_table_profile() -> None:
    request = RunRequest(
        document_id="doc-0123456789abcdef0123456789abcdef",
        mode="live",
        input_kind="general_furniture",
        proposal_mode="model_generated",
    )
    assert request.input_kind == "general_furniture"


def test_hypothesis_quantity_rejects_free_numeric_value_without_premise_reference() -> None:
    with pytest.raises(ValidationError, match="hypothesis quantity requires premise references"):
        GeneralQuantity(value=999, state="hypothesis")


def test_hypothesis_quantity_must_reference_a_premise_declared_by_the_proposal() -> None:
    proposal = _proposal()
    component = proposal.components[0].model_copy(update={
        "quantity": GeneralQuantity(value=4, state="hypothesis", dependency_refs=("premise:missing",)),
    })

    with pytest.raises(ValidationError, match="unknown quantity premise"):
        GeneralFurnitureProposal(**(proposal.model_dump() | {"components": (component,)}))

    valid = component.model_copy(update={
        "quantity": GeneralQuantity(value=4, state="hypothesis", dependency_refs=("premise:premise-panel",)),
    })
    accepted = GeneralFurnitureProposal(**(proposal.model_dump() | {"components": (valid,)}))
    assert accepted.components[0].quantity.value == 4


def test_review_preserves_explicit_economic_scope_and_does_not_default_it() -> None:
    base = {
        "base_proposal_revision": 1,
        "base_review_revision": 0,
        "reviewer_name": "tecnica",
        "reason": "Alcance económico explícito.",
        "operations": (GeneralReviewOperation(kind="drop", source_component_ids=("component-1",), reason="Se excluye."),),
        "components": (),
    }
    unknown = GeneralFurnitureReviewRequest(**base)
    material_only = GeneralFurnitureReviewRequest(**(base | {"required_cost_scope": ("material",)}))

    assert unknown.required_cost_scope == ()
    assert unknown.required_hours_scope == ()
    assert material_only.required_cost_scope == ("material",)
