from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

from backend.app.agente.tools import tool_schemas
from backend.app.contratos.modelos import DecompositionScenario, DrawingExtraction, ExplainPieceArgs, InspectEvidenceArgs, SelectScenarioArgs
from backend.app.servicios.explanations import explain_proposal
from pydantic import ValidationError


class Provider(Protocol):
    def create_response(self, *, input_items, tools, previous_response_id, timeout_s): ...


@dataclass(frozen=True)
class AgentLimits:
    max_model_calls: int = 15
    max_tool_calls: int = 30
    timeout_s: float = 120
    max_validation_repairs: int = 2


@dataclass(frozen=True)
class AgentAction:
    tool_name: str
    ok: bool
    evidence_ids: tuple[str, ...]
    summary: str
    selected_scenario_id: str | None = None


@dataclass(frozen=True)
class AgentOutcome:
    selected_scenario_id: str
    model_calls: int
    tool_calls: int
    actions: tuple[AgentAction, ...]


MAX_DIGEST_ITEMS = 60
MAX_TEXT_CHARS = 120
MAX_VALID_IDS = 100


def _initial_context(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...]) -> dict:
    """Ledger digest for the first message; the keys that existed before are unchanged, the rest is additive.

    Drawing text is untrusted data and is kept apart under its own key; nothing here comes from private references.
    """
    linetypes: dict[str, int] = {}
    for entity in extraction.entities:
        if entity.kind == "LINE":
            name = entity.linetype or "UNKNOWN"
            linetypes[name] = linetypes.get(name, 0) + 1
    return {
        "drawing_id": extraction.drawing_id, "status": extraction.status, "warnings": extraction.warnings,
        "evidence_ids": [item.id for item in extraction.evidence], "result_revision": 1,
        "scenarios": [{"id": item.id, "title": item.title, "assumptions": item.assumptions, "components": [{"id": component.id, "role": component.role, "label": component.label} for component in item.components]} for item in scenarios],
        "source_unit": extraction.source_unit,
        "views": [{"id": item.id, "label": item.label, "bounds_mm": item.bounds_mm.model_dump(mode="json") if item.bounds_mm else None} for item in extraction.views],
        "dimensions": [{"id": item.id, "kind": item.kind, "value_mm": item.value_mm, "view_id": item.view_id, "evidence_ids": item.evidence_ids} for item in extraction.dimensions[:MAX_DIGEST_ITEMS]],
        "evidence_catalog": [{"id": item.id, "kind": item.kind, "description": item.description} for item in extraction.evidence[:MAX_DIGEST_ITEMS]],
        "line_linetypes": linetypes,
        "untrusted_drawing_text": [{"id": item.id, "view_id": item.view_id, "text": item.text[:MAX_TEXT_CHARS]} for item in extraction.texts[:MAX_DIGEST_ITEMS]],
        "proposal_details": [{"id": component.id, "scenario_id": item.id, "quantity": component.quantity, "length_mm": component.length_mm, "width_mm": component.width_mm, "length_derivation": component.length_derivation, "length_basis_mm": component.length_basis_mm, "observed_thickness_mm": component.observed_thickness_mm, "unconfirmed_thickness": component.thickness_mm is None} for item in scenarios for component in item.components],
    }


def _valid_ids(values) -> list[str]:
    return sorted(values)[:MAX_VALID_IDS]


