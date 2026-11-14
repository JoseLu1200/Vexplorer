from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx

from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.prompts import SYSTEM_PROMPT
from backend.app.agente.runner import AgentLimits, run_agent, run_parts_agent
from backend.app.agente.tools import parts_tool_schemas, table_tool_schemas, tool_schemas
from backend.app.contratos.modelos import InspectEvidenceArgs
from backend.app.geometria import extract_drawing
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.servicios.decomposition import derive_decomposition_scenarios


class FakeProvider:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.calls = 0
        self.inputs = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        self.inputs.append(input_items)
        return self.responses.pop(0)


def test_provider_uses_configured_output_budget_without_exposing_secrets() -> None:
    seen = {}

    def handler(request: httpx.Request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "response", "status": "completed", "output": []})

    settings = ProviderSettings(api_key="secret-test-key", model="gpt-test", base_url="https://example.test/v1", max_output_tokens=4096)
    provider = OpenAIResponsesProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=1)
    assert seen["max_output_tokens"] == 4096
    assert "secret-test-key" not in json.dumps(seen)
    assert ProviderSettings(api_key="key", model="model", max_output_tokens=999999999).available is False


def test_inspect_evidence_rejects_unbounded_id_batches() -> None:
    with pytest.raises(ValueError):
        InspectEvidenceArgs(evidence_ids=tuple(f"evidence-{index}" for index in range(51)))


def test_agent_uses_native_tools_against_current_ledger_only() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)
    before = extraction.model_dump_json()
    evidence_id = extraction.evidence[0].id
    provider = FakeProvider(
        [
            ProviderResponse(id="response-1", tool_calls=(ToolCall(call_id="call-1", name="inspeccionar_evidencia", arguments={"evidence_ids": [evidence_id]}),)),
            ProviderResponse(id="response-2", tool_calls=(ToolCall(call_id="call-2", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),)),
        ]
    )

    outcome = run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5))

    assert outcome.selected_scenario_id == scenarios[0].id
    assert outcome.model_calls == 2 and outcome.tool_calls == 2
    assert [action.tool_name for action in outcome.actions] == ["inspeccionar_evidencia", "entregar_despiece"]
    assert outcome.actions[0].evidence_ids == (evidence_id,)
    assert outcome.actions[-1].selected_scenario_id == scenarios[0].id
    assert extraction.model_dump_json() == before


def test_agent_enforces_call_budget_and_tool_schemas_have_no_filesystem_access() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)
    provider = FakeProvider([ProviderResponse(id="r1", tool_calls=()), ProviderResponse(id="r2", tool_calls=())])

    with pytest.raises(RuntimeError, match="model_call_budget_exhausted"):
        run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))

    schemas = tool_schemas()
    assert all(tool["strict"] is True for tool in schemas)
    assert all("path" not in str(tool).lower() and "file" not in str(tool).lower() for tool in schemas)


def test_all_native_tool_schemas_satisfy_recursive_strict_mode() -> None:
    schemas = tool_schemas() + parts_tool_schemas() + table_tool_schemas()

    def assert_strict(value) -> None:
        if isinstance(value, dict):
            assert "default" not in value
            if value.get("type") == "object" or "properties" in value:
                properties = value.get("properties", {})
                assert value.get("additionalProperties") is False
                assert set(value.get("required", ())) == set(properties)
            for nested in value.values():
                assert_strict(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_strict(nested)

    for schema in schemas:
        assert schema["strict"] is True
        assert_strict(schema["parameters"])

    propose = next(schema for schema in schemas if schema["name"] == "proponer_descomposicion")
    component_spec = propose["parameters"]["$defs"]["TableComponentSpec"]
    assert "quantity_rule_version" in component_spec["required"]
    assert "placement_rule_version" in component_spec["required"]


def test_agent_returns_safe_tool_error_for_malformed_json_then_repairs() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="bad", name="inspeccionar_evidencia", arguments_json="{not-json"),)),
        ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="good", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),)),
    ])

    outcome = run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))

    assert outcome.selected_scenario_id == scenarios[0].id
    assert outcome.actions[0].ok is False
    assert outcome.actions[0].summary == "Argumentos de herramienta inválidos rechazados."


