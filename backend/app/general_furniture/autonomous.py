from __future__ import annotations

import hashlib
import json
import time
from base64 import b64encode
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

from pydantic import ValidationError

from backend.app.contratos.modelos import (
    GeneralAutoReviewArgs,
    GeneralAutoReviewDecisionArgs,
    GeneralAutoReviewCheck,
    GeneralComponentReview,
    GeneralCostBasis,
    GeneralDerivedPackage,
    GeneralFurnitureProposal,
    GeneralFurnitureReview,
    GeneralFurnitureReviewRequest,
    GeneralMachineProvenance,
    GeneralReviewOperation,
    GeneralScenarioOccurrence,
    GeneralScene,
    GeneralTextValue,
    ProposeGeneralFurnitureArgs,
)
from backend.app.general_furniture.derivations import derive_general_package
from backend.app.general_furniture.live import (
    GeneralFurnitureAgentOutcome,
    _is_raster_without_metric_ledger,
    _safe_validation_details,
    _strictify,
    general_allowed_document_refs,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.context_payload import (
    build_compact_geometry_context,
    query_compact_measurements,
)
from backend.app.general_furniture.construction_validation import (
    validate_construction_scenario,
)
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.projection_hypotheses import (
    derive_projection_hypotheses,
    derive_source_spatial_regions,
)
from backend.app.general_furniture.review import apply_general_review


AUTO_REVIEW_POLICY_VERSION = "general-auto-review-v2"
GENERAL_AUTO_REVIEW_PROMPT = """Actúas como crítico multimodal separado del proponente. Contrasta cada propuesta con imágenes reales, geometría y referencias del ledger.
Primero llama entregar_revision_autonoma. Si el servidor responde repair_requested, llama una sola vez proponer_mueble_general con una propuesta completa corregida; después vuelve a llamar entregar_revision_autonoma sobre esa propuesta.
No midas píxeles ni inventes valores. Las dimensiones observadas solo proceden del ledger. Las dimensiones deduced/estimated pueden proceder de parámetros constructivos declarados, con nominal, rango, método, dependencias y supuestos explícitos; no las rechaces solo por no ser observadas. Una cantidad provisional hypothesis/deduced/estimated requiere premisa declarada y checks quantity_basis+duplicate_scan; nunca cuentes vistas como instancias.
Una cota observed solo puede sostener la dimensión de la misma geometría visible. Si se copió a una pieza oculta o a otro componente por mera semejanza constructiva, rechaza esa transferencia y solicita un parámetro estimated separado con rango y premisa; sus dependientes permanecen estimated.
Aceptar significa que una hipótesis es coherente, no que sea un hecho observado. Contrasta cada candidato en sus regiones: un contorno cerrado puede ser cara material, hueco, rebaje o límite interior. Busca duplicados entre proyecciones, incoherencias dimensionales y bases de cantidad antes de aceptar.
Contrasta también la estabilidad global: vuelco, descuadre y arriostramiento. Cuando el escenario lo requiera, exige un detalle estimated explícito de estabilización o anclaje con premisa, ubicación y referencias; una simple nota pendiente no resuelve el escenario.
Cada check model_visual debe citar en source_refs al menos una referencia visual exacta del contexto, también los checks de cantidad y duplicados de detalles estimados. Las premisas por sí solas no constituyen evidencia visual; no inventes referencias para completar un check.
Decide explícitamente cada cota numérica anunciada en `required_dimension_field_review_targets`. Aceptar un parámetro no acepta automáticamente su asignación a length/width/thickness del componente: cada aceptación de campo cita un check model_visual pass dirigido a ese target exacto; cuando no puedas contrastarlo usa abstained, rejected o conflict. Para cada grupo `required_hardware_classification_field_review_targets`, decide al menos kind o geometry. Aceptar `kind=hardware` es una clasificación constructiva provisional del elemento propuesto como comprado/no fabricado: no identifica ni certifica un modelo comercial, fabricante, medidas de catálogo, capacidad o presencia observada. Puedes aceptar kind cuando función, detalle, cantidad, encaje, premisas y contexto visual sostienen su necesidad en el escenario aunque el herraje quede oculto; no exijas una ficha comercial. Mantén geometry específica, modelo, carga, fijación y cotas desconocidas o abstained cuando no estén justificadas.
La geometry de un detalle usa coordenadas locales de la cara de cada pieza asociada, nunca coordenadas del mueble completo. Divide los detalles por pieza cuando tengan orígenes o dimensiones diferentes; comprueba sus límites antes de proponerlos.
Usa solo checks method=model_visual y los `allowed_target_refs` exactos del input. Pueden ser campos `component:<id>.<campo>` o `parameter:`, `constraint:`, `detail:` y `decision:` anunciados. Rechaza geometría, identidad, existencia, parámetros o restricciones contradictorias; acepta estimaciones plausibles con base cerrada. El servidor recalcula bindings y restricciones deterministas. Si la evidencia no basta, abstente o marca incomplete/conflict sin pedir revisión humana. Nunca te declares independiente ni confirmado."""


class ReviewerProvider(Protocol):
    def create_response(self, *, input_items, tools, previous_response_id, timeout_s): ...


class GeneralAutonomousError(RuntimeError):
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


class _MissingDimensionFieldReviews(ValueError):
    def __init__(
        self,
        targets: tuple[str, ...],
        hardware_target_groups: tuple[tuple[str, ...], ...] = (),
    ) -> None:
        super().__init__("machine_dimension_field_reviews_required")
        self.targets = targets
        self.hardware_target_groups = hardware_target_groups


class _MissingHardwareClassificationReviews(ValueError):
    def __init__(self, target_groups: tuple[tuple[str, ...], ...]) -> None:
        super().__init__("machine_hardware_classification_field_review_required")
        self.target_groups = target_groups


def _safe_autonomous_validation_details(
    error: Exception,
) -> list[dict[str, object]]:
    if isinstance(error, _MissingDimensionFieldReviews):
        return [{
            "loc": ["field_reviews"],
            "msg": "machine_dimension_field_reviews_required",
            "type": "value_error",
            "missing_count": len(error.targets),
            "missing_targets": list(error.targets[:64]),
            "missing_hardware_any_of": [
                list(group) for group in error.hardware_target_groups[:64]
            ],
            "truncated": (
                len(error.targets) > 64
                or len(error.hardware_target_groups) > 64
            ),
        }]
    if isinstance(error, _MissingHardwareClassificationReviews):
        return [{
            "loc": ["field_reviews"],
            "msg": "machine_hardware_classification_field_review_required",
            "type": "value_error",
            "missing_count": len(error.target_groups),
            "missing_any_of": [list(group) for group in error.target_groups[:64]],
            "truncated": len(error.target_groups) > 64,
        }]
    return _safe_validation_details(error)


def _safe_autonomous_error_code(error: Exception) -> str:
    candidate = getattr(error, "code", None)
    if (
        isinstance(candidate, str)
        and 0 < len(candidate) <= 120
        and all(character.isalnum() or character in "_:-" for character in candidate)
    ):
        return candidate
    if isinstance(error, TimeoutError):
        return "general_auto_review_timeout"
    return "general_auto_review_failed"


@dataclass(frozen=True)
class AutoReviewLimits:
    max_model_calls: int = 5
    max_tool_calls: int = 5
    max_validation_repairs: int = 1
    max_semantic_repairs: int = 2
    max_derivation_repairs: int = 1
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_model_calls <= 5 or not 1 <= self.max_tool_calls <= 5:
            raise ValueError("general_auto_review_call_budget_invalid")
        if not 0 <= self.max_validation_repairs <= 2:
            raise ValueError("general_auto_review_validation_budget_invalid")
        if self.max_semantic_repairs not in (0, 1, 2):
            raise ValueError("general_auto_review_semantic_budget_invalid")
        if self.max_derivation_repairs not in (0, 1):
            raise ValueError("general_auto_review_derivation_budget_invalid")
        if self.timeout_s <= 0 or self.timeout_s > 300:
            raise ValueError("general_auto_review_timeout_budget_invalid")


@dataclass(frozen=True)
class GeneralAutonomousOutcome:
    original_proposal_outcome: GeneralFurnitureAgentOutcome
    effective_proposal_outcome: GeneralFurnitureAgentOutcome
    critic_snapshots: tuple[GeneralAutoReviewArgs, ...]
    semantic_repairs: int
    review: GeneralFurnitureReview
    derived: object
    trace: tuple[dict[str, object], ...]
    model_calls: int
    tool_calls: int
    status: str


@dataclass(frozen=True)
class GeneralAutonomousCheckpoint:
    phase: str
    proposal_revision: int
    proposal_outcome: GeneralFurnitureAgentOutcome
    critic_snapshot: GeneralAutoReviewArgs | None
    trace_event: dict[str, object]


def _derivation_failed_package(review: GeneralFurnitureReview) -> GeneralDerivedPackage:
    """Persist a valid review even when deterministic export remains unavailable."""
    return GeneralDerivedPackage(
        run_id=review.run_id,
        proposal_revision=review.proposal_revision,
        review_revision=review.review_revision,
        status="incomplete",
        bom_rows=(),
        artifacts=(),
        scene=GeneralScene(
            status="unavailable", items=(),
            warnings=("Derivación determinista no disponible; la revisión se conserva.",),
        ),
        cost_basis=GeneralCostBasis(
            status="unavailable", contributors=(),
            missing_data=("derivation_failed",),
        ),
        construction=None,
    )


def _tool_schemas(*, raster_without_metric_ledger: bool = False) -> list[dict]:
    def schema(name: str, description: str, model: type) -> dict:
        return {"type": "function", "name": name, "description": description, "parameters": _strictify(model.model_json_schema()), "strict": True}

    repair_description = (
        "Repara una propuesta visual rechazada sin inventar ledger: usa bindings=[], "
        "ejes null, source_view_ids=[] y solo source_document_refs exactas anunciadas."
        if raster_without_metric_ledger
        else (
            "Repara una propuesta rechazada. Solo lo observed usa el ledger; "
            "estimated declara nominal, rango, método, source_refs y premise refs, "
            "y toda dimensión dependiente conserva estado estimated. Las cantidades "
            "provisionales requieren premisas cerradas. No transfieras una cota observed "
            "a piezas ocultas u otros componentes: crea allí un parámetro estimated separado. "
            "Resuelve estabilidad necesaria con un detalle estimated explícito, no una nota pendiente."
        )
    )
    return [
        schema("entregar_revision_autonoma", "Entrega solo checks y decisiones por campo. Debes incluir un field_review explícito para cada target de required_dimension_field_review_targets y al menos un any_of de cada required_hardware_classification_field_review_targets; accepted exige un check model_visual pass dirigido al mismo target. kind=hardware accepted es clasificación constructiva provisional de elemento comprado/no fabricado, no certificación ni identificación comercial; geometry y especificaciones pueden quedar abstained. El servidor conserva componentes y operaciones; cualquier corrección estructural usa proponer_mueble_general.", GeneralAutoReviewDecisionArgs),
        schema("proponer_mueble_general", repair_description, ProposeGeneralFurnitureArgs),
    ]


def _deterministic_checks(args: GeneralAutoReviewArgs) -> tuple[GeneralAutoReviewCheck, ...]:
    checks = []
    for component in args.components:
        for field in ("length", "width", "thickness"):
            value = getattr(component, field)
            if value.value_mm is not None:
                checks.append(GeneralAutoReviewCheck(
                    id=f"det:{component.id}.{field}", kind="dimension_binding", outcome="pass", method="deterministic",
                    target_refs=(f"component:{component.id}.{field}",), source_refs=value.dependency_refs,
                    summary="El servidor recalculó el binding numérico sin introducir valores nuevos.",
                ))
    return tuple(checks)


def _review_target_refs(proposal, draft) -> set[str]:
    component_targets = {
        f"component:{component.id}.{field}"
        for component in draft.components
        for field in (
            "length", "width", "thickness", "quantity", "material", "finish",
            "existence", "kind", "role", "geometry",
        )
    }
    return component_targets | {
        *(f"parameter:{item.id}" for item in draft.construction_parameters),
        *(f"constraint:{item.id}" for item in draft.construction_constraints),
        *(f"detail:{item.id}" for item in draft.construction_details),
        *(f"decision:{item.id}" for item in draft.construction_decisions),
    }


def _required_numeric_dimension_targets(components) -> tuple[str, ...]:
    return tuple(sorted(
        f"component:{component.id}.{field}"
        for component in components
        for field in ("length", "width", "thickness")
        if getattr(component, field).value_mm is not None
    ))


def _required_hardware_classification_target_groups(
    components,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (
            f"component:{component.id}.kind",
            f"component:{component.id}.geometry",
        )
        for component in components
        if component.kind == "hardware"
        or (
            component.geometry is not None
            and component.geometry.shape_kind == "hardware"
        )
    )


def _validate_numeric_dimension_review_coverage(args: GeneralAutoReviewArgs) -> None:
    reviewed = {item.target_ref for item in args.field_reviews}
    missing = tuple(
        target for target in _required_numeric_dimension_targets(args.components)
        if target not in reviewed
    )
    missing_hardware = tuple(
        group
        for group in _required_hardware_classification_target_groups(args.components)
        if not reviewed.intersection(group)
    )
    if missing:
        raise _MissingDimensionFieldReviews(missing, missing_hardware)
    if missing_hardware:
        raise _MissingHardwareClassificationReviews(missing_hardware)
def _validate_visual_checks(
    args: GeneralAutoReviewArgs,
    allowed_source_refs: set[str],
    visual_refs: set[str],
    allowed_target_refs: set[str] | None = None,
) -> None:
    checks = {item.id: item for item in args.checks}
    valid_targets = allowed_target_refs or {
        f"component:{component.id}.{field}"
        for component in args.components
        for field in (
            "length", "width", "thickness", "quantity", "material", "finish",
            "existence", "kind", "role", "geometry",
        )
    }
    for check in args.checks:
        if check.method != "model_visual" or check.kind in {"geometry_match", "dimension_binding"}:
            raise ValueError("reviewer_cannot_claim_deterministic_check")
        if not set(check.target_refs) <= valid_targets:
            raise ValueError("machine_check_targets_unknown_field")
        if not set(check.source_refs) <= allowed_source_refs or not set(check.source_refs) & visual_refs:
            raise ValueError("visual_check_reference_outside_context")
    for field_review in args.field_reviews:
        if field_review.target_ref not in valid_targets:
            raise ValueError("machine_field_review_targets_unknown_field")
        if field_review.status == "accepted" and not any(
            check_id in checks
            and checks[check_id].outcome == "pass"
            and field_review.target_ref in checks[check_id].target_refs
            for check_id in field_review.check_ids
        ):
            raise ValueError("accepted_machine_field_requires_targeted_visual_check")
        if field_review.status == "accepted" and field_review.target_ref.endswith(".quantity"):
            selected = [checks.get(check_id) for check_id in field_review.check_ids]
            if (
                any(item is None or item.outcome != "pass" for item in selected)
                or not {"quantity_basis", "duplicate_scan"}
                <= {item.kind for item in selected if item is not None}
            ):
                raise ValueError("accepted_provisional_quantity_requires_closed_checks")


def _reject_forged_machine_facts(args: GeneralAutoReviewArgs) -> None:
    for component in args.components:
        for value in (component.length, component.width, component.thickness, component.quantity, component.material, component.finish):
            if value.state == "confirmed" or any(ref.startswith("human:") for ref in value.dependency_refs):
                raise ValueError("machine_review_cannot_confirm_fields")


def _server_review_args(
    decision: GeneralAutoReviewDecisionArgs,
    draft,
    previous_review: GeneralFurnitureReview | None,
) -> GeneralAutoReviewArgs:
    if previous_review is not None:
        components = tuple(
            item.model_copy(update={"replaces_component_ids": (item.id,)})
            for item in previous_review.components
        )
    else:
        components = tuple(
            GeneralComponentReview(
                id=item.id,
                label=item.label,
                kind=item.kind,
                role=item.role,
                length=item.length,
                width=item.width,
                thickness=item.thickness,
                quantity=item.quantity,
                material=GeneralTextValue(value=None, state="unknown"),
                finish=GeneralTextValue(value=None, state="unknown"),
                replaces_component_ids=(item.id,),
                source_view_ids=item.source_view_ids,
                source_observation_ids=item.source_observation_ids,
                source_contour_ids=item.source_contour_ids,
                source_evidence_ids=item.source_evidence_ids,
                source_dimension_ids=item.source_dimension_ids,
                source_document_refs=item.source_document_refs,
                assumptions=item.assumptions,
                unknown_fields=item.unknown_fields,
                scenario_id=item.scenario_id,
                necessity=item.necessity,
                geometry=item.geometry,
                construction_parameter_ids=item.construction_parameter_ids,
                detail_ids=item.detail_ids,
                quantity_basis_refs=item.quantity_basis_refs,
            )
            for item in draft.components
        )
    operations = tuple(
        GeneralReviewOperation(
            kind="replace",
            source_component_ids=(item.id,),
            result_component_ids=(item.id,),
            reason="Continuidad del snapshot; el crítico no reescribe componentes.",
        )
        for item in components
    )
    return GeneralAutoReviewArgs(
        scenario_id=decision.scenario_id,
        operations=operations,
        components=components,
        checks=decision.checks,
        field_reviews=decision.field_reviews,
        unresolved=decision.unresolved,
        status=decision.status,
    )


def _effective_auto_status(args: GeneralAutoReviewArgs, construction_validation=None) -> str:
    if construction_validation is not None and construction_validation.status == "invalid":
        return "conflict"
    if any(item.outcome == "fail" for item in args.checks) or any(item.status in {"rejected", "conflict"} for item in args.field_reviews):
        return "conflict"
    if args.status == "abstained":
        return "abstained"
    accepted = {item.target_ref for item in args.field_reviews if item.status == "accepted"}
    for component in args.components:
        if component.unknown_fields:
            return "incomplete"
        for field in ("length", "width", "thickness", "quantity", "material", "finish"):
            if getattr(component, field).state in {"unknown", "conflict"} or f"component:{component.id}.{field}" not in accepted:
                return "incomplete"
    return "accepted" if args.status == "accepted" and not args.unresolved else "incomplete"


def _repair_is_supported(args: GeneralAutoReviewArgs, construction_validation=None) -> bool:
    return (
        construction_validation is not None
        and construction_validation.status == "invalid"
    ) or any(item.outcome == "fail" and item.kind in {"cross_view_identity", "duplicate_scan", "quantity_basis", "visual_consistency"} for item in args.checks) or any(item.status in {"rejected", "conflict"} for item in args.field_reviews)


def _scenario_occurrences(args: GeneralAutoReviewArgs, checks: tuple[GeneralAutoReviewCheck, ...]) -> tuple[GeneralScenarioOccurrence, ...]:
    by_id = {item.id: item for item in checks}
    accepted = {item.target_ref: item for item in args.field_reviews if item.status == "accepted"}
    result = []
    for component in args.components:
        target = f"component:{component.id}.quantity"
        field_review = accepted.get(target)
        if (
            component.quantity.state not in {"hypothesis", "estimated", "deduced"}
            or component.quantity.value is None
            or field_review is None
        ):
            continue
        selected = [by_id.get(check_id) for check_id in field_review.check_ids]
        if any(item is None or item.outcome != "pass" for item in selected) or not {"quantity_basis", "duplicate_scan"} <= {item.kind for item in selected if item is not None}:
            continue
        sources = tuple(dict.fromkeys(ref for item in selected if item is not None for ref in item.source_refs))
        result.extend(GeneralScenarioOccurrence(
            id=f"provisional:{args.scenario_id}:{component.id}:{index}", component_id=component.id, occurrence_index=index,
            scenario_id=args.scenario_id, quantity_target_ref=target, check_ids=field_review.check_ids,
            premise_refs=component.quantity.dependency_refs, source_refs=sources,
        ) for index in range(1, component.quantity.value + 1))
    return tuple(result)


def _visual_metadata(page) -> dict[str, object]:
    return {
        "reference": f"visual:{page.reference}", "sha256": page.sha256,
        "source_view_ids": list(getattr(page, "source_view_ids", ())),
        "source_contour_ids": list(getattr(page, "source_contour_ids", ())),
        "source_document_refs": list(getattr(page, "source_document_refs", ())),
        "crop_bounds_source": getattr(page, "crop_bounds_source", None),
        "marks": [asdict(item) for item in getattr(page, "marks", ())],
        "warnings": list(getattr(page, "warnings", ())),
        "authority": "visual_context_not_measurement_source",
    }


def _review_input(context, outcome: GeneralFurnitureAgentOutcome) -> list[dict]:
    measurements = derive_geometry_measurements(context.extraction)
    raster_without_metric_ledger = _is_raster_without_metric_ledger(
        context.extraction, measurements, context.visual_pages
    )
    allowed_document_refs = general_allowed_document_refs(
        context.visual_pages,
        include_announced_children=raster_without_metric_ledger,
    )
    try:
        regions = derive_source_spatial_regions(context.extraction, measurements)
        projections = derive_projection_hypotheses(context.extraction, measurements)
        projection_warnings: tuple[str, ...] = ()
    except ValueError as exc:
        if str(exc) != "projection_input_budget_exceeded":
            raise
        regions = ()
        projections = ()
        projection_warnings = ("projection_input_budget_exceeded",)
    measurement_ids = tuple(dict.fromkeys(
        reference.removeprefix("measurement:")
        for binding in outcome.proposal.bindings
        for reference in binding.operand_refs
        if reference.startswith("measurement:")
    ))
    measurement_by_id = {item.id: item for item in measurements}
    referenced_segment_ids = tuple(
        value for value in measurement_ids
        if value in measurement_by_id
        and measurement_by_id[value].semantic == "contour_segment_length"
    )
    if len(referenced_segment_ids) > 128:
        raise ValueError("general_auto_referenced_measurement_budget_exceeded")
    referenced_measurements: list[dict[str, object]] = []
    offset = 0
    while offset < len(referenced_segment_ids):
        page = query_compact_measurements(
            measurements,
            measurement_ids=referenced_segment_ids,
            offset=offset,
            limit=64,
        )
        referenced_measurements.extend(page.to_payload()["items"])
        if page.next_offset is None:
            break
        offset = page.next_offset
    allowed_target_refs = sorted(_review_target_refs(outcome.proposal, outcome.draft))
    required_dimension_field_review_targets = list(
        _required_numeric_dimension_targets(outcome.draft.components)
    )
    required_hardware_classification_field_review_targets = [
        {"component_id": group[0].split(":", 1)[1].rsplit(".", 1)[0], "any_of": list(group)}
        for group in _required_hardware_classification_target_groups(
            outcome.draft.components
        )
    ]
    visible_source_refs = set()
    for page in context.visual_pages:
        visible_source_refs.add(f"visual:{page.reference}")
        visible_source_refs.update(page.source_contour_ids)
        visible_source_refs.update(mark.source_id for mark in page.marks)
        if raster_without_metric_ledger:
            visible_source_refs.add(page.reference)
            visible_source_refs.update(page.source_document_refs)
    allowed_source_refs = sorted(
        visible_source_refs
        | {f"premise:{item.id}" for item in outcome.proposal.premises}
    )
    payload = {
        "proposal": outcome.proposal.model_dump(mode="json"), "draft": outcome.draft.model_dump(mode="json"),
        "compact_geometry": build_compact_geometry_context(
            context.extraction, measurements, regions, projections
        ).to_payload(),
        "referenced_segment_measurements": referenced_measurements,
        "allowed_target_refs": allowed_target_refs,
        "required_dimension_field_review_targets": required_dimension_field_review_targets,
        "required_hardware_classification_field_review_targets": required_hardware_classification_field_review_targets,
        "allowed_source_refs": allowed_source_refs,
        "target_ref_format": "component:<component_id>.<length|width|thickness|quantity|material|finish|existence|kind|role|geometry> or parameter:<id> or constraint:<id> or detail:<id> or decision:<id>",
        "projection_warnings": projection_warnings,
        "projection_authority": "ambiguous_hypotheses_not_physical_identity_or_quantity",
        "visual_artifacts": [_visual_metadata(item) for item in context.visual_pages],
        "instruction": "Entrega solo checks, field_reviews, unresolved y status; no reescribas components ni operations. Debes decidir explícitamente cada required_dimension_field_review_target; aceptar un parameter no sustituye decidir su asignación al campo del componente. Para cada required_hardware_classification_field_review_target decide al menos uno de sus any_of. accepted kind=hardware es una clasificación constructiva provisional de elemento comprado/no fabricado, no una certificación comercial ni una afirmación de presencia observada; puede apoyarse en función, detalle, cantidad, encaje, premisas y contexto visual aunque el elemento quede oculto. Geometry, modelo, carga, fijación y cotas no justificadas permanecen abstained/unknown. accepted exige un check model_visual pass que incluya ese mismo target; si no basta la evidencia usa abstained/rejected/conflict. Usa target/source refs exactos de las listas permitidas. Rechaza con checks solo errores corregibles; ausencia irreducible permanece unknown/incomplete.",
    }
    if raster_without_metric_ledger:
        payload["allowed_document_refs"] = list(allowed_document_refs)
        payload["raster_authority"] = {
            "allowed_source_view_ids": [],
            "allowed_source_document_refs": list(allowed_document_refs),
            "allowed_numeric_binding_refs": [],
            "instruction": (
                "La página raster no crea una vista de ledger. Conserva source_view_ids=[], "
                "bindings=[] y ejes null; las referencias documentales deben pertenecer "
                "exactamente a allowed_source_document_refs."
            ),
        }
    content = [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}]
    content.extend({"type": "input_image", "image_url": f"data:{item.media_type};base64,{b64encode(item.content).decode('ascii')}", "detail": "high"} for item in context.visual_pages)
    return [{"role": "user", "content": content}]


