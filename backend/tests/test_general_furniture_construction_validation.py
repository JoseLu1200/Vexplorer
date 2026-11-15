from __future__ import annotations

import pytest

from backend.app.contratos.modelos import (
    GeneralBinding,
    GeneralComponentProposal,
    GeneralConstructionConstraint,
    GeneralConstructionDetail,
    GeneralConstructionDetailGeometry,
    GeneralConstructionParameter,
    GeneralDimensionRange,
    GeneralDraftComponent,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
    GeneralPieceGeometry,
    GeneralPremise,
    GeneralQuantity,
    GeneralResolvedConstructionParameter,
    GeneralValue,
    Point2D,
)
from backend.app.general_furniture.construction_validation import (
    validate_construction_scenario,
)


def _unknown_value() -> GeneralValue:
    return GeneralValue(value_mm=None, state="unknown")


def _proposal_and_draft(
    *,
    thickness_mm: float = 18,
    thickness_range: tuple[float, float] = (16, 19),
    opening_basis: str = "deduced",
    opening_mm: float = 564,
) -> tuple[GeneralFurnitureProposal, GeneralFurnitureDraft]:
    parameters = (
        GeneralConstructionParameter(
            id="width", label="Ancho total", basis="observed",
            method="observed_copy", binding_id="b-width",
            source_refs=("dimension:overall-width",), assumption_refs=(),
            rationale="Cota global observada.",
        ),
        GeneralConstructionParameter(
            id="thickness", label="Espesor", basis="estimated",
            nominal_mm=thickness_mm,
            range_mm=GeneralDimensionRange(
                min_mm=thickness_range[0], max_mm=thickness_range[1]
            ),
            method="construction_assumption", binding_id=None,
            source_refs=("contour:side",),
            assumption_refs=("premise:thickness",),
            rationale="Espesor provisional de tablero.",
        ),
        GeneralConstructionParameter(
            id="opening", label="Vano", basis=opening_basis,
            nominal_mm=opening_mm if opening_basis == "estimated" else None,
            range_mm=(
                GeneralDimensionRange(min_mm=opening_mm, max_mm=opening_mm)
                if opening_basis == "estimated" else None
            ),
            method=(
                "construction_assumption"
                if opening_basis == "estimated" else "arithmetic"
            ),
            binding_id=None if opening_basis == "estimated" else "b-opening",
            source_refs=("dimension:overall-width",),
            assumption_refs=("premise:thickness",),
            rationale="Vano interior del escenario.",
        ),
    )
    bindings = (
        GeneralBinding(
            id="b-width", operation="copy",
            operand_refs=("dimension:overall-width",),
        ),
        GeneralBinding(
            id="b-thickness", operation="copy",
            operand_refs=("parameter:thickness",),
        ),
        GeneralBinding(
            id="b-opening", operation="subtract",
            operand_refs=(
                "parameter:width", "parameter:thickness", "parameter:thickness"
            ),
        ),
    )
    component = GeneralComponentProposal(
        id="sides", label="Laterales", kind="panel", role="side_panel",
        scenario_id="cabinet", necessity="visible",
        geometry=GeneralPieceGeometry(
            shape_kind="rectangle", source_contour_ids=("side",),
            basis_refs=("contour:side",), rationale="Panel rectangular.",
        ),
        construction_parameter_ids=("width", "thickness", "opening"),
        quantity_basis_refs=("premise:two-sides",),
        length_binding_id="b-width", width_binding_id="b-opening",
        thickness_binding_id="b-thickness",
        quantity=GeneralQuantity(
            value=2, state="estimated", dependency_refs=("premise:two-sides",)
        ),
        premise_ids=("thickness", "two-sides"),
        source_contour_ids=("side",), assumptions=("Dos laterales.",),
    )
    constraint = GeneralConstructionConstraint(
        id="width-closure", kind="overall_closure",
        left_refs=("parameter:width",),
        right_refs=(
            "parameter:thickness", "parameter:opening", "parameter:thickness"
        ),
        tolerance_mm=0.1, severity="error",
        source_refs=("dimension:overall-width",),
        rationale="Los dos espesores y el vano cierran el ancho.",
    )
    proposal = GeneralFurnitureProposal(
        id="cabinet", drawing_id="drawing", ledger_revision="ledger",
        proposal_origin="native_tool", construction_scenario_id="cabinet",
        bindings=bindings, components=(component,),
        premises=(
            GeneralPremise(id="thickness", description="Espesor provisional."),
            GeneralPremise(id="two-sides", description="Dos laterales."),
        ),
        assumptions=("Construcción provisional.",),
        construction_parameters=parameters,
        construction_constraints=(constraint,),
    )
    effective_opening_state = (
        "estimated" if opening_basis == "estimated" or thickness_range else "deduced"
    )
    draft = GeneralFurnitureDraft(
        proposal_id=proposal.id, drawing_id=proposal.drawing_id,
        ledger_revision=proposal.ledger_revision, components=(GeneralDraftComponent(
            id="sides", label="Laterales", kind="panel", role="side_panel",
            length=_unknown_value(), width=_unknown_value(), thickness=_unknown_value(),
            quantity=component.quantity, premise_ids=component.premise_ids,
            source_view_ids=(), source_observation_ids=(),
            source_contour_ids=("side",), source_evidence_ids=(),
            source_dimension_ids=(), source_document_refs=(),
            assumptions=component.assumptions, unknown_fields=(),
        ),), premises=proposal.premises, assumptions=proposal.assumptions,
        construction_scenario_id="cabinet",
        construction_parameters=(
            GeneralResolvedConstructionParameter(
                id="width", label="Ancho total", nominal_mm=600,
                range_mm=GeneralDimensionRange(min_mm=600, max_mm=600),
                state="observed", method="observed_copy", binding_id="b-width",
                dependency_refs=("dimension:overall-width",),
                source_refs=("dimension:overall-width",), assumption_refs=(),
                rationale="Cota global observada.",
            ),
            GeneralResolvedConstructionParameter(
                id="thickness", label="Espesor", nominal_mm=thickness_mm,
                range_mm=GeneralDimensionRange(
                    min_mm=thickness_range[0], max_mm=thickness_range[1]
                ),
                state="estimated", method="construction_assumption",
                dependency_refs=("premise:thickness",),
                source_refs=("contour:side",),
                assumption_refs=("premise:thickness",),
                rationale="Espesor provisional de tablero.",
            ),
            GeneralResolvedConstructionParameter(
                id="opening", label="Vano", nominal_mm=opening_mm,
                range_mm=GeneralDimensionRange(
                    min_mm=(600 - 2 * thickness_range[1])
                    if opening_basis == "deduced" else opening_mm,
                    max_mm=(600 - 2 * thickness_range[0])
                    if opening_basis == "deduced" else opening_mm,
                ),
                state=effective_opening_state, method=(
                    "construction_assumption"
                    if opening_basis == "estimated" else "arithmetic"
                ),
                binding_id=None if opening_basis == "estimated" else "b-opening",
                formula=None if opening_basis == "estimated" else "width-2*thickness",
                dependency_refs=("parameter:width", "parameter:thickness"),
                source_refs=("dimension:overall-width",),
                assumption_refs=("premise:thickness",),
                rationale="Vano interior del escenario.",
            ),
        ), construction_constraints=(constraint,),
    )
    return proposal, draft


