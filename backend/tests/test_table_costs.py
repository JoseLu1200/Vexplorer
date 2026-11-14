from __future__ import annotations

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
from backend.app.estimacion.table_costs import (
    estimate_table_costs,
    get_table_cost_catalog,
)


def _field(value: float | None, state: str = "confirmed") -> TableFieldValue:
    if value is None:
        state = "unknown"
    return TableFieldValue(
        value_mm=value,
        state=state,
        dependency_refs=("review:dimensions",) if value is not None else (),
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
                id="premise-top",
                kind="topology",
                description="Tablero superior rectangular.",
            ),
            TablePremise(
                id="premise-supports",
                kind="topology",
                description="Dos soportes laterales rectangulares.",
            ),
        ),
        assumptions=("table_construction_hypothesis",),
    )


def _evaluated(
    *,
    top: tuple[float | None, float | None, float | None] = (1200, 700, 30),
    supports: tuple[float | None, float | None, float | None] = (720, 700, 60),
    support_quantity: int = 2,
    accepted: bool = True,
) -> EvaluatedTableProgram:
    program = _program()
    components = (
        EvaluatedTableComponent(
            id="top",
            role="tabletop",
            length=_field(top[0]),
            width=_field(top[1]),
            thickness=_field(top[2]),
            quantity=1,
            quantity_rule_id="top_one",
            placement_rule_id="top_flush",
            accepted=accepted,
            premise_ids=("premise-top",),
            evidence_ids=("evidence-top",),
        ),
        EvaluatedTableComponent(
            id="supports",
            role="side_support",
            length=_field(supports[0]),
            width=_field(supports[1]),
            thickness=_field(supports[2]),
            quantity=support_quantity,
            quantity_rule_id="two_side_supports",
            placement_rule_id="side_supports_flush",
            accepted=accepted,
            premise_ids=("premise-supports",),
            evidence_ids=("evidence-supports",),
        ),
    )
    occurrences = (
        TableOccurrence(id="top-1", component_id="top", occurrence_index=1),
    ) + tuple(
        TableOccurrence(
            id=f"support-{index}",
            component_id="supports",
            occurrence_index=index,
        )
        for index in range(1, support_quantity + 1)
    )
    return EvaluatedTableProgram(
        raw_program=program,
        normalized_program=program,
        program_hash="a" * 64,
        ledger_revision="ledger-1",
        registry_versions={"quantity": "1", "placement": "1"},
        bindings=(),
        components=components,
        occurrences=occurrences,
        placements=(),
        overall_dimensions=TableOverallDimensions(
            width_mm=1200,
            depth_mm=700,
            height_mm=750,
        ),
        consumed_measurement_ids=("overall-width", "overall-depth"),
        measurement_dispositions=(),
        accepted_target_ids=("program-table", "top", "supports"),
        state="completed" if accepted else "needs_review",
    )


def _concept(estimate, concept_type: str, component_id: str | None = None):
    return next(
        item
        for item in estimate.concepts
        if item.concept_type == concept_type and item.component_id == component_id
    )


def test_area_material_converts_mm2_to_m2_and_counts_each_occurrence_once():
    estimate = estimate_table_costs(
        _evaluated(),
        result_revision=3,
        scope=TableCostScope(material_tariff_id="demo_board_area_v1"),
    )

    top = _concept(estimate, "material_area", "top")
    supports = _concept(estimate, "material_area", "supports")
    assert (top.quantity, top.quantity_unit, top.amount_eur) == (0.84, "m2", 35.28)
    assert top.occurrence_ids == ("top-1",)
    assert (supports.quantity, supports.quantity_unit, supports.amount_eur) == (
        1.008,
        "m2",
        42.34,
    )
    assert supports.occurrence_ids == ("support-1", "support-2")


