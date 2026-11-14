from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Protocol

from backend.app.agente.comparacion import compare_candidates
from backend.app.agente.tools import tool_schemas
from backend.app.agente.vision import render_view
from backend.app.contratos.modelos import CompareCandidatesArgs, DecompositionScenario, DrawingExtraction, ExplainPieceArgs, InspectEvidenceArgs, SelectScenarioArgs, VisualizeViewArgs
from backend.app.servicios.explanations import explain_proposal
from backend.app.validador.plausibilidad import WorkshopCatalog, check_plausibility
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
MAX_LAYER_NAME_CHARS = 40
MAX_EVIDENCE_IDS = 200
# Inspection payload bounds: a flattened circle is 65 points, so rows of holes or big blocks must be summarized.
MAX_INSPECT_ENTITIES = 40
MAX_INSPECT_CONTOURS = 20
MAX_INLINE_POINTS = 16


def _point_summary(points) -> dict:
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return {
        "point_count": len(points),
        "bounds": {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)},
        "first": points[0].model_dump(mode="json"), "last": points[-1].model_dump(mode="json"),
    }


def _entity_payload(entity) -> dict:
    """Full record for short entities; circles as center and diameter; long flattened curves as a bounded summary."""
    points = entity.points_mm if entity.points_mm is not None else entity.source_points
    unit = "mm" if entity.points_mm is not None else "source"
    if entity.kind == "CIRCLE" and len(points) >= 4:
        ring = points[:-1] if points[0] == points[-1] else points
        center_x = sum(point.x for point in ring) / len(ring)
        center_y = sum(point.y for point in ring) / len(ring)
        diameter = 2 * ((ring[0].x - center_x) ** 2 + (ring[0].y - center_y) ** 2) ** 0.5
        return {"id": entity.id, "kind": entity.kind, "layer": entity.layer, "linetype": entity.linetype, "unit": unit, "center": {"x": round(center_x, 6), "y": round(center_y, 6)}, "diameter": round(diameter, 6)}
    if len(points) > MAX_INLINE_POINTS:
        return {"id": entity.id, "kind": entity.kind, "layer": entity.layer, "linetype": entity.linetype, "unit": unit, **_point_summary(points)}
    return entity.model_dump(mode="json")


def _contour_payload(contour) -> dict:
    points = contour.points_mm if contour.points_mm is not None else contour.points_source
    if len(points) > MAX_INLINE_POINTS:
        return {"id": contour.id, "view_id": contour.view_id, "closed": contour.closed, "source_entity_ids": list(contour.source_entity_ids), "unit": "mm" if contour.points_mm is not None else "source", **_point_summary(points)}
    return contour.model_dump(mode="json")


def _shown(total: int, limit: int = MAX_DIGEST_ITEMS) -> dict:
    return {"total": total, "shown": min(total, limit), "truncated": total > limit}


def _evidence_with_prefix(extraction: DrawingExtraction, prefix: str) -> list[dict]:
    return [{"id": item.id, "description": item.description} for item in extraction.evidence if item.id.startswith(prefix)][:MAX_DIGEST_ITEMS]


def _aggregates(extraction: DrawingExtraction) -> dict:
    """Deterministic counts the model reasons about better than long lists. Layer names are drawing text: untrusted."""
    kinds: dict[str, int] = {}
    layers: dict[str, int] = {}
    diameters: dict[str, int] = {}
    for entity in extraction.entities:
        kinds[entity.kind] = kinds.get(entity.kind, 0) + 1
        layer = entity.layer[:MAX_LAYER_NAME_CHARS]
        layers[layer] = layers.get(layer, 0) + 1
        points = entity.points_mm
        if entity.kind == "CIRCLE" and points and len(points) >= 4:
            ring = points[:-1]
            center_x = sum(point.x for point in ring) / len(ring)
            center_y = sum(point.y for point in ring) / len(ring)
            key = f"{2 * ((ring[0].x - center_x) ** 2 + (ring[0].y - center_y) ** 2) ** 0.5:.1f}"
            diameters[key] = diameters.get(key, 0) + 1
    top_layers = dict(sorted(layers.items(), key=lambda item: (-item[1], item[0]))[:MAX_DIGEST_ITEMS])
    return {
        "entity_kinds": dict(sorted(kinds.items())),
        "untrusted_layer_counts": top_layers,
        "circle_diameters_mm": dict(sorted(diameters.items(), key=lambda item: float(item[0]))),
        "hole_rows": _evidence_with_prefix(extraction, "evidence-holes-"),
        "block_references": _evidence_with_prefix(extraction, "evidence-block-"),
        "hatches": _evidence_with_prefix(extraction, "evidence-hatch-"),
        "hidden_lines": _evidence_with_prefix(extraction, "evidence-hidden-"),
        "layer_counts_info": _shown(len(layers)),
    }


def _plausibility(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], catalog: WorkshopCatalog | None) -> dict:
    try:
        findings = check_plausibility(extraction, scenarios, catalog)
    except (OSError, ValueError) as exc:
        return {"plausibility_findings": [], "plausibility_unavailable": type(exc).__name__}
    return {"plausibility_findings": [item.model_dump(mode="json") for item in findings[:MAX_DIGEST_ITEMS]]}


