from __future__ import annotations

import hashlib
import json
import time
from base64 import b64encode
from dataclasses import asdict
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from backend.app.agente.runner import AgentLimits
from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
    InspectGeneralContextArgs,
    ProposeGeneralFurnitureArgs,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.context_payload import (
    build_compact_geometry_context,
    query_compact_measurements,
)
from backend.app.general_furniture.projection_hypotheses import (
    derive_projection_hypotheses,
    derive_source_spatial_regions,
)
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.agente.vision import VisionMark


GENERAL_FURNITURE_SYSTEM_PROMPT = """Eres un asistente de interpretación de mobiliario genérico para revisión técnica.
Usa exclusivamente las herramientas anunciadas. Propón componentes nuevos respaldados por IDs del contexto, no elijas una plantilla prefijada.
Las cotas del dibujo son observaciones; asignarlas como largo, ancho o espesor de un componente sigue siendo una hipótesis.
No midas píxeles. Distingue estrictamente observación, deducción y estimación: una estimación numérica debe ser `estimated`, incluir nominal, rango, método, referencias fuente y una premisa explícita; nunca la presentes como observada. Una deducción que dependa de cualquier estimación sigue siendo estimated y conserva el rango. Puedes proponer cantidades estimated cuando grupos físicos y una premisa cerrada las sostengan; nunca cuentes vistas como instancias.
Las medidas de `compact_geometry.measurements` son observaciones deterministas autorizadas del ledger: usa exactamente su `binding_ref` (`measurement:<id>`) en operand_refs. Su asignación a largo/ancho/espesor sigue siendo hipótesis. El contexto inicial contiene spans; consulta segmentos concretos con `inspeccionar_evidencia_general.measurement_ids` o paginación si hacen falta.
Construye un único escenario coherente y compacto. Declara parámetros compartidos (máximo 32) para cotas observadas, deducidas y estimadas; reutilízalos en componentes y restricciones de cierre. Usa bindings copy/add/subtract/scale_rational con `dimension:<id>`, `measurement:<id>`, `parameter:<id>` o `binding:<id-previo>`. Las estimaciones constructivas razonables son útiles y no deben quedar unknown solo por faltar una cota, siempre que estén acotadas y explicadas. Declara componentes necesarios aunque no tengan contorno propio, con necessity deduced_required o estimated_required, geometría explícita y referencias de base.
Regla de serialización de parámetros: observed y deduced llevan binding_id obligatorio y nominal_mm=null, range_mm=null; el servidor calcula sus valores. estimated lleva binding_id=null y sí exige nominal_mm y range_mm con min/max, source_refs y assumption_refs.
Propón solo detalles de unión, canteado o mecanizado que sean constructivamente relevantes; márcalos deduced/estimated con premisas. Añade pocas decisiones de alto impacto y restricciones de cierre/encaje. No mezcles alternativas incompatibles en el mismo scenario_id.
En quantity_basis_refs incluye al menos un premise:<id> declarado y, si existen, refs exactas contour:/observation:/evidence:/view: que sostienen el recuento. En decision.target_refs nunca uses IDs desnudos: usa component:<id> o component:<id>.<length|width|thickness|quantity|material|finish|existence|kind|role|geometry>, parameter:<id>, constraint:<id> o detail:<id>.
Un contorno cerrado puede ser una cara material, un hueco, un rebaje o un límite interior: contrástalo con las regiones visuales y no conviertas automáticamente cada rectángulo en panel. Las correspondencias entre proyecciones son candidatas ambiguas, no piezas adicionales.
Una vista no es una ocurrencia física. Una instancia visible en varias proyecciones puede sostener cantidad hypothesis=1 con premisa explícita; repetición u ocultación ambigua permanece unknown o como alternativa. La salida es revisable, nunca documentación industrial lista para fabricar."""


class GeneralFurnitureProvider(Protocol):
    def create_response(
        self, *, input_items, tools, previous_response_id, timeout_s
    ): ...


class GeneralLiveError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        trace: tuple[dict[str, object], ...],
        model_calls: int,
        tool_calls: int,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.trace = trace
        self.model_calls = model_calls
        self.tool_calls = tool_calls


