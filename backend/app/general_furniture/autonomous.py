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
    GeneralFurnitureProposal,
    GeneralFurnitureReview,
    GeneralFurnitureReviewRequest,
    GeneralMachineProvenance,
    GeneralReviewOperation,
    GeneralScenarioOccurrence,
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
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.projection_hypotheses import (
    derive_projection_hypotheses,
    derive_source_spatial_regions,
)
from backend.app.general_furniture.review import apply_general_review


AUTO_REVIEW_POLICY_VERSION = "general-auto-review-v2"
GENERAL_AUTO_REVIEW_PROMPT = """Actúas como crítico multimodal separado del proponente. Contrasta cada propuesta con imágenes reales, geometría y referencias del ledger.
Primero llama entregar_revision_autonoma. Si el servidor responde repair_requested, llama una sola vez proponer_mueble_general con una propuesta completa corregida; después vuelve a llamar entregar_revision_autonoma sobre esa propuesta.
No midas píxeles ni inventes valores. Las dimensiones numéricas solo proceden de bindings dimension:/measurement: anunciados. Una cantidad visual solo puede ser hypothesis, con premisa declarada y checks quantity_basis+duplicate_scan; nunca cuentes vistas como instancias.
Aceptar significa que una hipótesis es coherente, no que sea un hecho observado. Contrasta cada candidato en sus regiones: un contorno cerrado puede ser cara material, hueco, rebaje o límite interior. Busca duplicados entre proyecciones, incoherencias dimensionales y bases de cantidad antes de aceptar.
Usa solo checks method=model_visual y los `allowed_target_refs` exactos del input. El formato es `component:<id>.<campo>` con punto antes de length/width/thickness/quantity/material/finish; kind, role y existencia no son campos revisables. El servidor recalcula bindings y geometría deterministas. Si la evidencia no basta, abstente o marca incomplete/conflict sin pedir revisión humana. Nunca te declares independiente ni confirmado."""


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


@dataclass(frozen=True)
class AutoReviewLimits:
    max_model_calls: int = 3
    max_tool_calls: int = 3
    max_validation_repairs: int = 1
    max_semantic_repairs: int = 1
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_model_calls <= 5 or not 1 <= self.max_tool_calls <= 5:
            raise ValueError("general_auto_review_call_budget_invalid")
        if not 0 <= self.max_validation_repairs <= 2:
            raise ValueError("general_auto_review_validation_budget_invalid")
        if self.max_semantic_repairs not in (0, 1):
            raise ValueError("general_auto_review_semantic_budget_invalid")
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