def test_shared_estimated_thickness_preserves_correlation_in_closure() -> None:
    proposal, draft = _proposal_and_draft()

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "valid"
    closure = result.constraint_results[0]
    assert closure.status == "pass"
    assert closure.left_range_mm == GeneralDimensionRange(min_mm=600, max_mm=600)
    assert closure.right_range_mm == GeneralDimensionRange(min_mm=600, max_mm=600)
    assert closure.residual_mm == pytest.approx(0)
    assert result.parameter_order == ("width", "thickness", "opening")


def test_observed_width_rejects_a_604_mm_construction_closure() -> None:
    proposal, draft = _proposal_and_draft(
        thickness_mm=20,
        thickness_range=(20, 20),
        opening_basis="estimated",
        opening_mm=564,
    )

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "invalid"
    closure = result.constraint_results[0]
    assert closure.status == "fail"
    assert closure.residual_mm == pytest.approx(4)
    assert any(issue.code == "construction_constraint_failed" for issue in result.issues)


def _validation_at_constraint_boundary(
    *, width_range: tuple[float, float], constraint_kind: str
):
    proposal, draft = _proposal_and_draft(
        thickness_mm=18,
        thickness_range=(18, 18),
        opening_basis="estimated",
        opening_mm=564.5,
    )
    constraint = proposal.construction_constraints[0].model_copy(
        update={"kind": constraint_kind, "tolerance_mm": 1.0}
    )
    width = draft.construction_parameters[0].model_copy(
        update={
            "nominal_mm": sum(width_range) / 2,
            "range_mm": GeneralDimensionRange(
                min_mm=width_range[0], max_mm=width_range[1]
            ),
        }
    )
    proposal = proposal.model_copy(
        update={"construction_constraints": (constraint,)}
    )
    draft = draft.model_copy(
        update={
            "construction_parameters": (
                width,
                *draft.construction_parameters[1:],
            ),
            "construction_constraints": (constraint,),
        }
    )
    return validate_construction_scenario(proposal, draft)


