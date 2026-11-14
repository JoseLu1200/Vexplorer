from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from backend.app.contratos.modelos import DescriptorDimensions, EvaluatedTableBinding, EvaluatedTableComponent, EvaluatedTableProgram, FurnitureDescriptorV2, LibraryItem, Result, ReviewDecision, ReviewRequest, TableFieldValue, TableOccurrence, TableOverallDimensions
from backend.app.semantic.descriptor import build_descriptor, descriptor_fingerprint, semantic_text
from backend.app.similarity.service import geometric_match
from backend.app.geometria import extract_drawing
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.repository import DemoRepository
from backend.tests.test_backend_parts_repository import _parts_payload
from backend.tests.test_backend_contract_table import _analysis as _table_analysis, _program as _table_program


def _reviewed_result(tmp_path: Path) -> Result:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    repository = DemoRepository(tmp_path / "semantic.sqlite3")
    run_id = "run-semantic"
    repository.create_run(run_id, "geometry_only", extraction, derive_decomposition_scenarios(extraction))
    from backend.app.contratos.modelos import ReviewRequest

    return repository.review(run_id, ReviewRequest(base_result_revision=1, reviewer_name="Técnica", scenario_id="scenario-between-sides", confirmed_thickness_mm=18, material="Tablero", finish="Melamina", notes="Confirmado"))


def test_descriptor_is_invariant_to_ids_order_and_human_notes(tmp_path: Path) -> None:
    result = _reviewed_result(tmp_path)
    payload = deepcopy(result.model_dump(mode="json"))
    payload["run_id"] = "run-other"
    payload["pieces"].reverse()
    payload["review"]["reason"] = "otra nota que no debe entrar"
    for index, piece in enumerate(payload["pieces"]):
        piece["id"] = f"renamed-{index}"
    renamed = Result.model_validate(payload)

    first = build_descriptor(result)
    second = build_descriptor(renamed)

    assert first == second
    assert descriptor_fingerprint(first) == descriptor_fingerprint(second)
    serialized = semantic_text(first)
    assert "run-" not in serialized and "proposal-" not in serialized and "nota" not in serialized


def test_descriptor_keeps_unknowns_explicit_instead_of_inventing_values(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    repository = DemoRepository(tmp_path / "unknown.sqlite3")
    run_id = "run-unknown"
    repository.create_run(run_id, "geometry_only", extraction, derive_decomposition_scenarios(extraction))
    result = repository.get_result(run_id)

    descriptor = build_descriptor(result)

    assert descriptor.material is None
    assert descriptor.dimensions.width_mm is not None
    assert "material" in descriptor.unknown_fields
    assert "confirmed_components" in descriptor.unknown_fields


def test_descriptor_has_canonical_roles_dimensions_and_semantic_structure(tmp_path: Path) -> None:
    descriptor = build_descriptor(_reviewed_result(tmp_path))

    assert descriptor.descriptor_version == "furniture-v1"
    assert descriptor.family == "rectangular_shelving"
    assert descriptor.dimensions.model_dump() == {"width_mm": 900.0, "depth_mm": 300.0, "height_mm": 1200.0}
    assert [(item.role, item.quantity) for item in descriptor.roles] == [("base_panel", 1), ("shelf", 2), ("side_panel", 2), ("top_panel", 1)]
    assert descriptor.structure == "top_base_between_sides"


def test_parts_result_uses_descriptor_v2_without_ids_or_keys(tmp_path: Path) -> None:
    extraction, parts, candidate = _parts_payload()
    repository = DemoRepository(tmp_path / "parts-semantic.sqlite3")
    repository.create_run("run-parts", "geometry_only", extraction, (), part_analysis=parts, assembly_candidates=(candidate,))

    descriptor = build_descriptor(repository.get_result("run-parts"))
    text = semantic_text(descriptor)

    assert descriptor.descriptor_version == "furniture-v2"
    assert descriptor.classification_status == "hypothesis"
    assert descriptor.thicknesses_mm == ()
    assert "P01" not in text and "part-P01" not in text and "run-parts" not in text


def test_parts_geometric_similarity_distinguishes_thickness() -> None:
    base = FurnitureDescriptorV2(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800, depth_mm=300, height_mm=1200), roles=(), structure="top_base_between_sides", thicknesses_mm=(18,), classification_status="hypothesis", unknown_fields=())
    thick = base.model_copy(update={"thicknesses_mm": (36,)})
    candidate = LibraryItem(id="library-thick", run_id="run-thick", result_revision=1, label="thick", descriptor=thick, descriptor_fingerprint="a" * 64, created_at="2026-11-14T00:00:00Z")
    match = geometric_match(base, candidate)
    assert match.score < 1
    assert any(item.field == "thicknesses_mm" for item in match.differences)


