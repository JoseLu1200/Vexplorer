"""Pruebas de integración de la regla de pandeo (1.6) en el runner del agente."""
from __future__ import annotations

import json

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import (
    AgentLimits,
    run_agent,
    run_parts_agent,
    run_table_agent,
)
from backend.app.contratos.modelos import (
    AssemblyCandidate,
    AssemblyPartUse,
    Bounds2D,
    ComponentProposal,
    DecompositionScenario,
    DrawingEntity,
    DrawingExtraction,
    DrawingView,
    Evidence,
    MountedTableAnalysis,
    ObservedPartDimension,
    ObservedQuantity,
    PartDimensions,
    PartViewReference,
    Point2D,
    SeparatedPartObservation,
    SeparatedPartsExtraction,
    TableMeasure,
)
from backend.app.validador.plausibilidad import PANDEO_WARNING_CODE


class _FakeProvider:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = list(responses)
        self.inputs: list[list[dict]] = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.inputs.append(input_items)
        return self.responses.pop(0)


def _extraction(*, input_kind: str = "mounted_views_legacy") -> DrawingExtraction:
    points = (Point2D(x=0, y=0), Point2D(x=1200, y=0))
    entity = DrawingEntity(
        id="ent-1",
        kind="LINE",
        layer="0",
        source_points=points,
        points_mm=points,
    )
    view = DrawingView(
        id="view-1",
        label="FRONT",
        entity_ids=("ent-1",),
        bounds_source=Bounds2D(min_x=0, min_y=0, max_x=1200, max_y=16),
        bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=1200, max_y=16),
    )
    return DrawingExtraction(
        drawing_id="drawing-runner-pandeo",
        input_kind=input_kind,
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=(entity,),
        views=(view,),
        contours=(),
        dimensions=(),
        evidence=(
            Evidence(
                id="ev-1",
                kind="geometry",
                source_entity_ids=("ent-1",),
                description="Geometría base",
            ),
        ),
        observations=(),
    )


def test_run_agent_emits_pandeo_warning_for_long_thin_shelf() -> None:
    extraction = _extraction()
    shelf = ComponentProposal(
        id="comp-shelf",
        label="Balda larga",
        role="shelf",
        quantity=1,
        length_mm=1200.0,
        width_mm=300.0,
        thickness_mm=16.0,
        source_observation_ids=("obs-1",),
        evidence_ids=("ev-1",),
        assumptions=("medida observada",),
    )
    scenario = DecompositionScenario(
        id="scn-1",
        title="Escenario balda",
        components=(shelf,),
        assumptions=("hipótesis de prueba",),
    )
    provider = _FakeProvider(
        [
            ProviderResponse(
                id="r1",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        name="entregar_despiece",
                        arguments={"scenario_id": "scn-1"},
                    ),
                ),
            )
        ]
    )

    outcome = run_agent(
        extraction,
        (scenario,),
        provider,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
    )

    assert outcome.selected_scenario_id == "scn-1"
    initial_context = json.loads(provider.inputs[0][0]["content"])
    assert any(PANDEO_WARNING_CODE in item for item in initial_context["warnings"])
    assert any(PANDEO_WARNING_CODE in item for item in outcome.warnings)
    pandeo_findings = [
        item for item in outcome.plausibility_findings if item.get("code") == PANDEO_WARNING_CODE
    ]
    assert len(pandeo_findings) == 1
    assert pandeo_findings[0]["status"] == "warning"
    assert pandeo_findings[0]["observed"]["length_mm"] == 1200.0
    assert pandeo_findings[0]["observed"]["thickness_mm"] == 16.0


def test_run_agent_abstains_cleanly_when_thickness_is_unknown() -> None:
    extraction = _extraction()
    shelf = ComponentProposal(
        id="comp-shelf-unknown",
        label="Balda sin espesor",
        role="shelf",
        quantity=1,
        length_mm=1200.0,
        width_mm=300.0,
        thickness_mm=None,
        source_observation_ids=("obs-1",),
        evidence_ids=("ev-1",),
        assumptions=("espesor desconocido",),
    )
    scenario = DecompositionScenario(
        id="scn-unknown",
        title="Escenario espesor desconocido",
        components=(shelf,),
        assumptions=("hipótesis de prueba",),
    )
    provider = _FakeProvider(
        [
            ProviderResponse(
                id="r1",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        name="entregar_despiece",
                        arguments={"scenario_id": "scn-unknown"},
                    ),
                ),
            )
        ]
    )

    outcome = run_agent(
        extraction,
        (scenario,),
        provider,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
    )

    assert outcome.selected_scenario_id == "scn-unknown"
    initial_context = json.loads(provider.inputs[0][0]["content"])
    assert not any(PANDEO_WARNING_CODE in item for item in initial_context["warnings"])
    assert not any(PANDEO_WARNING_CODE in item for item in outcome.warnings)
    assert not [
        item for item in outcome.plausibility_findings if item.get("check") == "structural_deflection"
    ]