@dataclass(frozen=True)
class GeneralFurnitureAgentOutcome:
    proposal: GeneralFurnitureProposal
    draft: GeneralFurnitureDraft
    model_calls: int
    tool_calls: int
    trace: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class GeneralVisualPage:
    reference: str
    media_type: str
    sha256: str
    content: bytes
    source_view_ids: tuple[str, ...] = ()
    source_contour_ids: tuple[str, ...] = ()
    source_document_refs: tuple[str, ...] = ()
    crop_bounds_source: tuple[float, float, float, float] | None = None
    marks: tuple[VisionMark, ...] = ()
    warnings: tuple[str, ...] = ()


def _is_raster_without_metric_ledger(
    extraction: DrawingExtraction,
    measurements,
    visual_pages: tuple[GeneralVisualPage, ...],
) -> bool:
    return (
        bool(visual_pages)
        and not extraction.views
        and not any(item.value_mm is not None for item in extraction.dimensions)
        and not any(item.value_mm is not None for item in measurements)
    )


def general_allowed_document_refs(
    visual_pages: tuple[GeneralVisualPage, ...],
    *,
    include_announced_children: bool,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            reference
            for page in visual_pages
            for reference in (
                page.reference,
                *(page.source_document_refs if include_announced_children else ()),
            )
        )
    )


def _safe_live_error_code(error: Exception) -> str:
    candidate = getattr(error, "code", None)
    if (
        isinstance(candidate, str)
        and 0 < len(candidate) <= 120
        and all(character.isalnum() or character in "_:-" for character in candidate)
    ):
        return candidate
    if isinstance(error, TimeoutError):
        return "general_live_provider_timeout"
    return "general_live_provider_error"


def _safe_validation_details(error: Exception) -> list[dict[str, object]]:
    if isinstance(error, ValidationError):
        return [
            {
                "loc": [str(part)[:80] for part in item.get("loc", ())[:8]],
                "msg": str(item.get("msg", "invalid value"))[:200],
                "type": str(item.get("type", "value_error"))[:80],
            }
            for item in error.errors(include_url=False, include_input=False)[:16]
        ]
    if isinstance(error, ValueError):
        code = str(error)
        safe = code if code and len(code) <= 120 and all(character.isalnum() or character in "_:- " for character in code) else "invalid_value"
        return [{"loc": [], "msg": safe, "type": "value_error"}]
    return [{"loc": [], "msg": "invalid tool arguments", "type": "invalid_arguments"}]


def _strictify(value):
    if isinstance(value, dict):
        normalized = {
            key: _strictify(item) for key, item in value.items() if key != "default"
        }
        if normalized.get("type") == "object" or "properties" in normalized:
            properties = normalized.get("properties", {})
            normalized["additionalProperties"] = False
            normalized["required"] = list(properties)
        return normalized
    if isinstance(value, list):
        return [_strictify(item) for item in value]
    return value


def _compact_contour(item) -> dict[str, object]:
    points = item.points_source
    return {
        "id": item.id,
        "view_id": item.view_id,
        "source_entity_ids": item.source_entity_ids,
        "closed": item.closed,
        "point_count": len(points),
        "points_source": [
            (float(point.x), float(point.y)) for point in points[:64]
        ],
        "points_truncated": len(points) > 64,
    }


