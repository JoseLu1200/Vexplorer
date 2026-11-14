"""Canal visual opcional: render Set-of-Mark desde el ledger, desactivado por defecto."""
from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits, run_agent
from backend.app.agente.tools import tool_schemas
from backend.app.agente.vision import MAX_SIDE_PX, render_view
from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"


class FakeProvider:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.inputs: list = []
        self.tools: list = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.inputs.append(input_items)
        self.tools.append(tools)
        return self.responses.pop(0)


def test_vision_tool_is_hidden_by_default_and_strict_when_enabled() -> None:
    assert "visualizar_vista" not in [tool["name"] for tool in tool_schemas()]
    tool = next(tool for tool in tool_schemas(vision=True) if tool["name"] == "visualizar_vista")
    schema = tool["parameters"]
    assert tool["strict"] is True and schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"]) == {"view_id", "highlight_contour_ids"}
    assert "path" not in str(tool).lower() and "file" not in str(tool).lower()


def test_render_is_deterministic_bounded_and_marks_real_contours() -> None:
    extraction = extract_drawing(FIXTURE)
    view = next(item for item in extraction.views if item.label == "FRONT")
    contour_ids = {item.id for item in extraction.contours if item.view_id == view.id}

    first = render_view(extraction, view.id, tuple(sorted(contour_ids))[:1])
    second = render_view(extraction, view.id, tuple(sorted(contour_ids))[:1])

    assert first == second
    assert set(first.marks.values()) == contour_ids
    image = Image.open(BytesIO(first.png))
    assert image.format == "PNG" and max(image.size) <= MAX_SIDE_PX


def test_agent_receives_the_image_as_a_user_message_after_the_tool_output() -> None:
    extraction = extract_drawing(FIXTURE)
    scenarios = derive_decomposition_scenarios(extraction)
    view = next(item for item in extraction.views if item.label == "FRONT")
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="c1", name="visualizar_vista", arguments={"view_id": view.id, "highlight_contour_ids": []}),)),
        ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="c2", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),)),
    ])

    outcome = run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5), vision=True)

    assert outcome.selected_scenario_id == scenarios[0].id
    assert "visualizar_vista" in [tool["name"] for tool in provider.tools[0]]
    tool_output, image_message = provider.inputs[1]
    output = json.loads(tool_output["output"])
    assert output["ok"] is True and output["marks"]
    image_part = image_message["content"][1]
    assert image_message["role"] == "user" and image_part["type"] == "input_image"
    assert base64.b64decode(image_part["image_url"].split(",", 1)[1]).startswith(b"\x89PNG")


def test_vision_tool_rejects_unknown_references_and_is_unknown_when_disabled() -> None:
    extraction = extract_drawing(FIXTURE)
    scenarios = derive_decomposition_scenarios(extraction)
    call = ToolCall(call_id="c1", name="visualizar_vista", arguments={"view_id": "view-nope", "highlight_contour_ids": []})

    enabled = FakeProvider([ProviderResponse(id="r1", tool_calls=(call,)), ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="c2", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),))])
    run_agent(extraction, scenarios, enabled, AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5), vision=True)
    rejected = json.loads(enabled.inputs[1][0]["output"])
    assert rejected["error"] == "unknown_reference" and "view-front" in rejected["valid_view_ids"]
    assert len(enabled.inputs[1]) == 1  # no image attached

    disabled = FakeProvider([ProviderResponse(id="r1", tool_calls=(call,)), ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="c2", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),))])
    run_agent(extraction, scenarios, disabled, AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5))
    assert json.loads(disabled.inputs[1][0]["output"])["error"] == "unknown_tool"