def test_equality_tolerance_includes_both_float_noise_boundaries() -> None:
    result = _validation_at_constraint_boundary(
        width_range=(599.4999999999999, 601.5000000000001),
        constraint_kind="sum_equals",
    )

    assert result.status == "valid"
    assert result.constraint_results[0].status == "pass"


def test_greater_equal_tolerance_includes_negative_float_noise_boundary() -> None:
    result = _validation_at_constraint_boundary(
        width_range=(599.4999999999999, 599.4999999999999),
        constraint_kind="greater_equal",
    )

    assert result.status == "valid"
    assert result.constraint_results[0].status == "pass"


@pytest.mark.parametrize("constraint_kind", ("sum_equals", "greater_equal"))
def test_constraint_rejects_a_real_excess_beyond_numeric_epsilon(
    constraint_kind: str,
) -> None:
    result = _validation_at_constraint_boundary(
        width_range=(599.49999, 599.49999),
        constraint_kind=constraint_kind,
    )

    assert result.status == "invalid"
    assert result.constraint_results[0].status == "fail"


@pytest.mark.parametrize("constraint_kind", ("sum_equals", "greater_equal"))
def test_constraint_keeps_a_wide_interval_crossing_tolerance_unknown(
    constraint_kind: str,
) -> None:
    result = _validation_at_constraint_boundary(
        width_range=(599.49, 600.5),
        constraint_kind=constraint_kind,
    )

    assert result.status == "incomplete"
    assert result.constraint_results[0].status == "unknown"


def test_recalculation_rejects_a_tampered_materialized_parameter() -> None:
    proposal, draft = _proposal_and_draft()
    opening = draft.construction_parameters[2].model_copy(
        update={"nominal_mm": 563}
    )
    draft = draft.model_copy(
        update={
            "construction_parameters": (
                *draft.construction_parameters[:2], opening
            )
        }
    )

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "invalid"
    assert any(
        issue.code == "construction_parameter_mismatch"
        and "parameter:opening" in issue.target_refs
        for issue in result.issues
    )


def test_quantity_basis_cannot_count_views_as_physical_pieces() -> None:
    proposal, draft = _proposal_and_draft()
    component = proposal.components[0].model_copy(
        update={"quantity_basis_refs": ("view:front",)}
    )
    proposal = proposal.model_copy(update={"components": (component,)})

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "invalid"
    assert any(
        issue.code == "construction_quantity_counts_views"
        for issue in result.issues
    )


def test_parameter_binding_cycle_is_rejected_before_publishing_numbers() -> None:
    proposal, draft = _proposal_and_draft()
    bindings = tuple(
        binding.model_copy(
            update={"operand_refs": ("parameter:opening",)}
        )
        if binding.id == "b-opening" else binding
        for binding in proposal.bindings
    )
    proposal = proposal.model_copy(update={"bindings": bindings})

    with pytest.raises(ValueError, match="construction_expression_cycle"):
        validate_construction_scenario(proposal, draft)


def test_rational_binding_is_recalculated_and_closes_against_its_source() -> None:
    proposal, draft = _proposal_and_draft()
    half = GeneralConstructionParameter(
        id="half-width", label="Mitad del ancho", basis="deduced",
        method="arithmetic", binding_id="b-half", source_refs=("dimension:overall-width",),
        assumption_refs=(), rationale="Mitad exacta del ancho observado.",
    )
    half_binding = GeneralBinding(
        id="b-half", operation="scale_rational",
        rational_numerator=1, rational_denominator=2,
        operand_refs=("parameter:width",),
    )
    half_constraint = GeneralConstructionConstraint(
        id="two-halves", kind="sum_equals",
        left_refs=("parameter:width",),
        right_refs=("parameter:half-width", "parameter:half-width"),
        tolerance_mm=0.1, severity="error",
        source_refs=("dimension:overall-width",),
        rationale="Dos mitades cierran el ancho.",
    )
    proposal = proposal.model_copy(update={
        "bindings": (*proposal.bindings, half_binding),
        "construction_parameters": (*proposal.construction_parameters, half),
        "construction_constraints": (*proposal.construction_constraints, half_constraint),
    })
    resolved_half = GeneralResolvedConstructionParameter(
        id="half-width", label="Mitad del ancho", nominal_mm=300,
        range_mm=GeneralDimensionRange(min_mm=300, max_mm=300),
        state="deduced", method="arithmetic", binding_id="b-half",
        formula="width*1/2", dependency_refs=("parameter:width",),
        source_refs=("dimension:overall-width",), assumption_refs=(),
        rationale="Mitad exacta del ancho observado.",
    )
    draft = draft.model_copy(update={
        "construction_parameters": (*draft.construction_parameters, resolved_half),
        "construction_constraints": (*draft.construction_constraints, half_constraint),
    })

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "valid"
    assert result.constraint_results[-1].status == "pass"
    assert result.constraint_results[-1].residual_mm == pytest.approx(0)