def _parts_inputs(*, thickness_mm: float | None) -> tuple[SeparatedPartsExtraction, AssemblyCandidate]:
    thickness_dim = (
        ObservedPartDimension(
            value_mm=thickness_mm,
            state="observed",
            measurement_ids=("dim-t",),
            view_ids=("view-1",),
            evidence_ids=("ev-1",),
        )
        if thickness_mm is not None
        else ObservedPartDimension(value_mm=None, state="unknown")
    )
    obs = SeparatedPartObservation(
        id="obs-shelf",
        part_key="BALDA",
        association_basis="explicit_key",
        views=(
            PartViewReference(
                view_id="view-1",
                role="FRONT",
                contour_ids=("cnt-1",),
                local_origin_source=Point2D(x=0, y=0),
                local_bounds_source=Bounds2D(min_x=0, min_y=0, max_x=1200, max_y=16),
                local_bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=1200, max_y=16),
            ),
        ),
        dimensions=PartDimensions(
            length=ObservedPartDimension(
                value_mm=1200.0,
                state="observed",
                measurement_ids=("dim-l",),
                view_ids=("view-1",),
                evidence_ids=("ev-1",),
            ),
            width=ObservedPartDimension(
                value_mm=300.0,
                state="observed",
                measurement_ids=("dim-w",),
                view_ids=("view-1",),
                evidence_ids=("ev-1",),
            ),
            thickness=thickness_dim,
        ),
        quantity=ObservedQuantity(value=1, state="observed", evidence_ids=("ev-1",)),
        status="complete" if thickness_mm is not None else "partial",
        source_entity_ids=("ent-1",),
        evidence_ids=("ev-1",),
    )
    parts = SeparatedPartsExtraction(
        drawing_id="drawing-runner-pandeo",
        candidate_revision="cand-rev-1",
        observations=(obs,),
    )
    candidate = AssemblyCandidate(
        id="cand-1",
        family="rectangular_shelving",
        layout="between_sides",
        uses=(
            AssemblyPartUse(
                id="use-shelf",
                part_observation_id="obs-shelf",
                role="shelf",
                source_quantity=1,
                allocated_quantity=1,
                occurrence_indices=(1,),
                quantity_source="observed_annotation",
                evidence_ids=("ev-1",),
            ),
        ),
        constraints=(),
        derived_dimensions=(),
        unknown_fields=() if thickness_mm is not None else ("thickness",),
        assumptions=("hipótesis piezas separadas",),
        evidence_ids=("ev-1",),
    )
    return parts, candidate


def test_run_parts_agent_emits_pandeo_and_abstains_on_unknown_thickness() -> None:
    extraction = _extraction(input_kind="separated_part_views")
    parts_long, cand_long = _parts_inputs(thickness_mm=16.0)
    provider_long = _FakeProvider(
        [
            ProviderResponse(
                id="r1",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        name="entregar_candidato_montaje",
                        arguments={
                            "candidate_revision": "cand-rev-1",
                            "assembly_candidate_id": "cand-1",
                        },
                    ),
                ),
            )
        ]
    )
    outcome_long = run_parts_agent(
        extraction,
        parts_long,
        (cand_long,),
        provider_long,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
    )
    assert outcome_long.selected_assembly_candidate_id == "cand-1"
    assert any(PANDEO_WARNING_CODE in item for item in outcome_long.warnings)

    parts_unknown, cand_unknown = _parts_inputs(thickness_mm=None)
    provider_unknown = _FakeProvider(
        [
            ProviderResponse(
                id="r1",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        name="entregar_candidato_montaje",
                        arguments={
                            "candidate_revision": "cand-rev-1",
                            "assembly_candidate_id": "cand-1",
                        },
                    ),
                ),
            )
        ]
    )
    outcome_unknown = run_parts_agent(
        extraction,
        parts_unknown,
        (cand_unknown,),
        provider_unknown,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
    )
    assert outcome_unknown.selected_assembly_candidate_id == "cand-1"
    assert not any(PANDEO_WARNING_CODE in item for item in outcome_unknown.warnings)


