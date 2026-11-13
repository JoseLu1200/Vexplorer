from __future__ import annotations

from pathlib import Path

from backend.app.contratos.modelos import AssemblyCandidate, AssemblyConstraint, AssemblyPartUse, DerivedAssemblyDimension, DrawingExtraction, ObservedPartDimension, ObservedQuantity, PartDimensions, PartViewReference, Point2D, ReviewRequest, SeparatedPartObservation, SeparatedPartsExtraction
from backend.app.historico.service import _assembly_dimensions
from backend.app.servicios.repository import DemoRepository
from backend.app.servicios.explanations import explain_result
from backend.tests.test_backend_contract import _unknown_extraction


def _parts_payload() -> tuple[DrawingExtraction, SeparatedPartsExtraction, AssemblyCandidate]:
    extraction = _unknown_extraction().model_copy(update={"input_kind": "separated_part_views"})
    unknown = ObservedPartDimension(value_mm=None, state="unknown")
    observation = SeparatedPartObservation(id="part-P01", part_key="P01", association_basis="explicit_key", views=(PartViewReference(view_id="view-1", role="FRONT", contour_ids=("contour-1",), local_origin_source=Point2D(x=0, y=0), local_bounds_source={"min_x": 0, "min_y": 0, "max_x": 100, "max_y": 50}, local_bounds_mm=None),), dimensions=PartDimensions(length=unknown, width=unknown, thickness=unknown), quantity=ObservedQuantity(value=None, state="unknown"), status="partial", source_entity_ids=("entity-1",), evidence_ids=("evidence-1",))
    parts = SeparatedPartsExtraction(drawing_id=extraction.drawing_id, candidate_revision="parts-rev-1", observations=(observation,))
    candidate = AssemblyCandidate(id="assembly-1", family="unknown", layout="unknown", uses=(AssemblyPartUse(id="use-unknown", part_observation_id=observation.id, role="unknown", source_quantity=None, allocated_quantity=None, occurrence_indices=(), quantity_source="unknown", evidence_ids=("evidence-1",)),), constraints=(), derived_dimensions=(), unknown_fields=("family", "layout", "quantity", "dimensions"), assumptions=("classification_not_observed",), evidence_ids=("evidence-1",))
    return extraction, parts, candidate


def test_repository_persists_parts_snapshot_without_legacy_scenarios(tmp_path: Path) -> None:
    extraction, parts, candidate = _parts_payload()
    repository = DemoRepository(tmp_path / "parts.sqlite3")

    run = repository.create_run("run-parts", "geometry_only", extraction, (), document_id="doc-1", part_analysis=parts, assembly_candidates=(candidate,))
    result = repository.get_result("run-parts")

    assert run.input_kind == "separated_part_views"
    assert run.candidate_revision == "parts-rev-1"
    assert result.input_semantics == "separated_part_views"
    assert result.part_analysis == parts
    assert result.assembly_candidates == (candidate,)
    assert result.scenarios == ()


def test_parts_review_selects_candidate_and_resolves_only_observed_values(tmp_path: Path) -> None:
    extraction, parts, _candidate = _parts_payload()
    observed = lambda value, name: ObservedPartDimension(value_mm=value, state="observed", view_ids=("view-1",), evidence_ids=(f"evidence-{name}",))
    observation = parts.observations[0].model_copy(update={"dimensions": PartDimensions(length=observed(800, "length"), width=observed(300, "width"), thickness=observed(18, "thickness")), "quantity": ObservedQuantity(value=2, state="observed", evidence_ids=("evidence-quantity",)), "status": "complete", "evidence_ids": ("evidence-length", "evidence-width", "evidence-thickness", "evidence-quantity")})
    parts = parts.model_copy(update={"observations": (observation,)})
    candidate = AssemblyCandidate(id="assembly-complete", family="rectangular_shelving", layout="between_sides", uses=(AssemblyPartUse(id="use-sides", part_observation_id=observation.id, role="side_panel", source_quantity=2, allocated_quantity=2, occurrence_indices=(1, 2), quantity_source="observed_annotation", evidence_ids=("evidence-quantity",)),), constraints=(), derived_dimensions=(DerivedAssemblyDimension(axis="width", value_mm=None, state="unknown", operand_refs=()),), unknown_fields=(), assumptions=("assembly_layout_not_observed",), evidence_ids=observation.evidence_ids)
    repository = DemoRepository(tmp_path / "review.sqlite3")
    repository.create_run("run-parts", "geometry_only", extraction, (), part_analysis=parts, assembly_candidates=(candidate,))

    reviewed = repository.review("run-parts", ReviewRequest(base_result_revision=1, reviewer_name="Operador local", assembly_candidate_id=candidate.id, notes="Selecciona explícitamente montaje y roles propuestos"))

    assert reviewed.selected_assembly_candidate_id == candidate.id
    assert reviewed.review and reviewed.review.selected_assembly_candidate_id == candidate.id
    assert reviewed.pieces[0].quantity == 2
    assert reviewed.pieces[0].thickness_mm == 18
    assert reviewed.pieces[0].source_part_observation_ids == (observation.id,)


def test_historical_dimensions_use_selected_assembly_derivations_not_a_piece_axis(tmp_path: Path) -> None:
    extraction, parts, candidate = _parts_payload()
    constraints = tuple(AssemblyConstraint(id=f"constraint-{axis}", kind="exterior_from_parts", operation="sum", dimension=f"assembled_{axis}", operand_refs=(f"part.{axis}",), result_mm=value, status="pass", evidence_ids=("evidence-1",)) for axis, value in (("width", 900), ("height", 1200), ("depth", 300)))
    dimensions = tuple(DerivedAssemblyDimension(axis=axis, value_mm=value, state="derived", operand_refs=(f"part.{axis}",), constraint_id=f"constraint-{axis}") for axis, value in (("width", 900), ("height", 1200), ("depth", 300)))
    candidate = candidate.model_copy(update={"family": "rectangular_shelving", "layout": "between_sides", "constraints": constraints, "derived_dimensions": dimensions, "unknown_fields": ()})
    repository = DemoRepository(tmp_path / "historical.sqlite3")
    repository.create_run("run-parts", "geometry_only", extraction, (), part_analysis=parts, assembly_candidates=(candidate,))
    reviewed = repository.review("run-parts", ReviewRequest(base_result_revision=1, reviewer_name="Operador", assembly_candidate_id=candidate.id, notes="Selecciona ensamblaje"))
    assert _assembly_dimensions(reviewed) == (900, 300, 1200)


def test_parts_explanations_use_part_observation_provenance(tmp_path: Path) -> None:
    extraction, parts, candidate = _parts_payload()
    repository = DemoRepository(tmp_path / "explanations.sqlite3")
    repository.create_run("run-parts", "geometry_only", extraction, (), part_analysis=parts, assembly_candidates=(candidate,))
    initial = explain_result(extraction, repository.get_result("run-parts"))
    reviewed = repository.review("run-parts", ReviewRequest(base_result_revision=1, reviewer_name="Operador", assembly_candidate_id=candidate.id, notes="Selecciona hipótesis"))
    after = explain_result(extraction, reviewed)
    assert initial.pieces[0].proposal_id == candidate.uses[0].id
    assert initial.pieces[0].source_entity_ids == parts.observations[0].source_entity_ids
    assert initial.pieces[0].field_states["quantity"] == "unknown"
    assert after.pieces[0].source_contour_ids == tuple(contour for view in parts.observations[0].views for contour in view.contour_ids)