def test_missing_materialized_parameter_is_incomplete_not_a_false_conflict() -> None:
    proposal, draft = _proposal_and_draft()
    draft = draft.model_copy(
        update={"construction_parameters": draft.construction_parameters[:2]}
    )

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "incomplete"
    assert result.constraint_results[0].status == "unknown"
    assert any(
        issue.code == "construction_parameter_unresolved" for issue in result.issues
    )


def test_observed_parameter_cannot_claim_an_arithmetic_or_parameter_binding() -> None:
    proposal, draft = _proposal_and_draft()
    invalid_width_binding = proposal.bindings[0].model_copy(
        update={"operand_refs": ("parameter:thickness",)}
    )
    proposal = proposal.model_copy(
        update={"bindings": (invalid_width_binding, *proposal.bindings[1:])}
    )

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "invalid"
    assert any(
        issue.code == "construction_observed_binding_invalid"
        for issue in result.issues
    )


def test_two_parameters_cannot_alias_the_same_materialized_binding() -> None:
    proposal, draft = _proposal_and_draft()
    alias = GeneralConstructionParameter(
        id="width-alias", label="Alias del ancho", basis="observed",
        method="observed_copy", binding_id="b-width",
        source_refs=("dimension:overall-width",), assumption_refs=(),
        rationale="Alias no permitido.",
    )
    proposal = proposal.model_copy(
        update={"construction_parameters": (*proposal.construction_parameters, alias)}
    )
    resolved_alias = GeneralResolvedConstructionParameter(
        id="width-alias", label="Alias del ancho", nominal_mm=600,
        range_mm=GeneralDimensionRange(min_mm=600, max_mm=600),
        state="observed", method="observed_copy", binding_id="b-width",
        dependency_refs=("dimension:overall-width",),
        source_refs=("dimension:overall-width",), assumption_refs=(),
        rationale="Alias no permitido.",
    )
    draft = draft.model_copy(
        update={
            "construction_parameters": (
                *draft.construction_parameters, resolved_alias
            )
        }
    )

    with pytest.raises(ValueError, match="construction_parameter_binding_alias"):
        validate_construction_scenario(proposal, draft)


def test_eight_binding_levels_are_allowed_but_the_ninth_is_rejected() -> None:
    proposal, draft = _proposal_and_draft()
    parameters = list(proposal.construction_parameters)
    bindings = list(proposal.bindings)
    resolved = list(draft.construction_parameters)
    previous = "thickness"
    for index in range(1, 10):
        parameter_id = f"level-{index}"
        binding_id = f"b-level-{index}"
        parameters.append(GeneralConstructionParameter(
            id=parameter_id, label=f"Nivel {index}", basis="deduced",
            method="arithmetic", binding_id=binding_id,
            source_refs=("contour:side",), assumption_refs=("premise:thickness",),
            rationale="Cadena acotada de expresiones.",
        ))
        bindings.append(GeneralBinding(
            id=binding_id, operation="copy",
            operand_refs=(f"parameter:{previous}",),
        ))
        resolved.append(GeneralResolvedConstructionParameter(
            id=parameter_id, label=f"Nivel {index}", nominal_mm=18,
            range_mm=GeneralDimensionRange(min_mm=16, max_mm=19),
            state="estimated", method="arithmetic", binding_id=binding_id,
            formula=f"copy parameter:{previous}",
            dependency_refs=(f"parameter:{previous}",),
            source_refs=("contour:side",),
            assumption_refs=("premise:thickness",),
            rationale="Cadena acotada de expresiones.",
        ))
        previous = parameter_id

    proposal_eight = proposal.model_copy(update={
        "bindings": tuple(bindings[:-1]),
        "construction_parameters": tuple(parameters[:-1]),
    })
    draft_eight = draft.model_copy(
        update={"construction_parameters": tuple(resolved[:-1])}
    )

    assert validate_construction_scenario(proposal_eight, draft_eight).max_depth == 8

    proposal_nine = proposal.model_copy(update={
        "bindings": tuple(bindings),
        "construction_parameters": tuple(parameters),
    })
    draft_nine = draft.model_copy(update={"construction_parameters": tuple(resolved)})
    with pytest.raises(ValueError, match="construction_expression_depth_exceeded"):
        validate_construction_scenario(proposal_nine, draft_nine)