def test_volume_material_uses_thickness_and_supports_can_be_top_contributor():
    estimate = estimate_table_costs(
        _evaluated(),
        result_revision=3,
        scope=TableCostScope(material_tariff_id="demo_solid_volume_v1"),
    )

    top = _concept(estimate, "material_volume", "top")
    supports = _concept(estimate, "material_volume", "supports")
    assert (top.quantity, top.quantity_unit, top.amount_eur) == (0.0252, "m3", 22.68)
    assert (supports.quantity, supports.quantity_unit, supports.amount_eur) == (
        0.06048,
        "m3",
        54.43,
    )
    contributions = [
        item for item in estimate.concepts if item.concept_type == "material_volume"
    ]
    assert (
        max(contributions, key=lambda item: item.amount_eur or 0).component_id
        == "supports"
    )


def test_fixed_preparation_is_once_and_edge_is_priced_only_when_scoped():
    without_edge = estimate_table_costs(
        _evaluated(),
        result_revision=3,
        scope=TableCostScope(material_tariff_id="demo_board_area_v1"),
    )
    with_edge = estimate_table_costs(
        _evaluated(),
        result_revision=3,
        scope=TableCostScope(
            material_tariff_id="demo_board_area_v1", edge_scope="all_exposed"
        ),
    )

    fixed = [item for item in with_edge.concepts if item.concept_type == "fixed"]
    assert len(fixed) == 1
    assert (fixed[0].quantity, fixed[0].amount_eur) == (1.0, 25.0)
    assert all(
        item.state == "not_applicable"
        for item in without_edge.concepts
        if item.concept_type == "edge"
    )
    assert (
        _concept(with_edge, "edge", "top").quantity,
        _concept(with_edge, "edge", "top").amount_eur,
    ) == (3.8, 9.5)
    assert (
        _concept(with_edge, "edge", "supports").quantity,
        _concept(with_edge, "edge", "supports").amount_eur,
    ) == (5.68, 14.2)
    assert with_edge.known_subtotal_eur == 126.32


def test_missing_dimension_and_unbased_work_stay_unknown_not_zero():
    estimate = estimate_table_costs(
        _evaluated(supports=(720, 700, None)),
        result_revision=4,
        scope=TableCostScope(
            material_tariff_id="demo_solid_volume_v1",
            operation_tariff_ids=("demo_machining_hour_v1", "external_operation"),
        ),
    )

    support_material = _concept(estimate, "material_volume", "supports")
    assert (
        support_material.state,
        support_material.quantity,
        support_material.amount_eur,
    ) == ("unknown", None, None)
    pending_types = {
        item.concept_type for item in estimate.concepts if item.state == "unknown"
    }
    assert {"material_volume", "operation", "labor", "finish"} <= pending_types
    known_operation = next(
        item
        for item in estimate.concepts
        if item.id == "operation:demo_machining_hour_v1"
    )
    unknown_operation = next(
        item for item in estimate.concepts if item.id == "operation:external_operation"
    )
    assert (known_operation.rate_eur_per_unit, known_operation.amount_eur) == (
        36.0,
        None,
    )
    assert unknown_operation.rate_eur_per_unit is None
    assert "requested_tariff:external_operation" in unknown_operation.dependency_refs
    labor = next(item for item in estimate.concepts if item.id == "labor:unbased")
    finish = next(item for item in estimate.concepts if item.id == "finish:unbased")
    assert not any(
        ref.startswith(("tariff:", "requested_tariff:"))
        for concept in (labor, finish)
        for ref in concept.dependency_refs
    )
    assert (
        estimate.known_subtotal_eur,
        estimate.grand_total_eur,
        estimate.total_state,
    ) == (47.68, None, "partial")


def test_catalog_and_result_identity_are_explicit_and_provisional():
    estimate = estimate_table_costs(
        _evaluated(),
        result_revision=7,
        scope=TableCostScope(material_tariff_id="demo_board_area_v1"),
    )

    assert (estimate.result_revision, estimate.program_hash) == (7, "a" * 64)
    assert (estimate.catalog_version, estimate.currency) == (
        "synthetic-table-costs-2026-11-14",
        "EUR",
    )
    assert any("sintéticas" in warning for warning in estimate.warnings)
    assert any(
        "no representa precio de venta" in warning for warning in estimate.warnings
    )
    material = _concept(estimate, "material_area", "top")
    assert "date:2026-11-14" in material.dependency_refs
    assert any(
        ref.startswith("source:synthetic development rates")
        for ref in material.dependency_refs
    )


