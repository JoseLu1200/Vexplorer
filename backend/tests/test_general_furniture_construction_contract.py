from __future__ import annotations

from pydantic import ValidationError
import pytest

from backend.app.contratos import modelos as contracts


def _estimated_thickness():
    return contracts.GeneralConstructionParameter(
        id="panel-t",
        label="Espesor de tablero",
        basis="estimated",
        nominal_mm=18,
        range_mm=contracts.GeneralDimensionRange(min_mm=16, max_mm=19),
        method="construction_assumption",
        binding_id=None,
        source_refs=("contour:side",),
        assumption_refs=("premise:board-t",),
        rationale="Espesor provisional coherente con el dibujo y la construcción propuesta.",
    )


def test_estimated_parameter_requires_bounded_nominal_and_provenance() -> None:
    parameter = _estimated_thickness()

    assert parameter.nominal_mm == 18
    assert parameter.range_mm.min_mm == 16

    with pytest.raises(ValidationError, match="nominal must be inside estimated range"):
        contracts.GeneralConstructionParameter(
            **(parameter.model_dump() | {"nominal_mm": 22})
        )
    with pytest.raises(ValidationError, match="estimated parameter requires assumption"):
        contracts.GeneralConstructionParameter(
            **(parameter.model_dump() | {"assumption_refs": ()})
        )


