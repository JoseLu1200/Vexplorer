import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    MountedTableAnalysis,
    TableBinding,
    TableComponentSpec,
    TableConfirmedValue,
    TableMeasure,
    TableOperandRef,
    TablePremise,
    TableProgramProposal,
    TableReviewDecision,
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


def test_review_separates_acceptance_from_human_values():
    decision = TableReviewDecision(target_kind="program", target_id="program-side", action="accept", reason="Montaje elegido por la técnica")
    confirmed = TableConfirmedValue(target_kind="measurement_slot", target_id="top-t", value_mm=30, reason="Espesor medido por la técnica")
    assert decision.action == "accept"
    assert confirmed.source == "human"
    with pytest.raises(ValidationError):
        TableConfirmedValue(target_kind="component_dimension", target_id="top", value_mm=30, reason="No se admite saltar el DAG")