def _initial_context(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], catalog: WorkshopCatalog | None = None) -> dict:
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
        "evidence_ids": [item.id for item in extraction.evidence][:MAX_EVIDENCE_IDS], "result_revision": 1,
        "scenarios": [{"id": item.id, "title": item.title, "assumptions": item.assumptions, "components": [{"id": component.id, "role": component.role, "label": component.label} for component in item.components]} for item in scenarios],
        "source_unit": extraction.source_unit,
        "views": [{"id": item.id, "label": item.label, "bounds_mm": item.bounds_mm.model_dump(mode="json") if item.bounds_mm else None} for item in extraction.views],
        "dimensions": [{"id": item.id, "kind": item.kind, "value_mm": item.value_mm, "view_id": item.view_id, "evidence_ids": item.evidence_ids} for item in extraction.dimensions[:MAX_DIGEST_ITEMS]],
        "evidence_catalog": [{"id": item.id, "kind": item.kind, "description": item.description} for item in extraction.evidence[:MAX_DIGEST_ITEMS]],
        "line_linetypes": linetypes,
        "untrusted_drawing_text": [{"id": item.id, "view_id": item.view_id, "text": item.text[:MAX_TEXT_CHARS]} for item in extraction.texts[:MAX_DIGEST_ITEMS]],
        "proposal_details": [{"id": component.id, "scenario_id": item.id, "quantity": component.quantity, "length_mm": component.length_mm, "width_mm": component.width_mm, "length_derivation": component.length_derivation, "length_basis_mm": component.length_basis_mm, "observed_thickness_mm": component.observed_thickness_mm, "unconfirmed_thickness": component.thickness_mm is None} for item in scenarios for component in item.components],
        "digest_counts": {
            "dimensions": _shown(len(extraction.dimensions)),
            "evidence_catalog": _shown(len(extraction.evidence)),
            "evidence_ids": _shown(len(extraction.evidence), MAX_EVIDENCE_IDS),
            "untrusted_drawing_text": _shown(len(extraction.texts)),
        },
        **_aggregates(extraction),
        **_plausibility(extraction, scenarios, catalog),
    }


def _valid_ids(values) -> list[str]:
    return sorted(values)[:MAX_VALID_IDS]


def _image_message(png: bytes) -> dict:
    """Responses API user message carrying the rendered view; sent after the tool outputs of the same turn."""
    return {"role": "user", "content": [
        {"type": "input_text", "text": "Imagen de visualizar_vista dibujada desde el ledger; usa la tabla de marcas del resultado de la herramienta."},
        {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii")},
    ]}


def run_agent(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], provider: Provider, limits: AgentLimits = AgentLimits(), *, vision: bool = False, catalog: WorkshopCatalog | None = None) -> AgentOutcome:
    started = time.monotonic()
    model_calls = 0
    tool_calls = 0
    previous_response_id = None
    input_items = [{"role": "user", "content": json.dumps(_initial_context(extraction, scenarios, catalog), ensure_ascii=False)}]
    tools = tool_schemas(vision)
    views = {item.id: item for item in extraction.views}
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
        response = provider.create_response(input_items=input_items, tools=tools, previous_response_id=previous_response_id, timeout_s=remaining)
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes usar una herramienta permitida: " + ", ".join(tool["name"] for tool in tools) + ". Termina con entregar_despiece y un scenario_id existente."}]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise RuntimeError("tool_call_budget_exhausted")
        outputs = []
        images: list[dict] = []
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
                        "entities": [_entity_payload(entities[item]) for item in sorted(source_ids) if item in entities][:MAX_INSPECT_ENTITIES],
                        "contours": [_contour_payload(item) for item in extraction.contours if set(item.source_entity_ids) & source_ids][:MAX_INSPECT_CONTOURS],
                        "entity_counts": _shown(len(source_ids), MAX_INSPECT_ENTITIES),
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
                elif call.name == "comparar_candidatas":
                    args = CompareCandidatesArgs.model_validate_json(json.dumps(arguments), strict=True)
                    unknown = [item for item in args.candidate_ids if item not in proposals]
                    if unknown or args.candidate_ids[0] == args.candidate_ids[1]:
                        data = {"ok": False, "error": "unknown_reference" if unknown else "duplicate_reference", "valid_candidate_ids": _valid_ids(proposals)}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Comparación con propuestas desconocidas o repetidas rechazada."))
                    else:
                        comparison = compare_candidates(proposals[args.candidate_ids[0]], proposals[args.candidate_ids[1]])
                        shared = tuple(comparison["relations"][0]["evidence_ids"])
                        data = {"ok": True, **comparison}
                        actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=shared, summary="Comparación determinista de dos propuestas consultada."))
                elif call.name == "visualizar_vista" and vision:
                    args = VisualizeViewArgs.model_validate_json(json.dumps(arguments), strict=True)
                    view_contours = {item.id for item in extraction.contours if item.view_id == args.view_id}
                    unknown = [item for item in args.highlight_contour_ids if item not in view_contours]
                    if args.view_id not in views or unknown:
                        data = {"ok": False, "error": "unknown_reference", "valid_view_ids": _valid_ids(views), **({"valid_contour_ids": _valid_ids(view_contours)} if args.view_id in views else {})}
                        actions.append(AgentAction(tool_name=call.name, ok=False, evidence_ids=(), summary="Vista o contorno desconocido rechazado."))
                    else:
                        rendered = render_view(extraction, args.view_id, args.highlight_contour_ids)
                        data = {"ok": True, "view_id": args.view_id, "marks": rendered.marks, "image": "adjunta en el siguiente mensaje", "width_px": rendered.width_px, "height_px": rendered.height_px}
                        images.append(_image_message(rendered.png))
                        actions.append(AgentAction(tool_name=call.name, ok=True, evidence_ids=(), summary="Vista dibujada desde el ledger con contornos numerados."))
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
        input_items = outputs + images
    raise RuntimeError("model_call_budget_exhausted")
