from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import AssemblyCandidate, AssemblyConstraint, AssemblyPartUse, DerivedAssemblyDimension, DescriptorDimensions, DrawingExtraction, EmbeddingMetadata, FurnitureDescriptor, FurnitureDescriptorV2, ObservedPartDimension, ObservedQuantity, PartDimensions, PartViewReference, Point2D, SeparatedPartObservation, SeparatedPartsExtraction
from backend.tests.test_backend_contract import _unknown_extraction


def _unknown_dimension() -> ObservedPartDimension:
    return ObservedPartDimension(value_mm=None, state="unknown")


def _observation() -> SeparatedPartObservation:
    return SeparatedPartObservation(
        id="part-observation-P01", part_key="P01", association_basis="explicit_key",
        views=(PartViewReference(view_id="view-P01-front", role="FRONT", contour_ids=("contour-P01-front",), local_origin_source=Point2D(x=100, y=200), local_bounds_source={"min_x": 0, "min_y": 0, "max_x": 800, "max_y": 300}, local_bounds_mm={"min_x": 0, "min_y": 0, "max_x": 800, "max_y": 300}),),
        dimensions=PartDimensions(
            length=ObservedPartDimension(value_mm=800, state="observed", measurement_ids=("dimension-length",), view_ids=("view-P01-front",), evidence_ids=("evidence-length",)),
            width=ObservedPartDimension(value_mm=300, state="observed", measurement_ids=("dimension-width",), view_ids=("view-P01-front",), evidence_ids=("evidence-width",)), thickness=_unknown_dimension()),
        quantity=ObservedQuantity(value=None, state="unknown"), status="partial", source_entity_ids=("entity-P01",), evidence_ids=("evidence-length", "evidence-width"),
    )


def test_drawing_extraction_is_backward_compatible_and_declares_input_kind() -> None:
    payload = _unknown_extraction().model_dump(mode="json")
    payload.pop("input_kind", None)
    assert DrawingExtraction.model_validate(payload).input_kind == "mounted_views_legacy"


def test_part_dimensions_preserve_unknown_thickness_and_nullable_quantity() -> None:
    observation = _observation()
    assert observation.dimensions.length.value_mm == 800
    assert observation.dimensions.thickness.value_mm is None
    assert observation.quantity.value is None and observation.quantity.state == "unknown"


def test_observed_values_require_source_references_and_unknown_values_must_be_null() -> None:
    with pytest.raises(ValidationError, match="observed dimension requires"):
        ObservedPartDimension(value_mm=18, state="observed")
    with pytest.raises(ValidationError, match="unknown or conflict dimension"):
        ObservedPartDimension(value_mm=18, state="unknown")
    with pytest.raises(ValidationError, match="observed quantity requires"):
        ObservedQuantity(value=2, state="observed")


def test_parts_extraction_rejects_view_reuse() -> None:
    observation = _observation()
    duplicate = observation.model_copy(update={"id": "part-observation-P02", "part_key": "P02"})
    with pytest.raises(ValidationError, match="view belongs to more than one"):
        SeparatedPartsExtraction(drawing_id="drawing-1", candidate_revision="parts-rev-1", observations=(observation, duplicate))


def test_assembly_candidate_keeps_roles_and_layout_as_hypotheses_with_unknown_quantity() -> None:
    candidate = AssemblyCandidate(id="assembly-1", family="rectangular_shelving", layout="between_sides", uses=(AssemblyPartUse(part_observation_id="part-observation-P01", role="shelf", quantity=None, quantity_source="unknown", evidence_ids=("evidence-length",)),), constraints=(), derived_dimensions=(), unknown_fields=("uses.part-observation-P01.quantity",), assumptions=("role_assignment_not_observed", "assembly_layout_not_observed"), evidence_ids=("evidence-length",))
    assert candidate.state == "hypothesis" and candidate.needs_review is True
    assert candidate.uses[0].quantity is None and candidate.uses[0].role_status == "hypothesis"


def test_parts_descriptor_is_v2_and_legacy_v1_does_not_accept_new_semantics() -> None:
    descriptor = FurnitureDescriptorV2(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800, depth_mm=300, height_mm=1200), roles=(), structure="top_base_between_sides", thicknesses_mm=(18,), classification_status="hypothesis", unknown_fields=())
    metadata = EmbeddingMetadata(model="text-embedding-3-small", dimensions=256, descriptor_version="furniture-v2", cache_key="cache-v2", status="generated")
    assert descriptor.descriptor_version == "furniture-v2"
    assert metadata.descriptor_version == "furniture-v2"
    with pytest.raises(ValidationError):
        FurnitureDescriptor(family="rectangular_shelving", dimensions=descriptor.dimensions, roles=(), structure="top_base_between_sides", thicknesses_mm=(18,), classification_status="hypothesis", unknown_fields=())


def test_conflicts_and_derived_numbers_require_structured_provenance() -> None:
    with pytest.raises(ValidationError, match="conflict dimension requires"):
        ObservedPartDimension(value_mm=None, state="conflict", view_ids=("view-1",), evidence_ids=("evidence-1",))
    with pytest.raises(ValidationError, match="passing constraint requires"):
        AssemblyConstraint(id="constraint-1", kind="exterior_from_parts", operation="sum", dimension="assembled_width", operand_refs=("part-1.length", "part-2.thickness"), result_mm=900, status="pass", evidence_ids=())
    with pytest.raises(ValidationError, match="unknown or conflict constraint"):
        AssemblyConstraint(id="constraint-1", kind="exterior_from_parts", operation="sum", dimension="assembled_width", operand_refs=("part-1.length",), result_mm=900, status="unknown", evidence_ids=())


def test_assembly_candidate_rejects_duplicate_derived_axes_and_overlap_with_unassigned() -> None:
    dimension = DerivedAssemblyDimension(axis="width", value_mm=None, state="unknown", operand_refs=())
    use = AssemblyPartUse(part_observation_id="part-1", role="unknown", quantity=None, quantity_source="unknown", evidence_ids=())
    with pytest.raises(ValidationError, match="used and unassigned"):
        AssemblyCandidate(id="assembly-1", family="rectangular_shelving", layout="between_sides", uses=(use,), unassigned_part_observation_ids=("part-1",), constraints=(), derived_dimensions=(dimension,), unknown_fields=("layout",), assumptions=("not_observed",), evidence_ids=("evidence-1",))
    with pytest.raises(ValidationError, match="derived assembly axes"):
        AssemblyCandidate(id="assembly-1", family="rectangular_shelving", layout="between_sides", uses=(use,), constraints=(), derived_dimensions=(dimension, dimension), unknown_fields=("layout",), assumptions=("not_observed",), evidence_ids=("evidence-1",))
