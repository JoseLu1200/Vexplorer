from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contratos import modelos
from backend.app.contratos.modelos import (
    Bounds2D, DrawingContour, DrawingEntity, DrawingExtraction, DrawingView,
    Evidence, GeneralComponentReview, GeneralFurnitureReview, GeneralOccurrence,
    GeneralQuantity, GeneralTextValue, GeneralValue, Point2D,
)


def _box(x0: float, y0: float, x1: float, y1: float) -> tuple[Point2D, ...]:
    return (Point2D(x=x0, y=y0), Point2D(x=x1, y=y0), Point2D(x=x1, y=y1), Point2D(x=x0, y=y1))


def _extraction(offset2: float | None = None, *, metric: bool = True) -> DrawingExtraction:
    specs = [("front-1", "front", 0., 0., 20., 40.), ("top-1", "top", 0., 0., 20., 10.)]
    if offset2 is not None:
        specs += [("front-2", "front", offset2, 0., offset2 + 20., 40.), ("top-2", "top", offset2, 0., offset2 + 20., 10.)]
    entities = tuple(DrawingEntity(id=f"entity-{cid}", kind="LWPOLYLINE", layer="OBJECT", source_points=_box(x0, y0, x1, y1), points_mm=_box(x0, y0, x1, y1) if metric else None) for cid, _, x0, y0, x1, y1 in specs)
    contours = tuple(DrawingContour(id=cid, view_id=vid, source_entity_ids=(f"entity-{cid}",), points_source=_box(x0, y0, x1, y1), points_mm=_box(x0, y0, x1, y1) if metric else None, closed=True) for cid, vid, x0, y0, x1, y1 in specs)
    xmax = max(row[4] for row in specs)
    views = tuple(DrawingView(id=vid, label="UNKNOWN", entity_ids=tuple(item.id for item in entities if vid in item.id), bounds_source=Bounds2D(min_x=0, min_y=0, max_x=xmax, max_y=ymax), bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=xmax, max_y=ymax) if metric else None) for vid, ymax in (("front", 40), ("top", 10)))
    return DrawingExtraction(drawing_id="drawing", input_kind="general_furniture", status="ready", source_unit="mm" if metric else "unknown", unit_scale_to_mm=1 if metric else None, coordinate_unit="mm" if metric else "source", entities=entities, views=views, contours=contours, dimensions=(), evidence=tuple(Evidence(id=f"evidence-{item.id}", kind="geometry", source_entity_ids=item.source_entity_ids, description=item.id) for item in contours), observations=())