def _tool_schemas() -> list[dict]:
    def schema(name: str, description: str, model: type) -> dict:
        return {"type": "function", "name": name, "description": description, "parameters": _strictify(model.model_json_schema()), "strict": True}

    return [
        schema("entregar_revision_autonoma", "Entrega solo checks y decisiones por campo. El servidor conserva componentes y operaciones; cualquier corrección estructural usa proponer_mueble_general.", GeneralAutoReviewDecisionArgs),
        schema("proponer_mueble_general", "Repara una propuesta rechazada. Las dimensiones usan solo bindings del ledger; cantidades visuales siguen hypothesis con premisas cerradas.", ProposeGeneralFurnitureArgs),
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


def _validate_visual_checks(args: GeneralAutoReviewArgs, allowed_refs: set[str], visual_refs: set[str]) -> None:
    checks = {item.id: item for item in args.checks}
    valid_targets = {f"component:{component.id}.{field}" for component in args.components for field in ("length", "width", "thickness", "quantity", "material", "finish")}
    for check in args.checks:
        if check.method != "model_visual" or check.kind in {"geometry_match", "dimension_binding"}:
            raise ValueError("reviewer_cannot_claim_deterministic_check")
        if not set(check.target_refs) <= valid_targets:
            raise ValueError("machine_check_targets_unknown_field")
        if not set(check.source_refs) <= allowed_refs or not set(check.source_refs) & visual_refs:
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


def _effective_auto_status(args: GeneralAutoReviewArgs) -> str:
    if any(item.outcome == "fail" for item in args.checks) or any(item.status in {"rejected", "conflict"} for item in args.field_reviews):
        return "conflict"
    if args.status == "abstained":
        return "abstained"
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
        if any(field.strip().lower() not in nonblocking_unknowns for field in component.unknown_fields):
            return "incomplete"
        for field in ("length", "width", "thickness", "quantity"):
            target = f"component:{component.id}.{field}"
            if getattr(component, field).state in {"unknown", "conflict"} or field_status.get(target) != "accepted":
                return "incomplete"
        for field in ("material", "finish"):
            target = f"component:{component.id}.{field}"
            state = getattr(component, field).state
            expected = "abstained" if state == "unknown" else "accepted"
            if state == "conflict" or field_status.get(target) != expected:
                return "incomplete"
    return "accepted"


def _repair_is_supported(args: GeneralAutoReviewArgs) -> bool:
    return any(item.outcome == "fail" and item.kind in {"cross_view_identity", "duplicate_scan", "quantity_basis", "visual_consistency"} for item in args.checks) or any(item.status in {"rejected", "conflict"} for item in args.field_reviews)


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
        if component.quantity.state != "hypothesis" or component.quantity.value is None or field_review is None:
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


def _review_input(context, outcome: GeneralFurnitureAgentOutcome) -> list[dict]:
    measurements = derive_geometry_measurements(context.extraction)
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
    allowed_target_refs = [
        f"component:{component.id}.{field}"
        for component in outcome.draft.components
        for field in ("length", "width", "thickness", "quantity", "material", "finish")
    ]
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
    )
    payload = {
        "proposal": outcome.proposal.model_dump(mode="json"), "draft": outcome.draft.model_dump(mode="json"),
        "compact_geometry": build_compact_geometry_context(
            context.extraction, measurements, regions, projections
        ).to_payload(),
        "referenced_segment_measurements": referenced_measurements,
        "allowed_target_refs": allowed_target_refs,
        "allowed_source_refs": allowed_source_refs,
        "target_ref_format": "component:<component_id>.<length|width|thickness|quantity|material|finish>; use a dot before the field, never a colon",
        "projection_warnings": projection_warnings,
        "projection_authority": "ambiguous_hypotheses_not_physical_identity_or_quantity",
        "visual_artifacts": [_visual_metadata(item) for item in context.visual_pages],
        "instruction": "Entrega solo checks, field_reviews, unresolved y status; no reescribas components ni operations. Usa target/source refs exactos de las listas permitidas. Rechaza con checks solo errores corregibles; ausencia irreducible permanece unknown/incomplete.",
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
    draft = materialize_general_proposal(
        context.extraction,
        proposal,
        allowed_document_refs=general_allowed_document_refs(
            context.visual_pages,
            include_announced_children=_is_raster_without_metric_ledger(
                context.extraction,
                derive_geometry_measurements(context.extraction),
                context.visual_pages,
            ),
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
    evidence_reinspection_requested = False
    effective = proposal_outcome
    measurements = derive_geometry_measurements(context.extraction)
    visual_refs = {f"visual:{item.reference}" for item in context.visual_pages}
    for page in context.visual_pages:
        visual_refs.update(page.source_contour_ids)
        visual_refs.update(mark.source_id for mark in page.marks)
    visual_refs.update(general_allowed_document_refs(
        context.visual_pages,
        include_announced_children=_is_raster_without_metric_ledger(
            context.extraction, measurements, context.visual_pages
        ),
    ))
    allowed_refs = set(visual_refs)
    allowed_refs.update(f"view:{item.id}" for item in context.extraction.views)
    allowed_refs.update(f"contour:{item.id}" for item in context.extraction.contours)
    allowed_refs.update(f"dimension:{item.id}" for item in context.extraction.dimensions)
    allowed_refs.update(f"evidence:{item.id}" for item in context.extraction.evidence)
    allowed_refs.update(item.binding_ref for item in measurements)
    input_items = _review_input(context, effective)

    for model_call in range(1, limits.max_model_calls + 1):
        remaining = limits.timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("general_auto_review_timeout")
        response = reviewer_provider.create_response(input_items=input_items, tools=_tool_schemas(), previous_response_id=previous_response_id, timeout_s=remaining)
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
                repaired_targets = [
                    f"component:{component.id}.{field}"
                    for component in effective.draft.components
                    for field in ("length", "width", "thickness", "quantity", "material", "finish")
                ]
                input_items = [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps({"ok": True, "status": "proposal_repaired", "proposal": effective.proposal.model_dump(mode="json"), "draft": effective.draft.model_dump(mode="json"), "allowed_target_refs": repaired_targets, "instruction": "Revisa ahora la propuesta reparada. Entrega solo checks/decisiones; no components/operations."}, ensure_ascii=False)}]
                continue
            if call.name != "entregar_revision_autonoma":
                raise ValueError("unknown_tool")
            current_revision = proposal_revision + semantic_repairs
            current_previous = previous_review if semantic_repairs == 0 else None
            decision = GeneralAutoReviewDecisionArgs.model_validate_json(
                json.dumps(raw), strict=True
            )
            args = _server_review_args(decision, effective.draft, current_previous)
            current_allowed_refs = allowed_refs | {
                f"premise:{item.id}" for item in effective.proposal.premises
            }
            _validate_visual_checks(args, current_allowed_refs, visual_refs)
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
            effective_status = _effective_auto_status(args)
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
            if effective_status in {"incomplete", "conflict"} and semantic_repairs < limits.max_semantic_repairs and _repair_is_supported(args):
                event = {"tool": call.name, "ok": True, "summary": "Crítica detectó un error semántico reparable.", "phase": "general_auto_critique", "provider_response_id": response.id, "provider_model": getattr(response, "model", None), "provider_call_id": call.call_id, "status": effective_status}
                trace.append(event)
                if checkpoint_sink is not None:
                    checkpoint_sink(GeneralAutonomousCheckpoint(
                        phase="critic",
                        proposal_revision=current_revision,
                        proposal_outcome=effective,
                        critic_snapshot=args,
                        trace_event=event,
                    ))
                input_items = [{"type": "function_call_output", "call_id": call.call_id, "output": json.dumps({"ok": True, "status": "repair_requested", "unresolved": args.unresolved, "instruction": "Emite una propuesta completa corregida mediante proponer_mueble_general; no inventes cifras."}, ensure_ascii=False)}]
                continue
            checks = _deterministic_checks(args) + args.checks
            relation = "self_review" if proposer_model and proposer_model == getattr(response, "model", None) else "separate_model"
            review_data = base_review.model_dump(mode="python") | {
                "reviewer_name": "autonomous-reviewer", "reviewer_kind": "machine",
                "machine_provenance": GeneralMachineProvenance(model=getattr(response, "model", None) or "unknown-model", policy_version=AUTO_REVIEW_POLICY_VERSION, response_ids=tuple(dict.fromkeys(response_ids)), review_relation=relation),
                "scenario_occurrences": _scenario_occurrences(args, checks), "machine_checks": checks,
                "machine_field_reviews": args.field_reviews, "auto_review_status": effective_status,
                "status": base_review.status if effective_status == "accepted" else "reviewed_incomplete",
            }
            review = GeneralFurnitureReview.model_validate(review_data)
            derived = derive_general_package(review)
            trace.append({"tool": call.name, "ok": True, "summary": "Revisión multimodal provisional completada.", "phase": "general_auto_review", "provider_response_id": response.id, "provider_model": getattr(response, "model", None), "provider_call_id": call.call_id, "provider_input_tokens": getattr(response, "input_tokens", None), "provider_output_tokens": getattr(response, "output_tokens", None), "provider_total_tokens": getattr(response, "total_tokens", None), "status": effective_status})
            return GeneralAutonomousOutcome(proposal_outcome, effective, tuple(snapshots), semantic_repairs, review, derived, tuple(trace), model_call, tool_calls, effective_status)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            validation_repairs += 1
            details = _safe_validation_details(exc)
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
