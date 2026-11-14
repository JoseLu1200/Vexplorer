import json

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits, run_table_agent
from backend.app.agente.tools import table_tool_schemas
from backend.app.contratos.modelos import Bounds2D, DrawingEntity, DrawingExtraction, DrawingView, Evidence, MountedTableAnalysis, Point2D, TableMeasure


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.inputs = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.inputs.append(input_items)
        return self.responses.pop(0)


def _analysis():
    measures = tuple(
        TableMeasure(
            id=name,
            semantic=semantic,
            axis=axis,
            value_mm=value,
            state="observed",
            measurement_ids=(f"dim-{name}",),
            view_ids=("front",),
            evidence_ids=(f"ev-{name}",),
            source_entity_ids=(f"entity-{name}",),
        )
        for name, semantic, axis, value in (
            ("w", "overall_width", "width", 1200),
            ("h", "overall_height", "height", 750),
            ("d", "overall_depth", "depth", 700),
        )
    )
    return MountedTableAnalysis(drawing_id="drawing", ledger_revision="ledger-1", measures=measures, admitted_measurement_ids=("w", "h", "d"), state="ready")


def _extraction():
    entities = tuple(
        DrawingEntity(id=f"entity-{name}", kind="LINE", layer="VIEW_GEOMETRY", source_points=(Point2D(x=0, y=index), Point2D(x=value, y=index)), points_mm=(Point2D(x=0, y=index), Point2D(x=value, y=index)))
        for index, (name, value) in enumerate((("w", 1200), ("h", 750), ("d", 700)))
    )
    return DrawingExtraction(
        drawing_id="drawing", input_kind="mounted_orthographic_views", status="ready", source_unit="mm", unit_scale_to_mm=1, coordinate_unit="mm",
        entities=entities,
        views=(DrawingView(id="front", label="FRONT", entity_ids=tuple(item.id for item in entities), bounds_source=Bounds2D(min_x=0, min_y=0, max_x=1200, max_y=750), bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=1200, max_y=750)),),
        contours=(), dimensions=(),
        evidence=tuple(Evidence(id=f"ev-{name}", kind="geometry", source_entity_ids=(f"entity-{name}",), description=f"Medida {name}") for name in ("w", "h", "d")),
        observations=(),
    )


def _proposal_arguments():
    bindings = []
    for binding_id, measure_id in (("top-l", "w"), ("top-w", "d"), ("top-t", "h"), ("side-l", "h"), ("side-w", "d"), ("side-t", "w")):
        bindings.append({"id": binding_id, "operation": "copy", "operand_refs": [{"ref_type": "measure", "ref_id": measure_id}]})
    return {
        "bindings": bindings,
        "components": [
            {"id": "top", "role": "tabletop", "length_binding_id": "top-l", "width_binding_id": "top-w", "thickness_binding_id": "top-t", "quantity_rule_id": "top_one", "quantity_rule_version": "1", "placement_rule_id": "top_flush", "placement_rule_version": "1", "evidence_ids": ["ev-w"], "premise_ids": ["p-top"]},
            {"id": "sides", "role": "side_support", "length_binding_id": "side-l", "width_binding_id": "side-w", "thickness_binding_id": "side-t", "quantity_rule_id": "two_side_supports", "quantity_rule_version": "1", "placement_rule_id": "side_supports_flush", "placement_rule_version": "1", "evidence_ids": ["ev-h"], "premise_ids": ["p-side"]},
        ],
        "premises": [
            {"id": "p-top", "kind": "topology", "required": True, "description": "Tapa rectangular"},
            {"id": "p-side", "kind": "topology", "required": True, "description": "Dos soportes laterales"},
        ],
        "assumptions": ["construction_hypothesis"],
        "evidence_ids": ["ev-w", "ev-h", "ev-d"],
    }


def test_table_agent_inspects_source_values_then_proposes_reference_only_program():
    analysis = _analysis()
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="inspect", name="inspeccionar_medidas_mesa", arguments={"measurement_ids": ["w", "h", "d"]}),)),
        ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="propose", name="proponer_descomposicion", arguments=_proposal_arguments()),)),
    ])

    outcome = run_table_agent(_extraction(), analysis, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))

    context = json.loads(provider.inputs[0][0]["content"])
    assert context["input_kind"] == "mounted_orthographic_views"
    assert all("value_mm" not in item for item in context["measurements"])
    assert context["plausibility"] == {
        "findings": [],
        "total": 0,
        "truncated": False,
        "authority": "advisory_workshop_catalog_not_measurement_source",
    }
    inspected = json.loads(provider.inputs[1][0]["output"])
    assert inspected["ok"] is True
    assert {item["value_mm"] for item in inspected["measures"]} == {1200, 750, 700}
    assert {item["id"] for item in inspected["source_entities"]} == {"entity-w", "entity-h", "entity-d"}
    assert inspected["source_entities"][0]["points_mm"]
    assert outcome.program.ledger_revision == analysis.ledger_revision
    assert outcome.program.proposal_origin == "model_generated"
    assert outcome.program.table_template_id is None
    assert [item.tool_name for item in outcome.actions] == ["inspeccionar_medidas_mesa", "proponer_descomposicion"]
    assert {item["name"] for item in table_tool_schemas()} == {"inspeccionar_medidas_mesa", "proponer_descomposicion"}


def test_table_agent_unknown_measure_returns_bounded_valid_ids_for_repair():
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="bad", name="inspeccionar_medidas_mesa", arguments={"measurement_ids": ["missing"]}),)),
        ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="propose", name="proponer_descomposicion", arguments=_proposal_arguments()),)),
    ])
    outcome = run_table_agent(_extraction(), _analysis(), provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))
    error = json.loads(provider.inputs[1][0]["output"])
    assert error["error"] == "unknown_reference"
    assert error["details"] == {"valid_ids": ["d", "h", "w"], "valid_ids_total": 3, "valid_ids_truncated": False}
    assert outcome.program.id.startswith("table-program-")


def test_table_agent_vision_is_explicit_bounded_context_not_measurement_source():
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="propose", name="proponer_descomposicion", arguments=_proposal_arguments()),)),
    ])
    outcome = run_table_agent(
        _extraction(),
        _analysis(),
        provider,
        AgentLimits(max_model_calls=1, max_tool_calls=1, timeout_s=5),
        vision_enabled=True,
    )
    content = provider.inputs[0][0]["content"]
    assert content[0]["type"] == "input_text"
    context = json.loads(content[0]["text"])
    assert context["vision"]["authority"] == "context_only_not_measurement_source"
    assert len(context["vision"]["views"]) == 1
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert content[1]["detail"] == "high"
    vision_action = outcome.actions[0]
    assert vision_action.tool_name == "renderizar_contexto_visual"
    assert vision_action.artifact_sha256 == context["vision"]["views"][0]["sha256"]
    assert vision_action.mark_count == len(context["vision"]["views"][0]["marks"])