def general_furniture_tool_schemas(
    *, raster_without_metric_ledger: bool = False
) -> list[dict]:
    def schema(name: str, description: str, model) -> dict:
        return {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": _strictify(model.model_json_schema()),
            "strict": True,
        }

    proposal_description = (
        "Propone componentes visuales revisables usando exclusivamente las referencias exactas anunciadas. "
        "Como el raster no tiene ledger métrico ni vistas autorizadas, usa bindings=[], "
        "length_binding_id/width_binding_id/thickness_binding_id=null y source_view_ids=[]. "
        "Cita source_document_refs solo desde allowed_source_document_refs; no midas píxeles."
        if raster_without_metric_ledger
        else "Propone un escenario constructivo provisional completo usando IDs del ledger. Parámetros observed/deduced: binding_id obligatorio y nominal_mm/range_mm null; estimated: binding_id null y nominal_mm+rango+source_refs+premisas. quantity_basis_refs incluye premise:<id> y puede citar refs exactas contour:/observation:/evidence:/view:. decision.target_refs usa siempre namespace: component:<id>[.<field>], parameter:<id>, constraint:<id> o detail:<id>, nunca IDs desnudos. Usa bindings copy/add/subtract/scale_rational; toda deducción dependiente de estimate sigue estimated; nunca cuentes vistas como instancias."
    )
    return [
        schema(
            "inspeccionar_evidencia_general",
            "Consulta evidencias/vistas y segmentos exactos del ledger. Para primera página de segmentos usa query_measurements=true, measurement_ids=[], offset=0, limit<=64; continúa con next_offset. No crea medidas ni confirma componentes.",
            InspectGeneralContextArgs,
        ),
        schema(
            "proponer_mueble_general",
            proposal_description,
            ProposeGeneralFurnitureArgs,
        ),
    ]


