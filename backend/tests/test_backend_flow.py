from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.contratos.modelos import (
    Bounds2D,
    ComponentProposal,
    DecompositionScenario,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingObservation,
    DrawingView,
    Evidence,
    ObservedDimension,
    Point2D,
    ReviewDecision,
    ReviewRequest,
)
from backend.app.estimacion.service import estimate_result
from backend.app.historico.service import find_comparables
from backend.app.salida.service import export_csv, export_json
from backend.app.servicios.decomposition import derive_decomposition_scenarios, resolve_orthographic_dimensions
from backend.app.servicios.repository import DemoRepository


def _extraction() -> DrawingExtraction:
    points = (
        Point2D(x=0, y=0),
        Point2D(x=900, y=0),
        Point2D(x=900, y=1800),
        Point2D(x=0, y=1800),
    )
    return DrawingExtraction(
        drawing_id="drawing-demo",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1,
        coordinate_unit="mm",
        entities=(DrawingEntity(id="entity-front", kind="LWPOLYLINE", layer="VIEW_GEOMETRY", source_points=points, points_mm=points),),
        views=(DrawingView(id="view-front", label="FRONT", entity_ids=("entity-front",), bounds_source=Bounds2D(min_x=0, min_y=0, max_x=900, max_y=1800), bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=900, max_y=1800)),),
        contours=(DrawingContour(id="contour-front", view_id="view-front", source_entity_ids=("entity-front",), points_source=points, points_mm=points, closed=True),),
        dimensions=(ObservedDimension(id="dim-width", kind="overall", value_mm=900, source_entity_ids=("entity-front",), evidence_ids=("evidence-front",), origin="observed"),),
        evidence=(Evidence(id="evidence-front", kind="geometry", source_entity_ids=("entity-front",), description="Contorno frontal observado"),),
        observations=(DrawingObservation(id="observation-front", view_id="view-front", contour_ids=("contour-front",), dimension_ids=("dim-width",)),),
        warnings=("mounting_ambiguous",),
        synthetic=True,
    )


def _scenario() -> DecompositionScenario:
    return DecompositionScenario(
        id="scenario-basic",
        title="Descomposición rectangular por confirmar",
        components=(
            ComponentProposal(
                id="proposal-panel",
                label="Panel rectangular",
                role="unknown",
                quantity=None,
                length_mm=900,
                width_mm=None,
                thickness_mm=None,
                source_observation_ids=("observation-front",),
                source_contour_ids=("contour-front",),
                evidence_ids=("evidence-front",),
                assumptions=("El contorno puede corresponder a un panel; montaje no observado.",),
            ),
        ),
        assumptions=("La cantidad y el espesor requieren confirmación humana.",),
    )


def test_review_is_versioned_and_preserves_immutable_extraction(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "demo.sqlite3")
    repository.create_run("run-1", "geometry_only", _extraction(), (_scenario(),))

    original_ledger = repository.get_extraction("run-1").model_dump_json()
    initial = repository.get_result("run-1", 1)
    reviewed = repository.review(
        "run-1",
        ReviewRequest(
            base_result_revision=1,
            reviewer_name="Técnica demo",
            decisions=(
                ReviewDecision(
                    proposal_id="proposal-panel",
                    action="confirm",
                    role="shelf",
                    quantity=2,
                    length_mm=900,
                    width_mm=320,
                    thickness_mm=19,
                    material="tablero sintético",
                    finish="melamina sintética",
                    notes="Montaje y espesor confirmados para la demo.",
                ),
            ),
        ),
    )

    assert initial.result_revision == 1 and initial.state == "needs_review"
    assert reviewed.result_revision == 2 and reviewed.state == "completed"
    assert reviewed.pieces[0].quantity == 2
    assert repository.get_result("run-1", 1) == initial
    assert repository.get_run("run-1").state == "needs_review"
    assert repository.get_extraction("run-1").model_dump_json() == original_ledger


def test_comparables_and_estimate_reference_exact_review_without_double_counting(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "demo.sqlite3")
    repository.create_run("run-1", "geometry_only", _extraction(), (_scenario(),))
    reviewed = repository.review(
        "run-1",
        ReviewRequest(
            base_result_revision=1,
            reviewer_name="Técnica demo",
            decisions=(ReviewDecision(proposal_id="proposal-panel", action="confirm", role="shelf", quantity=2, length_mm=900, width_mm=320, thickness_mm=19, material="tablero sintético", finish="melamina sintética", notes="Confirmado"),),
        ),
    )

    comparables = find_comparables(reviewed, limit=2)
    estimate = estimate_result(reviewed, comparables)

    assert comparables and all(item.synthetic for item in comparables)
    assert "900×320" in comparables[0].differences[0]
    assert estimate.result_revision == 2
    assert estimate.currency == "EUR"
    assert estimate.total == round(sum(item.amount for item in estimate.concepts), 2)
    assert len({item.id for item in estimate.concepts}) == len(estimate.concepts)
    assert any(item.cost_type == "fixed" and item.factor == 1 for item in estimate.concepts)
    assert estimate.hours is None
    repository.save_estimate("run-1", estimate)
    assert repository.get_estimate("run-1", 2) == estimate


