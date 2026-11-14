from __future__ import annotations

import json
import hashlib
import time
from base64 import b64encode
from dataclasses import dataclass, replace
from typing import Protocol

from backend.app.agente.tools import parts_tool_schemas, table_tool_schemas, tool_schemas
from backend.app.agente.vision import render_view
from backend.app.validador.plausibilidad import evaluate_plausibility
from backend.app.contratos.modelos import (
    AssemblyCandidate,
    DecompositionScenario,
    DrawingExtraction,
    ExplainPieceArgs,
    InspectEvidenceArgs,
    ListEvidenceArgs,
    InspectSeparatedPartArgs,
    InspectTableMeasuresArgs,
    MountedTableAnalysis,
    ProposeTableProgramArgs,
    SelectAssemblyCandidateArgs,
    SelectScenarioArgs,
    SeparatedPartsExtraction,
    TableProgramProposal,
    VisualizeTableViewArgs,
)
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
    artifact_sha256: str | None = None
    mark_count: int | None = None
    view_id: str | None = None
    provider_response_id: str | None = None
    provider_model: str | None = None
    provider_call_id: str | None = None
    provider_duration_ms: int | None = None
    provider_input_tokens: int | None = None
    provider_output_tokens: int | None = None
    provider_total_tokens: int | None = None


@dataclass(frozen=True)
class AgentOutcome:
    selected_scenario_id: str
    model_calls: int
    tool_calls: int
    actions: tuple[AgentAction, ...]


@dataclass(frozen=True)
class PartsAgentOutcome:
    selected_assembly_candidate_id: str
    model_calls: int
    tool_calls: int
    actions: tuple[AgentAction, ...]


@dataclass(frozen=True)
class TableAgentOutcome:
    program: TableProgramProposal
    model_calls: int
    tool_calls: int
    actions: tuple[AgentAction, ...]


def _valid_reference_details(values, limit: int = 50) -> dict:
    ordered = sorted(set(values))
    return {"valid_ids": ordered[:limit], "valid_ids_total": len(ordered), "valid_ids_truncated": len(ordered) > limit}


def _remaining_time(started: float, timeout_s: float) -> float:
    remaining = timeout_s - (time.monotonic() - started)
    if remaining <= 0:
        raise TimeoutError("agent_deadline_exceeded")
    return remaining


def _safe_trace_text(value, limit: int = 128) -> str | None:
    return value if isinstance(value, str) and value and len(value) <= limit else None


def _safe_trace_count(value, maximum: int = 1_000_000_000) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum else None


def _attach_provider_metadata(actions: list[AgentAction], start: int, response, call) -> None:
    metadata = {
        "provider_response_id": _safe_trace_text(getattr(response, "id", None)),
        "provider_model": _safe_trace_text(getattr(response, "model", None)),
        "provider_call_id": _safe_trace_text(getattr(call, "call_id", None), 256),
        "provider_duration_ms": _safe_trace_count(getattr(response, "duration_ms", None), 86_400_000),
        "provider_input_tokens": _safe_trace_count(getattr(response, "input_tokens", None)),
        "provider_output_tokens": _safe_trace_count(getattr(response, "output_tokens", None)),
        "provider_total_tokens": _safe_trace_count(getattr(response, "total_tokens", None)),
    }
    actions[start:] = [replace(action, **metadata) for action in actions[start:]]


