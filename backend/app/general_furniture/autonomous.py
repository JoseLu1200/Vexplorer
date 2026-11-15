from __future__ import annotations

import hashlib
import json
import re
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
from backend.app.general_furniture.orthographic_hypotheses import (
    derive_orthographic_hypotheses,
)
from backend.app.general_furniture.context_payload import (
    build_compact_geometry_context,
    build_compact_review_context,
    build_region_visual_links,
    query_compact_measurements,
)
from backend.app.general_furniture.evidence_accounting import (
    EvidenceAccountingReport,
    build_evidence_accounting_report,
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


AUTO_REVIEW_POLICY_VERSION = "general-auto-review-v3"
GENERAL_AUTO_REVIEW_PROMPT = """Actúas como crítico multimodal separado del proponente. Contrasta cada propuesta con imágenes reales, geometría y referencias del ledger.
Primero llama entregar_revision_autonoma. Si el servidor responde repair_requested, llama una sola vez proponer_mueble_general con una propuesta completa corregida; después vuelve a llamar entregar_revision_autonoma sobre esa propuesta.
No midas píxeles ni inventes valores. Las dimensiones observadas solo proceden del ledger. Las dimensiones deduced/estimated pueden proceder de parámetros constructivos declarados, con nominal, rango, método, dependencias y supuestos explícitos; no las rechaces solo por no ser observadas. Una cantidad provisional hypothesis/deduced/estimated requiere premisa declarada y checks quantity_basis+duplicate_scan; nunca cuentes vistas como instancias.
Una cota observed solo puede sostener la dimensión de la misma geometría visible. Si se copió a una pieza oculta o a otro componente por mera semejanza constructiva, rechaza esa transferencia y solicita un parámetro estimated separado con rango y premisa; sus dependientes permanecen estimated.
Un componente fabricado debe representar un tipo de pieza física cortable, no un subensamblaje funcional agregado. Cuando existencia y cantidad de un conjunto oculto necesario estén aceptadas y haya una premisa funcional cerrada, solicita descomponer el mínimo coherente de piezas fabricadas con kind, geometry y length/width/thickness estimated, cada valor con nominal, rango y premisa. No conviertas por ello campos ocultos en observed; si falta esa premisa, abstente y conserva unknown.
Aceptar significa que una hipótesis es coherente, no que sea un hecho observado. Contrasta cada candidato en sus regiones: un contorno cerrado puede ser cara material, hueco, rebaje o límite interior. Busca duplicados entre proyecciones, incoherencias dimensionales y bases de cantidad antes de aceptar.
Los IDs internos y el orden serializado de entidades sirven para trazabilidad, pero no prueban por sí solos identidad, cantidad ni correspondencias entre proyecciones. Decide esas relaciones mediante geometría, capas declaradas, anotaciones explícitas (incluidas etiquetas PART cuando existan) y contraste entre fuentes; conserva los IDs al citar la evidencia.
`compact_geometry.orthographic_hypotheses` solo facilita el contraste provisional de ejes, intervalos y alineaciones mediante sus refs `contour:` y `measurement:` anunciadas. El id de la hipótesis no es una referencia citable y la hipótesis no prueba identidad, ownership, cantidad ni material; tampoco clasifica un hueco ni contorno interior como pieza. Conserva alternativas many-to-many y la incertidumbre indicada por warnings/authority.
Para piezas de las mismas vistas, exige una sola alternativa de `orthographic_frame_alternatives` como alineación global; no mezcles direct y mirrored ni grupos incompatibles. Sus hypothesis_ids solo agrupan contexto, no son refs. El contexto ortográfico no define por sí solo un marco 2D de montaje: si x/y/rotation y todas las ocurrencias no tienen base cerrada, conserva `construction_placements=[]` y exige una decision category=assembly que explique ausencia y alternativas; rechaza coordenadas inventadas o autoridad observed.
Contrasta también la estabilidad global: vuelco, descuadre y arriostramiento. Cuando el escenario lo requiera, exige un detalle estimated explícito de estabilización o anclaje con premisa, ubicación y referencias; una simple nota pendiente no resuelve el escenario.
Cada check model_visual debe citar en source_refs al menos una referencia visual exacta del contexto, también los checks de cantidad y duplicados de detalles estimados. Las premisas por sí solas no constituyen evidencia visual; no inventes referencias para completar un check.
Decide explícitamente cada cota numérica anunciada en `required_dimension_field_review_targets`. Aceptar un parámetro no acepta automáticamente su asignación a length/width/thickness del componente: cada aceptación de campo cita un check model_visual pass dirigido a ese target exacto; cuando no puedas contrastarlo usa abstained, rejected o conflict. Para cada grupo `required_hardware_classification_field_review_targets`, decide al menos kind o geometry. Aceptar `kind=hardware` es una clasificación constructiva provisional del elemento propuesto como comprado/no fabricado: no identifica ni certifica un modelo comercial, fabricante, medidas de catálogo, capacidad o presencia observada. Puedes aceptar kind cuando función, detalle, cantidad, encaje, premisas y contexto visual sostienen su necesidad en el escenario aunque el herraje quede oculto; no exijas una ficha comercial. Mantén geometry específica, modelo, carga, fijación y cotas desconocidas o abstained cuando no estén justificadas.
Decide también cada `required_existence_field_review_target` y cada `required_evidence_disposition_review_target`. La cobertura contable no confirma existencia, identidad física, cantidad ni fabricabilidad. Un descarte nonmaterial requiere contraste dirigido; una duplicate_projection aceptada requiere duplicate_scan o cross_view_identity dirigido al target exacto. shared_projection_support requiere ambos checks pass, duplicate_scan y shared_projection_support, dirigidos al target exacto: verifica anclas assigned exclusivas, relación ortográfica global compatible y ausencia de ownership/cantidad. Un check puede cubrir varios targets contrastados, pero cada target conserva su field_review individual.
material/finish desconocidos permanecen visibles como unknown en el componente y en la base de coste; no son campos críticos de corte. No los aceptes sin evidencia, pero puedes omitir sus field_reviews y no los repitas en unresolved terminal cuando kind, existence, geometry, length, width, thickness y quantity ya cierran la pieza fabricada.
Los elementos de `evidence_accounting.invalid_region_reasons` son diagnósticos deterministas para reparar la propuesta y no son review targets salvo que su `evidence_region:*` aparezca literalmente en `allowed_target_refs`. Nunca dirijas checks ni field_reviews a un target omitido. Para aceptar cualquier quantity provisional, su field_review debe citar checks pass separados o combinados de `quantity_basis y duplicate_scan`, ambos dirigidos a esa quantity exacta.
La geometry de un detalle usa coordenadas locales de la cara de cada pieza asociada, nunca coordenadas del mueble completo: x recorre length e y recorre width. Divide los detalles por pieza cuando tengan orígenes o dimensiones diferentes; comprueba sus límites antes de proponerlos.
Las dimension_refs del detalle son opcionales y deben resolverse por el grafo constructivo, preferentemente parameter:<id>; un binding solo sirve si termina en parámetros resolubles. Las mediciones ledger van en source_refs, no directamente en dimension_refs. Si los puntos explícitos y los bounds de la pieza bastan, dimension_refs puede quedar vacío.
Usa solo checks method=model_visual y los `allowed_target_refs` exactos del input. Pueden ser campos `component:<id>.<campo>` o `parameter:`, `constraint:`, `detail:` y `decision:` anunciados. Rechaza geometría, identidad, existencia, parámetros o restricciones contradictorias; acepta estimaciones plausibles con base cerrada. El servidor recalcula bindings y restricciones deterministas. Si la evidencia no basta, abstente o marca incomplete/conflict sin pedir revisión humana. Nunca te declares independiente ni confirmado."""


_CANONICAL_ROLES = frozenset({
    "side_panel", "top_panel", "bottom_panel", "shelf", "divider",
    "back_panel", "door", "tabletop", "table_leg", "leg_frame",
    "stretcher", "support", "unknown",
})
_ASSEMBLY_RELATIONS = frozenset({
    "supported_by", "fixed_to", "attached_to", "contained_by",
    "aligned_with", "adjacent_to", "hinged_to",
})


def _valid_role(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", value))


def _valid_directive_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value))