def test_occurrence_quantity_mismatch_is_rejected_instead_of_double_counted():
    evaluated = _evaluated()
    malformed = evaluated.model_copy(update={"occurrences": evaluated.occurrences[:-1]})

    try:
        estimate_table_costs(
            malformed,
            result_revision=3,
            scope=TableCostScope(material_tariff_id="demo_board_area_v1"),
        )
    except ValueError as error:
        assert "occurrence quantity mismatch" in str(error)
    else:
        raise AssertionError("quantity/occurrence mismatch must not be priced")


def test_repeated_operation_tariff_is_rejected_before_estimation():
    with pytest.raises(ValidationError, match="duplicate operation tariff ids"):
        TableCostScope(
            material_tariff_id="demo_board_area_v1",
            operation_tariff_ids=("demo_machining_hour_v1", "demo_machining_hour_v1"),
        )


def test_catalog_exposes_every_selectable_synthetic_tariff():
    catalog = get_table_cost_catalog()

    assert catalog.catalog_version == "synthetic-table-costs-2026-11-14"
    assert catalog.synthetic is True
    by_id = {item.id: item for item in catalog.tariffs}
    assert set(by_id) == {
        "demo_board_area_v1",
        "demo_solid_volume_v1",
        "demo_edge_exposed_v1",
        "demo_machining_hour_v1",
        "demo_preparation_fixed_v1",
    }
    assert (
        by_id["demo_board_area_v1"].scope,
        by_id["demo_board_area_v1"].rate_unit,
    ) == (
        "material",
        "EUR/m2",
    )
    assert (
        by_id["demo_solid_volume_v1"].scope,
        by_id["demo_solid_volume_v1"].rate_unit,
    ) == (
        "material",
        "EUR/m3",
    )
    assert by_id["demo_edge_exposed_v1"].scope == "edge"
    assert by_id["demo_machining_hour_v1"].scope == "operation"
    assert (
        by_id["demo_preparation_fixed_v1"].scope,
        by_id["demo_preparation_fixed_v1"].concept_type,
    ) == ("preparation", "fixed")
    assert all(item.synthetic is True for item in catalog.tariffs)


def test_every_emitted_tariff_reference_resolves_and_setup_uses_catalog_rate():
    catalog = get_table_cost_catalog()
    catalog_by_id = {item.id: item for item in catalog.tariffs}
    estimates = (
        estimate_table_costs(
            _evaluated(),
            result_revision=3,
            scope=TableCostScope(
                material_tariff_id="demo_board_area_v1",
                edge_scope="all_exposed",
                operation_tariff_ids=("demo_machining_hour_v1",),
            ),
        ),
        estimate_table_costs(_evaluated(), result_revision=3, scope=TableCostScope()),
        estimate_table_costs(
            _evaluated(),
            result_revision=3,
            scope=TableCostScope(
                material_tariff_id="external_material",
                operation_tariff_ids=("external_operation",),
            ),
        ),
    )

    referenced_tariff_ids = {
        reference.removeprefix("tariff:")
        for estimate in estimates
        for concept in estimate.concepts
        for reference in concept.dependency_refs
        if reference.startswith("tariff:")
    }
    assert referenced_tariff_ids <= set(catalog_by_id)

    setup = [item for item in estimates[0].concepts if item.id == "fixed:preparation"]
    assert len(setup) == 1
    setup_tariff = catalog_by_id["demo_preparation_fixed_v1"]
    assert setup_tariff.concept_type == "fixed"
    assert setup_tariff.rate_unit == "EUR/unit"
    assert (setup[0].rate_eur_per_unit, setup[0].amount_eur) == (
        setup_tariff.rate_eur_per_unit,
        setup_tariff.rate_eur_per_unit,
    )
