from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits, run_agent
from backend.app.agente.tools import tool_schemas
from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios


class FakeProvider:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        return self.responses.pop(0)


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
