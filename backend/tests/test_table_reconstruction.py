from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.contratos.modelos import HumanReview, Result, TableReviewDecision
from backend.app.geometria.extraction import extract_drawing
from backend.app.geometria.mounted_table import (
    analyze_mounted_table,
    catalog_table_programs,
    evaluate_table_program,
)


def _case():
    extraction = extract_drawing(
        Path("data/planos_demo/mesa_demo_001.dxf"),
        input_kind="mounted_orthographic_views",
    )
    analysis = analyze_mounted_table(extraction)
    program = catalog_table_programs(analysis)[0]
    decisions = (
        TableReviewDecision(target_kind="program", target_id=program.id, action="accept", reason="Selecciona topología"),
        *(TableReviewDecision(target_kind="component", target_id=item.id, action="accept", reason="Acepta componente") for item in program.components),
        *(TableReviewDecision(target_kind="premise", target_id=item.id, action="accept", reason="Acepta premisa") for item in program.premises),
    )
    evaluated = evaluate_table_program(analysis, program, decisions=decisions)
    result = Result(
        run_id="run-table", result_revision=2, state="completed",
        scenarios=(), pieces=(), created_at="2026-11-14T00:00:00Z",
        review=HumanReview(
            reviewer_name="Operador local", reason="Revisión de mesa",
            timestamp="2026-11-14T00:00:00Z", selected_scenario_id=None,
        ),
        input_semantics="mounted_orthographic_views", table_analysis=analysis,
        table_programs=(program,), selected_table_program_id=program.id,
        evaluated_table_program=evaluated,
    )
    return extraction, analysis, program, evaluated, result


def _service():
    try:
        from backend.app.servicios.table_reconstruction import (
            derive_table_drawing_plan,
            reconstruct_table_scene,
        )
    except ImportError as exc:  # pragma: no cover - exercised only in the RED step
        pytest.fail(f"table reconstruction service is missing: {exc}")
    return derive_table_drawing_plan, reconstruct_table_scene


def test_reviewed_table_produces_traceable_sheets_and_three_physical_solids() -> None:
    extraction, analysis, program, evaluated, result = _case()
    derive_table_drawing_plan, reconstruct_table_scene = _service()

    plan = derive_table_drawing_plan(
        extraction, analysis, evaluated, result_revision=2,
    )
    scene = reconstruct_table_scene(extraction, analysis, result)

    assert plan.result_revision == 2
    assert plan.program_hash == evaluated.program_hash
    assert [item.kind for item in plan.sheets] == [
        "general", "component", "component", "cut_sheet",
    ]
    general = plan.sheets[0]
    occurrence_projections = [
        item for item in general.primitives
        if item.kind == "rect" and item.id.startswith("general-occurrence-")
    ]
    assert len(occurrence_projections) == 3 * len(evaluated.occurrences)
    assert {
        item.text for item in general.primitives
        if item.kind == "text" and item.id.startswith("general-view-label-")
    } == {"FRONT", "TOP", "SIDE"}
    component_sheets = [item for item in plan.sheets if item.kind == "component"]
    assert all(sum(item.kind == "dimension" for item in sheet.primitives) == 3 for sheet in component_sheets)
    assert {
        item.component_id: next(
            primitive.text for primitive in item.primitives
            if primitive.kind == "text" and (primitive.text or "").startswith("QTY=")
        )
        for item in component_sheets
    } == {
        "component-tabletop": "QTY=1",
        "component-side-support": "QTY=2",
    }
    cut_sheet = next(item for item in plan.sheets if item.kind == "cut_sheet")
    assert sum(item.kind == "rect" for item in cut_sheet.primitives) == 3
    assert sum(item.kind == "dimension" for item in cut_sheet.primitives) == 6
    assert sum(item.kind == "text" and "T=" in (item.text or "") for item in cut_sheet.primitives) == 3
    actual_measure_refs = {f"measure:{item.id}" for item in analysis.measures}
    general_measure_refs = {
        ref for primitive in general.primitives for ref in primitive.dependency_refs
        if ref.startswith("measure:")
    }
    assert general_measure_refs <= actual_measure_refs
    assert {
        f"measure:{next(item.id for item in analysis.measures if item.semantic == semantic)}"
        for semantic in ("overall_width", "overall_height", "overall_depth")
    } <= general_measure_refs
    assert scene.state == "ready"
    assert len(scene.objects) == 3
    assert [item.role for item in scene.objects] == ["tabletop", "side_support", "side_support"]
    top = scene.objects[0]
    assert top.position_mm.model_dump() == {"x": 0.0, "y": 720.0, "z": 0.0}
    assert top.dimensions_mm.model_dump() == {"x": 1200.0, "y": 30.0, "z": 700.0}
    assert top.bbox_mm.max.model_dump() == {"x": 1200.0, "y": 750.0, "z": 700.0}
    assert all(item.evidence_ids for item in scene.objects)


def test_unreviewed_program_never_creates_table_solids() -> None:
    extraction, analysis, program, _, result = _case()
    _, reconstruct_table_scene = _service()
    proposed = evaluate_table_program(analysis, program)
    unreviewed = result.model_copy(update={
        "result_revision": 1,
        "state": "needs_review",
        "review": None,
        "selected_table_program_id": None,
        "evaluated_table_program": proposed,
    })

    scene = reconstruct_table_scene(extraction, analysis, unreviewed)

    assert scene.state == "incomplete"
    assert scene.objects == ()
    assert "table_review_required" in scene.warnings