def _semantic_repair_directives(
    unresolved: tuple[str, ...], *, component_ids: set[str],
) -> tuple[str, ...]:
    """Return only closed semantic repair directives; prose has no authority."""
    directives: list[str] = []
    announced_new_ids = {
        parts[2]
        for value in unresolved
        for parts in (value.split(":"),)
        if parts[0] == "missing_component" and len(parts) == 3
    }
    for value in unresolved:
        prefix = value.partition(":")[0]
        if prefix not in {
            "missing_component", "role_correction", "assembly_missing",
            "assembly_remove",
        }:
            continue
        parts = value.split(":")
        if prefix == "missing_component":
            if len(parts) not in {2, 3}:
                raise ValueError("semantic_directive_malformed")
            if not _valid_role(parts[1]) or parts[1] == "unknown":
                raise ValueError("semantic_directive_role_invalid")
            if len(parts) == 3 and (
                not _valid_directive_id(parts[2]) or parts[2] in component_ids
            ):
                raise ValueError("semantic_directive_component_invalid")
        elif prefix == "role_correction":
            if len(parts) != 3:
                raise ValueError("semantic_directive_malformed")
            if parts[1] not in component_ids:
                raise ValueError("semantic_directive_component_unknown")
            if not _valid_role(parts[2]):
                raise ValueError("semantic_directive_role_invalid")
        else:
            if len(parts) != 4:
                raise ValueError("semantic_directive_malformed")
            if (
                parts[1] not in component_ids | announced_new_ids
                or parts[3] not in component_ids | announced_new_ids
            ):
                raise ValueError("semantic_directive_component_unknown")
            if parts[1] == parts[3]:
                raise ValueError("semantic_directive_self_relation")
            if parts[2] not in _ASSEMBLY_RELATIONS:
                raise ValueError("semantic_directive_relation_invalid")
        directives.append(value)
    return tuple(directives)


def _assembly_edges(proposal: GeneralFurnitureProposal) -> set[tuple[str, str, str]]:
    relations = list(proposal.assembly_relations)
    relations.extend(
        relation
        for alternative in proposal.assembly_alternatives
        for relation in alternative.relations
    )
    return {
        (item.subject_component_id, item.relation, item.object_component_id)
        for item in relations
    }


