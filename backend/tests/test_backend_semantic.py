from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from backend.app.contratos.modelos import DescriptorDimensions, FurnitureDescriptorV2, LibraryItem, Result
from backend.app.semantic.descriptor import build_descriptor, descriptor_fingerprint, semantic_text
from backend.app.similarity.service import geometric_match
from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.repository import DemoRepository
from backend.tests.test_backend_parts_repository import _parts_payload


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