def _materialize_repair(context, raw: dict) -> GeneralFurnitureAgentOutcome:
    args = ProposeGeneralFurnitureArgs.model_validate_json(json.dumps(raw), strict=True)
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    proposal = GeneralFurnitureProposal(
        id=f"general-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}", drawing_id=context.extraction.drawing_id,
        ledger_revision=context.ledger_revision, proposal_origin="native_tool", **args.model_dump(),
    )
    measurements = derive_geometry_measurements(context.extraction)
    raster_without_metric_ledger = _is_raster_without_metric_ledger(
        context.extraction, measurements, context.visual_pages
    )
    draft = materialize_general_proposal(
        context.extraction,
        proposal,
        allowed_document_refs=general_allowed_document_refs(
            context.visual_pages,
            include_announced_children=raster_without_metric_ledger,
        ),
    )
    return GeneralFurnitureAgentOutcome(proposal, draft, 0, 1, ())


def run_general_autonomous(
    context,
    proposal_outcome: GeneralFurnitureAgentOutcome,
    *,
    reviewer_provider: ReviewerProvider,
    proposer_model: str | None,
    limits: AutoReviewLimits = AutoReviewLimits(),
    proposal_revision: int = 1,
    previous_review: GeneralFurnitureReview | None = None,
    checkpoint_sink: Callable[[GeneralAutonomousCheckpoint], None] | None = None,
) -> GeneralAutonomousOutcome:
    if len(context.visual_pages) > 4 or any(len(item.content) > 4 * 1024 * 1024 for item in context.visual_pages):
        raise ValueError("general_auto_visual_context_budget_exceeded")
    started = time.monotonic()
    previous_response_id = None
    response_ids: list[str] = []
    trace: list[dict[str, object]] = []
    snapshots: list[GeneralAutoReviewArgs] = []
    validation_repairs = semantic_repairs = tool_calls = 0
    effective = proposal_outcome
    visual_refs = {f"visual:{item.reference}" for item in context.visual_pages}
    for page in context.visual_pages:
        visual_refs.update(page.source_contour_ids)
        visual_refs.update(mark.source_id for mark in page.marks)
    measurements = derive_geometry_measurements(context.extraction)
    raster_without_metric_ledger = _is_raster_without_metric_ledger(
        context.extraction, measurements, context.visual_pages
    )
    allowed_refs = set(visual_refs)
    if raster_without_metric_ledger:
        for page in context.visual_pages:
            visual_refs.add(page.reference)
            visual_refs.update(page.source_document_refs)
            allowed_refs.add(page.reference)
            allowed_refs.update(page.source_document_refs)
    allowed_refs.update(f"view:{item.id}" for item in context.extraction.views)
    allowed_refs.update(f"contour:{item.id}" for item in context.extraction.contours)
    allowed_refs.update(f"dimension:{item.id}" for item in context.extraction.dimensions)
    allowed_refs.update(f"evidence:{item.id}" for item in context.extraction.evidence)
    allowed_refs.update(item.binding_ref for item in measurements)
    input_items = _review_input(context, effective)

    for model_call in range(1, limits.max_model_calls + 1):
        remaining = limits.timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            raise GeneralAutonomousError(
                "general_auto_review_timeout", trace=tuple(trace),
                model_calls=model_call - 1, tool_calls=tool_calls,
            )
        try:
            response = reviewer_provider.create_response(
                input_items=input_items,
                tools=_tool_schemas(
                    raster_without_metric_ledger=raster_without_metric_ledger
                ),
                previous_response_id=previous_response_id,
                timeout_s=remaining,
            )
        except GeneralAutonomousError:
            raise
        except Exception as exc:
            raise GeneralAutonomousError(
                _safe_autonomous_error_code(exc), trace=tuple(trace),
                model_calls=model_call, tool_calls=tool_calls,
            ) from exc
        previous_response_id = response.id
        response_ids.append(response.id)
        if not response.tool_calls:
            input_items = [{"role": "user", "content": "Debes usar una herramienta permitida."}]
            continue
        call = response.tool_calls[0]
        tool_calls += 1
        if tool_calls > limits.max_tool_calls:
            raise GeneralAutonomousError(
                "general_auto_review_tool_call_budget_exhausted",
                trace=tuple(trace), model_calls=model_call, tool_calls=tool_calls,
            )
        try:
            raw = json.loads(call.arguments_json) if call.arguments_json is not None else call.arguments
            if not isinstance(raw, dict):
                raise TypeError("tool arguments must be an object")
            if call.name == "proponer_mueble_general":
                if not snapshots or semantic_repairs >= limits.max_semantic_repairs:
                    raise ValueError("semantic_repair_not_requested")
                repaired = _materialize_repair(context, raw)
                if repaired.proposal.id == effective.proposal.id:
                    raise ValueError("semantic_repair_must_change_proposal")
                effective = repaired
                semantic_repairs += 1
                event = {"tool": call.name, "ok": True, "summary": "Propuesta semántica reparada contra el mismo ledger.", "phase": "general_auto_semantic_repair", "provider_response_id": response.id, "provider_model": getattr(response, "model", None), "provider_call_id": call.call_id}
                trace.append(event)
                if checkpoint_sink is not None:
                    checkpoint_sink(GeneralAutonomousCheckpoint(
                        phase="semantic_repair",
                        proposal_revision=proposal_revision + semantic_repairs,
                        proposal_outcome=effective,
                        critic_snapshot=None,
                        trace_event=event,
                    ))
                repaired_targets = sorted(
                    _review_target_refs(effective.proposal, effective.draft)
                )
                repaired_required_dimensions = list(
                    _required_numeric_dimension_targets(effective.draft.components)
                )
                repaired_hardware_targets = [
                    {"component_id": group[0].split(":", 1)[1].rsplit(".", 1)[0], "any_of": list(group)}
                    for group in _required_hardware_classification_target_groups(
                        effective.draft.components
                    )
                ]
                input_items = [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps({"ok": True, "status": "proposal_repaired", "proposal": effective.proposal.model_dump(mode="json"), "draft": effective.draft.model_dump(mode="json"), "allowed_target_refs": repaired_targets, "required_dimension_field_review_targets": repaired_required_dimensions, "required_hardware_classification_field_review_targets": repaired_hardware_targets, "instruction": "Revisa ahora la propuesta reparada. Entrega solo checks/decisiones; no components/operations. Decide explícitamente cada required_dimension_field_review_target y al menos un any_of por clasificación hardware; accepted exige check model_visual pass dirigido al mismo target. kind=hardware accepted solo clasifica provisionalmente un elemento comprado/no fabricado; no certifica ni identifica un modelo comercial, y geometry/especificaciones pueden quedar abstained."}, ensure_ascii=False)}]
                continue
            if call.name != "entregar_revision_autonoma":
                raise ValueError("unknown_tool")
            current_revision = proposal_revision + semantic_repairs
            current_previous = previous_review if semantic_repairs == 0 else None
            decision = GeneralAutoReviewDecisionArgs.model_validate_json(
                json.dumps(raw), strict=True
            )
            args = _server_review_args(decision, effective.draft, current_previous)
            _validate_numeric_dimension_review_coverage(args)
            current_allowed_refs = allowed_refs | {
                f"premise:{item.id}" for item in effective.proposal.premises
            }
            _validate_visual_checks(
                args,
                current_allowed_refs,
                visual_refs,
                _review_target_refs(effective.proposal, effective.draft),
            )
            _reject_forged_machine_facts(args)
            request = GeneralFurnitureReviewRequest(
                base_proposal_revision=current_revision,
                base_review_revision=current_previous.review_revision if current_previous else 0,
                reviewer_name="autonomous-reviewer", reason="Revisión multimodal autónoma provisional.",
                operations=args.operations, components=args.components,
            )
            base_review = apply_general_review(
                run_id=context.run_id, proposal_id=effective.proposal.id, proposal_revision=current_revision,
                draft=effective.draft, request=request, previous_review=current_previous,
            )
            snapshots.append(args)
            construction_validation = validate_construction_scenario(
                effective.proposal, effective.draft
            )
            effective_status = _effective_auto_status(args, construction_validation)
            if effective_status in {"incomplete", "conflict"} and semantic_repairs < limits.max_semantic_repairs and _repair_is_supported(args, construction_validation):
                remaining_model_calls = limits.max_model_calls - model_call
                remaining_tool_calls = limits.max_tool_calls - tool_calls
                event = {"tool": call.name, "ok": True, "summary": "Crítica detectó un error semántico reparable.", "phase": "general_auto_critique", "provider_response_id": response.id, "provider_model": getattr(response, "model", None), "provider_call_id": call.call_id, "status": effective_status, "remaining_model_calls": remaining_model_calls, "remaining_tool_calls": remaining_tool_calls}
                trace.append(event)
                if checkpoint_sink is not None:
                    checkpoint_sink(GeneralAutonomousCheckpoint(
                        phase="critic",
                        proposal_revision=current_revision,
                        proposal_outcome=effective,
                        critic_snapshot=args,
                        trace_event=event,
                    ))
                if remaining_model_calls >= 2 and remaining_tool_calls >= 2:
                    repair_output = {
                        "ok": True,
                        "status": "repair_requested",
                        "unresolved": args.unresolved,
                        "construction_validation": construction_validation.model_dump(mode="json"),
                        "instruction": "Emite una propuesta completa corregida mediante proponer_mueble_general. Una cota observed solo sirve para la misma geometría visible; en piezas ocultas u otros componentes usa un parámetro estimated separado con rango y premisa. Resuelve estabilidad necesaria con detalle estimated explícito, no solo pendiente.",
                    }
                    if construction_validation.status == "invalid":
                        repair_output["instruction"] = (
                            "Corrige todas las restricciones deterministas fallidas mediante "
                            "una propuesta completa; conserva observaciones y no inventes cifras. "
                            "Las estimaciones válidas declaran nominal, rango, método y supuestos. "
                            "No transfieras cotas observed entre geometrías: piezas ocultas u otros "
                            "componentes requieren parámetro estimated separado. Resuelve estabilidad "
                            "necesaria con detalle estimated explícito."
                        )
                    if raster_without_metric_ledger:
                        repair_output.update({
                            "allowed_source_view_ids": [],
                            "allowed_source_document_refs": list(
                                general_allowed_document_refs(
                                    context.visual_pages,
                                    include_announced_children=True,
                                )
                            ),
                            "allowed_numeric_binding_refs": [],
                            "raster_instruction": "Usa bindings=[], ejes null y source_view_ids=[].",
                        })
                    input_items = [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(repair_output, ensure_ascii=False)}]
                    continue
                trace.append({
                    "tool": call.name,
                    "ok": False,
                    "summary": "Presupuesto insuficiente para una propuesta reparada y su crítica final; se conserva la revisión incompleta.",
                    "phase": "general_auto_repair_budget",
                    "remaining_model_calls": remaining_model_calls,
                    "remaining_tool_calls": remaining_tool_calls,
                    "diagnostic": "increase_general_review_max_calls_or_resume_from_checkpoint",
                })
            checks = _deterministic_checks(args) + args.checks
            relation = "self_review" if proposer_model and proposer_model == getattr(response, "model", None) else "separate_model"
            review_data = base_review.model_dump(mode="python") | {
                "reviewer_name": "autonomous-reviewer", "reviewer_kind": "machine",
                "machine_provenance": GeneralMachineProvenance(model=getattr(response, "model", None) or "unknown-model", policy_version=AUTO_REVIEW_POLICY_VERSION, response_ids=tuple(dict.fromkeys(response_ids)), review_relation=relation),
                "scenario_occurrences": _scenario_occurrences(args, checks), "machine_checks": checks,
                "machine_field_reviews": args.field_reviews, "auto_review_status": effective_status,
                "construction_validation": construction_validation,
                "status": base_review.status if effective_status == "accepted" else "reviewed_incomplete",
            }
            review = GeneralFurnitureReview.model_validate(review_data)
            derived = None
            for derivation_attempt in range(limits.max_derivation_repairs + 1):
                try:
                    derived = derive_general_package(review)
                    if derivation_attempt:
                        trace.append({
                            "tool": call.name, "ok": True,
                            "summary": "La derivación server-side se regeneró sin otra llamada al modelo.",
                            "phase": "general_auto_derivation_recovered",
                            "derivation_attempt": derivation_attempt + 1,
                        })
                    break
                except Exception:
                    trace.append({
                        "tool": call.name,
                        "ok": False,
                        "summary": "La derivación server-side falló después de una revisión válida.",
                        "phase": "general_auto_derivation",
                        "diagnostic": "general_auto_review_derivation_failed",
                        "derivation_attempt": derivation_attempt + 1,
                    })
                    if derivation_attempt >= limits.max_derivation_repairs:
                        derived = _derivation_failed_package(review)
                        effective_status = "incomplete"
                        trace.append({
                            "tool": call.name, "ok": True,
                            "summary": "Se conserva la revisión válida con un paquete derivado incompleto.",
                            "phase": "general_auto_derivation_fallback",
                            "diagnostic": "derivation_unavailable_review_persisted",
                        })
                        break
            assert derived is not None
            trace.append({"tool": call.name, "ok": True, "summary": "Revisión multimodal provisional completada.", "phase": "general_auto_review", "provider_response_id": response.id, "provider_model": getattr(response, "model", None), "provider_call_id": call.call_id, "provider_input_tokens": getattr(response, "input_tokens", None), "provider_output_tokens": getattr(response, "output_tokens", None), "provider_total_tokens": getattr(response, "total_tokens", None), "status": effective_status})
            return GeneralAutonomousOutcome(proposal_outcome, effective, tuple(snapshots), semantic_repairs, review, derived, tuple(trace), model_call, tool_calls, effective_status)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            validation_repairs += 1
            details = _safe_autonomous_validation_details(exc)
            trace.append({"tool": call.name, "ok": False, "summary": "Herramienta autónoma inválida rechazada.", "provider_response_id": response.id, "details": details})
            if validation_repairs > limits.max_validation_repairs:
                raise GeneralAutonomousError(
                    "general_auto_review_repair_budget_exhausted",
                    trace=tuple(trace), model_calls=model_call, tool_calls=tool_calls,
                ) from exc
            input_items = [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps({"ok": False, "error": "invalid_arguments", "details": details}, ensure_ascii=False)}]
    raise GeneralAutonomousError(
        "general_auto_review_model_call_budget_exhausted",
        trace=tuple(trace), model_calls=limits.max_model_calls, tool_calls=tool_calls,
    )
