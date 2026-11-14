import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    MountedTableAnalysis,
    TableBinding,
    TableComponentSpec,
    TableConfirmedValue,
    TableCostCatalog,
    TableCostTariff,
    TableMeasure,
    TableOperandRef,
    TablePremise,
    TableProgramProposal,
    TableReviewDecision,
    TableDrawingPrimitive,
    Point2D,
    RunRequest,
)


def _analysis() -> MountedTableAnalysis:
    return MountedTableAnalysis(
        drawing_id="drawing-table",
        ledger_revision="ledger-table-1",
        measures=(
            TableMeasure(id="width", semantic="overall_width", axis="width", value_mm=1200, state="observed", measurement_ids=("dim-w",), view_ids=("front", "top"), evidence_ids=("ev-w",), source_entity_ids=("line-w",)),
            TableMeasure(id="height", semantic="overall_height", axis="height", value_mm=750, state="observed", measurement_ids=("dim-h",), view_ids=("front", "side"), evidence_ids=("ev-h",), source_entity_ids=("line-h",)),
            TableMeasure(id="depth", semantic="overall_depth", axis="depth", value_mm=700, state="observed", measurement_ids=("dim-d",), view_ids=("top", "side"), evidence_ids=("ev-d",), source_entity_ids=("line-d",)),
        ),
        admitted_measurement_ids=("width", "height", "depth"),
        state="ready",
    )


def _program() -> TableProgramProposal:
    return TableProgramProposal(
        id="program-side",
        ledger_revision="ledger-table-1",
        proposal_origin="model_generated",
        bindings=(
            TableBinding(id="top-l", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="width"),)),
            TableBinding(id="top-w", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="depth"),)),
            TableBinding(id="support-l", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="height"),)),
            TableBinding(id="top-t", operation="subtract", operand_refs=(TableOperandRef(ref_type="measure", ref_id="height"), TableOperandRef(ref_type="binding", ref_id="support-l"))),
            TableBinding(id="support-w", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="depth"),)),
            TableBinding(id="support-t", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="width"),)),
        ),
        components=(
            TableComponentSpec(id="top", role="tabletop", length_binding_id="top-l", width_binding_id="top-w", thickness_binding_id="top-t", quantity_rule_id="top_one", quantity_rule_version="1", placement_rule_id="top_flush", placement_rule_version="1", evidence_ids=("ev-w",), premise_ids=("premise-top",)),
            TableComponentSpec(id="supports", role="side_support", length_binding_id="support-l", width_binding_id="support-w", thickness_binding_id="support-t", quantity_rule_id="two_side_supports", quantity_rule_version="1", placement_rule_id="side_supports_flush", placement_rule_version="1", evidence_ids=("ev-h",), premise_ids=("premise-side",)),
        ),
        premises=(
            TablePremise(id="premise-top", kind="topology", description="La tapa es una pieza rectangular"),
            TablePremise(id="premise-side", kind="topology", description="La mesa usa dos soportes laterales"),
        ),
        assumptions=("construction_hypothesis",),
        evidence_ids=("ev-w", "ev-h", "ev-d"),
    )


def test_table_ledger_requires_traceable_observed_values_and_exact_ids():
    analysis = _analysis()
    assert analysis.profile == "rectangular_table_v1"
    assert analysis.admitted_measurement_ids == tuple(item.id for item in analysis.measures)
    with pytest.raises(ValidationError):
        TableMeasure(id="bad", semantic="overall_width", axis="width", value_mm=1200, state="observed")
    geometric = TableMeasure(id="section", semantic="unknown", axis="section", value_mm=30, state="observed", view_ids=("front",), evidence_ids=("ev-section",), source_entity_ids=("line-section",), geometry_relation="offset_from_min_x")
    assert geometric.measurement_ids == () and geometric.value_mm == 30
    envelope = geometric.model_copy(update={"id": "envelope", "semantic": "overall_width", "geometry_relation": "envelope_extent"})
    assert envelope.geometry_relation == "envelope_extent"


def test_table_program_rejects_future_binding_references_and_wrong_topology():
    program = _program()
    assert program.components[1].quantity_rule_id == "two_side_supports"
    with pytest.raises(ValidationError, match="previous binding"):
        TableProgramProposal.model_validate(program.model_copy(update={"bindings": (TableBinding(id="a", operation="copy", operand_refs=(TableOperandRef(ref_type="binding", ref_id="b"),)), TableBinding(id="b", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="width"),)))}).model_dump())
    with pytest.raises(ValidationError, match="exactly one tabletop"):
        TableProgramProposal.model_validate(program.model_copy(update={"components": (program.components[0], program.components[0].model_copy(update={"id": "top-2"}))}).model_dump())


