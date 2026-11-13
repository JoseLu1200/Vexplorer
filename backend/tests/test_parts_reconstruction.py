from __future__ import annotations

from pathlib import Path

from backend.app.contratos.modelos import ReviewRequest
from backend.app.geometria.extraction import extract_drawing
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
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
