from __future__ import annotations

import pytest

from backend.app.contratos.modelos import (
    GeneralComponentReview,
    GeneralDraftComponent,
    GeneralFurnitureDraft,
    GeneralFurnitureReviewRequest,
    GeneralQuantity,
    GeneralReviewOperation,
    GeneralPremise,
    GeneralTextValue,
    GeneralValue,
)
from backend.app.general_furniture.review import apply_general_review


def _component(*, quantity: GeneralQuantity) -> GeneralComponentReview:
    return GeneralComponentReview(
        id="panel-reviewed",
        label="Panel revisado",
        kind="panel",
        role="side_panel",
        length=GeneralValue(value_mm=720, state="confirmed", dependency_refs=("human:length",)),
        width=GeneralValue(value_mm=None, state="unknown"),
        thickness=GeneralValue(value_mm=18, state="confirmed", dependency_refs=("human:thickness",)),
        quantity=quantity,
        material=GeneralTextValue(value=None, state="unknown"),
        finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=("panel-proposed",),
        source_view_ids=("view-front", "view-side", "view-top"),
        source_observation_ids=("observation-front",),
        source_evidence_ids=("evidence-height",),
        source_dimension_ids=("dim-height",),
        assumptions=("El rol lateral fue confirmado por la persona revisora.",),
        unknown_fields=("width", "material", "finish", "placement"),
    )


def _draft() -> GeneralFurnitureDraft:
    unknown = GeneralValue(value_mm=None, state="unknown")
    return GeneralFurnitureDraft(
        proposal_id="proposal-1", drawing_id="drawing-1", ledger_revision="ledger-1",
        components=(GeneralDraftComponent(
            id="panel-proposed", label="Panel", kind="panel", role="unknown",
            length=unknown, width=unknown, thickness=unknown,
            quantity=GeneralQuantity(value=None, state="unknown"), premise_ids=("p1",),
            source_view_ids=("view-front", "view-side", "view-top"),
            source_observation_ids=("observation-front",), source_evidence_ids=("evidence-height",),
            source_dimension_ids=("dim-height",), source_document_refs=(), assumptions=("Rol pendiente",),
            unknown_fields=("length", "width", "thickness", "quantity", "placement"),
        ),),
        premises=(GeneralPremise(id="p1", description="Panel hipotético"),), assumptions=("Revisión requerida",),
    )


def test_review_preserves_server_resolved_field_provenance() -> None:
    value = GeneralValue(value_mm=564, state="deduced", dependency_refs=("binding:opening",), evidence_ids=("evidence-overall",), dimension_ids=("dim-overall",))
    quantity = GeneralQuantity(value=2, state="hypothesis", dependency_refs=("premise:p1",), evidence_ids=("evidence-count",))
    draft = _draft()
    draft = draft.model_copy(update={"components": (draft.components[0].model_copy(update={"length": value, "quantity": quantity}),)})
    component = _component(quantity=quantity).model_copy(update={"length": value})
    request = GeneralFurnitureReviewRequest(base_proposal_revision=1, base_review_revision=0, reviewer_name="reviewer", reason="Preserve resolved provenance.", operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel-proposed",), result_component_ids=("panel-reviewed",), reason="Same field."),), components=(component,))
    review = apply_general_review(run_id="run", proposal_id="proposal-1", proposal_revision=1, draft=draft, request=request)
    assert review.components[0].length == value
    assert review.components[0].quantity == quantity


def test_review_creates_occurrences_from_reviewed_quantity_not_source_views() -> None:
    component = _component(
        quantity=GeneralQuantity(value=2, state="confirmed", dependency_refs=("human:quantity",))
    )
    request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1,
        base_review_revision=0,
        reviewer_name="tecnica",
        reason="Confirma dos laterales; el ancho sigue pendiente.",
        operations=(GeneralReviewOperation(
            kind="replace",
            source_component_ids=("panel-proposed",),
            result_component_ids=("panel-reviewed",),
            reason="Se corrige el rol sin deducir cantidad de las vistas.",
        ),),
        components=(component,),
    )

    reviewed = apply_general_review(
        run_id="run-1", proposal_id="proposal-1", proposal_revision=1,
        draft=_draft(), request=request,
    )

    assert [item.id for item in reviewed.occurrences] == ["panel-reviewed:1", "panel-reviewed:2"]
    assert reviewed.components[0].width.state == "unknown"
    assert reviewed.status == "reviewed_incomplete"


def test_review_with_unknown_quantity_creates_no_physical_occurrences() -> None:
    component = _component(quantity=GeneralQuantity(value=None, state="unknown"))
    request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1, base_review_revision=0, reviewer_name="tecnica",
        reason="Cantidad pendiente.",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel-proposed",), result_component_ids=("panel-reviewed",), reason="Mantiene desconocido."),),
        components=(component,),
    )

    reviewed = apply_general_review(
        run_id="run-1", proposal_id="proposal-1", proposal_revision=1,
        draft=_draft(), request=request,
    )

    assert reviewed.occurrences == ()


def test_review_rejects_client_fabricated_derived_measurement() -> None:
    component = _component(quantity=GeneralQuantity(value=None, state="unknown")).model_copy(
        update={"width": GeneralValue(value_mm=999, state="derived", dependency_refs=("dimension:made-up",))}
    )
    request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1, base_review_revision=0, reviewer_name="tecnica",
        reason="Intento inválido.",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel-proposed",), result_component_ids=("panel-reviewed",), reason="No válido."),),
        components=(component,),
    )

    with pytest.raises(ValueError, match="unconfirmed_value_must_match_proposal"):
        apply_general_review(run_id="run-1", proposal_id="proposal-1", proposal_revision=1, draft=_draft(), request=request)


def test_second_review_replaces_current_reviewed_ids_not_original_draft_ids() -> None:
    first_component = _component(quantity=GeneralQuantity(value=None, state="unknown"))
    first_request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1, base_review_revision=0, reviewer_name="tecnica", reason="Primera.",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel-proposed",), result_component_ids=("panel-reviewed",), reason="Primera."),),
        components=(first_component,),
    )
    first = apply_general_review(run_id="run-1", proposal_id="proposal-1", proposal_revision=1, draft=_draft(), request=first_request)
    second_component = first_component.model_copy(update={"id": "panel-v2", "replaces_component_ids": ("panel-reviewed",)})
    second_request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1, base_review_revision=1, reviewer_name="tecnica", reason="Segunda.",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel-reviewed",), result_component_ids=("panel-v2",), reason="Segunda."),),
        components=(second_component,),
    )

    second = apply_general_review(run_id="run-1", proposal_id="proposal-1", proposal_revision=1, draft=_draft(), request=second_request, previous_review=first)

    assert second.review_revision == 2
    assert second.components[0].id == "panel-v2"


def test_hypothesis_quantity_never_creates_physical_occurrences() -> None:
    component = _component(quantity=GeneralQuantity(value=4, state="hypothesis", dependency_refs=("premise:four",)))
    draft = _draft().model_copy(update={"components": (_draft().components[0].model_copy(update={"quantity": component.quantity}),)})
    request = GeneralFurnitureReviewRequest(
        base_proposal_revision=1, base_review_revision=0, reviewer_name="tecnica", reason="Aún hipótesis.",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel-proposed",), result_component_ids=("panel-reviewed",), reason="Conserva hipótesis."),),
        components=(component,),
    )

    reviewed = apply_general_review(run_id="run-1", proposal_id="proposal-1", proposal_revision=1, draft=draft, request=request)

    assert reviewed.occurrences == ()
