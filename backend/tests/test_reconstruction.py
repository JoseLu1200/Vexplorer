from __future__ import annotations

from pathlib import Path

from backend.app.contratos.modelos import HumanReview, ResolvedPiece, Result
from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.reconstruction import reconstruct_scene


def _result(*, reviewed: bool = True, incomplete: bool = False, cap_sides: bool = False) -> tuple[object, Result]:
    extraction = extract_drawing(Path("data/planos_demo/estanteria_montada.dxf"))
    scenarios = derive_decomposition_scenarios(extraction)
    selected = scenarios[1] if cap_sides else scenarios[0]
    dimensions = {
        "side_panel": (1164.0 if cap_sides else 1200.0, 300.0, 18.0, 2),
        "top_panel": (900.0 if cap_sides else 864.0, 300.0, 18.0, 1),
        "base_panel": (900.0 if cap_sides else 864.0, 300.0, 18.0, 1),
        "shelf": (864.0, 300.0, 18.0, 2),
    }
    pieces = []
    for proposal in selected.components:
        length, width, thickness, quantity = dimensions[proposal.role]
        if incomplete:
            thickness = None
        pieces.append(ResolvedPiece(
            id=f"piece-{proposal.role}", proposal_id=proposal.id, label=proposal.label,
            role=proposal.role, quantity=quantity, length_mm=length, width_mm=width,
            thickness_mm=thickness, material=None, finish=None,
            source_observation_ids=proposal.source_observation_ids,
            source_contour_ids=proposal.source_contour_ids, evidence_ids=proposal.evidence_ids,
            human_confirmation="fixture review" if reviewed else "pending",
            field_states={"length_mm": "calculated", "width_mm": "observed", "thickness_mm": "confirmed" if thickness else "unknown"},
        ))
    result = Result(
        run_id="run-scene", result_revision=3 if cap_sides else 2 if reviewed else 1,
        state="needs_review" if incomplete or not reviewed else "completed",
        scenarios=scenarios, pieces=tuple(pieces), created_at="2026-11-13T00:00:00Z",
        review=HumanReview(
            reviewer_name="reviewer", reason="selected mounting", timestamp="2026-11-13T00:00:00Z",
            selected_scenario_id=selected.id,
        ) if reviewed else None,
    )
    return extraction, result


def test_scene_is_unavailable_before_human_mounting_review():
    extraction, result = _result(reviewed=False)

    scene = reconstruct_scene(extraction, result)

    assert scene.state == "unavailable"
    assert scene.objects == ()
    assert "human_review_required" in scene.warnings


def test_between_sides_scene_places_six_physical_occurrences_from_observed_levels():
    extraction, result = _result()

    scene = reconstruct_scene(extraction, result)

    assert scene.state == "ready"
    assert scene.selected_scenario_id == "scenario-between-sides"
    assert len(scene.objects) == 6
    assert {item.role for item in scene.objects} == {"side_panel", "top_panel", "base_panel", "shelf"}
    sides = sorted((item for item in scene.objects if item.role == "side_panel"), key=lambda item: item.occurrence_index)
    assert [item.position_mm.x for item in sides] == [0.0, 882.0]
    assert all(item.dimensions_mm.model_dump() == {"x": 18.0, "y": 1200.0, "z": 300.0} for item in sides)
    shelves = sorted((item for item in scene.objects if item.role == "shelf"), key=lambda item: item.occurrence_index)
    assert [item.position_mm.y for item in shelves] == [400.0, 800.0]
    assert all(item.position_mm.x == 18.0 for item in shelves)
    assert all(item.dimensions_mm.model_dump() == {"x": 864.0, "y": 18.0, "z": 300.0} for item in shelves)
    assert all(item.bbox_mm.max.x - item.bbox_mm.min.x == item.dimensions_mm.x for item in scene.objects)
    assert sum(item.dimensions_mm.x * item.dimensions_mm.y * item.dimensions_mm.z for item in scene.objects) == 31_622_400
    assert scene.collision_status == "not_evaluated"


def test_incomplete_review_omits_solids_instead_of_inventing_thickness():
    extraction, result = _result(incomplete=True)

    scene = reconstruct_scene(extraction, result)

    assert scene.state == "incomplete"
    assert scene.objects == ()
    assert any(warning.startswith("incomplete_piece:") for warning in scene.warnings)


def test_scene_objects_trace_to_pieces_and_evidence_not_drawing_views():
    extraction, result = _result()

    scene = reconstruct_scene(extraction, result)

    piece_ids = {piece.id for piece in result.pieces}
    evidence_ids = {evidence.id for evidence in extraction.evidence}
    assert all(item.piece_id in piece_ids for item in scene.objects)
    assert all(set(item.evidence_ids) <= evidence_ids for item in scene.objects)
    assert all(item.occurrence_index >= 1 for item in scene.objects)
    assert not any(item.role == "back_panel" for item in scene.objects)


def test_cap_sides_review_changes_panel_positions_without_changing_observed_shelf_levels():
    extraction, result = _result(cap_sides=True)

    scene = reconstruct_scene(extraction, result)

    assert scene.state == "ready"
    assert scene.result_revision == 3
    assert scene.selected_scenario_id == "scenario-cap-sides"
    sides = sorted((item for item in scene.objects if item.role == "side_panel"), key=lambda item: item.occurrence_index)
    assert [(item.position_mm.x, item.position_mm.y) for item in sides] == [(0.0, 18.0), (882.0, 18.0)]
    assert all(item.dimensions_mm.y == 1164.0 for item in sides)
    top = next(item for item in scene.objects if item.role == "top_panel")
    base = next(item for item in scene.objects if item.role == "base_panel")
    assert (top.position_mm.x, top.position_mm.y, top.dimensions_mm.x) == (0.0, 1182.0, 900.0)
    assert (base.position_mm.x, base.position_mm.y, base.dimensions_mm.x) == (0.0, 0.0, 900.0)
    shelves = sorted((item for item in scene.objects if item.role == "shelf"), key=lambda item: item.occurrence_index)
    assert [item.position_mm.y for item in shelves] == [400.0, 800.0]


def test_scene_rejects_reviewed_base_length_inconsistent_with_mounting_envelope():
    extraction, result = _result()
    pieces = tuple(
        piece.model_copy(update={"length_mm": 850.0}) if piece.role == "base_panel" else piece
        for piece in result.pieces
    )

    scene = reconstruct_scene(extraction, result.model_copy(update={"pieces": pieces}))

    assert scene.state == "incomplete"
    assert scene.objects == ()
    assert "inconsistent_resolved_dimensions" in scene.warnings


def test_scene_rejects_shelf_thickness_or_depth_inconsistent_with_reviewed_panels():
    extraction, result = _result()
    pieces = tuple(
        piece.model_copy(update={"thickness_mm": 20.0, "width_mm": 310.0}) if piece.role == "shelf" else piece
        for piece in result.pieces
    )

    scene = reconstruct_scene(extraction, result.model_copy(update={"pieces": pieces}))

    assert scene.state == "incomplete"
    assert scene.objects == ()
    assert "inconsistent_panel_dimensions" in scene.warnings


def test_scene_rejects_duplicate_resolved_role_instead_of_overwriting_piece():
    extraction, result = _result()
    duplicate = next(piece for piece in result.pieces if piece.role == "top_panel").model_copy(
        update={"id": "piece-top-duplicate"}
    )

    scene = reconstruct_scene(
        extraction, result.model_copy(update={"pieces": result.pieces + (duplicate,)})
    )

    assert scene.state == "incomplete"
    assert scene.objects == ()
    assert "duplicate_resolved_role:top_panel" in scene.warnings
