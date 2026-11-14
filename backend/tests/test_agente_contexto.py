"""Contexto del agente (agregados, truncado explícito, plausibilidad) y proveedor configurable, sin llamar a la API."""
from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import httpx
import pytest

from backend.app.agente.config import DEFAULT_MAX_OUTPUT_TOKENS, ProviderSettings
from backend.app.agente.prompts import SYSTEM_PROMPT, system_prompt
from backend.app.agente.provider import (
    OpenAIResponsesProvider,
    ProviderResponse,
    ToolCall,
)
from backend.app.agente.runner import MAX_DIGEST_ITEMS, AgentLimits, run_agent
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


def _deliver(scenario_id: str) -> ProviderResponse:
    return ProviderResponse(id="r", tool_calls=(ToolCall(call_id="c", name="entregar_despiece", arguments={"scenario_id": scenario_id}),))


def test_digest_reports_counts_aggregates_and_plausibility(tmp_path: Path) -> None:
    document = ezdxf.readfile(FIXTURE)
    modelspace = document.modelspace()
    for index in range(MAX_DIGEST_ITEMS + 5):
        modelspace.add_text(f"nota {index}", dxfattribs={"layer": "NOTAS"}).set_placement((-500, index * 10))
    for index in range(4):
        modelspace.add_circle((-300, 32 * index), 2.5)
    path = tmp_path / "rich.dxf"
    document.saveas(path)
    extraction = extract_drawing(path)
    scenarios = derive_decomposition_scenarios(extraction)
    provider = FakeProvider([_deliver(scenarios[0].id)])

    run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=1, max_tool_calls=1, timeout_s=5))
    context = json.loads(provider.inputs[0][0]["content"])

    assert context["digest_counts"]["untrusted_drawing_text"] == {"total": len(extraction.texts), "shown": MAX_DIGEST_ITEMS, "truncated": True}
    assert len(extraction.texts) > MAX_DIGEST_ITEMS + 4
    assert context["digest_counts"]["dimensions"]["truncated"] is False
    assert context["entity_kinds"]["CIRCLE"] == 4
    assert context["untrusted_layer_counts"]["NOTAS"] == MAX_DIGEST_ITEMS + 5
    assert context["circle_diameters_mm"] == {"5.0": 4}
    assert len(context["hole_rows"]) == 1 and "pitch 32.0 mm" in context["hole_rows"][0]["description"]
    checks = {item["check"]: item["status"] for item in context["plausibility_findings"]}
    assert checks["hole_row_drilling_system"] == "pass"
    assert checks["observed_thickness_in_catalog"] == "unknown"
    # Original keys stay as they were.
    assert {"drawing_id", "evidence_ids", "scenarios", "proposal_details", "line_linetypes"} <= set(context)


def test_inspecting_a_hole_row_returns_a_bounded_summary(tmp_path: Path) -> None:
    document = ezdxf.readfile(FIXTURE)
    for column in range(2):
        for row in range(30):
            document.modelspace().add_circle((-3000 + 400 * column, 32 * row), 2.5)
    path = tmp_path / "holes.dxf"
    document.saveas(path)
    extraction = extract_drawing(path)
    scenarios = derive_decomposition_scenarios(extraction)
    # Far from the views, circles are assigned to the nearest view label, so take the longest row.
    row = max((item for item in extraction.evidence if item.id.startswith("evidence-holes-")), key=lambda item: len(item.source_entity_ids))
    assert len(row.source_entity_ids) >= 10
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="c1", name="inspeccionar_evidencia", arguments={"evidence_ids": [row.id]}),)),
        _deliver(scenarios[0].id),
    ])

    run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5))
    raw = provider.inputs[1][0]["output"]
    output = json.loads(raw)

    assert len(raw) < 8000
    count = len(row.source_entity_ids)
    assert output["entity_counts"] == {"total": count, "shown": count, "truncated": False}
    first = output["entities"][0]
    assert first["kind"] == "CIRCLE" and first["diameter"] == pytest.approx(5.0) and "source_points" not in first


def test_prompt_explains_new_digest_keys_and_keeps_no_vision_default() -> None:
    assert SYSTEM_PROMPT == system_prompt(False)
    assert "No recibes imágenes" in SYSTEM_PROMPT and "visualizar_vista" not in SYSTEM_PROMPT
    for key in ("digest_counts", "plausibility_findings", "hole_rows", "untrusted_layer_counts"):
        assert key in SYSTEM_PROMPT
    assert "No recibes imágenes" not in system_prompt(True) and "visualizar_vista" in system_prompt(True)


def test_provider_settings_read_token_budget_and_vision_flag(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("VEXPLORER_AGENT_VISION", raising=False)
    default = ProviderSettings.from_env()
    assert default.max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS and default.vision_enabled is False

    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "8000")
    monkeypatch.setenv("VEXPLORER_AGENT_VISION", "1")
    configured = ProviderSettings.from_env()
    assert configured.max_output_tokens == 8000 and configured.vision_enabled is True

    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "nope")
    assert ProviderSettings.from_env().max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS


def _provider(handler, vision: bool = False) -> OpenAIResponsesProvider:
    settings = ProviderSettings(api_key="test", model="test-model", base_url="https://example.invalid/v1", max_output_tokens=3000, vision_enabled=vision)
    return OpenAIResponsesProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_provider_sends_configured_budget_and_prompt() -> None:
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "resp-1", "status": "completed", "output": [{"type": "function_call", "call_id": "c1", "name": "entregar_despiece", "arguments": "{\"scenario_id\": \"s\"}"}]})

    response = _provider(handler, vision=True).create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=5)

    assert sent["max_output_tokens"] == 3000
    assert sent["instructions"] == system_prompt(True)
    assert response.tool_calls[0].name == "entregar_despiece"


def test_provider_reports_why_a_response_was_incomplete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "resp-1", "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": [
            {"type": "function_call", "call_id": "c1", "name": "entregar_despiece", "arguments": "{\"scenario_"},
        ]})

    with pytest.raises(RuntimeError, match="provider_response_incomplete:max_output_tokens"):
        _provider(handler).create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=5)