def _validate_semantic_repair_delta(
    before: GeneralFurnitureProposal,
    after: GeneralFurnitureProposal,
    *,
    directives: tuple[str, ...],
    checks: tuple[GeneralAutoReviewCheck, ...],
    field_reviews: tuple[object, ...] = (),
) -> None:
    before_components = {item.id: item for item in before.components}
    after_components = {item.id: item for item in after.components}
    missing_roles: list[str] = []
    missing_by_id: dict[str, str] = {}
    for item in directives:
        if not item.startswith("missing_component:"):
            continue
        parts = item.split(":")
        if len(parts) == 2:
            missing_roles.append(parts[1])
        else:
            missing_by_id[parts[2]] = parts[1]
    added = set(after_components) - set(before_components)
    for component_id in sorted(added):
        role = after_components[component_id].role
        if component_id in missing_by_id:
            if role != missing_by_id[component_id]:
                raise ValueError("semantic_repair_unannounced_component_added")
            continue
        if role not in missing_roles:
            raise ValueError("semantic_repair_unannounced_component_added")
        missing_roles.remove(role)

    removable_ids = {
        target.split(":", 1)[1].split(".", 1)[0]
        for check in checks
        if check.outcome == "fail" and check.kind in {"duplicate_scan", "cross_view_identity"}
        for target in check.target_refs
        if target.startswith("component:")
    }
    removed = set(before_components) - set(after_components)
    if not removed <= removable_ids:
        raise ValueError("semantic_repair_unannounced_component_removed")

    role_permissions = {
        (parts[1], parts[2])
        for item in directives
        if item.startswith("role_correction:")
        for parts in (item.split(":"),)
    }
    for component_id in set(before_components) & set(after_components):
        old_role = before_components[component_id].role
        new_role = after_components[component_id].role
        if old_role != new_role and (component_id, new_role) not in role_permissions:
            raise ValueError("semantic_repair_unannounced_role_change")

    allowed_targets = {
        target
        for check in checks if check.outcome == "fail"
        for target in check.target_refs
    } | {
        item.target_ref
        for item in field_reviews
        if getattr(item, "status", None) in {"rejected", "conflict"}
    }
    binding_fields = {
        "length": "length_binding_id",
        "width": "width_binding_id",
        "thickness": "thickness_binding_id",
    }
    allowed_binding_ids: set[str] = set()
    for component_id in removed:
        component = before_components[component_id]
        allowed_binding_ids.update(
            value for value in (
                component.length_binding_id,
                component.width_binding_id,
                component.thickness_binding_id,
            ) if value is not None
        )
    for component_id in added:
        component = after_components[component_id]
        allowed_binding_ids.update(
            value for value in (
                component.length_binding_id,
                component.width_binding_id,
                component.thickness_binding_id,
            ) if value is not None
        )
    for component_id in set(before_components) & set(after_components):
        old = before_components[component_id]
        new = after_components[component_id]
        old_data = old.model_dump(mode="python")
        new_data = new.model_dump(mode="python")
        for field in ("role", "length_binding_id", "width_binding_id", "thickness_binding_id", "quantity", "unknown_fields"):
            old_data.pop(field, None)
            new_data.pop(field, None)
        if old_data != new_data:
            raise ValueError("semantic_repair_unannounced_component_field_change")
        for field, attribute in (*binding_fields.items(), ("quantity", "quantity")):
            old_value = getattr(old, attribute)
            new_value = getattr(new, attribute)
            if old_value == new_value:
                continue
            target = f"component:{component_id}.{field}"
            if target not in allowed_targets:
                raise ValueError("semantic_repair_unannounced_component_field_change")
            if field != "quantity":
                allowed_binding_ids.update(
                    value for value in (old_value, new_value) if value is not None
                )

    before_bindings = {item.id: item for item in before.bindings}
    after_bindings = {item.id: item for item in after.bindings}
    for binding_id in set(before_bindings) | set(after_bindings):
        if before_bindings.get(binding_id) != after_bindings.get(binding_id):
            if binding_id not in allowed_binding_ids:
                raise ValueError("semantic_repair_unannounced_binding_change")

    before_edges = _assembly_edges(before)
    after_edges = _assembly_edges(after)
    added_edge_permissions = {
        tuple(item.split(":")[1:])
        for item in directives if item.startswith("assembly_missing:")
    }
    removed_edge_permissions = {
        tuple(item.split(":")[1:])
        for item in directives if item.startswith("assembly_remove:")
    }
    removed_incident = {
        edge for edge in before_edges
        if edge[0] in removed or edge[2] in removed
    }
    if not (after_edges - before_edges) <= added_edge_permissions:
        raise ValueError("semantic_repair_unannounced_assembly_change")
    if not (before_edges - after_edges) <= removed_edge_permissions | removed_incident:
        raise ValueError("semantic_repair_unannounced_assembly_change")


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


class _MissingRequiredFieldReviews(ValueError):
    def __init__(self, targets: tuple[str, ...]) -> None:
        super().__init__("machine_required_field_reviews_missing")
        self.targets = targets


class _DirectedDispositionCheckError(ValueError):
    def __init__(self, failures: tuple[dict[str, object], ...]) -> None:
        super().__init__("duplicate_projection_requires_directed_duplicate_check")
        self.failures = failures