def test_circle_detail_crossing_a_rectangular_piece_edge_is_rejected() -> None:
    proposal, draft = _proposal_and_draft()
    detail = GeneralConstructionDetail(
        id="bore-outside", kind="bore", component_ids=("sides",),
        parameter_refs=(), quantity=1, state="estimated",
        source_refs=("contour:side",), assumption_refs=("premise:thickness",),
        rationale="Taladro provisional que debe quedar dentro del panel.",
        geometry=GeneralConstructionDetailGeometry(
            kind="circle",
            points_mm=(Point2D(x=590, y=150), Point2D(x=610, y=150)),
            dimension_refs=(),
        ),
    )
    component = proposal.components[0].model_copy(
        update={"detail_ids": (detail.id,)}
    )
    proposal = proposal.model_copy(update={
        "components": (component,),
        "construction_details": (detail,),
    })
    draft_component = draft.components[0].model_copy(update={
        "length": GeneralValue(value_mm=600, state="hypothesis"),
        "width": GeneralValue(value_mm=300, state="hypothesis"),
        "detail_ids": (detail.id,),
    })
    draft = draft.model_copy(update={
        "components": (draft_component,),
        "construction_details": (detail,),
    })

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "invalid"
    assert any(
        issue.code == "construction_detail_out_of_bounds"
        and issue.target_refs == ("detail:bore-outside", "component:sides.geometry")
        for issue in result.issues
    )


@pytest.mark.parametrize(
    ("points", "expected_status"),
    (
        ((Point2D(x=550, y=250), Point2D(x=590, y=250)), "valid"),
        ((Point2D(x=250, y=550), Point2D(x=250, y=590)), "invalid"),
    ),
)
def test_detail_local_axes_use_x_length_and_y_width(points, expected_status) -> None:
    proposal, draft = _proposal_and_draft()
    detail = GeneralConstructionDetail(
        id="local-axis-detail", kind="fastener", component_ids=("sides",),
        parameter_refs=(), quantity=2, state="estimated",
        source_refs=("contour:side",), assumption_refs=("premise:thickness",),
        rationale="Detalle local sobre un panel no cuadrado.",
        geometry=GeneralConstructionDetailGeometry(
            kind="line", points_mm=points, dimension_refs=(),
        ),
    )
    component = proposal.components[0].model_copy(
        update={"detail_ids": (detail.id,)}
    )
    proposal = proposal.model_copy(update={
        "components": (component,), "construction_details": (detail,),
    })
    draft_component = draft.components[0].model_copy(update={
        "length": GeneralValue(value_mm=600, state="hypothesis"),
        "width": GeneralValue(value_mm=300, state="hypothesis"),
        "detail_ids": (detail.id,),
    })
    draft = draft.model_copy(update={
        "components": (draft_component,), "construction_details": (detail,),
    })

    result = validate_construction_scenario(proposal, draft)

    assert result.status == expected_status


def _proposal_with_polyline_detail(
    dimension_refs: tuple[str, ...],
) -> tuple[GeneralFurnitureProposal, GeneralFurnitureDraft]:
    proposal, draft = _proposal_and_draft()
    measurement_refs = (
        "measurement:contour:side:span-x",
        "measurement:contour:side:span-y",
    )
    detail = GeneralConstructionDetail(
        id="perimeter-joint", kind="joint", component_ids=("sides",),
        parameter_refs=(), quantity=1, state="estimated",
        source_refs=measurement_refs,
        assumption_refs=("premise:thickness",),
        rationale="Unión perimetral provisional dentro de la cara del panel.",
        geometry=GeneralConstructionDetailGeometry(
            kind="polyline",
            points_mm=(
                Point2D(x=0, y=0), Point2D(x=600, y=0),
                Point2D(x=600, y=300), Point2D(x=0, y=300),
                Point2D(x=0, y=0),
            ),
            dimension_refs=dimension_refs,
        ),
    )
    component = proposal.components[0].model_copy(
        update={"detail_ids": (detail.id,)}
    )
    proposal = proposal.model_copy(update={
        "components": (component,), "construction_details": (detail,),
    })
    draft_component = draft.components[0].model_copy(update={
        "length": GeneralValue(value_mm=600, state="hypothesis"),
        "width": GeneralValue(value_mm=300, state="hypothesis"),
        "detail_ids": (detail.id,),
    })
    draft = draft.model_copy(update={
        "components": (draft_component,), "construction_details": (detail,),
    })
    return proposal, draft


