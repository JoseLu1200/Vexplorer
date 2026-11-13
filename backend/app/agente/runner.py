from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

from backend.app.agente.tools import tool_schemas
from backend.app.contratos.modelos import DecompositionScenario, DrawingExtraction, InspectEvidenceArgs, SelectScenarioArgs


class Provider(Protocol):
    def create_response(self, *, input_items, tools, previous_response_id, timeout_s): ...


@dataclass(frozen=True)
class AgentLimits:
    max_model_calls: int = 15
    max_tool_calls: int = 30
    timeout_s: float = 120


@dataclass(frozen=True)
class AgentOutcome:
    selected_scenario_id: str
    model_calls: int
    tool_calls: int


def run_agent(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], provider: Provider, limits: AgentLimits = AgentLimits()) -> AgentOutcome:
    started = time.monotonic()
    model_calls = 0
    tool_calls = 0
    previous_response_id = None
    input_items = [{"role": "user", "content": json.dumps({"drawing_id": extraction.drawing_id, "status": extraction.status, "warnings": extraction.warnings, "evidence_ids": [item.id for item in extraction.evidence], "scenarios": [{"id": item.id, "title": item.title, "assumptions": item.assumptions, "component_roles": [component.role for component in item.components]} for item in scenarios]}, ensure_ascii=False)}]
    evidence = {item.id: item for item in extraction.evidence}
    scenario_ids = {item.id for item in scenarios}
    while model_calls < limits.max_model_calls:
        remaining = limits.timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("agent_deadline_exceeded")
        model_calls += 1
        response = provider.create_response(input_items=input_items, tools=tool_schemas(), previous_response_id=previous_response_id, timeout_s=remaining)
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes usar una herramienta permitida."}]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise RuntimeError("tool_call_budget_exhausted")
        outputs = []
        for call in response.tool_calls:
            tool_calls += 1
            if call.name == "inspeccionar_evidencia":
                args = InspectEvidenceArgs.model_validate(call.arguments)
                unknown = [item for item in args.evidence_ids if item not in evidence]
                data = {"ok": not unknown, "error": "unknown_reference" if unknown else None, "evidence": [evidence[item].model_dump(mode="json") for item in args.evidence_ids if item in evidence]}
            elif call.name == "seleccionar_escenario":
                args = SelectScenarioArgs.model_validate(call.arguments)
                if args.scenario_id not in scenario_ids:
                    data = {"ok": False, "error": "unknown_reference"}
                else:
                    return AgentOutcome(selected_scenario_id=args.scenario_id, model_calls=model_calls, tool_calls=tool_calls)
            else:
                data = {"ok": False, "error": "unknown_tool"}
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
        input_items = outputs
    raise RuntimeError("model_call_budget_exhausted")