class _AcceptedFieldCheckError(ValueError):
    def __init__(self, failures: tuple[dict[str, object], ...]) -> None:
        super().__init__("accepted_machine_field_requires_targeted_visual_check")
        self.failures = failures


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
    if isinstance(error, _MissingRequiredFieldReviews):
        return [{
            "loc": ["field_reviews"],
            "msg": "machine_required_field_reviews_missing",
            "type": "value_error",
            "missing_count": len(error.targets),
            "missing_targets": list(error.targets[:64]),
            "truncated": len(error.targets) > 64,
        }]
    if isinstance(error, _DirectedDispositionCheckError):
        truncated = len(error.failures) > 64
        return [
            {
                "loc": ["field_reviews", str(item["target_ref"])[:200]],
                "msg": "duplicate_projection_requires_directed_duplicate_check",
                "type": "value_error",
                "target_ref": str(item["target_ref"])[:200],
                "disposition_kind": str(item["disposition_kind"])[:80],
                "check_ids": [
                    str(check_id)[:120]
                    for check_id in item["check_ids"][:16]
                ],
                "selected_checks": list(item["selected_checks"][:16]),
                "expected_kinds": list(item["expected_kinds"]),
                "check_kind_rule": str(item["check_kind_rule"]),
                "required_outcome": "pass",
                "requires_exact_target": True,
                "truncated": truncated or len(item["check_ids"]) > 16,
            }
            for item in error.failures[:64]
        ]
    if isinstance(error, _AcceptedFieldCheckError):
        truncated = len(error.failures) > 64
        return [
            {
                "loc": ["field_reviews", str(item["target_ref"])[:200]],
                "msg": "accepted_machine_field_requires_targeted_visual_check",
                "type": "value_error",
                "target_ref": str(item["target_ref"])[:200],
                "check_ids": [
                    str(check_id)[:120]
                    for check_id in item["check_ids"][:16]
                ],
                "selected_checks": list(item["selected_checks"][:16]),
                "failure_reasons": list(item["failure_reasons"]),
                "required_outcome": "pass",
                "requires_exact_target": True,
                "truncated": truncated or len(item["check_ids"]) > 16,
            }
            for item in error.failures[:64]
        ]
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
    allow_extended_test_timeout: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.max_model_calls <= 5 or not 1 <= self.max_tool_calls <= 5:
            raise ValueError("general_auto_review_call_budget_invalid")
        if not 0 <= self.max_validation_repairs <= 2:
            raise ValueError("general_auto_review_validation_budget_invalid")
        if self.max_semantic_repairs not in (0, 1, 2):
            raise ValueError("general_auto_review_semantic_budget_invalid")
        if self.max_derivation_repairs not in (0, 1):
            raise ValueError("general_auto_review_derivation_budget_invalid")
        timeout_ceiling = 900 if self.allow_extended_test_timeout else 300
        if self.timeout_s <= 0 or self.timeout_s > timeout_ceiling:
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
            "Si un subensamblaje funcional oculto es necesario por una premisa cerrada, "
            "descompónlo en tipos de pieza física fabricada con kind, geometry y tres "
            "dimensiones estimated acotadas; sin esa premisa conserva unknown. "
            "En detalles locales x recorre length e y recorre width; sepáralos por pieza. "
            "Resuelve estabilidad necesaria con un detalle estimated explícito, no una nota pendiente."
        )
    )
    return [
        schema("entregar_revision_autonoma", "Entrega solo checks y decisiones por campo usando exclusivamente allowed_target_refs. Incluye un field_review individual para cada target requerido de dimensiones, existencia y disposición de evidencia, y al menos un any_of por hardware. No revises invalid_region_reasons salvo que su target esté permitido. Cada quantity accepted exige checks pass quantity_basis y duplicate_scan dirigidos a esa quantity. accepted kind=hardware es clasificación constructiva provisional, no certificación ni identificación comercial. Un mismo check multitarjeta puede respaldar varios targets contrastados, pero accepted exige que incluya cada target exacto. duplicate_projection exige duplicate_scan o cross_view_identity dirigido; shared_projection_support exige ambos duplicate_scan y shared_projection_support pass sobre el target exacto y nunca acredita ownership o cantidad. El servidor conserva componentes y operaciones; cualquier corrección estructural usa proponer_mueble_general.", GeneralAutoReviewDecisionArgs),
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
        (f"component:{component.id}.kind",)
        for component in components
        if component.kind == "hardware"
        or (
            component.geometry is not None
            and component.geometry.shape_kind == "hardware"
        )
    )


def _required_cut_piece_review_targets(components) -> tuple[str, ...]:
    return tuple(sorted(
        f"component:{component.id}.{field}"
        for component in components
        if component.kind != "hardware"
        for field in (
            "kind", "existence", "geometry", "length", "width", "thickness",
            "quantity",
        )
    ))


def _required_hardware_review_targets(components) -> tuple[str, ...]:
    return tuple(sorted(
        f"component:{component.id}.{field}"
        for component in components
        if component.kind == "hardware"
        for field in ("kind", "quantity")
    ))


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


def _validate_required_review_coverage(
    field_reviews,
    *,
    required_existence_targets: tuple[str, ...],
    required_disposition_targets: tuple[str, ...],
    required_component_targets: tuple[str, ...] = (),
) -> None:
    reviewed = {item.target_ref for item in field_reviews}
    required = tuple(dict.fromkeys(
        target for target in (
            *required_component_targets,
            *required_existence_targets,
            *required_disposition_targets,
        )
    ))
    missing = tuple(target for target in required if target not in reviewed)
    if missing:
        raise _MissingRequiredFieldReviews(missing)


