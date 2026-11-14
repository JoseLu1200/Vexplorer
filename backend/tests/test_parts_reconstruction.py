from __future__ import annotations

from pathlib import Path

from backend.app.contratos.modelos import ReviewDecision, ReviewRequest
from backend.app.geometria.extraction import extract_drawing
from backend.app.geometria.parts import (
    derive_assembly_candidates,
    extract_separated_parts,
    recompute_reviewed_assembly_candidate,
)
from backend.app.servicios.reconstruction import reconstruct_parts_scene
from backend.app.servicios.repository import DemoRepository


def _run(tmp_path: Path, fixture: str = "piezas_completo.dxf"):
    extraction = extract_drawing(
        Path("data/planos_demo") / fixture, input_kind="separated_part_views",
    )
    parts = extract_separated_parts(extraction)
    candidates = derive_assembly_candidates(parts)
    candidate = next(
        item for item in candidates
        if item.layout == "between_sides"
        and any(use.part_observation_id == "part-observation-k1" and use.role == "side_panel" for use in item.uses)
        and any(use.part_observation_id == "part-observation-k2" and use.role == "top_panel" for use in item.uses)
    )
    repository = DemoRepository(tmp_path / "parts-scene.sqlite3")
    repository.create_run(
        "run-parts-scene", "geometry_only", extraction, (),
        part_analysis=parts, assembly_candidates=candidates,
    )
    return extraction, parts, candidate, repository


def test_parts_scene_is_unavailable_before_candidate_review(tmp_path: Path) -> None:
    extraction, parts, _candidate, repository = _run(tmp_path)

    scene = reconstruct_parts_scene(extraction, parts, repository.get_result("run-parts-scene"))

    assert scene.state == "unavailable"
    assert scene.objects == ()
    assert "assembly_review_required" in scene.warnings


def test_reviewed_parts_candidate_creates_six_traceable_schematic_occurrences(tmp_path: Path) -> None:
    extraction, parts, candidate, repository = _run(tmp_path)
    result = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id, notes="Selecciona hipótesis dimensional",
        ),
    )

    scene = reconstruct_parts_scene(extraction, parts, result)

    assert result.state == "completed"
    assert scene.state == "ready"
    assert len(scene.objects) == 6
    assert {item.role for item in scene.objects} == {"side_panel", "top_panel", "base_panel", "shelf"}
    assert all(item.part_observation_id in {part.id for part in parts.observations} for item in scene.objects)
    assert all(item.bbox_mm.max.x - item.bbox_mm.min.x == item.dimensions_mm.x for item in scene.objects)
    assert all(item.bbox_mm.max.y - item.bbox_mm.min.y == item.dimensions_mm.y for item in scene.objects)
    assert all(item.bbox_mm.max.z - item.bbox_mm.min.z == item.dimensions_mm.z for item in scene.objects)
    sides = sorted((item for item in scene.objects if item.role == "side_panel"), key=lambda item: item.occurrence_index)
    assert [(item.position_mm.x, item.dimensions_mm.y) for item in sides] == [(0.0, 1200.0), (882.0, 1200.0)]
    shelves = sorted((item for item in scene.objects if item.role == "shelf"), key=lambda item: item.occurrence_index)
    assert len({item.position_mm.y for item in shelves}) == 2
    assert all("schematic evenly spaced" in item.placement_basis for item in shelves)
    assert any("Shelf heights are schematic" in assumption for assumption in scene.assumptions)
    assert scene.collision_status == "not_evaluated"


def test_missing_observed_thickness_keeps_parts_scene_without_solids(tmp_path: Path) -> None:
    extraction = extract_drawing(
        Path("data/planos_demo/piezas_espesor_desconocido.dxf"),
        input_kind="separated_part_views",
    )
    parts = extract_separated_parts(extraction)
    candidates = derive_assembly_candidates(parts)
    candidate = candidates[0]
    repository = DemoRepository(tmp_path / "parts-incomplete.sqlite3")
    repository.create_run(
        "run-parts-incomplete", "geometry_only", extraction, (),
        part_analysis=parts, assembly_candidates=candidates,
    )
    result = repository.review(
        "run-parts-incomplete",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id, notes="Revisión conserva el espesor ausente",
        ),
    )

    scene = reconstruct_parts_scene(extraction, parts, result)

    assert result.state == "needs_review"
    assert scene.state == "incomplete"
    assert scene.objects == ()
    assert any(warning.startswith("incomplete_piece:") for warning in scene.warnings)