def _table_analysis(*, thickness_mm: float | None) -> MountedTableAnalysis:
    thickness_measure = (
        TableMeasure(
            id="t",
            semantic="tabletop_thickness",
            axis="height",
            value_mm=thickness_mm,
            state="observed",
            measurement_ids=("dim-t",),
            view_ids=("view-1",),
            evidence_ids=("ev-1",),
            source_entity_ids=("ent-1",),
        )
        if thickness_mm is not None
        else TableMeasure(
            id="t",
            semantic="tabletop_thickness",
            axis="height",
            value_mm=None,
            state="unknown",
            evidence_ids=("ev-1",),
            source_entity_ids=("ent-1",),
        )
    )
    measures = (
        TableMeasure(
            id="w",
            semantic="overall_width",
            axis="width",
            value_mm=1200.0,
            state="observed",
            measurement_ids=("dim-w",),
            view_ids=("view-1",),
            evidence_ids=("ev-1",),
            source_entity_ids=("ent-1",),
        ),
        TableMeasure(
            id="d",
            semantic="overall_depth",
            axis="depth",
            value_mm=700.0,
            state="observed",
            measurement_ids=("dim-d",),
            view_ids=("view-1",),
            evidence_ids=("ev-1",),
            source_entity_ids=("ent-1",),
        ),
        TableMeasure(
            id="h",
            semantic="overall_height",
            axis="height",
            value_mm=750.0,
            state="observed",
            measurement_ids=("dim-h",),
            view_ids=("view-1",),
            evidence_ids=("ev-1",),
            source_entity_ids=("ent-1",),
        ),
        thickness_measure,
    )
    return MountedTableAnalysis(
        drawing_id="drawing-runner-pandeo",
        ledger_revision="ledger-1",
        measures=measures,
        admitted_measurement_ids=("w", "d", "h", "t"),
        state="ready" if thickness_mm is not None else "needs_review",
    )


def _table_proposal_arguments() -> dict:
    return {
        "bindings": [
            {"id": "top-l", "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": "w"}]},
            {"id": "top-w", "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": "d"}]},
            {"id": "top-t", "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": "t"}]},
            {"id": "side-l", "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": "h"}]},
            {"id": "side-w", "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": "d"}]},
            {"id": "side-t", "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": "t"}]},
        ],
        "components": [
            {
                "id": "top",
                "role": "tabletop",
                "length_binding_id": "top-l",
                "width_binding_id": "top-w",
                "thickness_binding_id": "top-t",
                "quantity_rule_id": "top_one",
                "quantity_rule_version": "1",
                "placement_rule_id": "top_flush",
                "placement_rule_version": "1",
                "evidence_ids": ["ev-1"],
                "premise_ids": ["p-top"],
            },
            {
                "id": "sides",
                "role": "side_support",
                "length_binding_id": "side-l",
                "width_binding_id": "side-w",
                "thickness_binding_id": "side-t",
                "quantity_rule_id": "two_side_supports",
                "quantity_rule_version": "1",
                "placement_rule_id": "side_supports_flush",
                "placement_rule_version": "1",
                "evidence_ids": ["ev-1"],
                "premise_ids": ["p-side"],
            },
        ],
        "premises": [
            {"id": "p-top", "kind": "topology", "required": True, "description": "Tapa rectangular"},
            {"id": "p-side", "kind": "topology", "required": True, "description": "Dos soportes"},
        ],
        "assumptions": ["construction_hypothesis"],
        "evidence_ids": ["ev-1"],
    }


def test_run_table_agent_emits_pandeo_and_abstains_on_unknown_thickness() -> None:
    extraction = _extraction(input_kind="mounted_orthographic_views")
    provider_long = _FakeProvider(
        [
            ProviderResponse(
                id="r1",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        name="proponer_descomposicion",
                        arguments=_table_proposal_arguments(),
                    ),
                ),
            )
        ]
    )
    outcome_long = run_table_agent(
        extraction,
        _table_analysis(thickness_mm=16.0),
        provider_long,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
    )
    assert any(PANDEO_WARNING_CODE in item for item in outcome_long.warnings)
    assert any(
        item.get("code") == PANDEO_WARNING_CODE and item.get("status") == "warning"
        for item in outcome_long.plausibility_findings
    )

    provider_unknown = _FakeProvider(
        [
            ProviderResponse(
                id="r1",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        name="proponer_descomposicion",
                        arguments=_table_proposal_arguments(),
                    ),
                ),
            )
        ]
    )
    outcome_unknown = run_table_agent(
        extraction,
        _table_analysis(thickness_mm=None),
        provider_unknown,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
    )
    assert not any(PANDEO_WARNING_CODE in item for item in outcome_unknown.warnings)
    assert not any(
        item.get("check") == "structural_deflection"
        for item in outcome_unknown.plausibility_findings
    )