def _validate_evidence_disposition_checks(
    args: GeneralAutoReviewArgs,
    disposition_kinds: dict[str, str],
) -> None:
    checks = {item.id: item for item in args.checks}
    failures: list[dict[str, object]] = []
    for review in args.field_reviews:
        disposition_kind = disposition_kinds.get(review.target_ref)
        if review.status != "accepted" or disposition_kind not in {
            "duplicate_projection", "multi_region_assigned",
            "shared_projection_support",
        }:
            continue
        selected = tuple(checks.get(check_id) for check_id in review.check_ids)
        expected_kinds = (
            ("duplicate_scan", "shared_projection_support")
            if disposition_kind == "shared_projection_support"
            else ("duplicate_scan", "cross_view_identity")
        )
        passing_kinds = {
            check.kind
            for check in selected
            if check is not None
            and check.outcome == "pass"
            and review.target_ref in check.target_refs
        }
        check_kind_rule = (
            "all_of" if disposition_kind == "shared_projection_support" else "any_of"
        )
        supported = (
            set(expected_kinds) <= passing_kinds
            if check_kind_rule == "all_of"
            else bool(set(expected_kinds) & passing_kinds)
        )
        if not supported:
            failures.append({
                "target_ref": review.target_ref,
                "disposition_kind": disposition_kind,
                "check_ids": review.check_ids,
                "expected_kinds": expected_kinds,
                "check_kind_rule": check_kind_rule,
                "selected_checks": tuple(
                    {
                        "id": check_id,
                        "kind": check.kind if check is not None else "missing",
                        "outcome": check.outcome if check is not None else "missing",
                        "targets_exact": (
                            review.target_ref in check.target_refs
                            if check is not None else False
                        ),
                    }
                    for check_id, check in zip(review.check_ids, selected)
                ),
            })
    if failures:
        raise _DirectedDispositionCheckError(tuple(failures))


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
    accepted_failures: list[dict[str, object]] = []
    accepted_quantities = []
    for field_review in args.field_reviews:
        if field_review.target_ref not in valid_targets:
            raise ValueError("machine_field_review_targets_unknown_field")
        if field_review.status != "accepted":
            continue
        selected = tuple(checks.get(check_id) for check_id in field_review.check_ids)
        if not any(
            check is not None
            and check.outcome == "pass"
            and field_review.target_ref in check.target_refs
            for check in selected
        ):
            selected_checks = tuple(
                {
                    "id": check_id,
                    "kind": check.kind if check is not None else "missing",
                    "outcome": check.outcome if check is not None else "missing",
                    "targets_exact": (
                        field_review.target_ref in check.target_refs
                        if check is not None else False
                    ),
                }
                for check_id, check in zip(field_review.check_ids, selected)
            )
            accepted_failures.append({
                "target_ref": field_review.target_ref,
                "check_ids": field_review.check_ids,
                "selected_checks": selected_checks,
                "failure_reasons": tuple(dict.fromkeys(
                    "missing_check"
                    if check is None else
                    "nonpass_check"
                    if check.outcome != "pass" else
                    "wrong_target"
                    for check in selected
                )),
            })
            continue
        if field_review.target_ref.endswith(".quantity"):
            accepted_quantities.append(field_review)
    if accepted_failures:
        raise _AcceptedFieldCheckError(tuple(accepted_failures))
    for field_review in accepted_quantities:
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


def _effective_auto_status(
    args: GeneralAutoReviewArgs,
    construction_validation=None,
    accounting_report: EvidenceAccountingReport | None = None,
    required_review_targets: tuple[str, ...] = (),
) -> str:
    if construction_validation is not None and construction_validation.status == "invalid":
        return "conflict"
    if any(item.outcome == "fail" for item in args.checks) or any(item.status in {"rejected", "conflict"} for item in args.field_reviews):
        return "conflict"
    if args.status == "abstained":
        return "abstained"
    if accounting_report is not None and not accounting_report.reviewable:
        return "incomplete"
    accepted = {item.target_ref for item in args.field_reviews if item.status == "accepted"}
    if not set(required_review_targets) <= accepted:
        return "incomplete"
    if not args.components:
        return "incomplete"
    field_status = {item.target_ref: item.status for item in args.field_reviews}
    nonblocking_unknowns = {"material", "finish", "acabado"}
    blocking_unresolved_markers = {
        "identidad", "correspondencia", "proyecci", "montaje", "unión", "union",
        "mecanizado", "cantidad", "quantity", "dimensi", "espesor", "ancho", "largo",
        "geometr", "cara material",
    }
    for unresolved in args.unresolved:
        normalized = unresolved.casefold()
        if (
            not any(marker in normalized for marker in nonblocking_unknowns)
            or any(marker in normalized for marker in blocking_unresolved_markers)
        ):
            return "incomplete"
    for component in args.components:
        if component.kind != "hardware" and any(field.strip().lower() not in nonblocking_unknowns for field in component.unknown_fields):
            return "incomplete"
        fields = (
            ("quantity",)
            if component.kind == "hardware"
            else ("length", "width", "thickness", "quantity")
        )
        for field in fields:
            if getattr(component, field).state in {"unknown", "conflict"} or f"component:{component.id}.{field}" not in accepted:
                return "incomplete"
        for field in (() if component.kind == "hardware" else ("material", "finish")):
            target = f"component:{component.id}.{field}"
            state = getattr(component, field).state
            allowed_statuses = {None, "abstained"} if state == "unknown" else {"accepted"}
            if state == "conflict" or field_status.get(target) not in allowed_statuses:
                return "incomplete"
    return "accepted"


def _repair_is_supported(
    args: GeneralAutoReviewArgs,
    construction_validation=None,
    accounting_report: EvidenceAccountingReport | None = None,
) -> bool:
    directives = _semantic_repair_directives(args.unresolved, component_ids={item.id for item in args.components})
    return bool(directives) or (
        construction_validation is not None
        and construction_validation.status == "invalid"
    ) or (
        accounting_report is not None and not accounting_report.reviewable
    ) or any(item.outcome == "fail" and item.kind in {"cross_view_identity", "duplicate_scan", "quantity_basis", "visual_consistency"} for item in args.checks) or any(item.status in {"rejected", "conflict"} for item in args.field_reviews) or _necessary_aggregate_needs_structural_repair(args)