def run_agent(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], provider: Provider, limits: AgentLimits = AgentLimits()) -> AgentOutcome:
    started = time.monotonic()
    model_calls = 0
    tool_calls = 0
    previous_response_id = None
    shown_evidence_ids = [item.id for item in extraction.evidence[:200]]
    input_items = [{"role": "user", "content": json.dumps({"drawing_id": extraction.drawing_id, "status": extraction.status, "warnings": extraction.warnings, "evidence_ids": shown_evidence_ids, "evidence_counts": {"total": len(extraction.evidence), "shown": len(shown_evidence_ids), "truncated": len(extraction.evidence) > len(shown_evidence_ids)}, "result_revision": 1, "scenarios": [{"id": item.id, "title": item.title, "assumptions": item.assumptions, "components": [{"id": component.id, "role": component.role, "label": component.label} for component in item.components]} for item in scenarios]}, ensure_ascii=False)}]
    evidence = {item.id: item for item in extraction.evidence}
    entities = {item.id: item for item in extraction.entities}
    scenario_ids = {item.id for item in scenarios}
    proposals = {proposal.id: (scenario, proposal) for scenario in scenarios for proposal in scenario.components}
    repairs = 0
    actions: list[AgentAction] = []
    while model_calls < limits.max_model_calls:
        remaining = _remaining_time(started, limits.timeout_s)
        model_calls += 1
        try:
            response = provider.create_response(input_items=input_items, tools=tool_schemas(), previous_response_id=previous_response_id, timeout_s=remaining)
        except Exception:
            _remaining_time(started, limits.timeout_s)
            raise
        _remaining_time(started, limits.timeout_s)
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes usar una herramienta permitida."}]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise RuntimeError("tool_call_budget_exhausted")
        outputs = []
        for call in response.tool_calls:
            _remaining_time(started, limits.timeout_s)
            action_start = len(actions)
            tool_calls += 1
            try:
                arguments = json.loads(call.arguments_json) if call.arguments_json is not None else call.arguments
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                if call.name == "listar_evidencias":
                    args = ListEvidenceArgs.model_validate_json(json.dumps(arguments), strict=True)
                    filtered = sorted((item for item in evidence.values() if args.kind is None or item.kind == args.kind), key=lambda item: item.id)
                    page = filtered[args.cursor:args.cursor + args.limit]
                    next_cursor = args.cursor + len(page) if args.cursor + len(page) < len(filtered) else None
                    data = {"ok": True, "items": [{"id": item.id, "kind": item.kind, "description": item.description[:200]} for item in page], "cursor": args.cursor, "next_cursor": next_cursor, "total": len(filtered)}
                    actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=tuple(item.id for item in page), summary="Página de evidencias del ledger listada."))
                elif call.name == "inspeccionar_evidencia":
                    args = InspectEvidenceArgs.model_validate_json(json.dumps(arguments), strict=True)
                    unknown = [item for item in args.evidence_ids if item not in evidence]
                    source_ids = {source_id for item in args.evidence_ids if item in evidence for source_id in evidence[item].source_entity_ids}
                    data = {
                        "ok": not unknown, "error": "unknown_reference" if unknown else None,
                        "evidence": [evidence[item].model_dump(mode="json") for item in args.evidence_ids if item in evidence],
                        "entities": [entities[item].model_dump(mode="json") for item in source_ids if item in entities],
                        "contours": [item.model_dump(mode="json") for item in extraction.contours if set(item.source_entity_ids) & source_ids],
                        "dimensions": [item.model_dump(mode="json") for item in extraction.dimensions if set(item.evidence_ids) & set(args.evidence_ids)],
                    }
                    if unknown:
                        data["details"] = _valid_reference_details(evidence)
                    actions.append(AgentAction(tool_name=call.name, ok=not unknown, evidence_ids=tuple(item for item in args.evidence_ids if item in evidence), summary="Evidencia vectorial del ledger inspeccionada." if not unknown else "Referencia de evidencia desconocida rechazada."))
                elif call.name == "explicar_pieza":
                    args = ExplainPieceArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if args.result_revision != 1:
                        data = {"ok": False, "error": "revision_not_available"}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Revisión no disponible en este bucle rechazada."))
                    elif args.piece_id not in proposals:
                        data = {"ok": False, "error": "unknown_reference", "details": _valid_reference_details(proposals)}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Propuesta desconocida rechazada."))
                    else:
                        scenario, proposal = proposals[args.piece_id]
                        explanation = explain_proposal(extraction, scenario, proposal)
                        data = {"ok": True, "explanation": explanation.model_dump(mode="json")}
                        actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=explanation.evidence_ids, summary="Explicación determinista de hipótesis consultada."))
                elif call.name == "entregar_despiece":
                    args = SelectScenarioArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if args.scenario_id not in scenario_ids:
                        data = {"ok": False, "error": "unknown_reference", "details": _valid_reference_details(scenario_ids)}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Escenario desconocido rechazado."))
                    else:
                        actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=(), summary="Escenario hipotético entregado para revisión humana.", selected_scenario_id=args.scenario_id))
                        _remaining_time(started, limits.timeout_s)
                        _attach_provider_metadata(actions, action_start, response, call)
                        return AgentOutcome(selected_scenario_id=args.scenario_id, model_calls=model_calls, tool_calls=tool_calls, actions=tuple(actions))
                else:
                    data = {"ok": False, "error": "unknown_tool"}
                    actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Herramienta no autorizada rechazada."))
            except (ValidationError, json.JSONDecodeError, TypeError) as exc:
                repairs += 1
                details = exc.errors(include_url=False, include_input=False) if isinstance(exc, ValidationError) else []
                data = {"ok": False, "error": "invalid_arguments", "details": details}
                actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Argumentos de herramienta inválidos rechazados."))
                _remaining_time(started, limits.timeout_s)
                if repairs > limits.max_validation_repairs:
                    raise RuntimeError("validation_repair_budget_exhausted") from exc
            _remaining_time(started, limits.timeout_s)
            _attach_provider_metadata(actions, action_start, response, call)
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
        input_items = outputs
    raise RuntimeError("model_call_budget_exhausted")