def test_observed_thickness_changes_panel_sizes_without_changing_outer_width(tmp_path: Path) -> None:
    extraction, parts, candidate, repository = _run(tmp_path, "piezas_espesor_36.dxf")
    result = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id, notes="Selecciona control de espesor observado",
        ),
    )

    scene = reconstruct_parts_scene(extraction, parts, result)

    assert scene.state == "ready"
    sides = sorted((item for item in scene.objects if item.role == "side_panel"), key=lambda item: item.occurrence_index)
    assert [item.position_mm.x for item in sides] == [0.0, 864.0]
    assert all(item.dimensions_mm.x == 36.0 for item in sides)
    top = next(item for item in scene.objects if item.role == "top_panel")
    assert top.dimensions_mm.x == 828.0
    assert max(item.bbox_mm.max.x for item in scene.objects) == 900.0


def test_human_confirmed_quantity_creates_occurrences_missing_from_original_candidate(tmp_path: Path) -> None:
    extraction, parts, candidate, repository = _run(tmp_path, "piezas_qty_desconocida.dxf")
    unknown_use = next(
        use for use in candidate.uses
        if use.part_observation_id == "part-observation-k3" and use.role == "shelf"
    )
    revision_two = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id, notes="Conserva cantidad K3 desconocida",
        ),
    )
    assert revision_two.state == "needs_review"
    assert unknown_use.occurrence_indices == ()

    revision_three = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=2, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id,
            decisions=(ReviewDecision(
                proposal_id=unknown_use.id, action="confirm", role="shelf", quantity=2,
                length_mm=864, width_mm=300, thickness_mm=18,
                notes="Confirma dos ocurrencias físicas K3",
            ),),
            notes="Completa cantidad y medidas mediante revisión humana",
        ),
    )

    scene = reconstruct_parts_scene(extraction, parts, revision_three)

    assert revision_three.state == "completed"
    assert scene.state == "ready"
    assert len(scene.objects) == 6
    confirmed_piece = next(piece for piece in revision_three.pieces if piece.proposal_id == unknown_use.id)
    assert confirmed_piece.field_states["quantity"] == "confirmed"
    occurrences = [item for item in scene.objects if item.piece_id == confirmed_piece.id]
    assert [item.occurrence_index for item in occurrences] == [1, 2]
    assert all(item.evidence_ids == confirmed_piece.evidence_ids for item in occurrences)


def test_confirming_known_quantities_preserves_disjoint_source_occurrence_indices(tmp_path: Path) -> None:
    extraction, parts, candidate, repository = _run(tmp_path)
    top_use = next(use for use in candidate.uses if use.role == "top_panel")
    base_use = next(use for use in candidate.uses if use.role == "base_panel")
    result = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id,
            decisions=tuple(
                ReviewDecision(
                    proposal_id=use.id, action="confirm", role=use.role, quantity=1,
                    length_mm=864, width_mm=300, thickness_mm=18,
                    notes="Confirma allocation existente sin renumerarla",
                )
                for use in (top_use, base_use)
            ),
            notes="Conserva índices de ocurrencia de la fuente",
        ),
    )

    scene = reconstruct_parts_scene(extraction, parts, result)

    assert scene.state == "ready"
    top_object = next(item for item in scene.objects if item.proposal_id == top_use.id)
    base_object = next(item for item in scene.objects if item.proposal_id == base_use.id)
    assert top_object.occurrence_index == 1
    assert base_object.occurrence_index == 2
    assert top_object.part_observation_id == base_object.part_observation_id