def _necessary_aggregate_needs_structural_repair(
    args: GeneralAutoReviewArgs,
) -> bool:
    accepted = {
        item.target_ref for item in args.field_reviews if item.status == "accepted"
    }
    abstained = {
        item.target_ref for item in args.field_reviews if item.status == "abstained"
    }
    for component in args.components:
        if component.kind == "hardware" or component.necessity not in {
            "deduced_required", "estimated_required",
        }:
            continue
        prefix = f"component:{component.id}"
        if not {f"{prefix}.existence", f"{prefix}.quantity"} <= accepted:
            continue
        if (
            component.quantity.value is None
            or component.quantity.state in {"unknown", "conflict"}
        ):
            continue
        structurally_unknown = set()
        if component.kind == "unknown":
            structurally_unknown.add(f"{prefix}.kind")
        if component.geometry.shape_kind == "unknown":
            structurally_unknown.add(f"{prefix}.geometry")
        critical_targets = {
            f"{prefix}.kind", f"{prefix}.geometry", f"{prefix}.length",
            f"{prefix}.width", f"{prefix}.thickness",
        }
        structurally_unknown.update(
            f"{prefix}.{field}"
            for field in ("length", "width", "thickness")
            if getattr(component, field).state in {"unknown", "conflict"}
        )
        if (critical_targets & abstained) or structurally_unknown:
            return True
    return False


def _recoverable_dimension_measurements(args: GeneralAutoReviewArgs, measurements) -> tuple[dict[str, object], ...]:
    field_status = {item.target_ref: item.status for item in args.field_reviews}
    needs_dimension_evidence = any(
        getattr(component, field).state == "unknown"
        and field_status.get(f"component:{component.id}.{field}") == "abstained"
        for component in args.components
        for field in ("length", "width", "thickness")
    )
    if not needs_dimension_evidence:
        return ()
    candidates = tuple(
        item for item in measurements
        if item.semantic == "contour_segment_length" and item.value_mm is not None
    )
    if not candidates:
        return ()
    return tuple(query_compact_measurements(candidates, offset=0, limit=64).to_payload()["items"])


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
        targeted = [item for item in selected if item is not None and target in item.target_refs]
        if (
            len(targeted) != len(selected)
            or any(item.outcome != "pass" for item in targeted)
            or not {"quantity_basis", "duplicate_scan"} <= {item.kind for item in targeted}
        ):
            continue
        sources = tuple(dict.fromkeys(ref for item in targeted for ref in item.source_refs))
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


def _accounting_report(
    context,
    outcome: GeneralFurnitureAgentOutcome,
) -> EvidenceAccountingReport:
    measurements = derive_geometry_measurements(context.extraction)
    try:
        projections = derive_projection_hypotheses(context.extraction, measurements)
    except ValueError as exc:
        if str(exc) != "projection_input_budget_exceeded":
            raise
        projections = ()
    return build_evidence_accounting_report(
        context.extraction,
        outcome.proposal,
        outcome.draft,
        projection_hypotheses=projections,
        orthographic_hypotheses=derive_orthographic_hypotheses(
            context.extraction, measurements
        ).hypotheses,
    )


def _disposition_review_kinds(
    proposal: GeneralFurnitureProposal,
    accounting: EvidenceAccountingReport,
) -> dict[str, str]:
    multi_region_components = set(accounting.multi_region_component_ids)
    return {
        f"evidence_region:{item.candidate_region_id}": (
            "multi_region_assigned"
            if item.kind == "assigned"
            and item.component_id in multi_region_components
            else item.kind
        )
        for item in proposal.evidence_dispositions
    }


def _disposition_review_requirements(
    proposal: GeneralFurnitureProposal,
    accounting: EvidenceAccountingReport,
) -> list[dict[str, object]]:
    kinds = _disposition_review_kinds(proposal, accounting)
    requirements = []
    for target_ref in accounting.required_disposition_review_targets:
        disposition_kind = kinds.get(target_ref, "unknown")
        directed = disposition_kind in {
            "duplicate_projection",
            "multi_region_assigned",
            "shared_projection_support",
        }
        shared_support = disposition_kind == "shared_projection_support"
        requirements.append({
            "target_ref": target_ref,
            "disposition_kind": disposition_kind,
            "required_pass_check_kinds": (
                ["duplicate_scan", "shared_projection_support"]
                if shared_support
                else ["duplicate_scan", "cross_view_identity"] if directed else []
            ),
            "check_kind_rule": (
                "all_of" if shared_support
                else "any_of" if directed
                else "exact_target_pass"
            ),
        })
    return requirements