def run_general_furniture_agent(
    extraction: DrawingExtraction,
    *,
    ledger_revision: str,
    provider: GeneralFurnitureProvider,
    limits: AgentLimits = AgentLimits(),
    visual_pages: tuple[GeneralVisualPage, ...] = (),
) -> GeneralFurnitureAgentOutcome:
    if len(visual_pages) > 4 or any(
        len(item.content) > 4 * 1024 * 1024 for item in visual_pages
    ):
        raise ValueError("general_visual_context_budget_exceeded")
    started = time.monotonic()
    previous_response_id = None
    calls = 0
    tool_calls = 0
    repairs = 0
    trace: list[dict[str, object]] = []
    evidence = {item.id: item for item in extraction.evidence}
    dimensions = {item.id: item for item in extraction.dimensions}
    general_measures = derive_geometry_measurements(extraction)
    raster_without_metric_ledger = _is_raster_without_metric_ledger(
        extraction, general_measures, visual_pages
    )
    allowed_document_refs = general_allowed_document_refs(
        visual_pages,
        include_announced_children=raster_without_metric_ledger,
    )
    try:
        spatial_regions = derive_source_spatial_regions(extraction, general_measures)
        projection_hypotheses = derive_projection_hypotheses(
            extraction, general_measures
        )
        projection_warnings: tuple[str, ...] = ()
    except ValueError as exc:
        if str(exc) != "projection_input_budget_exceeded":
            raise
        spatial_regions = ()
        projection_hypotheses = ()
        projection_warnings = ("projection_input_budget_exceeded",)
    context = {
        "drawing_id": extraction.drawing_id,
        "ledger_revision": ledger_revision,
        "source_unit": extraction.source_unit,
        "coordinate_unit": extraction.coordinate_unit,
        "views": [
            {
                "id": item.id,
                "label": item.label,
                "bounds_mm": item.bounds_mm.model_dump(mode="json")
                if item.bounds_mm
                else None,
                "bounds_source": item.bounds_source.model_dump(mode="json"),
            }
            for item in extraction.views
        ],
        "observations": [
            {
                "id": item.id,
                "view_id": item.view_id,
                "dimension_ids": item.dimension_ids,
            }
            for item in extraction.observations
        ],
        "dimensions": [
            {
                "id": item.id,
                "kind": item.kind,
                "has_metric_value": item.value_mm is not None,
                "evidence_ids": item.evidence_ids,
            }
            for item in extraction.dimensions
        ],
        "compact_geometry": build_compact_geometry_context(
            extraction,
            general_measures,
            spatial_regions,
            projection_hypotheses,
        ).to_payload(),
        "projection_warnings": projection_warnings,
        "projection_authority": "ambiguous_hypotheses_not_physical_identity_or_quantity",
        "evidence_ids": sorted(evidence),
        "instruction": "Propón un escenario constructivo coherente, no una plantilla. Parámetros observed/deduced: binding_id requerido, nominal_mm=null y range_mm=null. Parámetros estimated: binding_id=null, nominal+rango+método+source_refs+premise:<id>. Cualquier binding dependiente conserva estimated. Reutiliza parámetros compartidos para cerrar encajes y separaciones. Consulta segmentos paginados solo si hacen falta. Las cantidades provisionales requieren premisa y grupos físicos; nunca cuentes proyecciones como unidades.",
        "visual_pages": [
            {
                "reference": item.reference,
                "sha256": item.sha256,
                "source_view_ids": item.source_view_ids,
                "source_contour_ids": item.source_contour_ids,
                "source_document_refs": item.source_document_refs,
                "crop_bounds_source": item.crop_bounds_source,
                "marks": [asdict(mark) for mark in item.marks],
                "warnings": item.warnings,
                "authority": "context_only_not_measurement_source",
            }
            for item in visual_pages
        ],
    }
    if raster_without_metric_ledger:
        context["raster_authority"] = {
            "allowed_source_view_ids": [],
            "allowed_source_document_refs": list(allowed_document_refs),
            "allowed_numeric_binding_refs": [],
            "instruction": (
                "No inventes IDs de vista para páginas PDF. Usa source_view_ids=[], "
                "bindings=[] y ejes null; cita solo source_document_refs de esta lista. "
                "La imagen autoriza interpretación visual, nunca medidas en píxeles."
            ),
        }
    content: list[dict[str, object]] = [
        {"type": "input_text", "text": json.dumps(context, ensure_ascii=False)}
    ]
    content.extend(
        {
            "type": "input_image",
            "image_url": f"data:{item.media_type};base64,{b64encode(item.content).decode('ascii')}",
            "detail": "high",
        }
        for item in visual_pages
    )
    input_items = [{"role": "user", "content": content}]
    while calls < limits.max_model_calls:
        remaining = limits.timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            raise GeneralLiveError(
                "agent_deadline_exceeded", trace=tuple(trace),
                model_calls=calls, tool_calls=tool_calls,
            )
        calls += 1
        try:
            response = provider.create_response(
                input_items=input_items,
                tools=general_furniture_tool_schemas(
                    raster_without_metric_ledger=raster_without_metric_ledger
                ),
                previous_response_id=previous_response_id,
                timeout_s=remaining,
            )
        except GeneralLiveError:
            raise
        except Exception as exc:
            raise GeneralLiveError(
                _safe_live_error_code(exc), trace=tuple(trace),
                model_calls=calls, tool_calls=tool_calls,
            ) from exc
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [
                {"role": "user", "content": "Debes usar una herramienta permitida."}
            ]
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            raise GeneralLiveError(
                "tool_call_budget_exhausted", trace=tuple(trace),
                model_calls=calls, tool_calls=tool_calls,
            )
        outputs = []
        for call in response.tool_calls:
            tool_calls += 1
            metadata = {
                "provider_response_id": getattr(response, "id", None),
                "provider_model": getattr(response, "model", None),
                "provider_call_id": getattr(call, "call_id", None),
                "provider_duration_ms": getattr(response, "duration_ms", None),
                "provider_input_tokens": getattr(response, "input_tokens", None),
                "provider_output_tokens": getattr(response, "output_tokens", None),
                "provider_total_tokens": getattr(response, "total_tokens", None),
            }
            try:
                raw = (
                    json.loads(call.arguments_json)
                    if call.arguments_json is not None
                    else call.arguments
                )
                if not isinstance(raw, dict):
                    raise TypeError("tool arguments must be an object")
                if call.name == "inspeccionar_evidencia_general":
                    args = InspectGeneralContextArgs.model_validate_json(
                        json.dumps(raw), strict=True
                    )
                    unknown = [
                        item for item in args.evidence_ids if item not in evidence
                    ]
                    views_by_id = {item.id: item for item in extraction.views}
                    unknown += [
                        item for item in args.view_ids if item not in views_by_id
                    ]
                    selected_view_ids = {
                        item for item in args.view_ids if item in views_by_id
                    }
                    selected_entities = [
                        item
                        for item in extraction.entities
                        if any(
                            item.id in views_by_id[view_id].entity_ids
                            for view_id in selected_view_ids
                        )
                    ]
                    selected_contours = [
                        item for item in extraction.contours
                        if item.view_id in selected_view_ids
                    ]
                    measurement_source = (
                        general_measures
                        if args.measurement_ids
                        else tuple(
                            item for item in general_measures
                            if item.semantic == "contour_segment_length"
                        )
                        if args.query_measurements
                        else ()
                    )
                    measurement_page = query_compact_measurements(
                        measurement_source,
                        measurement_ids=args.measurement_ids,
                        offset=args.measurement_offset,
                        limit=args.measurement_limit,
                    )
                    data = {
                        "ok": not unknown,
                        "error": "unknown_reference" if unknown else None,
                        "evidence": [
                            evidence[item].model_dump(mode="json")
                            for item in args.evidence_ids
                            if item in evidence
                        ],
                        "dimensions": [
                            item.model_dump(mode="json")
                            for item in dimensions.values()
                            if set(item.evidence_ids) & set(args.evidence_ids)
                        ],
                        "views": [
                            views_by_id[item].model_dump(mode="json")
                            for item in args.view_ids
                            if item in views_by_id
                        ],
                        "contours": [
                            _compact_contour(item)
                            for item in selected_contours[:128]
                        ],
                        "entities": [
                            {
                                "id": item.id,
                                "kind": item.kind,
                                "layer": item.layer,
                                "linetype": item.linetype,
                                "point_count": len(item.points_mm or item.source_points),
                                "circular": item.circular.model_dump(mode="json") if item.circular else None,
                            }
                            for item in selected_entities[:256]
                        ],
                        "measurements": measurement_page.to_payload(),
                        "truncation": {
                            "contours_returned": min(len(selected_contours), 128),
                            "contours_total": len(selected_contours),
                            "entities_returned": min(len(selected_entities), 256),
                            "entities_total": len(selected_entities),
                        },
                        "authority": "vector_context_only; component assignments remain hypotheses",
                    }
                    trace.append(
                        {
                            "tool": call.name,
                            "ok": not unknown,
                            "summary": "Ledger evidence inspected.",
                            **metadata,
                        }
                    )
                elif call.name == "proponer_mueble_general":
                    args = ProposeGeneralFurnitureArgs.model_validate_json(
                        json.dumps(raw), strict=True
                    )
                    canonical = json.dumps(
                        args.model_dump(mode="json"),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                    proposal = GeneralFurnitureProposal(
                        id=f"general-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}",
                        drawing_id=extraction.drawing_id,
                        ledger_revision=ledger_revision,
                        proposal_origin="native_tool",
                        **args.model_dump(),
                    )
                    draft = materialize_general_proposal(
                        extraction,
                        proposal,
                        allowed_document_refs=allowed_document_refs,
                    )
                    trace.append(
                        {
                            "tool": call.name,
                            "ok": True,
                            "summary": "Evidence-grounded component proposal created for review.",
                            **metadata,
                        }
                    )
                    return GeneralFurnitureAgentOutcome(
                        proposal, draft, calls, tool_calls, tuple(trace)
                    )
                else:
                    data = {"ok": False, "error": "unknown_tool"}
                    trace.append(
                        {
                            "tool": call.name,
                            "ok": False,
                            "summary": "Unknown tool rejected.",
                            **metadata,
                        }
                    )
            except (
                ValidationError,
                ValueError,
                TypeError,
                json.JSONDecodeError,
            ) as exc:
                repairs += 1
                details = _safe_validation_details(exc)
                trace.append(
                    {
                        "tool": call.name,
                        "ok": False,
                        "summary": "Invalid tool arguments rejected.",
                        "details": details,
                        **metadata,
                    }
                )
                if repairs > limits.max_validation_repairs:
                    raise GeneralLiveError(
                        "validation_repair_budget_exhausted",
                        trace=tuple(trace), model_calls=calls,
                        tool_calls=tool_calls,
                    ) from exc
                data = {
                    "ok": False,
                    "error": "invalid_arguments",
                    "details": details,
                }
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(data, ensure_ascii=False),
                }
            )
        input_items = outputs
    raise GeneralLiveError(
        "model_call_budget_exhausted", trace=tuple(trace),
        model_calls=calls, tool_calls=tool_calls,
    )