def run_parts_agent(
    extraction: DrawingExtraction,
    parts: SeparatedPartsExtraction,
    candidates: tuple[AssemblyCandidate, ...],
    provider: Provider,
    limits: AgentLimits = AgentLimits(),
) -> PartsAgentOutcome:
    started = time.monotonic()
    model_calls = 0
    tool_calls = 0
    repairs = 0
    previous_response_id = None
    observations = {item.id: item for item in parts.observations}
    candidate_ids = {item.id for item in candidates}
    input_items = [{"role": "user", "content": json.dumps({
        "input_kind": "separated_part_views",
        "candidate_revision": parts.candidate_revision,
        "warnings": parts.warnings,
        "part_observations": [{
            "id": item.id,
            "association_basis": item.association_basis,
            "view_roles": [view.role for view in item.views],
            "quantity_state": item.quantity.state,
            "status": item.status,
        } for item in parts.observations],
        "assembly_candidates": [{
            "id": item.id,
            "family": item.family,
            "layout": item.layout,
            "uses": [{
                "id": use.id,
                "part_observation_id": use.part_observation_id,
                "role": use.role,
                "allocated_quantity": use.allocated_quantity,
            } for use in item.uses],
            "unassigned_part_observation_ids": item.unassigned_part_observation_ids,
            "assumptions": item.assumptions,
            "needs_review": item.needs_review,
        } for item in candidates],
    }, ensure_ascii=False)}]
    actions: list[AgentAction] = []
    while model_calls < limits.max_model_calls:
        remaining = _remaining_time(started, limits.timeout_s)
        model_calls += 1
        try:
            response = provider.create_response(
                input_items=input_items,
                tools=parts_tool_schemas(),
                previous_response_id=previous_response_id,
                timeout_s=remaining,
            )
        except Exception:
            _remaining_time(started, limits.timeout_s)
            raise
        _remaining_time(started, limits.timeout_s)
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes usar una herramienta permitida."}]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise RuntimeError("tool_call_budget_exhausted")
        outputs = []
        for call in response.tool_calls:
            _remaining_time(started, limits.timeout_s)
            action_start = len(actions)
            tool_calls += 1
            try:
                arguments = json.loads(call.arguments_json) if call.arguments_json is not None else call.arguments
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                if call.name == "inspeccionar_pieza":
                    args = InspectSeparatedPartArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if args.candidate_revision != parts.candidate_revision:
                        data = {"ok": False, "error": "candidate_revision_mismatch"}
                        actions.append(AgentAction(call.name, False, (), "Revisión candidata ajena al ledger rechazada."))
                    elif args.part_observation_id not in observations:
                        data = {"ok": False, "error": "unknown_reference", "details": _valid_reference_details(observations)}
                        actions.append(AgentAction(call.name, False, (), "Observación de pieza desconocida rechazada."))
                    else:
                        observation = observations[args.part_observation_id]
                        data = {"ok": True, "part_observation": observation.model_dump(mode="json")}
                        actions.append(AgentAction(call.name, True, observation.evidence_ids, "Observación de pieza y sus fuentes inspeccionadas."))
                elif call.name == "entregar_candidato_montaje":
                    args = SelectAssemblyCandidateArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if args.candidate_revision != parts.candidate_revision:
                        data = {"ok": False, "error": "candidate_revision_mismatch"}
                        actions.append(AgentAction(call.name, False, (), "Revisión candidata ajena al ledger rechazada."))
                    elif args.assembly_candidate_id not in candidate_ids:
                        data = {"ok": False, "error": "unknown_reference", "details": _valid_reference_details(candidate_ids)}
                        actions.append(AgentAction(call.name, False, (), "Candidato de montaje desconocido rechazado."))
                    else:
                        actions.append(AgentAction(
                            call.name, True, (), "Candidato hipotético entregado para revisión humana.",
                            selected_scenario_id=args.assembly_candidate_id,
                        ))
                        _remaining_time(started, limits.timeout_s)
                        _attach_provider_metadata(actions, action_start, response, call)
                        return PartsAgentOutcome(args.assembly_candidate_id, model_calls, tool_calls, tuple(actions))
                else:
                    data = {"ok": False, "error": "unknown_tool"}
                    actions.append(AgentAction(call.name, False, (), "Herramienta no autorizada rechazada."))
            except (ValidationError, json.JSONDecodeError, TypeError) as exc:
                repairs += 1
                details = exc.errors(include_url=False, include_input=False) if isinstance(exc, ValidationError) else []
                data = {"ok": False, "error": "invalid_arguments", "details": details}
                actions.append(AgentAction(call.name, False, (), "Argumentos de herramienta inválidos rechazados."))
                _remaining_time(started, limits.timeout_s)
                if repairs > limits.max_validation_repairs:
                    raise RuntimeError("validation_repair_budget_exhausted") from exc
            _remaining_time(started, limits.timeout_s)
            _attach_provider_metadata(actions, action_start, response, call)
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
        input_items = outputs
    raise RuntimeError("model_call_budget_exhausted")