def test_cabinet_contract_represents_observed_estimated_and_transitive_dimension() -> None:
    width = contracts.GeneralConstructionParameter(
        id="cabinet-width", label="Ancho total", basis="observed",
        nominal_mm=None, range_mm=None, method="observed_copy",
        binding_id="b-width", source_refs=("dimension:overall-width",),
        assumption_refs=(), rationale="Cota total observada.",
    )
    opening = contracts.GeneralConstructionParameter(
        id="opening-width", label="Vano interior", basis="deduced",
        nominal_mm=None, range_mm=None, method="arithmetic",
        binding_id="b-opening", source_refs=("dimension:overall-width",),
        assumption_refs=("premise:board-t",),
        rationale="Ancho total menos dos espesores compartidos.",
    )
    geometry = contracts.GeneralPieceGeometry(
        shape_kind="rectangle", source_contour_ids=("side",),
        basis_refs=("contour:side",), rationale="Panel rectangular declarado.",
    )
    component = contracts.GeneralComponentProposal(
        id="side", label="Lateral", kind="panel", role="side_panel",
        scenario_id="cabinet-main", necessity="visible", geometry=geometry,
        construction_parameter_ids=("panel-t",), detail_ids=(),
        quantity_basis_refs=("premise:two-sides",),
        length_binding_id="b-width", width_binding_id="b-opening",
        thickness_binding_id="b-t",
        quantity=contracts.GeneralQuantity(
            value=2, state="estimated", dependency_refs=("premise:two-sides",)
        ),
        premise_ids=("board-t", "two-sides"), source_contour_ids=("side",),
        assumptions=("Dos laterales en el escenario principal.",),
    )
    proposal = contracts.GeneralFurnitureProposal(
        id="cabinet", drawing_id="drawing", ledger_revision="ledger",
        proposal_origin="native_tool", construction_scenario_id="cabinet-main",
        bindings=(
            contracts.GeneralBinding(id="b-width", operation="copy", operand_refs=("dimension:overall-width",)),
            contracts.GeneralBinding(id="b-t", operation="copy", operand_refs=("parameter:panel-t",)),
            contracts.GeneralBinding(id="b-opening", operation="subtract", operand_refs=("parameter:cabinet-width", "parameter:panel-t", "parameter:panel-t")),
        ),
        construction_parameters=(width, _estimated_thickness(), opening),
        construction_constraints=(contracts.GeneralConstructionConstraint(
            id="width-closure", kind="overall_closure",
            left_refs=("parameter:cabinet-width",),
            right_refs=("parameter:panel-t", "parameter:opening-width", "parameter:panel-t"),
            tolerance_mm=0.1, severity="error",
            source_refs=("dimension:overall-width",),
            rationale="El espesor compartido cierra exactamente el ancho.",
        ),),
        construction_details=(), construction_decisions=(),
        components=(component,),
        premises=(
            contracts.GeneralPremise(id="board-t", description="Espesor provisional de tablero."),
            contracts.GeneralPremise(id="two-sides", description="Dos laterales visibles."),
        ),
        assumptions=("Escenario constructivo provisional.",),
    )

    assert proposal.components[0].scenario_id == "cabinet-main"
    assert proposal.bindings[2].operand_refs.count("parameter:panel-t") == 2
    assert proposal.construction_constraints[0].severity == "error"

    from backend.app.general_furniture.proposal import materialize_general_proposal
    from backend.tests.test_general_furniture_proposal import _extraction

    adapted_bindings = tuple(
        binding.model_copy(update={
            "operand_refs": tuple(
                "dimension:dim-width" if ref == "dimension:overall-width" else ref
                for ref in binding.operand_refs
            )
        })
        for binding in proposal.bindings
    )
    adapted_parameters = tuple(
        parameter.model_copy(update={
            "source_refs": tuple(
                    "dimension:dim-width" if ref == "dimension:overall-width" else
                    "evidence:evidence-width" if ref == "contour:side" else ref
                for ref in parameter.source_refs
            )
        })
        for parameter in proposal.construction_parameters
    )
    adapted_component = component.model_copy(update={
        "source_contour_ids": (),
        "source_view_ids": ("view-front",),
        "source_observation_ids": ("observation-front",),
        "source_evidence_ids": ("evidence-width",),
        "source_dimension_ids": ("dim-width",),
        "geometry": geometry.model_copy(update={
            "source_contour_ids": (),
            "basis_refs": ("evidence:evidence-width",),
        }),
    })
    adapted = proposal.model_copy(update={
        "drawing_id": "drawing-1",
        "bindings": adapted_bindings,
        "construction_parameters": adapted_parameters,
        "construction_constraints": tuple(
            constraint.model_copy(update={"source_refs": ("dimension:dim-width",)})
            for constraint in proposal.construction_constraints
        ),
        "components": (adapted_component,),
    })
    draft = materialize_general_proposal(_extraction(), adapted)
    by_id = {item.id: item for item in draft.construction_parameters}

    assert by_id["opening-width"].nominal_mm == 764
    assert by_id["opening-width"].range_mm.model_dump() == {"min_mm": 762.0, "max_mm": 768.0}
    assert by_id["opening-width"].state == "estimated"
    assert draft.components[0].width.state == "estimated"


def test_construction_contract_enforces_compact_limits() -> None:
    parameter = _estimated_thickness()
    values = tuple(
        parameter.model_copy(update={"id": f"parameter-{index}"})
        for index in range(33)
    )

    with pytest.raises(ValidationError):
        contracts.ProposeGeneralFurnitureArgs(
            bindings=(), components=(), premises=(), assumptions=(),
            construction_scenario_id="too-many",
            construction_parameters=values,
            construction_constraints=(), construction_details=(),
            construction_decisions=(),
        )


def test_scale_rational_materializes_nominal_and_range() -> None:
    from backend.app.general_furniture.inference import resolve_construction_graph

    binding = contracts.GeneralBinding(
        id="half-width", operation="scale_rational",
        operand_refs=("dimension:width",),
        rational_numerator=1, rational_denominator=2,
    )
    resolved, parameters = resolve_construction_graph(
        (binding,), (),
        {"dimension:width": contracts.GeneralValue(
            value_mm=600, state="observed",
            dependency_refs=("dimension:width",),
            method="observed_copy",
        )},
    )

    assert resolved["half-width"].value_mm == 300
    assert resolved["half-width"].state == "deduced"
    assert parameters == ()