def test_table_program_has_no_free_numeric_operands_and_catalog_requires_template():
    with pytest.raises(ValidationError):
        TableOperandRef.model_validate({"ref_type": "constant", "ref_id": "18"})
    program = _program()
    with pytest.raises(ValidationError, match="template"):
        TableProgramProposal.model_validate(program.model_copy(update={"proposal_origin": "catalog_baseline"}).model_dump())


def test_table_program_allows_reachable_intermediate_binding_but_rejects_real_dead_node():
    program = _program()
    bindings = list(program.bindings)
    bindings.insert(2, TableBinding(id="height-copy", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="height"),)))
    top_t_index = next(index for index, item in enumerate(bindings) if item.id == "top-t")
    bindings[top_t_index] = TableBinding(id="top-t", operation="subtract", operand_refs=(TableOperandRef(ref_type="binding", ref_id="height-copy"), TableOperandRef(ref_type="binding", ref_id="support-l")))
    valid = TableProgramProposal.model_validate(program.model_copy(update={"bindings": tuple(bindings)}).model_dump())
    assert valid.bindings[2].id == "height-copy"
    with pytest.raises(ValidationError, match="dead bindings"):
        TableProgramProposal.model_validate(valid.model_copy(update={"bindings": valid.bindings + (TableBinding(id="unused", operation="copy", operand_refs=(TableOperandRef(ref_type="measure", ref_id="width"),)),)}).model_dump())


def test_review_separates_acceptance_from_human_values():
    decision = TableReviewDecision(target_kind="program", target_id="program-side", action="accept", reason="Montaje elegido por la técnica")
    confirmed = TableConfirmedValue(target_kind="measurement_slot", target_id="top-t", value_mm=30, reason="Espesor medido por la técnica")
    assert decision.action == "accept"
    assert confirmed.source == "human"
    with pytest.raises(ValidationError):
        TableConfirmedValue(target_kind="component_dimension", target_id="top", value_mm=30, reason="No se admite saltar el DAG")


def test_technical_drawing_can_preserve_observed_state():
    primitive = TableDrawingPrimitive(
        id="dimension-width",
        kind="dimension",
        points_mm=(Point2D(x=0, y=0), Point2D(x=1200, y=0), Point2D(x=0, y=100)),
        value_mm=1200,
        state="observed",
        dependency_refs=("measure:width",),
    )
    assert primitive.state == "observed"
    with pytest.raises(ValidationError, match="exactly 3 points"):
        TableDrawingPrimitive(id="bad", kind="dimension", points_mm=(Point2D(x=0, y=0), Point2D(x=1, y=0)), state="unknown")


def test_table_cost_catalog_has_unique_discoverable_tariffs():
    tariff = TableCostTariff(id="material-demo", label="Tablero demo", concept_type="material_area", scope="material", rate_eur_per_unit=20, rate_unit="EUR/m2")
    catalog = TableCostCatalog(catalog_version="table-costs-v1", tariffs=(tariff,))
    assert catalog.synthetic is True
    with pytest.raises(ValidationError, match="duplicate"):
        TableCostCatalog(catalog_version="table-costs-v1", tariffs=(tariff, tariff))


def test_table_run_requires_explicit_profile_and_catalog_template():
    document_id = "doc-" + "a" * 32
    baseline = RunRequest(document_id=document_id, mode="geometry_only", input_kind="mounted_orthographic_views", table_profile="rectangular_table_v1", proposal_mode="catalog_baseline", table_template_id="side_supports_v1")
    assert baseline.table_template_id == "side_supports_v1"
    live = RunRequest(document_id=document_id, mode="live", input_kind="mounted_orthographic_views", table_profile="rectangular_table_v1", proposal_mode="model_generated")
    assert live.table_template_id is None
    with pytest.raises(ValidationError, match="template"):
        RunRequest(document_id=document_id, mode="geometry_only", input_kind="mounted_orthographic_views", table_profile="rectangular_table_v1", proposal_mode="catalog_baseline")
    with pytest.raises(ValidationError, match="model_generated"):
        RunRequest(document_id=document_id, mode="live", input_kind="mounted_orthographic_views", table_profile="rectangular_table_v1")