def test_polyline_detail_raw_measurement_dimension_refs_stay_incomplete() -> None:
    measurement_refs = (
        "measurement:contour:side:span-x",
        "measurement:contour:side:span-y",
    )
    proposal, draft = _proposal_with_polyline_detail(measurement_refs)

    result = validate_construction_scenario(proposal, draft)

    assert result.status == "incomplete"
    assert [issue.code for issue in result.issues] == [
        "construction_detail_dimension_unresolved",
        "construction_detail_dimension_unresolved",
    ]
    assert [issue.target_refs for issue in result.issues] == [
        ("detail:perimeter-joint", measurement_refs[0]),
        ("detail:perimeter-joint", measurement_refs[1]),
    ]


def test_polyline_detail_keeps_measurement_provenance_out_of_dimension_refs() -> None:
    proposal, draft = _proposal_with_polyline_detail(())

    result = validate_construction_scenario(proposal, draft)

    assert proposal.construction_details[0].source_refs == (
        "measurement:contour:side:span-x",
        "measurement:contour:side:span-y",
    )
    assert result.status == "valid"
    assert result.issues == ()


@pytest.mark.parametrize(
    ("edge_x", "expected_status"), ((103.0, "valid"), (110.0, "invalid"))
)
def test_circle_geometry_matches_its_declared_diameter(
    edge_x: float, expected_status: str
) -> None:
    proposal, draft = _proposal_and_draft()
    diameter = GeneralConstructionParameter(
        id="bore-diameter", label="Diámetro", basis="estimated",
        nominal_mm=6, range_mm=GeneralDimensionRange(min_mm=5, max_mm=7),
        method="construction_assumption", binding_id=None,
        source_refs=("contour:side",), assumption_refs=("premise:thickness",),
        rationale="Diámetro provisional.",
    )
    resolved_diameter = GeneralResolvedConstructionParameter(
        id="bore-diameter", label="Diámetro", nominal_mm=6,
        range_mm=GeneralDimensionRange(min_mm=5, max_mm=7),
        state="estimated", method="construction_assumption",
        dependency_refs=("premise:thickness",), source_refs=("contour:side",),
        assumption_refs=("premise:thickness",), rationale="Diámetro provisional.",
    )
    detail = GeneralConstructionDetail(
        id="bore", kind="bore", component_ids=("sides",),
        parameter_refs=("parameter:bore-diameter",), quantity=1,
        state="estimated", source_refs=("contour:side",),
        assumption_refs=("premise:thickness",), rationale="Taladro provisional.",
        geometry=GeneralConstructionDetailGeometry(
            kind="circle",
            points_mm=(Point2D(x=100, y=100), Point2D(x=edge_x, y=100)),
            dimension_refs=("parameter:bore-diameter",),
        ),
    )
    component = proposal.components[0].model_copy(update={"detail_ids": (detail.id,)})
    proposal = proposal.model_copy(update={
        "components": (component,),
        "construction_parameters": (*proposal.construction_parameters, diameter),
        "construction_details": (detail,),
    })
    draft_component = draft.components[0].model_copy(update={
        "length": GeneralValue(value_mm=600, state="hypothesis"),
        "width": GeneralValue(value_mm=300, state="hypothesis"),
        "detail_ids": (detail.id,),
    })
    draft = draft.model_copy(update={
        "components": (draft_component,),
        "construction_parameters": (
            *draft.construction_parameters, resolved_diameter
        ),
        "construction_details": (detail,),
    })

    result = validate_construction_scenario(proposal, draft)

    assert result.status == expected_status
    mismatch = [
        issue for issue in result.issues
        if issue.code == "construction_detail_dimension_mismatch"
    ]
    assert bool(mismatch) is (expected_status == "invalid")