def test_agent_explains_revision_one_hypothesis_with_deterministic_sources() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)
    proposal = scenarios[0].components[0]
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="explain", name="explicar_pieza", arguments={"piece_id": proposal.id, "result_revision": 1}),)),
        ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="deliver", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),)),
    ])

    outcome = run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))

    initial_context = json.loads(provider.inputs[0][0]["content"])
    assert initial_context["result_revision"] == 1
    assert {"id": proposal.id, "role": proposal.role, "label": proposal.label} in initial_context["scenarios"][0]["components"]
    tool_output = json.loads(provider.inputs[1][0]["output"])
    assert tool_output["ok"] is True
    explanation = tool_output["explanation"]
    assert explanation["proposal_id"] == proposal.id
    assert explanation["source_entity_ids"]
    assert explanation["premises"]
    assert "thickness_mm" in explanation["unknown_fields"]
    assert outcome.actions[0].tool_name == "explicar_pieza"
    assert outcome.actions[0].ok is True
    assert outcome.actions[0].summary == "Explicación determinista de hipótesis consultada."


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    [
        ({"piece_id": "proposal-missing", "result_revision": 1}, "unknown_reference"),
        ({"piece_id": "proposal-any", "result_revision": 2}, "revision_not_available"),
    ],
)
def test_agent_rejects_unknown_or_unavailable_explanation(arguments, expected_error) -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
    extraction = extract_drawing(fixture)
    scenarios = derive_decomposition_scenarios(extraction)
    provider = FakeProvider([
        ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="explain", name="explicar_pieza", arguments=arguments),)),
        ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="deliver", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),)),
    ])

    run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))

    tool_output = json.loads(provider.inputs[1][0]["output"])
    assert tool_output["ok"] is False and tool_output["error"] == expected_error
    if expected_error == "unknown_reference":
        assert tool_output["details"]["valid_ids"]
        assert tool_output["details"]["valid_ids_total"] == sum(len(item.components) for item in scenarios)


def test_parts_agent_inspects_grounded_part_and_selects_existing_candidate() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "piezas_completo.dxf"
    extraction = extract_drawing(fixture, input_kind="separated_part_views")
    parts = extract_separated_parts(extraction)
    candidates = derive_assembly_candidates(parts)
    observation = parts.observations[0]
    selected = candidates[0]
    provider = FakeProvider([
        ProviderResponse(id="parts-1", tool_calls=(ToolCall(
            call_id="inspect", name="inspeccionar_pieza",
            arguments={"candidate_revision": parts.candidate_revision, "part_observation_id": observation.id},
        ),)),
        ProviderResponse(id="parts-2", tool_calls=(ToolCall(
            call_id="select", name="entregar_candidato_montaje",
            arguments={"candidate_revision": parts.candidate_revision, "assembly_candidate_id": selected.id},
        ),)),
    ])

    outcome = run_parts_agent(extraction, parts, candidates, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))

    context = json.loads(provider.inputs[0][0]["content"])
    assert context["input_kind"] == "separated_part_views"
    assert {item["id"] for item in context["part_observations"]} == {item.id for item in parts.observations}
    assert context["assembly_candidates"][0]["id"] == candidates[0].id
    assert all("value_mm" not in item for item in context["assembly_candidates"])
    inspected = json.loads(provider.inputs[1][0]["output"])
    assert inspected["ok"] is True
    assert inspected["part_observation"]["id"] == observation.id
    assert inspected["part_observation"]["dimensions"]["length"]["value_mm"] is not None
    assert outcome.selected_assembly_candidate_id == selected.id
    assert [item.tool_name for item in outcome.actions] == ["inspeccionar_pieza", "entregar_candidato_montaje"]
    assert {item["name"] for item in parts_tool_schemas()} == {"inspeccionar_pieza", "entregar_candidato_montaje"}
    assert "vistas 2D de piezas separadas" in SYSTEM_PROMPT
    assert "no calculas medidas" in SYSTEM_PROMPT


def test_parts_agent_unknown_reference_returns_valid_observation_ids() -> None:
    fixture = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "piezas_completo.dxf"
    extraction = extract_drawing(fixture, input_kind="separated_part_views")
    parts = extract_separated_parts(extraction)
    candidates = derive_assembly_candidates(parts)
    provider = FakeProvider([
        ProviderResponse(id="parts-1", tool_calls=(ToolCall(call_id="bad", name="inspeccionar_pieza", arguments={"candidate_revision": parts.candidate_revision, "part_observation_id": "missing"}),)),
        ProviderResponse(id="parts-2", tool_calls=(ToolCall(call_id="select", name="entregar_candidato_montaje", arguments={"candidate_revision": parts.candidate_revision, "assembly_candidate_id": candidates[0].id}),)),
    ])
    run_parts_agent(extraction, parts, candidates, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))
    error = json.loads(provider.inputs[1][0]["output"])
    assert error["error"] == "unknown_reference"
    assert set(error["details"]["valid_ids"]) == {item.id for item in parts.observations}