def test_parts_descriptor_represents_human_confirmed_quantity_without_mutating_observation(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "piezas_qty_desconocida.dxf"
    extraction = extract_drawing(fixture, input_kind="separated_part_views")
    parts = extract_separated_parts(extraction)
    candidates = derive_assembly_candidates(parts)
    candidate = candidates[0]
    unknown_use = next(item for item in candidate.uses if item.allocated_quantity is None)
    original = next(item for item in parts.observations if item.id == unknown_use.part_observation_id)
    repository = DemoRepository(tmp_path / "parts-confirmed.sqlite3")
    repository.create_run(
        "run-confirmed", "geometry_only", extraction, (),
        part_analysis=parts, assembly_candidates=candidates,
    )
    reviewed = repository.review("run-confirmed", ReviewRequest(
        base_result_revision=1,
        reviewer_name="Operadora local",
        assembly_candidate_id=candidate.id,
        decisions=(ReviewDecision(
            proposal_id=unknown_use.id,
            action="confirm",
            role=unknown_use.role,
            quantity=2,
            notes="Confirma dos ocurrencias físicas de esta pieza.",
        ),),
        notes="Selecciona el candidato y confirma la cantidad ausente.",
    ))

    descriptor = build_descriptor(reviewed)

    assert reviewed.state == "completed"
    assert original.quantity.value is None and original.quantity.state == "unknown"
    resolved_feature = next(
        item for item in descriptor.part_features
        if item.length_mm == original.dimensions.length.value_mm
        and item.width_mm == original.dimensions.width.value_mm
    )
    assert resolved_feature.quantity == 2
    assert resolved_feature.field_states["quantity"] == "confirmed"
    assert "quantity" not in resolved_feature.unknown_fields
    assert f"uses.{unknown_use.id}.quantity" not in descriptor.unknown_fields


def _completed_table_result() -> Result:
    program = _table_program()
    values = {"top": (1200.0, 700.0, 30.0, 1), "supports": (720.0, 700.0, 30.0, 2)}
    components = tuple(EvaluatedTableComponent(
        id=item.id,
        role=item.role,
        length=TableFieldValue(value_mm=values[item.id][0], state="calculated", dependency_refs=(f"binding:{item.length_binding_id}",)),
        width=TableFieldValue(value_mm=values[item.id][1], state="calculated", dependency_refs=(f"binding:{item.width_binding_id}",)),
        thickness=TableFieldValue(value_mm=values[item.id][2], state="confirmed", dependency_refs=("measure:section",)),
        quantity=values[item.id][3], quantity_rule_id=item.quantity_rule_id, placement_rule_id=item.placement_rule_id,
        accepted=True, premise_ids=item.premise_ids, evidence_ids=item.evidence_ids,
    ) for item in program.components)
    evaluated = EvaluatedTableProgram(
        raw_program=program, normalized_program=program, program_hash="a" * 64,
        ledger_revision=program.ledger_revision, registry_versions={"rectangular_table_v1": "1"},
        bindings=tuple(EvaluatedTableBinding(id=item.id, operation=item.operation, operand_refs=item.operand_refs, result=TableFieldValue(value_mm=1, state="calculated")) for item in program.bindings),
        components=components,
        occurrences=(TableOccurrence(id="occ-top", component_id="top", occurrence_index=1), TableOccurrence(id="occ-side-1", component_id="supports", occurrence_index=1), TableOccurrence(id="occ-side-2", component_id="supports", occurrence_index=2)),
        placements=(), overall_dimensions=TableOverallDimensions(width_mm=1200, depth_mm=700, height_mm=750),
        consumed_measurement_ids=("width", "height", "depth"), measurement_dispositions=(),
        accepted_target_ids=(program.id, "top", "supports", "premise-top", "premise-side"), state="completed",
    )
    return Result(run_id="run-table", result_revision=2, state="completed", scenarios=(), pieces=(), created_at="2026-11-14T00:00:00Z", input_semantics="mounted_orthographic_views", table_analysis=_table_analysis(), table_programs=(program,), selected_table_program_id=program.id, evaluated_table_program=evaluated)


def test_completed_table_uses_isolated_descriptor_v3_without_ids():
    result = _completed_table_result()
    descriptor = build_descriptor(result)
    text = semantic_text(descriptor)

    assert descriptor.descriptor_version == "furniture-v3"
    assert descriptor.structure == "side_support_table"
    assert descriptor.dimensions == DescriptorDimensions(width_mm=1200, depth_mm=700, height_mm=750)
    assert [(item.role, item.quantity) for item in descriptor.components] == [("side_support", 2), ("tabletop", 1)]
    assert "run-table" not in text and "program-side" not in text and "premise-side" not in text


def test_table_geometric_similarity_rejects_cross_version_and_distinguishes_thickness():
    descriptor = build_descriptor(_completed_table_result())
    thicker = descriptor.model_copy(update={"components": tuple(item.model_copy(update={"thickness_mm": item.thickness_mm * 2}) for item in descriptor.components)})
    candidate = LibraryItem(id="table-thick", run_id="run-thick", result_revision=2, label="thick", descriptor=thicker, descriptor_fingerprint="b" * 64, created_at="2026-11-14T00:00:00Z")
    assert geometric_match(descriptor, candidate).score < 1
    legacy = FurnitureDescriptorV2(family="rectangular_shelving", dimensions=DescriptorDimensions(), roles=(), structure="unknown", thicknesses_mm=(), classification_status="hypothesis", unknown_fields=())
    legacy_item = candidate.model_copy(update={"descriptor": legacy})
    with pytest.raises(ValueError, match="descriptor_space_incompatible"):
        geometric_match(descriptor, legacy_item)