def _review_payload(
    context,
    outcome: GeneralFurnitureAgentOutcome,
) -> dict[str, object]:
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
    accounting = build_evidence_accounting_report(
        context.extraction,
        outcome.proposal,
        outcome.draft,
        projection_hypotheses=projections,
        orthographic_hypotheses=derive_orthographic_hypotheses(
            context.extraction, measurements
        ).hypotheses,
    )
    allowed_target_refs = sorted(
        _review_target_refs(outcome.proposal, outcome.draft)
        | set(accounting.required_existence_review_targets)
        | set(accounting.required_disposition_review_targets)
    )
    required_dimension_field_review_targets = list(
        _required_numeric_dimension_targets(outcome.draft.components)
    )
    required_hardware_classification_field_review_targets = [
        {"component_id": group[0].split(":", 1)[1].rsplit(".", 1)[0], "any_of": list(group)}
        for group in _required_hardware_classification_target_groups(
            outcome.draft.components
        )
    ]
    required_cut_piece_field_review_targets = list(
        _required_cut_piece_review_targets(outcome.draft.components)
    )
    required_hardware_field_review_targets = list(
        _required_hardware_review_targets(outcome.draft.components)
    )
    visible_source_refs = set()
    for page in context.visual_pages:
        visible_source_refs.add(f"visual:{page.reference}")
        visible_source_refs.update(page.source_contour_ids)
        visible_source_refs.update(mark.source_id for mark in page.marks)
    visible_source_refs.update(general_allowed_document_refs(
        context.visual_pages,
        include_announced_children=_is_raster_without_metric_ledger(
            context.extraction, measurements, context.visual_pages
        ),
    ))
    allowed_source_refs = sorted(
        visible_source_refs
        | {f"premise:{item.id}" for item in outcome.proposal.premises}
        | set(accounting.required_disposition_review_targets)
    )
    payload = build_compact_review_context(
        outcome.proposal,
        outcome.draft,
        allowed_target_refs=tuple(allowed_target_refs),
        required_dimension_field_review_targets=tuple(
            required_dimension_field_review_targets
        ),
        required_hardware_classification_field_review_targets=tuple(
            required_hardware_classification_field_review_targets
        ),
        required_existence_field_review_targets=(
            accounting.required_existence_review_targets
        ),
        required_evidence_disposition_review_targets=(
            accounting.required_disposition_review_targets
        ),
        allowed_source_refs=tuple(allowed_source_refs),
    )
    payload.update({
        "compact_geometry": build_compact_geometry_context(
            context.extraction, measurements, regions, projections
        ).to_payload(),
        "referenced_segment_measurements": referenced_measurements,
        "required_cut_piece_field_review_targets": (
            required_cut_piece_field_review_targets
        ),
        "required_hardware_field_review_targets": (
            required_hardware_field_review_targets
        ),
        "evidence_accounting": accounting.to_payload(),
        "required_evidence_disposition_review_requirements": (
            _disposition_review_requirements(outcome.proposal, accounting)
        ),
        "review_target_authority": {
            "allowed_targets": "allowed_target_refs_only",
            "invalid_accounting_regions": (
                "diagnostics_not_review_targets_unless_explicitly_allowed"
            ),
            "accepted_quantity_requires": [
                "quantity_basis:pass",
                "duplicate_scan:pass",
            ],
        },
        "region_visual_links": [
            item.to_payload()
            for item in build_region_visual_links(
                context.extraction,
                accounting.candidate_regions,
                context.visual_pages,
            )
        ],
        "target_ref_format": "component:<component_id>.<length|width|thickness|quantity|material|finish|existence|kind|role|geometry> or parameter:<id> or constraint:<id> or detail:<id> or decision:<id>",
        "projection_warnings": projection_warnings,
        "projection_authority": "ambiguous_hypotheses_not_physical_identity_or_quantity",
        "semantic_repair_directives": {
            "allowed": [
                "missing_component:<canonical_role>",
                "missing_component:<role>:<new_component_id>",
                "role_correction:<existing_component_id>:<canonical_role>",
                "assembly_missing:<existing_subject_id>:<relation>:<existing_object_id>",
                "assembly_remove:<existing_subject_id>:<relation>:<existing_object_id>",
            ],
            "canonical_roles": sorted(_CANONICAL_ROLES),
            "assembly_relations": sorted(_ASSEMBLY_RELATIONS),
            "authority": "repair_request_only_not_acceptance_or_confirmation",
        },
        "visual_artifacts": [_visual_metadata(item) for item in context.visual_pages],
        "instruction": "Entrega solo checks, field_reviews, unresolved y status. Para cada pieza de corte decide kind, existence, geometry, length, width, thickness y quantity anunciados; material/finish unknown permanece visible y puede omitirse de reviews/unresolved terminal sin aceptarlo. Para hardware decide existence, quantity y al menos kind o geometry sin inventar cotas de catálogo. Decide también cada disposición. accepted kind=hardware es clasificación constructiva provisional, no una certificación comercial. Cada field_review es individual aunque un check contrastado cubra varios targets exactos. La cobertura contable no confirma piezas, cantidades, identidad ni fabricabilidad. duplicate_projection y asignaciones multi-región requieren duplicate_scan o cross_view_identity dirigido; shared_projection_support requiere ALL_OF duplicate_scan y shared_projection_support pass sobre el target exacto; nonmaterial requiere contraste dirigido. accepted exige check model_visual pass con el mismo target; evidencia insuficiente queda abstained/incomplete.",
    })
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
    return payload