def _review(quantity: int = 1) -> GeneralFurnitureReview:
    component = GeneralComponentReview(id="panel", label="Panel", kind="panel", role="side", length=GeneralValue(value_mm=20, state="confirmed"), width=GeneralValue(value_mm=40, state="confirmed"), thickness=GeneralValue(value_mm=10, state="confirmed"), quantity=GeneralQuantity(value=quantity, state="confirmed"), material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"), replaces_component_ids=("proposal-panel",))
    return GeneralFurnitureReview(run_id="run", proposal_id="proposal", proposal_revision=2, review_revision=3, reviewer_name="reviewer", reason="reviewed", reviewed_at="2026-11-14T10:00:00Z", operations=(), components=(component,), occurrences=tuple(GeneralOccurrence(id=f"panel:{i}", component_id="panel", occurrence_index=i) for i in range(1, quantity + 1)), status="approved")


def _candidate(extraction: DrawingExtraction, review: GeneralFurnitureReview):
    from backend.app.general_furniture.assembly import build_assembly_context
    context = build_assembly_context(extraction, review)
    regions = {item.view_id: item.id for item in context.regions}
    frames = (
        modelos.GeneralAssemblyFrame(id="front-frame", region_id=regions["front"], view_id="front", horizontal_axis="+x", vertical_axis="+y", origin_corner="lower_left"),
        modelos.GeneralAssemblyFrame(id="top-frame", region_id=regions["top"], view_id="top", horizontal_axis="+x", vertical_axis="+z", origin_corner="lower_left"),
    )
    orientation = modelos.GeneralAssemblyOrientation(length_axis="+x", width_axis="+y", thickness_axis="+z")
    placements = tuple(modelos.GeneralAssemblyPlacementHypothesis(occurrence_id=item.id, occurrence_index=item.occurrence_index, component_id=item.component_id, orientation=orientation, projections=(modelos.GeneralAssemblyProjection(frame_id="front-frame", contour_id=f"front-{item.occurrence_index}", evidence_ids=(f"evidence-front-{item.occurrence_index}",)), modelos.GeneralAssemblyProjection(frame_id="top-frame", contour_id=f"top-{item.occurrence_index}", evidence_ids=(f"evidence-top-{item.occurrence_index}",)))) for item in (*review.occurrences, *review.scenario_occurrences))
    return modelos.GeneralAssemblyCandidate(run_id=review.run_id, proposal_revision=review.proposal_revision, review_revision=review.review_revision, assembly_revision=1, candidate_id="candidate", alternative_id="primary", frames=frames, placements=placements, sources=("drawing:drawing",))


def test_orientation_rejects_reflection() -> None:
    with pytest.raises(ValidationError, match="determinant"):
        modelos.GeneralAssemblyOrientation(length_axis="+x", width_axis="+y", thickness_axis="-z")


def test_context_requires_metric_geometry() -> None:
    from backend.app.general_furniture.assembly import build_assembly_context
    with pytest.raises(ValueError, match="assembly_metric_scale_required"):
        build_assembly_context(_extraction(metric=False), _review())


def test_context_abstains_from_unsupported_non_panel_components() -> None:
    from backend.app.general_furniture.assembly import build_assembly_context
    review = _review()
    hardware = review.components[0].model_copy(update={"kind": "hardware"})
    review = review.model_copy(update={"components": (hardware,)})
    with pytest.raises(ValueError, match="assembly_unsupported_component_kind"):
        build_assembly_context(_extraction(), review)


def test_machine_accepted_hypotheses_use_provisional_scenario_occurrences() -> None:
    from backend.app.general_furniture.assembly import build_assembly_context, validate_assembly
    review = _review()
    component = review.components[0].model_copy(update={
        "length": GeneralValue(value_mm=20, state="hypothesis", dependency_refs=("binding:l",)),
        "width": GeneralValue(value_mm=40, state="hypothesis", dependency_refs=("binding:w",)),
        "thickness": GeneralValue(value_mm=10, state="hypothesis", dependency_refs=("binding:t",)),
        "quantity": GeneralQuantity(value=1, state="hypothesis", dependency_refs=("premise:q",)),
        "source_contour_ids": ("front-1", "top-1"),
        "source_evidence_ids": ("evidence-front-1", "evidence-top-1"),
    })
    scenario = modelos.GeneralScenarioOccurrence(id="provisional:panel:1", component_id="panel", occurrence_index=1, scenario_id="scenario", quantity_target_ref="component:panel.quantity", check_ids=("quantity", "duplicate"), premise_refs=("premise:q",), source_refs=("contour:front-1",))
    review = review.model_copy(update={"components": (component,), "occurrences": (), "scenario_occurrences": (scenario,), "machine_field_reviews": ()})
    context = build_assembly_context(_extraction(), review)
    assert context.components[0].occurrence_ids == ("provisional:panel:1",)
    report = validate_assembly(_extraction(), review, _candidate(_extraction(), review))
    assert report.status == "accepted"
    assert report.scene.items[0].occurrence_status == "provisional"


def test_unbacked_numeric_dimension_hypothesis_still_abstains() -> None:
    from backend.app.general_furniture.assembly import build_assembly_context
    review = _review()
    component = review.components[0].model_copy(update={"length": GeneralValue(value_mm=20, state="hypothesis")})
    review = review.model_copy(update={"components": (component,)})
    with pytest.raises(ValueError, match="assembly_reviewed_dimensions_required"):
        build_assembly_context(_extraction(), review)


def test_valid_candidate_derives_world_aabb_min_and_scene() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(), _review()
    report = validate_assembly(extraction, review, _candidate(extraction, review))
    assert report.status == "accepted"
    assert report.issues == ()
    assert report.placements[0].position_mm.model_dump() == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert report.placements[0].size_mm.model_dump() == {"x": 20.0, "y": 40.0, "z": 10.0}
    assert report.global_bounds_mm.model_dump() == {"min": {"x": 0.0, "y": 0.0, "z": 0.0}, "max": {"x": 20.0, "y": 40.0, "z": 10.0}}
    assert report.scene.status == "mounted_hypothesis"
    assert report.scene.items[0].occurrence_id == "panel:1"


def test_validator_rejects_missing_occurrence_and_unknown_sources() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(20), _review(2)
    candidate = _candidate(extraction, review)
    bad_projection = candidate.placements[0].projections[0].model_copy(update={"contour_id": "missing", "evidence_ids": ("also-missing",)})
    bad_placement = candidate.placements[0].model_copy(update={"projections": (bad_projection, candidate.placements[0].projections[1])})
    report = validate_assembly(extraction, review, candidate.model_copy(update={"placements": (bad_placement,)}))
    assert report.status == "rejected"
    assert {"missing_occurrence", "unknown_contour", "unknown_evidence"} <= {item.code for item in report.issues}
    assert report.scene is None


def test_validator_rejects_dimensions_incompatible_under_rotation() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    rotated = modelos.GeneralAssemblyOrientation(length_axis="+y", width_axis="-x", thickness_axis="+z")
    placement = candidate.placements[0].model_copy(update={"orientation": rotated})
    report = validate_assembly(extraction, review, candidate.model_copy(update={"placements": (placement,)}))
    assert report.status == "rejected"
    assert "dimension_mismatch" in {item.code for item in report.issues}


@pytest.mark.parametrize(("offset", "status", "penetration"), ((20.0, "accepted", 0.0), (19.9999995, "accepted", 0.0), (19.0, "accepted", 1.0), (18.0, "rejected", 2.0)))
def test_contact_allowed_but_penetration_rejected(offset: float, status: str, penetration: float) -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(offset), _review(2)
    report = validate_assembly(extraction, review, _candidate(extraction, review))
    assert report.status == status
    assert report.max_penetration_mm == penetration
    assert ("aabb_penetration" in {item.code for item in report.issues}) == (status == "rejected")


def test_unverified_overlap_hypothesis_does_not_waive_aabb_penetration() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(18), _review(2)
    candidate = _candidate(extraction, review)
    explanation = modelos.GeneralAssemblyPenetrationHypothesis(
        occurrence_ids=("panel:1", "panel:2"), kind="projected_overlap_machining_unverified",
        source_refs=("contour:front-1", "contour:front-2"),
    )
    candidate = candidate.model_copy(update={"penetration_hypotheses": (explanation,)})
    report = validate_assembly(extraction, review, candidate)
    assert report.status == "rejected"
    assert "aabb_penetration_unresolved" in {item.code for item in report.issues}
    assert any(item.severity == "error" for item in report.issues)


def test_candidate_forbids_free_numeric_position() -> None:
    extraction, review = _extraction(), _review()
    payload = _candidate(extraction, review).model_dump(mode="json")
    payload["placements"][0]["position_mm"] = {"x": 1, "y": 2, "z": 3}
    with pytest.raises(ValidationError, match="Extra inputs"):
        modelos.GeneralAssemblyCandidate.model_validate(payload)


def test_shared_contour_requires_explicit_occlusion_ambiguity() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(20), _review(2)
    candidate = _candidate(extraction, review)
    first = candidate.placements[0]
    second = candidate.placements[1].model_copy(update={"projections": first.projections})
    report = validate_assembly(extraction, review, candidate.model_copy(update={"placements": (first, second)}))
    assert "shared_contour_identity" in {item.code for item in report.issues}


def test_distinct_contour_ids_cannot_reuse_one_source_entity_identity() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(20), _review(2)
    contours = tuple(item.model_copy(update={"source_entity_ids": ("entity-front-1",)}) if item.id == "front-2" else item for item in extraction.contours)
    evidence = tuple(item.model_copy(update={"source_entity_ids": ("entity-front-1",)}) if item.id == "evidence-front-2" else item for item in extraction.evidence)
    extraction = extraction.model_copy(update={"contours": contours, "evidence": evidence})
    report = validate_assembly(extraction, review, _candidate(extraction, review))
    assert "shared_evidence_identity" in {item.code for item in report.issues}


def test_candidate_rejects_per_occurrence_frame_for_same_region() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    first = candidate.frames[0]
    contradictory = first.model_copy(update={"id": "front-opposite", "horizontal_axis": "-x", "origin_corner": "lower_right"})
    with pytest.raises(ValidationError, match="one coherent assembly frame"):
        modelos.GeneralAssemblyCandidate.model_validate({**candidate.model_dump(mode="json"), "frames": [*candidate.model_dump(mode="json")["frames"], contradictory.model_dump(mode="json")]})


def test_non_rectangular_outline_reports_box_fit_residual() -> None:
    from backend.app.general_furniture.assembly import build_assembly_context, validate_assembly
    extraction, review = _extraction(), _review()
    triangle = (Point2D(x=0, y=0), Point2D(x=20, y=0), Point2D(x=0, y=40))
    contour = extraction.contours[0].model_copy(update={"points_source": triangle, "points_mm": triangle})
    extraction = extraction.model_copy(update={"contours": (contour, extraction.contours[1])})
    context = build_assembly_context(extraction, review)
    assert next(item for item in context.contours if item.id == "front-1").box_fit_residual_mm > 0
    report = validate_assembly(extraction, review, _candidate(extraction, review))
    assert "contour_box_fit_residual" in {item.code for item in report.issues}


def test_floating_point_rectangle_noise_is_not_a_shape_residual() -> None:
    from backend.app.general_furniture.assembly import build_assembly_context, validate_assembly
    extraction, review = _extraction(), _review()
    noisy = (Point2D(x=0, y=0), Point2D(x=20, y=0), Point2D(x=20, y=40.00000001), Point2D(x=0, y=40))
    contour = extraction.contours[0].model_copy(update={"points_source": noisy, "points_mm": noisy})
    extraction = extraction.model_copy(update={"contours": (contour, extraction.contours[1])})
    assert build_assembly_context(extraction, review).warnings == ()
    assert validate_assembly(extraction, review, _candidate(extraction, review)).status == "accepted"


def test_valid_alternatives_are_evaluated_without_first_pass_selection() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(), _review()
    first = _candidate(extraction, review)
    second = first.model_copy(update={"candidate_id": "candidate-2", "alternative_id": "alternative-2", "assembly_revision": 2})
    reports = tuple(validate_assembly(extraction, review, item) for item in (first, second))
    assert [item.status for item in reports] == ["accepted", "accepted"]
    assert [first.alternative_id, second.alternative_id] == ["primary", "alternative-2"]


def test_placed_scene_item_requires_complete_instance_transform() -> None:
    component = _review().components[0]
    with pytest.raises(ValidationError, match="complete instance transform"):
        modelos.GeneralSceneItem(
            id="scene:panel:1", component_id="panel", occurrence_ids=("panel:1",),
            occurrence_status="confirmed", length=component.length, width=component.width,
            thickness=component.thickness, position_mm=modelos.Point3D(x=0, y=0, z=0),
            status="placed_hypothesis",
        )


def test_assembly_state_preserves_multiple_accepted_alternatives() -> None:
    from backend.app.general_furniture.assembly import validate_assembly
    extraction, review = _extraction(), _review()
    candidates = (_candidate(extraction, review), _candidate(extraction, review).model_copy(update={"candidate_id": "candidate-2", "alternative_id": "alternative-2", "assembly_revision": 2}))
    attempts = tuple(modelos.GeneralAssemblyAttempt(run_id="run", proposal_revision=2, review_revision=3, assembly_revision=item.assembly_revision, attempt_index=index, candidate=item, report=validate_assembly(extraction, review, item), model="test-model", policy_version="test-policy", sources=("drawing:drawing",), trace=()) for index, item in enumerate(candidates, 1))
    state = modelos.GeneralAssemblyState(run_id="run", proposal_revision=2, review_revision=3, assembly_revision=2, status="ambiguous", current=attempts[-1], accepted_alternatives=attempts, ambiguous=True)
    assert [item.candidate.alternative_id for item in state.accepted_alternatives] == ["primary", "alternative-2"]
    with pytest.raises(ValidationError, match="ambiguous flag"):
        modelos.GeneralAssemblyState(run_id="run", proposal_revision=2, review_revision=3, assembly_revision=2, status="accepted", current=attempts[-1], accepted_alternatives=attempts, ambiguous=False)