def run_table_agent(
    extraction: DrawingExtraction,
    analysis: MountedTableAnalysis,
    provider: Provider,
    limits: AgentLimits = AgentLimits(),
    *,
    vision_enabled: bool = False,
) -> TableAgentOutcome:
    if extraction.drawing_id != analysis.drawing_id or extraction.input_kind != "mounted_orthographic_views":
        raise ValueError("table_analysis_scope_mismatch")
    started = time.monotonic()
    model_calls = 0
    tool_calls = 0
    repairs = 0
    previous_response_id = None
    measures = {item.id: item for item in analysis.measures}
    entities = {item.id: item for item in extraction.entities}
    views = {item.id: item for item in extraction.views}
    allowed_evidence_ids = {evidence_id for item in analysis.measures for evidence_id in item.evidence_ids}
    try:
        plausibility_findings = evaluate_plausibility(extraction)
    except (FileNotFoundError, ValueError):
        plausibility_findings = ()
    context = {
        "input_kind": analysis.input_kind,
        "profile": analysis.profile,
        "ledger_revision": analysis.ledger_revision,
        "state": analysis.state,
        "warnings": analysis.warnings,
        "measurements": [{"id": item.id, "semantic": item.semantic, "axis": item.axis, "state": item.state, "slot_origin": item.slot_origin} for item in analysis.measures],
        "plausibility": {
            "findings": plausibility_findings[:20],
            "total": len(plausibility_findings),
            "truncated": len(plausibility_findings) > 20,
            "authority": "advisory_workshop_catalog_not_measurement_source",
        },
    }
    actions: list[AgentAction] = []
    visualized_view_ids: set[str] = set()
    vision_calls = 0
    visual_view_ids: set[str] = set()
    if vision_enabled:
        label_order = {"FRONT": 0, "TOP": 1, "SIDE": 2, "UNKNOWN": 3}
        selected_views = sorted(extraction.views, key=lambda item: (label_order[item.label], item.id))[:3]
        if not selected_views:
            raise RuntimeError("vision_geometry_unavailable")
        visual_view_ids = {item.id for item in selected_views}
        context["vision"] = {
            "authority": "context_only_not_measurement_source",
            "available_views": [{"view_id": item.id, "label": item.label} for item in selected_views],
            "instruction": "Solicita visualizar_vista por ID cuando el contexto visual ayude; usa las herramientas vectoriales para cualquier medida.",
        }
    input_items = [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
    while model_calls < limits.max_model_calls:
        remaining = _remaining_time(started, limits.timeout_s)
        model_calls += 1
        try:
            response = provider.create_response(input_items=input_items, tools=table_tool_schemas(include_vision=vision_enabled), previous_response_id=previous_response_id, timeout_s=remaining)
        except Exception:
            _remaining_time(started, limits.timeout_s)
            raise
        _remaining_time(started, limits.timeout_s)
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes inspeccionar IDs o proponer un programa mediante una herramienta permitida."}]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise RuntimeError("tool_call_budget_exhausted")
        outputs = []
        visual_inputs = []
        for call in response.tool_calls:
            _remaining_time(started, limits.timeout_s)
            action_start = len(actions)
            tool_calls += 1
            try:
                arguments = json.loads(call.arguments_json) if call.arguments_json is not None else call.arguments
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                if call.name == "inspeccionar_medidas_mesa":
                    args = InspectTableMeasuresArgs.model_validate_json(json.dumps(arguments), strict=True)
                    unknown = [item for item in args.measurement_ids if item not in measures]
                    selected = [measures[item] for item in args.measurement_ids if item in measures]
                    source_entity_ids = {entity_id for item in selected for entity_id in item.source_entity_ids}
                    source_view_ids = {view_id for item in selected for view_id in item.view_ids}
                    data = {
                        "ok": not unknown,
                        "error": "unknown_reference" if unknown else None,
                        "measures": [item.model_dump(mode="json") for item in selected],
                        "source_entities": [entities[item].model_dump(mode="json") for item in sorted(source_entity_ids) if item in entities],
                        "views": [views[item].model_dump(mode="json") for item in sorted(source_view_ids) if item in views],
                    }
                    if unknown:
                        data["details"] = _valid_reference_details(measures)
                    actions.append(AgentAction(call.name, not unknown, tuple(evidence_id for item in selected for evidence_id in item.evidence_ids), "Medidas y fuentes del ledger inspeccionadas." if not unknown else "Referencia de medida desconocida rechazada."))
                elif call.name == "visualizar_vista" and vision_enabled:
                    vision_calls += 1
                    args = VisualizeTableViewArgs.model_validate_json(json.dumps(arguments), strict=True)
                    if vision_calls > 3:
                        data = {"ok": False, "error": "vision_call_budget_exhausted"}
                        actions.append(AgentAction(call.name, False, (), "Presupuesto de llamadas visuales agotado."))
                    elif args.view_id not in visual_view_ids:
                        data = {"ok": False, "error": "unknown_reference", "details": _valid_reference_details(visual_view_ids)}
                        actions.append(AgentAction(call.name, False, (), "Referencia de vista desconocida rechazada."))
                    elif args.view_id in visualized_view_ids:
                        data = {"ok": False, "error": "view_already_visualized"}
                        actions.append(AgentAction(call.name, False, (), "Vista ya visualizada en esta ejecución."))
                    else:
                        try:
                            artifact = render_view(extraction, args.view_id)
                        except ValueError as exc:
                            code = str(exc) if str(exc) in {"unknown_view", "vision_budget_exceeded", "vision_geometry_unavailable"} else "vision_geometry_unavailable"
                            data = {"ok": False, "error": code}
                            actions.append(AgentAction(call.name, False, (), "No se pudo renderizar la vista solicitada dentro de los límites."))
                            _remaining_time(started, limits.timeout_s)
                            _attach_provider_metadata(actions, action_start, response, call)
                            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
                            continue
                        visualized_view_ids.add(args.view_id)
                        marks = [
                            {"mark_id": mark.mark_id, "source_kind": mark.source_kind, "source_id": mark.source_id}
                            for mark in artifact.marks
                        ]
                        data = {
                            "ok": True,
                            "view_id": artifact.view_id,
                            "sha256": artifact.sha256,
                            "width_px": artifact.width_px,
                            "height_px": artifact.height_px,
                            "marks": marks,
                            "authority": "context_only_not_measurement_source",
                        }
                        visual_inputs.append({"role": "user", "content": [
                            {"type": "input_text", "text": json.dumps({"view_id": artifact.view_id, "sha256": artifact.sha256, "marks": marks, "authority": "context_only_not_measurement_source"}, ensure_ascii=False)},
                            {"type": "input_image", "image_url": f"data:{artifact.media_type};base64,{b64encode(artifact.png).decode('ascii')}", "detail": "high"},
                        ]})
                        actions.append(AgentAction(
                            call.name, True, (),
                            "Vista PNG Set-of-Mark solicitada y derivada del ledger; no es fuente de medidas.",
                            artifact_sha256=artifact.sha256,
                            mark_count=len(artifact.marks),
                            view_id=artifact.view_id,
                        ))
                elif call.name == "proponer_descomposicion":
                    if vision_enabled and not visualized_view_ids:
                        data = {"ok": False, "error": "visual_context_required"}
                        actions.append(AgentAction(call.name, False, (), "El opt-in visual exige inspeccionar al menos una vista antes de proponer."))
                        _remaining_time(started, limits.timeout_s)
                        _attach_provider_metadata(actions, action_start, response, call)
                        outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
                        continue
                    args = ProposeTableProgramArgs.model_validate_json(json.dumps(arguments), strict=True)
                    referenced_measures = {operand.ref_id for binding in args.bindings for operand in binding.operand_refs if operand.ref_type == "measure"}
                    referenced_evidence = set(args.evidence_ids) | {evidence_id for component in args.components for evidence_id in component.evidence_ids}
                    if not referenced_measures <= set(measures) or not referenced_evidence <= allowed_evidence_ids:
                        data = {"ok": False, "error": "unknown_reference", "details": {"measurements": _valid_reference_details(measures), "evidence": _valid_reference_details(allowed_evidence_ids)}}
                        actions.append(AgentAction(call.name, False, (), "Programa con referencias ajenas al ledger rechazado."))
                    else:
                        canonical_args = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                        program = TableProgramProposal(
                            id=f"table-program-{hashlib.sha256(canonical_args.encode('utf-8')).hexdigest()[:16]}",
                            ledger_revision=analysis.ledger_revision,
                            proposal_origin="model_generated",
                            **args.model_dump(),
                        )
                        actions.append(AgentAction(call.name, True, tuple(sorted(referenced_evidence)), "Programa de descomposición referenciado entregado para validación y revisión."))
                        _remaining_time(started, limits.timeout_s)
                        _attach_provider_metadata(actions, action_start, response, call)
                        return TableAgentOutcome(program, model_calls, tool_calls, tuple(actions))
                else:
                    data = {"ok": False, "error": "unknown_tool"}
                    actions.append(AgentAction(call.name, False, (), "Herramienta no autorizada rechazada."))
            except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
                repairs += 1
                details = exc.errors(include_url=False, include_input=False) if isinstance(exc, ValidationError) else []
                data = {"ok": False, "error": "invalid_arguments", "details": details}
                actions.append(AgentAction(call.name, False, (), "Argumentos de herramienta inválidos rechazados."))
                _remaining_time(started, limits.timeout_s)
                if repairs > limits.max_validation_repairs:
                    raise RuntimeError("validation_repair_budget_exhausted") from exc
            _remaining_time(started, limits.timeout_s)
            _attach_provider_metadata(actions, action_start, response, call)
            outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(data, ensure_ascii=False)})
        input_items = [*outputs, *visual_inputs]
    raise RuntimeError("model_call_budget_exhausted")