def run_agent(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], provider: Provider, limits: AgentLimits = AgentLimits()) -> AgentOutcome:
    started = time.monotonic()
    model_calls = 0
    tool_calls = 0
    previous_response_id = None
    input_items = [{"role": "user", "content": json.dumps(_initial_context(extraction, scenarios), ensure_ascii=False)}]
    evidence = {item.id: item for item in extraction.evidence}
    entities = {item.id: item for item in extraction.entities}
    scenario_ids = {item.id for item in scenarios}
    proposals = {proposal.id: (scenario, proposal) for scenario in scenarios for proposal in scenario.components}
    repairs = 0
    actions: list[AgentAction] = []
    while model_calls < limits.max_model_calls:
        remaining = limits.timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("agent_deadline_exceeded")
        model_calls += 1
        response = provider.create_response(input_items=input_items, tools=tool_schemas(), previous_response_id=previous_response_id, timeout_s=remaining)
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes usar una herramienta permitida: " + ", ".join(tool["name"] for tool in tool_schemas()) + ". Termina con entregar_despiece y un scenario_id existente."}]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise RuntimeError("tool_call_budget_exhausted")
        outputs = []
        for call in response.tool_calls:
            tool_calls += 1
            try:
                arguments = json.loads(call.arguments_json) if call.arguments_json is not None else call.arguments
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                if call.name == "inspeccionar_evidencia":
                    args = InspectEvidenceArgs.model_validate_json(json.dumps(arguments), strict=True)
                    unknown = [item for item in args.evidence_ids if item not in evidence]
                    source_ids = {source_id for item in args.evidence_ids if item in evidence for source_id in evidence[item].source_entity_ids}
                    data = {
                        "ok": not unknown, "error": "unknown_reference" if unknown else None,
                        **({"unknown_ids": unknown, "valid_evidence_ids": _valid_ids(evidence)} if unknown else {}),
                        "evidence": [evidence[item].model_dump(mode="json") for item in args.evidence_ids if item in evidence],
                        "entities": [entities[item].model_dump(mode="json") for item in source_ids if item in entities],
                        "contours": [item.model_dump(mode="json") for item in extraction.contours if set(item.source_entity_ids) & source_ids],
                        "dimensions": [item.model_dump(mode="json") for item in extraction.dimensions if set(item.evidence_ids) & set(args.evidence_ids)],
                    }
                    actions.append(AgentAction(tool_name=call.name, ok=not unknown, evidence_ids=tuple(item for item in args.evidence_ids if item in evidence), summary="Evidencia vectorial del ledger inspeccionada." if not unknown else "Referencia de evidencia desconocida rechazada."))
                elif call.name == "explicar_pieza":
                    args = ExplainPieceArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if args.result_revision != 1:
                        data = {"ok": False, "error": "revision_not_available"}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Revisión no disponible en este bucle rechazada."))
                    elif args.piece_id not in proposals:
                        data = {"ok": False, "error": "unknown_reference", "valid_piece_ids": _valid_ids(proposals)}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Propuesta desconocida rechazada."))
                    else:
                        scenario, proposal = proposals[args.piece_id]
                        explanation = explain_proposal(extraction, scenario, proposal)
                        data = {"ok": True, "explanation": explanation.model_dump(mode="json")}
                        actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=explanation.evidence_ids, summary="Explicación determinista de hipótesis consultada."))
                elif call.name == "entregar_despiece":
                    args = SelectScenarioArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if args.scenario_id not in scenario_ids:
                        data = {"ok": False, "error": "unknown_reference", "valid_scenario_ids": _valid_ids(scenario_ids)}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Escenario desconocido rechazado."))
                    else:
                        actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=(), summary="Escenario hipotético entregado para revisión humana.", selected_scenario_id=args.scenario_id))
                        return AgentOutcome(selected_scenario_id=args.scenario_id, model_calls=model_calls, tool_calls=tool_calls, actions=tuple(actions))
                else:
                    data = {"ok": False, "error": "unknown_tool"}
                    actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Herramienta no autorizada rechazada."))
            except (ValidationError, json.JSONDecodeError, TypeError) as exc:
                repairs += 1
                details = exc.errors(include_url=False, include_input=False) if isinstance(exc, ValidationError) else []
                data = {"ok": False, "error": "invalid_arguments", "details": details}
                actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Argumentos de herramienta inválidos rechazados."))
                if repairs > limits.max_validation_repairs:
                    raise RuntimeError("validation_repair_budget_exhausted") from exc
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
        input_items = outputs
    raise RuntimeError("model_call_budget_exhausted")