def test_human_confirmed_thickness_recomputes_candidate_without_mutating_observation(tmp_path: Path) -> None:
    extraction, parts, candidate, repository = _run(tmp_path, "piezas_espesor_desconocido.dxf")
    shelf_use = next(
        use for use in candidate.uses
        if use.part_observation_id == "part-observation-k3" and use.role == "shelf"
    )
    revision_two = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id, notes="Conserva espesor K3 desconocido",
        ),
    )
    revision_three = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=2, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id,
            decisions=(ReviewDecision(
                proposal_id=shelf_use.id, action="confirm", role="shelf",
                thickness_mm=18, notes="Confirma espesor K3",
            ),),
            notes="Completa espesor mediante revisión humana",
        ),
    )

    effective = recompute_reviewed_assembly_candidate(
        candidate, parts, revision_three.pieces, result_revision=3,
    )

    raw_k3 = next(item for item in parts.observations if item.id == "part-observation-k3")
    assert raw_k3.dimensions.thickness.value_mm is None
    assert next(item for item in candidate.constraints if item.dimension == "thickness").status == "unknown"
    assert all(item.status == "pass" for item in effective.constraints)
    assert {item.axis: item.value_mm for item in effective.derived_dimensions} == {
        "width": 900.0, "height": 1200.0, "depth": 300.0,
    }
    assert "human_confirmed_operands_used" in effective.assumptions
    assert any(ref.startswith("review:3:piece:") for item in effective.constraints for ref in item.operand_refs)

    completed = revision_three.model_copy(update={"state": "completed"})
    scene = reconstruct_parts_scene(extraction, parts, completed)
    assert scene.state == "ready"
    assert len(scene.objects) == 6


def test_cap_sides_review_exposes_complete_formula_operands_and_reconstructs(tmp_path: Path) -> None:
    extraction, parts, candidate, repository = _run(tmp_path)
    reviewed = repository.review(
        "run-parts-scene",
        ReviewRequest(
            base_result_revision=1, reviewer_name="Operador local",
            assembly_candidate_id=candidate.id, notes="Base para control CAP",
        ),
    )
    cap_candidate = candidate.model_copy(update={"id": "assembly-cap-sides-audit", "layout": "cap_sides"})
    cap_pieces = tuple(
        piece.model_copy(update={
            "length_mm": 1164.0 if piece.role == "side_panel" else 900.0 if piece.role in {"top_panel", "base_panel"} else 864.0,
            "field_states": {**piece.field_states, "length_mm": "confirmed"},
        })
        for piece in reviewed.pieces
    )
    assert reviewed.review is not None
    cap_result = reviewed.model_copy(update={
        "state": "completed", "pieces": cap_pieces,
        "assembly_candidates": (cap_candidate,),
        "selected_assembly_candidate_id": cap_candidate.id,
        "review": reviewed.review.model_copy(update={"selected_assembly_candidate_id": cap_candidate.id}),
    })

    effective = recompute_reviewed_assembly_candidate(
        cap_candidate, parts, cap_pieces, result_revision=cap_result.result_revision,
    )
    horizontal = next(item for item in effective.constraints if item.kind == "role_compatibility")

    assert horizontal.status == "pass"
    assert horizontal.operation == "compatibility"
    assert horizontal.result_mm == 864.0
    assert len(horizontal.operand_refs) == 5
    assert sum(ref.endswith(".thickness_mm") for ref in horizontal.operand_refs) == 2
    assert {item.axis: item.value_mm for item in effective.derived_dimensions} == {
        "width": 900.0, "height": 1200.0, "depth": 300.0,
    }

    scene = reconstruct_parts_scene(extraction, parts, cap_result)
    assert scene.state == "ready"
    assert len(scene.objects) == 6
    sides = [item for item in scene.objects if item.role == "side_panel"]
    assert all((item.position_mm.y, item.dimensions_mm.y) == (18.0, 1164.0) for item in sides)
    top = next(item for item in scene.objects if item.role == "top_panel")
    shelf = next(item for item in scene.objects if item.role == "shelf")
    assert top.dimensions_mm.x == 900.0
    assert shelf.dimensions_mm.x == 864.0
