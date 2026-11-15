from __future__ import annotations

import hashlib
import json
import time
from base64 import b64encode
from dataclasses import asdict
from dataclasses import dataclass
from typing import Callable, Protocol

from pydantic import ValidationError

from backend.app.agente.runner import AgentLimits
from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
    InspectGeneralContextArgs,
    ProposeGeneralFurnitureArgs,
    ReferentialValidationError,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.orthographic_hypotheses import (
    derive_orthographic_hypotheses,
)
from backend.app.general_furniture.evidence_accounting import (
    EvidenceAccountingReport,
    build_evidence_accounting_report,
    derive_relevant_candidate_regions,
)
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
Una cota observada solo se reutiliza como dimensión de la misma geometría visible que la sustenta. No copies un espesor u otra cota observada a piezas ocultas o componentes distintos solo porque parezcan compartir construcción: declara para esas piezas un parámetro estimated separado, con nominal, rango, premisa y fuentes; sus dependientes siguen estimated.
No midas píxeles. Distingue estrictamente observación, deducción y estimación: una estimación numérica debe ser `estimated`, incluir nominal, rango, método, referencias fuente y una premisa explícita; nunca la presentes como observada. Una deducción que dependa de cualquier estimación sigue siendo estimated y conserva el rango. Puedes proponer cantidades estimated cuando grupos físicos y una premisa cerrada las sostengan; nunca cuentes vistas como instancias.
Las medidas de `compact_geometry.measurements` son observaciones deterministas autorizadas del ledger: usa exactamente su `binding_ref` (`measurement:<id>`) en operand_refs. Su asignación a largo/ancho/espesor sigue siendo hipótesis. El contexto inicial contiene spans; consulta segmentos concretos con `inspeccionar_evidencia_general.measurement_ids` o paginación si hacen falta.
`compact_geometry.orthographic_hypotheses` solo facilita el contraste provisional de ejes, intervalos y alineaciones mediante sus refs `contour:` y `measurement:` anunciadas. El id de la hipótesis no es una referencia citable y la hipótesis no prueba identidad, ownership, cantidad ni material; tampoco clasifica un hueco ni contorno interior como pieza. Conserva alternativas many-to-many y la incertidumbre indicada por warnings/authority.
Para piezas de las mismas vistas, contrasta y elige como máximo una alternativa de `orthographic_frame_alternatives` como alineación global; no mezcles direct y mirrored ni grupos incompatibles entre piezas. Sus hypothesis_ids solo agrupan contexto y tampoco son refs citables. Este contexto no define por sí solo el marco 2D de montaje: si x/y/rotation y la cobertura exacta de todas las ocurrencias no quedan cerradas por fuentes y premisas explícitas, usa `construction_placements=[]` y declara una decision category=assembly que explique la ausencia y las alternativas. Nunca inventes coordenadas ni eleves placements estimated a observed.
Construye un único escenario coherente y compacto. Reserva los construction_parameters compartidos (máximo 32) para estimaciones y relaciones que deban reutilizarse; una cota observed puede alimentar cada eje mediante bindings directos con operand_refs dimension:/measurement:, sin crear un parámetro individual. Usa bindings copy/add/subtract/scale_rational con `dimension:<id>`, `measurement:<id>`, `parameter:<id>` o `binding:<id-previo>`. Las estimaciones constructivas razonables son útiles y no deben quedar unknown solo por faltar una cota, siempre que estén acotadas y explicadas. Declara componentes necesarios aunque no tengan contorno propio, con necessity deduced_required o estimated_required, geometría explícita y referencias de base.
Un componente fabricado representa un tipo de pieza física cortable, no un subensamblaje funcional agregado. Si una premisa funcional cerrada exige un conjunto oculto, descompón el mínimo coherente de tipos de pieza física fabricada y declara para cada uno kind, geometry, length, width y thickness estimated con nominal, rango y premisa. No conviertas lo oculto en observed. Si no existe una premisa funcional cerrada, conserva unknown o abstente: no fuerces la descomposición.
Regla de serialización de parámetros: observed y deduced llevan binding_id obligatorio y nominal_mm=null, range_mm=null; el servidor calcula sus valores. estimated lleva binding_id=null y sí exige nominal_mm y range_mm con min/max, source_refs y assumption_refs.
Regla de namespaces: los campos *_binding_id, construction_parameter_ids, premise_ids, detail_ids y source_*_ids reciben IDs desnudos declarados, sin prefijo. En cambio operand_refs y las listas *_refs reciben referencias tipadas con su namespace autorizado. Para usar un parámetro estimado P en una dimensión, declara P con binding_id=null, crea un binding B de copia con operand_refs=["parameter:P"] y asigna al componente length_binding_id="B" (o el eje correspondiente), sin escribir parameter:P ni binding:B en *_binding_id.
Referencias documentales: en component.source_document_refs copia literalmente valores de allowed_source_document_refs. Cuando cites una página o documento dentro de source_refs, basis_refs y demás listas tipadas, usa el valor completo correspondiente de allowed_typed_document_source_refs; no copies ahí la referencia cruda ni añadas un prefijo distinto. Las demás referencias dimension:, measurement:, premise: e internas conservan sus namespaces autorizados. Una referencia visual o documental aporta contexto y nunca autoriza medir píxeles.
Propón solo detalles de unión, canteado o mecanizado que sean constructivamente relevantes; márcalos deduced/estimated con premisas. En la geometría local de cada detalle, x recorre length e y recorre width de su pieza. Divide el detalle por pieza cuando cambien el origen o las dimensiones locales. Añade pocas decisiones de alto impacto y restricciones de cierre/encaje. No mezcles alternativas incompatibles en el mismo scenario_id.
Las dimension_refs del detalle son opcionales y deben resolverse por el grafo constructivo, preferentemente parameter:<id>; un binding solo sirve si termina en parámetros resolubles. Las mediciones ledger van en source_refs o en operand_refs del parámetro, no directamente en dimension_refs. Si los puntos explícitos y los límites de la pieza bastan, usa dimension_refs=[].
Comprueba la estabilidad global de la construcción propuesta. Si la geometría deja riesgo de vuelco, descuadre o falta de arriostramiento, no lo dejes solo como pendiente: propone un detalle estimated explícito de estabilización o anclaje con premisa, ubicación y referencias, o marca conflicto si no existe una solución coherente.
En quantity_basis_refs incluye al menos un premise:<id> declarado. Las refs exactas contour:/observation:/evidence: solo pueden apoyar la ocurrencia: nunca cuentes su cardinalidad ni las uses para probar identidad física. No uses view: ni projection: como base de cantidad; las referencias visuales o documentales pertenecen a los machine checks del crítico. En decision.target_refs nunca uses IDs desnudos: usa component:<id> o component:<id>.<length|width|thickness|quantity|material|finish|existence|kind|role|geometry>, parameter:<id>, constraint:<id> o detail:<id>.
Los IDs internos y el orden serializado de entidades sirven para trazabilidad, pero no prueban por sí solos identidad, cantidad ni correspondencias entre proyecciones. Decide esas relaciones mediante geometría, capas declaradas, anotaciones explícitas (incluidas etiquetas PART cuando existan) y contraste entre fuentes; conserva los IDs al citar la evidencia.
En evidence_dispositions usa exclusivamente los IDs literales de evidence_accounting.candidate_regions (`evidence-candidate:*`), nunca IDs `projection-region:` de compact_geometry. `source_contour_ids` declara un claim del componente sobre cada contorno. Un contorno ambiguo que sirva como apoyo compartido a varias piezas se cita con una ref tipada en geometry.basis_refs, construction_parameter.source_refs o un binding measurement; esa cita no crea un claim ni demuestra cantidad. assigned exige component_id y que ese componente reclame el contorno candidato. duplicate_projection también exige component_id: duplicate_of_region_id debe ser otro evidence-candidate cuyo contorno reclame ese mismo componente y el candidato duplicado puede estar sin claim o reclamado solo por él; además debe existir una projection_hypothesis que conecte ambos contornos. Usa shared_projection_support solo cuando un contorno ambiguo apoya al menos dos componentes sin pertenecer a ninguno: component_id, duplicate_of_region_id y reason_code quedan null, support_component_ids enumera componentes distintos y cada uno tiene otra región como ancla assigned exclusiva. La relación ortográfica debe sostener todos los apoyos bajo una alineación global compatible; la disposition no declara ownership ni cantidad. nonmaterial y unresolved llevan component_id=null. Toda disposition cita en source_refs el contour:<id> exacto del candidato; si no puedes cerrar estas invariantes usa unresolved.
Un contorno cerrado puede ser una cara material, un hueco, un rebaje o un límite interior: contrástalo con las regiones visuales y no conviertas automáticamente cada rectángulo en panel. Las correspondencias entre proyecciones son candidatas ambiguas, no piezas adicionales.
Una vista no es una ocurrencia física. Una instancia visible en varias proyecciones puede sostener cantidad hypothesis=1 con premisa explícita; repetición u ocultación ambigua permanece unknown o como alternativa. La salida es revisable, nunca documentación industrial lista para fabricar."""

GENERAL_FURNITURE_SYSTEM_PROMPT += """
No declares uniones como observadas. `assembly_relations` solo expresa relaciones estructuradas revisables entre IDs de componentes, con estado hypothesis, unknown o conflict, premisas y fuentes autorizadas; no añade geometría numérica. Examina cada par de componentes que la evidencia muestre interactuando y cita source_refs visibles. supported_by describe apoyo funcional y puede coexistir con fixed_to; fixed_to solo con evidencia visible propia, nunca por asumir hidden joinery. Si el apoyo visible está respaldado pero el método de unión no, emite supported_by como hypothesis y conserva la fijación como unknown, sin inventar una alternativa. Si no hay ningún par visible respaldado, los campos assembly pueden quedar vacíos y debes registrar `assembly_not_identifiable` en unknown_fields o en la razón pública.
Para las funciones cubiertas por este vocabulario usa exactamente el canónico: side_panel, top_panel, bottom_panel, shelf, divider, back_panel, door, tabletop, table_leg, leg_frame, stretcher, support, unknown. Si existe una función legítima fuera del catálogo, usa un rol custom snake_case estable y explícalo; usa unknown solo cuando la función no sea resoluble. No traduzcas ni crees sinónimos de un concepto ya cubierto. No colapses componentes del mismo rol cuando tengan dimensiones, fuentes o identidad física distintas. cantidad cuenta ocurrencias físicas del componente, nunca vistas ni el número de contornos."""


class ProposalEvidenceAccountingError(ValueError):
    def __init__(self, report: EvidenceAccountingReport) -> None:
        super().__init__("proposal_evidence_accounting_incomplete")
        self.report = report


class GeneralFurnitureProvider(Protocol):
    def create_response(
        self, *, input_items, tools, previous_response_id, timeout_s
    ): ...


class GeneralLiveError(RuntimeError):
    """Live failure that retains only prior safe trace entries and counters."""

    def __init__(
        self,
        code: str,
        *,
        trace: tuple[dict[str, object], ...],
        model_calls: int,
        tool_calls: int,
        provider_status_code: int | None = None,
        provider_code: str | None = None,
        provider_request_id: str | None = None,
        provider_response_id: str | None = None,
        provider_incomplete_reason: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.trace = trace
        self.model_calls = model_calls
        self.tool_calls = tool_calls
        self.provider_status_code = provider_status_code
        self.provider_code = provider_code
        self.provider_request_id = provider_request_id
        self.provider_response_id = provider_response_id
        self.provider_incomplete_reason = provider_incomplete_reason


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


def general_allowed_typed_document_source_refs(
    visual_pages: tuple[GeneralVisualPage, ...],
    *,
    include_announced_children: bool,
) -> tuple[str, ...]:
    references: list[str] = []
    for page in visual_pages:
        references.append(
            page.reference
            if page.reference.startswith("visual:")
            else f"visual:{page.reference}"
        )
        if include_announced_children:
            references.extend(
                reference
                if reference.startswith(("document:", "visual:"))
                else f"document:{reference}"
                for reference in page.source_document_refs
            )
    return tuple(dict.fromkeys(references))


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


def _safe_provider_incomplete_reason(error: Exception) -> str | None:
    candidate = getattr(error, "incomplete_reason", None)
    if (
        isinstance(candidate, str)
        and 0 < len(candidate) <= 120
        and all(
            character.isalnum() or character in "_:-"
            for character in candidate
        )
    ):
        return candidate
    return None


def _safe_validation_details(error: Exception) -> list[dict[str, object]]:
    if isinstance(error, ProposalEvidenceAccountingError):
        report = error.report
        return [{
            "loc": ["evidence_dispositions"],
            "msg": "proposal_evidence_accounting_incomplete",
            "type": "value_error",
            "unresolved_candidate_region_ids": list(report.unresolved_region_ids[:64]),
            "invalid_candidate_region_ids": list(report.invalid_region_ids[:64]),
            "invalid_candidate_region_reasons": [
                {
                    "candidate_region_id": region_id,
                    "reason_code": reason_code,
                }
                for region_id, reason_code in report.invalid_region_reasons[:64]
            ],
            "missing_dimension_targets": list(report.missing_dimension_targets[:64]),
            "untraceable_dimension_targets": list(
                report.untraceable_dimension_targets[:64]
            ),
            "truncated": any(
                len(values) > 64
                for values in (
                    report.unresolved_region_ids,
                    report.invalid_region_ids,
                    report.missing_dimension_targets,
                    report.untraceable_dimension_targets,
                )
            ),
        }]
    if isinstance(error, ReferentialValidationError):
        return error.safe_details()[:20]
    if isinstance(error, ValidationError):
        details: list[dict[str, object]] = []
        for item in error.errors(
            include_url=False, include_context=True, include_input=False
        )[:16]:
            context = item.get("ctx")
            controlled_error = (
                context.get("error") if isinstance(context, dict) else None
            )
            if isinstance(controlled_error, ReferentialValidationError):
                details.extend(controlled_error.safe_details())
            else:
                details.append({
                    "loc": [str(part)[:80] for part in item.get("loc", ())[:8]],
                    "msg": str(item.get("msg", "invalid value"))[:200],
                    "type": str(item.get("type", "value_error"))[:80],
                })
            if len(details) >= 20:
                break
        return details[:20]
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
        else "Propone un escenario constructivo provisional completo usando IDs del ledger. Las orthographic_hypotheses solo ayudan a contrastar ejes/alineaciones mediante contour:/measurement:; su id no es citable y no prueba identidad, ownership, cantidad, material ni clasificación interior. Elige como máximo una orthographic_frame_alternative global y no mezcles direct/mirrored. Sin marco 2D y cobertura de ocurrencias cerrados usa construction_placements=[] y una decision category=assembly con motivo/alternativas; no inventes coordenadas. Contabiliza solo cada ID de evidence_accounting.candidate_regions mediante evidence_dispositions tipadas; nunca uses projection-region. source_contour_ids declara claims físicos; un contorno ambiguo de apoyo compartido se cita en basis_refs/source_refs/bindings tipados sin crear claim ni cantidad. assigned requiere component_id que reclame el contorno; duplicate_projection requiere component_id, un original evidence-candidate reclamado por el mismo componente y una projection_hypothesis entre ambos. shared_projection_support no tiene owner ni cantidad: enumera >=2 support_component_ids, cada uno con ancla assigned exclusiva, y exige relación ortográfica bajo una alineación global compatible. nonmaterial/unresolved usan component_id null. Toda disposition cita el contour:<id> exacto; si no se cierran las invariantes usa unresolved. No conviertas cada región o proyección en pieza. Parámetros observed/deduced: binding_id obligatorio y nominal_mm/range_mm null; estimated: binding_id null y nominal_mm+rango+source_refs+premisas. Una cota observed solo se asigna a la misma geometría visible; para piezas ocultas o componentes distintos crea un parámetro estimated separado con rango y premisa. Descompón todo subensamblaje funcional necesario con premisa cerrada en tipos de pieza física fabricada, cada una con geometría y tres dimensiones estimated; sin premisa conserva unknown. quantity_basis_refs exige premise:<id>; contour/observation/evidence solo apoyan ocurrencia y no se cuentan. decision.target_refs usa namespaces tipados. En detalles locales x recorre length e y recorre width, separados por pieza si cambia el marco. Usa bindings copy/add/subtract/scale_rational; dependientes de estimate siguen estimated. Comprueba estabilidad global y, si hace falta, propone un detalle estimated explícito de estabilización o anclaje, no solo una nota pendiente."
    )
    proposal_description += (
        " Declara assembly_relations solo como hypothesis/unknown/conflict con IDs de "
        "componentes, premise_ids y source_refs. supported_by describe apoyo funcional "
        "y puede coexistir con fixed_to; fixed_to solo con evidencia visible propia. "
        "Si solo el apoyo es visible, emite supported_by hypothesis y deja el método "
        "de fijación unknown; no inventes uniones ni geometría numérica. Examina cada par visible; "
        "si ninguno está respaldado, permite assembly vacío y registra "
        "assembly_not_identifiable. Para conceptos cubiertos usa exactamente el canónico: side_panel, top_panel, "
        "bottom_panel, shelf, divider, back_panel, door, tabletop, table_leg, "
        "leg_frame, stretcher, support, unknown; para una función legítima fuera del catálogo usa un rol custom snake_case estable; usa unknown solo si no se resuelve. "
        "No colapses componentes del mismo rol con dimensiones o fuentes distintas; "
        "cantidad cuenta ocurrencias físicas, no vistas ni contornos."
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
    cancelled: Callable[[], bool] | None = None,
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
    last_incomplete: tuple[
        GeneralFurnitureProposal,
        GeneralFurnitureDraft,
        EvidenceAccountingReport,
    ] | None = None
    incomplete_seen_at_call = 0
    incomplete_followup_responses = 0

    def preserve_incomplete(
        reason_code: str, *, metadata: dict[str, object] | None = None
    ) -> GeneralFurnitureAgentOutcome:
        assert last_incomplete is not None
        proposal, draft, accounting = last_incomplete
        trace.append(
            {
                "tool": "proponer_mueble_general",
                "ok": False,
                "summary": (
                    "Proposal preserved as incomplete after bounded recovery."
                ),
                "reason_code": reason_code,
                "evidence_accounting": accounting.to_payload(),
                **(metadata or {}),
            }
        )
        return GeneralFurnitureAgentOutcome(
            proposal, draft, calls, tool_calls, tuple(trace)
        )
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
    allowed_typed_document_source_refs = (
        general_allowed_typed_document_source_refs(
            visual_pages,
            include_announced_children=raster_without_metric_ledger,
        )
    )
    source_ref_groups = {
        "view": extraction.views,
        "observation": extraction.observations,
        "contour": extraction.contours,
        "evidence": extraction.evidence,
        "dimension": extraction.dimensions,
    }
    reference_authority = {
        "allowed_source_document_refs": list(allowed_document_refs),
        "assembly_source_ref_prefixes": list(source_ref_groups),
        "assembly_source_ref_examples": [
            f"{kind}:{items[0].id}"
            for kind, items in source_ref_groups.items() if items
        ],
        "instruction": (
            "En assembly_relations y assembly_alternatives, source_refs exige "
            "referencias tipadas tipo:id con IDs existentes del ledger, por ejemplo "
            "view:<id de vista> o evidence:<id de evidencia>, o una referencia exacta "
            "de allowed_source_document_refs. Un ID sin prefijo no es válido. "
            "Los campos source_view_ids/source_evidence_ids/etc de componentes usan "
            "IDs sin prefijo. Para source_document_refs copia SOLO elementos exactos "
            "de allowed_source_document_refs; si no necesitas referencia documental "
            "usa source_document_refs=[]. No inventes document:<id>, recortes ni "
            "referencias a partir de etiquetas visuales."
        ),
    }
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
    orthographic_hypotheses = derive_orthographic_hypotheses(
        extraction, general_measures
    ).hypotheses
    context = {
        "drawing_id": extraction.drawing_id,
        "reference_authority": reference_authority,
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
        "allowed_source_document_refs": list(allowed_document_refs),
        "allowed_typed_document_source_refs": list(
            allowed_typed_document_source_refs
        ),
        "evidence_accounting": {
            "candidate_regions": [
                asdict(item) for item in derive_relevant_candidate_regions(extraction)
            ],
            "authority": "candidate_evidence_not_physical_piece_or_recall",
            "required_dispositions": (
                "Exactly one typed evidence_disposition for every literal id in "
                "evidence_accounting.candidate_regions; never use projection-region "
                "or other compact_geometry region ids. source_contour_ids declares "
                "component claims; shared ambiguous support belongs in typed "
                "basis_refs/source_refs/bindings and creates neither claim nor "
                "quantity. component_id is required for assigned and "
                "duplicate_projection: assigned must be claimed by that component; "
                "duplicate_projection must reference an evidence-candidate original "
                "claimed by the same component and supported by a projection "
                "hypothesis. shared_projection_support has no owner or quantity, "
                "lists at least two distinct support components, requires a separate "
                "exclusive assigned anchor for each, and uses one globally compatible "
                "orthographic alignment. nonmaterial and unresolved use component_id null. Every "
                "disposition includes its exact contour:<id> source; otherwise use "
                "unresolved."
            ),
        },
        "evidence_ids": sorted(evidence),
        "instruction": "Propón un escenario constructivo coherente, no una plantilla. Parámetros observed/deduced: binding_id requerido, nominal_mm=null y range_mm=null. Parámetros estimated: binding_id=null, nominal+rango+método+source_refs+premise:<id>. Una cota observed solo se asigna a la misma geometría visible; para piezas ocultas o componentes distintos usa un parámetro estimated separado. Si una premisa funcional cerrada exige un subensamblaje oculto, descompónlo en tipos de pieza física fabricada con geometría y tres dimensiones estimated; sin esa premisa conserva unknown. Dependientes de estimate conservan estimated. En detalles locales x recorre length e y recorre width. Comprueba estabilidad/vuelco/arriostramiento y, si procede, declara un detalle estimated explícito, no solo pendiente. Las cantidades provisionales requieren premise:<id>; contour/observation/evidence solo apoyan ocurrencia y nunca se cuentan como unidades. Para conceptos cubiertos usa exactamente el rol canónico side_panel, top_panel, bottom_panel, shelf, divider, back_panel, door, tabletop, table_leg, leg_frame, stretcher, support, unknown. Para una función legítima fuera del catálogo usa un rol custom snake_case estable; usa unknown solo si la función no se resuelve. No colapses componentes del mismo rol con dimensiones, fuentes o identidad distintas; cantidad cuenta ocurrencias físicas, no vistas ni contornos. Examina pares visiblemente interactuantes y cita source_refs. supported_by es apoyo funcional y puede coexistir con fixed_to; fixed_to exige evidencia visible propia. Si solo el apoyo está respaldado, emite supported_by hypothesis y deja la fijación unknown. Si no hay par respaldado permite assembly vacío y registra assembly_not_identifiable; no infieras hidden joinery ni números.",
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
            "allowed_typed_document_source_refs": list(
                allowed_typed_document_source_refs
            ),
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
        if cancelled is not None and cancelled():
            raise GeneralLiveError(
                "job_cancelled", trace=tuple(trace),
                model_calls=calls, tool_calls=tool_calls,
            )
        remaining = limits.timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            if last_incomplete is not None:
                return preserve_incomplete("agent_deadline_exceeded")
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
            error_code = _safe_live_error_code(exc)
            incomplete_reason = _safe_provider_incomplete_reason(exc)
            provider_metadata = {}
            if incomplete_reason is not None:
                provider_metadata["provider_incomplete_reason"] = incomplete_reason
            if last_incomplete is not None:
                return preserve_incomplete(
                    error_code, metadata=provider_metadata
                )
            trace.append({
                "tool": "provider_response",
                "ok": False,
                "summary": "Provider response ended before a proposal was available.",
                "reason_code": error_code,
                **provider_metadata,
            })
            raise GeneralLiveError(
                error_code, trace=tuple(trace),
                model_calls=calls, tool_calls=tool_calls,
                provider_status_code=getattr(exc, "status_code", None),
                provider_code=getattr(exc, "provider_code", None),
                provider_request_id=getattr(exc, "request_id", None),
                provider_response_id=getattr(exc, "response_id", None),
                provider_incomplete_reason=incomplete_reason,
            ) from exc
        if cancelled is not None and cancelled():
            raise GeneralLiveError(
                "job_cancelled", trace=tuple(trace),
                model_calls=calls, tool_calls=tool_calls,
            )
        previous_response_id = response.id
        if not response.tool_calls:
            input_items = [
                {"role": "user", "content": "Debes usar una herramienta permitida."}
            ]
            if last_incomplete is not None and calls > incomplete_seen_at_call:
                incomplete_followup_responses += 1
                if incomplete_followup_responses >= max(
                    1, limits.max_validation_repairs
                ):
                    return preserve_incomplete(
                        "post_proposal_inspection_budget_exhausted"
                    )
            continue
        if tool_calls + len(response.tool_calls) > limits.max_tool_calls:
            if last_incomplete is not None:
                return preserve_incomplete("tool_call_budget_exhausted")
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
                    accounting = build_evidence_accounting_report(
                        extraction,
                        proposal,
                        draft,
                        projection_hypotheses=projection_hypotheses,
                        orthographic_hypotheses=orthographic_hypotheses,
                    )
                    if not accounting.reviewable:
                        last_incomplete = (proposal, draft, accounting)
                        incomplete_seen_at_call = calls
                        incomplete_followup_responses = 0
                        if repairs < limits.max_validation_repairs:
                            raise ProposalEvidenceAccountingError(accounting)
                        trace.append(
                            {
                                "tool": call.name,
                                "ok": False,
                                "summary": (
                                    "Proposal preserved as incomplete after bounded "
                                    "evidence-accounting repairs."
                                ),
                                "evidence_accounting": accounting.to_payload(),
                                **metadata,
                            }
                        )
                        return GeneralFurnitureAgentOutcome(
                            proposal, draft, calls, tool_calls, tuple(trace)
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
                    if last_incomplete is not None:
                        return preserve_incomplete(
                            "validation_repair_budget_exhausted"
                        )
                    raise GeneralLiveError(
                        "validation_repair_budget_exhausted",
                        trace=tuple(trace), model_calls=calls,
                        tool_calls=tool_calls,
                    ) from exc
                data = {
                    "ok": False,
                    "error": "invalid_arguments",
                    "details": details,
                    "reference_authority": reference_authority,
                }
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(data, ensure_ascii=False),
                }
            )
        input_items = outputs
        if last_incomplete is not None and calls > incomplete_seen_at_call:
            incomplete_followup_responses += 1
            if incomplete_followup_responses >= max(
                1, limits.max_validation_repairs
            ):
                return preserve_incomplete(
                    "post_proposal_inspection_budget_exhausted"
                )
    if last_incomplete is not None:
        return preserve_incomplete("model_call_budget_exhausted")
    raise GeneralLiveError(
        "model_call_budget_exhausted", trace=tuple(trace),
        model_calls=calls, tool_calls=tool_calls,
    )
