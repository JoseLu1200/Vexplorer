from __future__ import annotations

import csv
import io

import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    EvaluatedTableComponent,
    EvaluatedTableProgram,
    TableBinding,
    TableComponentSpec,
    TableCostScope,
    TableFieldValue,
    TableOccurrence,
    TableOperandRef,
    TableOverallDimensions,
    TablePremise,
    TableProgramProposal,
)
from backend.app.salida.table_cutlist import export_table_cutlist_csv


def _field(value: float, state: str = "confirmed") -> TableFieldValue:
    return TableFieldValue(
        value_mm=value,
        state=state,
        dependency_refs=("review:dimensions",),
    )


def _program() -> TableProgramProposal:
    bindings = tuple(
        TableBinding(
            id=binding_id,
            operation="copy",
            operand_refs=(TableOperandRef(ref_type="measure", ref_id=measure_id),),
        )
        for binding_id, measure_id in (
            ("top-l", "overall-width"),
            ("top-w", "overall-depth"),
            ("top-t", "top-thickness"),
            ("support-l", "support-height"),
            ("support-w", "overall-depth"),
            ("support-t", "support-thickness"),
        )
    )
    return TableProgramProposal(
        id="program-table",
        ledger_revision="ledger-1",
        proposal_origin="model_generated",
        bindings=bindings,
        components=(
            TableComponentSpec(
                id="top",
                role="tabletop",
                length_binding_id="top-l",
                width_binding_id="top-w",
                thickness_binding_id="top-t",
                quantity_rule_id="top_one",
                placement_rule_id="top_flush",
                premise_ids=("premise-top",),
            ),
            TableComponentSpec(
                id="supports",
                role="side_support",
                length_binding_id="support-l",
                width_binding_id="support-w",
                thickness_binding_id="support-t",
                quantity_rule_id="two_side_supports",
                placement_rule_id="side_supports_flush",
                premise_ids=("premise-supports",),
            ),
        ),
        premises=(
            TablePremise(
                id="premise-top", kind="topology", description="Tablero superior."
            ),
            TablePremise(
                id="premise-supports",
                kind="topology",
                description="Soportes laterales.",
            ),
        ),
        assumptions=("table_construction_hypothesis",),
    )


def _evaluated() -> EvaluatedTableProgram:
    program = _program()
    return EvaluatedTableProgram(
        raw_program=program,
        normalized_program=program,
        program_hash="a" * 64,
        ledger_revision="ledger-1",
        registry_versions={"quantity": "1", "placement": "1"},
        bindings=(),
        components=(
            EvaluatedTableComponent(
                id="top",
                role="tabletop",
                length=_field(1200),
                width=_field(700),
                thickness=_field(30),
                quantity=1,
                quantity_rule_id="top_one",
                placement_rule_id="top_flush",
                accepted=True,
                premise_ids=("premise-top",),
                evidence_ids=("evidence-top",),
            ),
            EvaluatedTableComponent(
                id="supports",
                role="side_support",
                length=_field(720, "calculated"),
                width=_field(700),
                thickness=_field(60),
                quantity=2,
                quantity_rule_id="two_side_supports",
                placement_rule_id="side_supports_flush",
                accepted=True,
                premise_ids=("premise-supports",),
                evidence_ids=("evidence-supports",),
            ),
        ),
        occurrences=(
            TableOccurrence(id="top-1", component_id="top", occurrence_index=1),
            TableOccurrence(
                id="support-2", component_id="supports", occurrence_index=2
            ),
            TableOccurrence(
                id="support-1", component_id="supports", occurrence_index=1
            ),
        ),
        placements=(),
        overall_dimensions=TableOverallDimensions(
            width_mm=1200, depth_mm=700, height_mm=750
        ),
        consumed_measurement_ids=("overall-width", "overall-depth"),
        measurement_dispositions=(),
        accepted_target_ids=("program-table", "top", "supports"),
        state="completed",
    )


def _rows(payload: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload)))


def test_export_uses_physical_occurrences_and_binds_rows_to_revision_and_program() -> (
    None
):
    rows = _rows(export_table_cutlist_csv(_evaluated(), result_revision=7))

    top, supports = rows
    assert (top["component_id"], top["quantity"], top["occurrence_ids"]) == (
        "top",
        "1",
        "top-1",
    )
    assert (
        supports["component_id"],
        supports["quantity"],
        supports["occurrence_ids"],
    ) == (
        "supports",
        "2",
        "support-1|support-2",
    )
    assert (supports["length_mm"], supports["length_state"]) == ("720.0", "calculated")
    assert all(
        row["result_revision"] == "7" and row["program_hash"] == "a" * 64
        for row in rows
    )
    assert all(row["manufacturing_status"] == "generic_not_certified" for row in rows)


def test_export_keeps_unmodeled_manufacturing_fields_explicitly_unknown() -> None:
    rows = _rows(export_table_cutlist_csv(_evaluated(), result_revision=7))

    for row in rows:
        assert (row["material"], row["finish"], row["grain"], row["edge_banding"]) == (
            "",
            "",
            "",
            "",
        )
        assert (
            row["material_state"],
            row["finish_state"],
            row["grain_state"],
            row["edge_banding_state"],
        ) == ("unknown", "unknown", "unknown", "unknown")
        assert row["unknown_fields"] == "material|finish|grain|edge_banding"
    assert "edge_banding_m" not in rows[0]
    assert "edge_cost" not in rows[0]


def test_export_rejects_a_table_hypothesis_that_is_not_fully_accepted() -> None:
    pending = _evaluated().model_copy(update={"state": "needs_review"})

    with pytest.raises(ValueError, match="table_revision_not_accepted"):
        export_table_cutlist_csv(pending, result_revision=7)


def test_export_rejects_declared_quantity_that_disagrees_with_occurrences() -> None:
    evaluated = _evaluated()
    malformed = evaluated.model_copy(update={"occurrences": evaluated.occurrences[:-1]})

    with pytest.raises(ValueError, match="occurrence_quantity_mismatch:supports"):
        export_table_cutlist_csv(malformed, result_revision=7)


def test_export_escapes_formula_injection_even_after_leading_whitespace() -> None:
    evaluated = _evaluated()
    injected = evaluated.components[0].model_copy(
        update={"evidence_ids": ('   =HYPERLINK("https://invalid")',)}
    )
    evaluated = evaluated.model_copy(
        update={"components": (injected, evaluated.components[1])}
    )

    row = _rows(export_table_cutlist_csv(evaluated, result_revision=7))[0]

    assert row["evidence_ids"].startswith("'   =HYPERLINK")


def test_export_rejects_non_positive_result_revision() -> None:
    with pytest.raises(ValueError, match="invalid_result_revision"):
        export_table_cutlist_csv(_evaluated(), result_revision=0)


def test_export_rejects_duplicate_physical_occurrence_ids() -> None:
    evaluated = _evaluated()
    duplicate = evaluated.occurrences[1].model_copy(update={"id": "support-1"})
    malformed = evaluated.model_copy(
        update={
            "occurrences": (
                evaluated.occurrences[0],
                duplicate,
                evaluated.occurrences[2],
            )
        }
    )

    with pytest.raises(ValueError, match="duplicate_occurrence_id:support-1"):
        export_table_cutlist_csv(malformed, result_revision=7)


def test_cost_scope_rejects_duplicate_operation_tariffs() -> None:
    with pytest.raises(ValidationError, match="duplicate operation tariff ids"):
        TableCostScope(
            operation_tariff_ids=("demo_machining_hour_v1", "demo_machining_hour_v1")
        )
