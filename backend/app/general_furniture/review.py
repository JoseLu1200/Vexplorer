from __future__ import annotations

from datetime import datetime, timezone

from backend.app.contratos.modelos import (
    GeneralFurnitureReview,
    GeneralFurnitureReviewRequest,
    GeneralFurnitureDraft,
    GeneralOccurrence,
)


def apply_general_review(
    *,
    run_id: str,
    proposal_id: str,
    proposal_revision: int,
    draft: GeneralFurnitureDraft,
    request: GeneralFurnitureReviewRequest,
    previous_review: GeneralFurnitureReview | None = None,
) -> GeneralFurnitureReview:
    if request.base_proposal_revision != proposal_revision:
        raise ValueError("proposal_revision_conflict")
    if draft.proposal_id != proposal_id:
        raise ValueError("review_proposal_mismatch")
    if request.base_review_revision == 0:
        if previous_review is not None:
            raise ValueError("review_revision_conflict")
        base_components = draft.components
    else:
        if (
            previous_review is None
            or previous_review.review_revision != request.base_review_revision
        ):
            raise ValueError("review_revision_conflict")
        base_components = previous_review.components
    draft_by_id = {item.id: item for item in base_components}
    source_sequence = [
        item
        for operation in request.operations
        for item in operation.source_component_ids
    ]
    if len(source_sequence) != len(set(source_sequence)) or set(source_sequence) != set(
        draft_by_id
    ):
        raise ValueError("review_operations_must_cover_each_source_once")
    for component in request.components:
        sources = [draft_by_id[item] for item in component.replaces_component_ids]
        allowed_refs = {
            "view": {value for item in sources for value in item.source_view_ids},
            "observation": {
                value for item in sources for value in item.source_observation_ids
            },
            "contour": {value for item in sources for value in item.source_contour_ids},
            "evidence": {
                value for item in sources for value in item.source_evidence_ids
            },
            "dimension": {
                value for item in sources for value in item.source_dimension_ids
            },
            "document": {
                value for item in sources for value in item.source_document_refs
            },
        }
        supplied = {
            "view": set(component.source_view_ids),
            "observation": set(component.source_observation_ids),
            "contour": set(component.source_contour_ids),
            "evidence": set(component.source_evidence_ids),
            "dimension": set(component.source_dimension_ids),
            "document": set(component.source_document_refs),
        }
        if any(not supplied[key] <= allowed_refs[key] for key in supplied):
            raise ValueError("review_reference_outside_proposal")
        for name in ("length", "width", "thickness"):
            value = getattr(component, name)
            if (
                not set(value.evidence_ids) <= allowed_refs["evidence"]
                or not set(value.dimension_ids) <= allowed_refs["dimension"]
            ):
                raise ValueError("review_field_reference_outside_proposal")
            if value.state == "confirmed":
                if not any(ref.startswith("human:") for ref in value.dependency_refs):
                    raise ValueError("confirmed_value_requires_human_provenance")
            elif value.state not in ("unknown", "conflict"):
                originals = [getattr(item, name) for item in sources]
                if value not in originals:
                    raise ValueError("unconfirmed_value_must_match_proposal")
        if component.quantity.state == "confirmed":
            if not any(
                ref.startswith("human:") for ref in component.quantity.dependency_refs
            ):
                raise ValueError("confirmed_quantity_requires_human_provenance")
        elif component.quantity.state not in (
            "unknown",
            "conflict",
        ) and component.quantity not in [item.quantity for item in sources]:
            raise ValueError("unconfirmed_quantity_must_match_proposal")
        if not set(component.quantity.evidence_ids) <= allowed_refs["evidence"]:
            raise ValueError("review_field_reference_outside_proposal")
        for name in ("material", "finish"):
            value = getattr(component, name)
            if not set(value.evidence_ids) <= allowed_refs["evidence"]:
                raise ValueError("review_field_reference_outside_proposal")
            if value.state == "confirmed":
                if not any(ref.startswith("human:") for ref in value.dependency_refs):
                    raise ValueError("confirmed_text_requires_human_provenance")
            elif value.state not in ("unknown", "conflict"):
                originals = [
                    getattr(item, name) for item in sources if hasattr(item, name)
                ]
                if not originals or value not in originals:
                    raise ValueError("unconfirmed_text_must_match_previous_review")
    if sum(component.quantity.value or 0 for component in request.components) > 5000:
        raise ValueError("general_occurrence_budget_exceeded")
    if request.furniture_quantity.state == "confirmed" and not any(
        ref.startswith("human:") for ref in request.furniture_quantity.dependency_refs
    ):
        raise ValueError("confirmed_furniture_quantity_requires_human_provenance")
    occurrences = tuple(
        GeneralOccurrence(
            id=f"{component.id}:{index}",
            component_id=component.id,
            occurrence_index=index,
        )
        for component in request.components
        if component.quantity.value is not None
        and component.quantity.state in ("observed", "derived", "confirmed")
        for index in range(1, component.quantity.value + 1)
    )
    incomplete_states = {"unknown", "conflict", "hypothesis"}
    incomplete = any(
        value.state in incomplete_states
        for component in request.components
        for value in (
            component.length,
            component.width,
            component.thickness,
            component.quantity,
            component.material,
            component.finish,
        )
    ) or any(component.unknown_fields for component in request.components)
    return GeneralFurnitureReview(
        run_id=run_id,
        proposal_id=proposal_id,
        proposal_revision=proposal_revision,
        review_revision=request.base_review_revision + 1,
        reviewer_name=request.reviewer_name,
        reason=request.reason,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        operations=request.operations,
        components=request.components,
        occurrences=occurrences,
        furniture_quantity=request.furniture_quantity,
        currency=request.currency,
        required_cost_scope=request.required_cost_scope,
        required_hours_scope=request.required_hours_scope,
        status="reviewed_incomplete" if incomplete else "approved",
    )