def _review_input(context, outcome: GeneralFurnitureAgentOutcome) -> list[dict]:
    payload = _review_payload(context, outcome)
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
    cancelled: Callable[[], bool] | None = None,
) -> GeneralAutonomousOutcome:
    if len(context.visual_pages) > 4 or any(len(item.content) > 4 * 1024 * 1024 for item in context.visual_pages):
        raise ValueError("general_auto_visual_context_budget_exceeded")
    started = time.monotonic()
    previous_response_id = None
    response_ids: list[str] = []
    trace: list[dict[str, object]] = []
    snapshots: list[GeneralAutoReviewArgs] = []
    validation_repairs = semantic_repairs = tool_calls = 0
    evidence_reinspection_requested = False
    effective = proposal_outcome
    measurements = derive_geometry_measurements(context.extraction)
    visual_refs = {f"visual:{item.reference}" for item in context.visual_pages}
    for page in context.visual_pages:
        visual_refs.update(page.source_contour_ids)
        visual_refs.update(mark.source_id for mark in page.marks)
    measurements = derive_geometry_measurements(context.extraction)
    raster_without_metric_ledger = _is_raster_without_metric_ledger(
        context.extraction, measurements, context.visual_pages
    )
    visual_refs.update(general_allowed_document_refs(
        context.visual_pages,
        include_announced_children=_is_raster_without_metric_ledger(
            context.extraction, measurements, context.visual_pages
        ),
    ))
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
    accounting_report = _accounting_report(context, effective)
    allowed_refs.update(accounting_report.required_disposition_review_targets)
    input_items = _review_input(context, effective)

    for model_call in range(1, limits.max_model_calls + 1):
        if cancelled is not None and cancelled():
            raise GeneralAutonomousError(
                "job_cancelled", trace=tuple(trace),
                model_calls=model_call - 1, tool_calls=tool_calls,
            )
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
        if cancelled is not None and cancelled():
            raise GeneralAutonomousError(
                "job_cancelled", trace=tuple(trace),
                model_calls=model_call, tool_calls=tool_calls,
            )
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
                latest = snapshots[-1]
                directives = _semantic_repair_directives(
                    latest.unresolved,
                    component_ids={item.id for item in latest.components},
                )
                if directives:
                    _validate_semantic_repair_delta(
                        effective.proposal,
                        repaired.proposal,
                        directives=directives,
                        checks=latest.checks,
                        field_reviews=latest.field_reviews,
                    )
                effective = repaired
                accounting_report = _accounting_report(context, effective)
                allowed_refs.update(
                    accounting_report.required_disposition_review_targets
                )
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
                repaired_payload = _review_payload(context, effective)
                repaired_payload.update({
                    "ok": True,
                    "status": "proposal_repaired",
                    "instruction": (
                        "Revisa el snapshot compacto reparado. Decide todos los targets "
                        "requeridos sin convertir cobertura contable en confirmación."
                    ),
                })
                input_items = [{
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(repaired_payload, ensure_ascii=False),
                }]
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
            required_component_targets = tuple(sorted({
                *_required_cut_piece_review_targets(effective.draft.components),
                *_required_hardware_review_targets(effective.draft.components),
            }))
            if decision.status == "accepted":
                _validate_required_review_coverage(
                    args.field_reviews,
                    required_existence_targets=(
                        accounting_report.required_existence_review_targets
                    ),
                    required_disposition_targets=(
                        accounting_report.required_disposition_review_targets
                    ),
                    required_component_targets=required_component_targets,
                )
            current_allowed_refs = allowed_refs | {
                f"premise:{item.id}" for item in effective.proposal.premises
            }
            required_review_targets = (
                set(accounting_report.required_existence_review_targets)
                | set(accounting_report.required_disposition_review_targets)
            )
            _validate_visual_checks(
                args,
                current_allowed_refs,
                visual_refs,
                _review_target_refs(effective.proposal, effective.draft)
                | required_review_targets,
            )
            _validate_evidence_disposition_checks(
                args,
                _disposition_review_kinds(
                    effective.proposal, accounting_report
                ),
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
            effective_status = _effective_auto_status(
                args,
                construction_validation,
                accounting_report,
                tuple(sorted({
                    *required_component_targets,
                    *accounting_report.required_existence_review_targets,
                    *accounting_report.required_disposition_review_targets,
                })),
            )
            recoverable_measurements = _recoverable_dimension_measurements(args, measurements)
            if (
                effective_status == "incomplete"
                and semantic_repairs < limits.max_semantic_repairs
                and not evidence_reinspection_requested
                and recoverable_measurements
            ):
                evidence_reinspection_requested = True
                trace.append({
                    "tool": call.name,
                    "ok": True,
                    "summary": "Se aportó evidencia métrica acotada para una abstención dimensional reparable.",
                    "phase": "general_auto_evidence_reinspection",
                    "provider_response_id": response.id,
                    "provider_model": getattr(response, "model", None),
                    "provider_call_id": call.call_id,
                    "status": effective_status,
                })
                input_items = [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps({
                    "ok": True,
                    "status": "repair_requested",
                    "candidate_measurements": recoverable_measurements,
                    "instruction": "Hay segmentos métricos del ledger que no se habían detallado. Si imagen y ledger sostienen una asignación, emite una propuesta completa corregida con bindings; si no, conserva la abstención. No midas píxeles ni inventes valores.",
                }, ensure_ascii=False)}]
                continue
            if effective_status in {"incomplete", "conflict"} and semantic_repairs < limits.max_semantic_repairs and _repair_is_supported(args, construction_validation, accounting_report):
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
                        "proposal": effective.proposal.model_dump(mode="json"),
                        "draft": effective.draft.model_dump(mode="json"),
                        "unresolved": args.unresolved,
                        "semantic_repair_directives": _semantic_repair_directives(args.unresolved, component_ids={item.id for item in args.components}),
                        "evidence_accounting": accounting_report.to_payload(),
                        "construction_validation": construction_validation.model_dump(mode="json"),
                        "instruction": "Emite una propuesta completa corregida mediante proponer_mueble_general. Resuelve regiones unresolved/invalid y cotas ausentes o sin traza sin inventar piezas, identidad ni cantidad. Una cota observed solo sirve para la misma geometría visible; en piezas ocultas u otros componentes usa un parámetro estimated separado con rango y premisa. Si existencia y cantidad aceptadas de un subensamblaje funcional necesario tienen premisa cerrada, descompón el mínimo coherente de tipos de pieza física fabricada con kind, geometry y tres dimensiones estimated acotadas; sin premisa conserva unknown. En detalles locales x recorre length e y recorre width y cada pieza usa su propio marco. Resuelve estabilidad necesaria con detalle estimated explícito, no solo pendiente.",
                    }
                    if construction_validation.status == "invalid":
                        repair_output["instruction"] = (
                            "Corrige todas las restricciones deterministas fallidas mediante "
                            "una propuesta completa; conserva observaciones y no inventes cifras. "
                            "Las estimaciones válidas declaran nominal, rango, método y supuestos. "
                            "No transfieras cotas observed entre geometrías: piezas ocultas u otros "
                            "componentes requieren parámetro estimated separado. Un subensamblaje "
                            "funcional necesario con premisa cerrada se descompone en tipos de pieza "
                            "física fabricada con geometría y tres dimensiones estimated acotadas; "
                            "sin premisa conserva unknown. En detalles locales x recorre length e y "
                            "recorre width, con marco separado por pieza. Resuelve estabilidad "
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