def test_exports_preserve_revision_and_protect_csv_formulas(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "demo.sqlite3")
    repository.create_run("run-1", "geometry_only", _extraction(), (_scenario(),))
    reviewed = repository.review(
        "run-1",
        ReviewRequest(
            base_result_revision=1,
            reviewer_name="Técnica demo",
            decisions=(ReviewDecision(proposal_id="proposal-panel", action="confirm", role="shelf", quantity=1, length_mm=900, width_mm=320, thickness_mm=19, material="=CMD", finish="+SUM(A1:A2)", notes="Confirmado"),),
        ),
    )

    json_payload = json.loads(export_json(reviewed))
    csv_payload = export_csv(reviewed)

    assert json_payload["result_revision"] == 2
    assert json_payload["pieces"][0]["material"] == "=CMD"
    assert "'=CMD" in csv_payload
    assert "'+SUM(A1:A2)" in csv_payload


def test_family_rules_propose_two_mountings_without_counting_views_as_parts(tmp_path: Path) -> None:
    from backend.app.geometria import extract_drawing

    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)

    assert len(scenarios) == 2
    assert scenarios[0].id in scenarios[1].incompatible_with
    for scenario in scenarios:
        by_role = {item.role: item for item in scenario.components}
        assert by_role["side_panel"].quantity == 2
        assert by_role["top_panel"].quantity == 1
        assert by_role["base_panel"].quantity == 1
        assert by_role["shelf"].quantity == 2
        assert all(item.thickness_mm is None for item in scenario.components)
        assert sum(item.quantity or 0 for item in scenario.components) != len(extraction.views)

    repository = DemoRepository(tmp_path / "demo.sqlite3")
    repository.create_run("run-family", "geometry_only", extraction, scenarios)
    reviewed = repository.review(
        "run-family",
        ReviewRequest(
            base_result_revision=1,
            reviewer_name="Técnica demo",
            scenario_id="scenario-between-sides",
            confirmed_thickness_mm=18,
            material="tablero sintético",
            finish="melamina sintética",
            notes="Montaje entre laterales confirmado por técnico",
        ),
    )

    assert reviewed.state == "completed"
    assert {piece.role: piece.quantity for piece in reviewed.pieces}["shelf"] == 2
    assert {piece.role: piece.length_mm for piece in reviewed.pieces}["shelf"] == 864


def test_orthographic_dimensions_preserve_axes_and_reject_disagreement() -> None:
    assert resolve_orthographic_dimensions((400, 1200), (400, 600), (600, 1200)) == (400, 1200, 600)
    assert resolve_orthographic_dimensions((400, 1200), (401, 600), (600, 1200)) is None


def test_manual_review_cannot_combine_incompatible_scenarios(tmp_path: Path) -> None:
    from backend.app.geometria import extract_drawing

    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)
    repository = DemoRepository(tmp_path / "demo.sqlite3")
    repository.create_run("run-exclusive", "geometry_only", extraction, scenarios)
    decisions = tuple(
        ReviewDecision(proposal_id=proposal.id, action="confirm", role=proposal.role, quantity=proposal.quantity or 1, length_mm=proposal.length_mm or proposal.length_basis_mm, width_mm=proposal.width_mm, thickness_mm=18, material="tablero sintético", finish="melamina sintética", notes="Confirmación manual")
        for scenario in scenarios for proposal in scenario.components
    )

    with pytest.raises(ValueError, match="incompatible_scenario_selection"):
        repository.review("run-exclusive", ReviewRequest(base_result_revision=1, reviewer_name="Revisora", decisions=decisions))
    assert repository.get_result("run-exclusive").result_revision == 1


def test_estimate_rejects_result_still_needing_review(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "demo.sqlite3")
    repository.create_run("run-partial", "geometry_only", _extraction(), (_scenario(),))
    partial = repository.review(
        "run-partial",
        ReviewRequest(base_result_revision=1, reviewer_name="Revisora", decisions=(ReviewDecision(proposal_id="proposal-panel", action="confirm", role="shelf", quantity=1, length_mm=900, width_mm=320, thickness_mm=19, material="tablero sintético", finish="melamina sintética", notes="Solo una parte"),)),
    ).model_copy(update={"state": "needs_review"})

    with pytest.raises(ValueError, match="result_needs_review"):
        estimate_result(partial, find_comparables(partial))
