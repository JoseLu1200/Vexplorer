from __future__ import annotations

import json
import time
from base64 import b64encode
from dataclasses import dataclass
from typing import Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.agente.provider import ProviderError
from backend.app.agente.tools import _strictify_schema
from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralAssemblyAttempt,
    GeneralAssemblyCandidate,
    GeneralAssemblyTraceEvent,
    GeneralAssemblyValidationIssue,
    GeneralAssemblyValidationReport,
    GeneralFurnitureReview,
)
from backend.app.general_furniture.context_payload import (
    CompactGeometryContext,
    build_compact_geometry_context,
    query_compact_measurements,
)
from backend.app.general_furniture.assembly import build_assembly_context
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.projection_hypotheses import (
    derive_projection_hypotheses,
    derive_source_spatial_regions,
)


ASSEMBLY_POLICY_VERSION = "general-assembly-v1"


class _StrictToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class InspectAssemblyContextArgs(_StrictToolModel):
    measurement_ids: tuple[str, ...] = Field(default=(), max_length=64)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=32, ge=1, le=64)


class EvaluateAssemblyCandidateArgs(_StrictToolModel):
    candidate: GeneralAssemblyCandidate


class FinalizeAssemblyCandidateArgs(_StrictToolModel):
    candidate: GeneralAssemblyCandidate


class AssemblyProvider(Protocol):
    def create_response(
        self, *, input_items, tools, previous_response_id, timeout_s
    ): ...


class AssemblyEvaluator(Protocol):
    def __call__(
        self, candidate: GeneralAssemblyCandidate
    ) -> GeneralAssemblyValidationReport: ...


class AssemblyLiveError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        trace: tuple[dict[str, object], ...] = (),
        model_calls: int = 0,
        tool_calls: int = 0,
        attempts: tuple[GeneralAssemblyAttempt, ...] = (),
        provider_status_code: int | None = None,
        provider_code: str | None = None,
        provider_incomplete_reason: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.trace = trace
        self.model_calls = model_calls
        self.tool_calls = tool_calls
        self.attempts = attempts
        self.provider_status_code = provider_status_code
        self.provider_code = provider_code
        self.provider_incomplete_reason = provider_incomplete_reason


@dataclass(frozen=True)
class AssemblyAgentLimits:
    max_model_calls: int = 5
    max_tool_calls: int = 15
    timeout_s: float = 180
    max_instances: int = 100
    max_contours: int = 512
    max_tool_payload_bytes: int = 512 * 1024

    def __post_init__(self) -> None:
        if not 1 <= self.max_model_calls <= 5:
            raise ValueError("assembly_model_call_budget_invalid")
        if not 1 <= self.max_tool_calls <= 30:
            raise ValueError("assembly_tool_call_budget_invalid")
        if not 1 <= self.timeout_s <= 180:
            raise ValueError("assembly_timeout_budget_invalid")
        if not 1 <= self.max_instances <= 100:
            raise ValueError("assembly_instance_budget_invalid")
        if not 1 <= self.max_contours <= 512:
            raise ValueError("assembly_contour_budget_invalid")
        if not 1024 <= self.max_tool_payload_bytes <= 1024 * 1024:
            raise ValueError("assembly_tool_payload_budget_invalid")


@dataclass(frozen=True)
class AssemblyAgentContext:
    run_id: str
    proposal_revision: int
    review_revision: int
    extraction: DrawingExtraction
    review: GeneralFurnitureReview
    visual_pages: tuple[object, ...] = ()


@dataclass(frozen=True)
class AssemblyAgentOutcome:
    attempt: GeneralAssemblyAttempt
    attempts: tuple[GeneralAssemblyAttempt, ...]
    model_calls: int
    tool_calls: int
    trace: tuple[dict[str, object], ...]


def _tool_schema(name: str, description: str, model: type[BaseModel]) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": _strictify_schema(model.model_json_schema()),
    }


def assembly_tool_schemas() -> list[dict]:
    return [
        _tool_schema(
            "inspeccionar_contexto_montaje",
            "Consulta medidas geométricas observadas por id o página.",
            InspectAssemblyContextArgs,
        ),
        _tool_schema(
            "evaluar_candidato_montaje",
            "Evalúa determinísticamente un candidato completo y devuelve errores reparables.",
            EvaluateAssemblyCandidateArgs,
        ),
        _tool_schema(
            "entregar_montaje_final",
            "Entrega un candidato completo; solo termina si el servidor lo valida.",
            FinalizeAssemblyCandidateArgs,
        ),
    ]


def _arguments(call, model: type[BaseModel], *, max_bytes: int) -> BaseModel:
    raw = getattr(call, "arguments_json", None)
    if raw is not None:
        if len(raw.encode("utf-8")) > max_bytes:
            raise ValueError("assembly_tool_payload_too_large")
        return model.model_validate_json(raw)
    else:
        value = getattr(call, "arguments", None)
        encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError("assembly_tool_payload_too_large")
        return model.model_validate_json(encoded)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "assembly_tool_arguments_invalid"
    value = str(exc)
    return value if value.startswith("assembly_") else "assembly_tool_arguments_invalid"


def _safe_error_details(exc: Exception) -> tuple[str, ...]:
    if not isinstance(exc, ValidationError):
        return ()
    return tuple(
        f"{'.'.join(str(part) for part in item.get('loc', ()))}:{item.get('type', 'validation_error')}"
        for item in exc.errors(include_url=False, include_context=False, include_input=False)[:16]
    )


def _context_payload(
    context: AssemblyAgentContext,
    compact: CompactGeometryContext,
    assembly_context,
    expected_assembly_revision: int,
) -> dict[str, object]:
    return {
        "instruction": (
            "Propón correspondencias y orientación ortogonal usando solo ids y fuentes del contexto. "
            "No inventes coordenadas libres. Evalúa antes de finalizar y corrige todos los errores."
        ),
        "run_id": context.run_id,
        "proposal_revision": context.proposal_revision,
        "review_revision": context.review_revision,
        "expected_assembly_revision": expected_assembly_revision,
        "review": context.review.model_dump(mode="json"),
        "compact_geometry": compact.to_payload(),
        "assembly_context": assembly_context.model_dump(mode="json"),
        "allowed_candidate_sources": tuple(sorted(_allowed_candidate_sources(context))),
        "visual_artifacts": tuple({
            "reference": f"visual:{getattr(page, 'reference')}",
            "sha256": getattr(page, "sha256"),
            "source_view_ids": getattr(page, "source_view_ids", ()),
            "source_contour_ids": getattr(page, "source_contour_ids", ()),
            "source_document_refs": getattr(page, "source_document_refs", ()),
            "authority": "visual_context_not_measurement_source",
        } for page in context.visual_pages),
    }


def _allowed_candidate_sources(context: AssemblyAgentContext) -> set[str]:
    allowed = {
        f"run:{context.run_id}",
        f"drawing:{context.extraction.drawing_id}",
        *(item.id for item in context.extraction.views),
        *(item.id for item in context.extraction.contours),
        *(item.id for item in context.extraction.evidence),
    }
    for page in context.visual_pages:
        allowed.add(f"visual:{getattr(page, 'reference')}")
        allowed.update(getattr(page, "source_document_refs", ()))
    return allowed


def _candidate_matches_context(
    candidate: GeneralAssemblyCandidate,
    context: AssemblyAgentContext,
    expected_revision: int,
) -> None:
    if (
        candidate.run_id != context.run_id
        or candidate.proposal_revision != context.proposal_revision
        or candidate.review_revision != context.review_revision
        or candidate.assembly_revision != expected_revision
    ):
        raise ValueError("assembly_candidate_revision_mismatch")
    if not set(candidate.sources) <= _allowed_candidate_sources(context):
        raise ValueError("assembly_candidate_source_not_allowed")


def _attempt(
    *,
    context: AssemblyAgentContext,
    candidate: GeneralAssemblyCandidate,
    report: GeneralAssemblyValidationReport,
    attempt_index: int,
    model: str,
    trace: list[dict[str, object]],
) -> GeneralAssemblyAttempt:
    return GeneralAssemblyAttempt(
        run_id=context.run_id,
        proposal_revision=context.proposal_revision,
        review_revision=context.review_revision,
        assembly_revision=candidate.assembly_revision,
        attempt_index=attempt_index,
        candidate=candidate,
        report=report,
        model=model,
        policy_version=ASSEMBLY_POLICY_VERSION,
        sources=candidate.sources,
        trace=tuple(
            GeneralAssemblyTraceEvent(
                sequence=index,
                kind=(
                    "inspect" if item.get("phase") == "assembly_inspect"
                    else "final" if item.get("phase") == "assembly_final"
                    else "evaluate" if item.get("phase") == "assembly_evaluate"
                    else "repair"
                ),
                summary=json.dumps(item, ensure_ascii=False, sort_keys=True)[:500],
            )
            for index, item in enumerate(trace[-64:], start=1)
        ),
    )


def build_terminal_assembly_attempt(
    context: AssemblyAgentContext,
    *,
    assembly_revision: int,
    attempt_index: int,
    model: str,
    error: Exception,
) -> GeneralAssemblyAttempt:
    code = (
        error.code
        if isinstance(error, AssemblyLiveError)
        else str(error)
        if str(error).startswith("assembly_")
        else "assembly_runtime_failed"
    )
    raw_trace = error.trace if isinstance(error, AssemblyLiveError) else ()
    last_candidate = (
        error.attempts[-1].candidate
        if isinstance(error, AssemblyLiveError) and error.attempts
        else None
    )
    last_report = (
        error.attempts[-1].report
        if isinstance(error, AssemblyLiveError) and error.attempts
        else None
    )
    trace = tuple(
        GeneralAssemblyTraceEvent(
            sequence=index,
            kind=(
                "inspect" if item.get("phase") == "assembly_inspect"
                else "final" if item.get("phase") == "assembly_final"
                else "evaluate" if item.get("phase") == "assembly_evaluate"
                else "repair"
            ),
            summary=json.dumps(item, ensure_ascii=False, sort_keys=True)[:500],
        )
        for index, item in enumerate(raw_trace[-64:], start=1)
    ) or (GeneralAssemblyTraceEvent(
        sequence=1,
        kind="repair",
        summary=json.dumps({"code": code, "phase": "assembly_terminal"}, sort_keys=True),
    ),)
    return GeneralAssemblyAttempt(
        run_id=context.run_id,
        proposal_revision=context.proposal_revision,
        review_revision=context.review_revision,
        assembly_revision=assembly_revision,
        attempt_index=attempt_index,
        candidate=last_candidate,
        report=GeneralAssemblyValidationReport(
            status="incomplete",
            issues=(GeneralAssemblyValidationIssue(
                code=code,
                severity="error",
                message="El montaje no pudo completarse de forma acotada.",
                source_refs=(
                    f"assembly_revision:{error.attempts[-1].assembly_revision}",
                ) if isinstance(error, AssemblyLiveError) and error.attempts else (),
            ),),
            placements=last_report.placements if last_report is not None else (),
            scene=None,
            global_bounds_mm=(
                last_report.global_bounds_mm if last_report is not None else None
            ),
            max_penetration_mm=(
                last_report.max_penetration_mm if last_report is not None else 0
            ),
        ),
        model=model,
        policy_version=ASSEMBLY_POLICY_VERSION,
        sources=(
            last_candidate.sources
            if last_candidate is not None
            else (f"run:{context.run_id}", f"drawing:{context.extraction.drawing_id}")
        ),
        trace=trace,
    )


def run_general_assembly_agent(
    context: AssemblyAgentContext,
    *,
    provider: AssemblyProvider,
    evaluator: AssemblyEvaluator,
    base_assembly_revision: int = 0,
    limits: AssemblyAgentLimits = AssemblyAgentLimits(),
    attempt_sink: Callable[[GeneralAssemblyAttempt], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> AssemblyAgentOutcome:
    started = clock()
    if len(context.extraction.contours) > limits.max_contours:
        raise AssemblyLiveError("assembly_contour_budget_exhausted")
    if len(context.review.occurrences) > limits.max_instances:
        raise AssemblyLiveError("assembly_instance_budget_exhausted")
    if len(context.visual_pages) > 4 or any(
        len(getattr(page, "content", b"")) > 4 * 1024 * 1024
        for page in context.visual_pages
    ):
        raise AssemblyLiveError("assembly_visual_budget_exhausted")
    measurements = derive_geometry_measurements(context.extraction)
    regions = derive_source_spatial_regions(context.extraction, measurements)
    hypotheses = derive_projection_hypotheses(context.extraction, measurements)
    compact = build_compact_geometry_context(
        context.extraction, measurements, regions, hypotheses
    )
    assembly_context = build_assembly_context(context.extraction, context.review)
    if clock() - started >= limits.timeout_s:
        raise AssemblyLiveError("assembly_timeout")
    trace: list[dict[str, object]] = []
    attempts: list[GeneralAssemblyAttempt] = []
    initial_content: list[dict[str, object]] = [
        {
            "type": "input_text",
            "text": json.dumps(
                _context_payload(
                    context,
                    compact,
                    assembly_context,
                    base_assembly_revision + 1,
                ),
                ensure_ascii=False,
            ),
        }
    ]
    initial_content.extend({
        "type": "input_image",
        "image_url": (
            f"data:{getattr(page, 'media_type')};base64,"
            f"{b64encode(getattr(page, 'content')).decode('ascii')}"
        ),
        "detail": "high",
    } for page in context.visual_pages)
    input_items: list[dict[str, object]] = [
        {"role": "user", "content": initial_content}
    ]
    previous_response_id = None
    tool_calls = 0
    for model_call in range(1, limits.max_model_calls + 1):
        remaining = limits.timeout_s - (clock() - started)
        if remaining <= 0:
            raise AssemblyLiveError(
                "assembly_timeout",
                trace=tuple(trace), model_calls=model_call - 1,
                tool_calls=tool_calls, attempts=tuple(attempts),
            )
        if cancelled is not None and cancelled():
            raise AssemblyLiveError(
                "assembly_cancelled", trace=tuple(trace),
                model_calls=model_call - 1, tool_calls=tool_calls,
                attempts=tuple(attempts),
            )
        try:
            response = provider.create_response(
                input_items=input_items,
                tools=assembly_tool_schemas(),
                previous_response_id=previous_response_id,
                timeout_s=remaining,
            )
        except ProviderError as exc:
            trace.append({"phase": "assembly_provider", "ok": False, "code": exc.code})
            raise AssemblyLiveError(
                exc.code, trace=tuple(trace), model_calls=model_call,
                tool_calls=tool_calls, attempts=tuple(attempts),
                provider_status_code=exc.status_code,
                provider_code=exc.provider_code,
                provider_incomplete_reason=exc.incomplete_reason,
            ) from None
        previous_response_id = response.id
        if clock() - started >= limits.timeout_s:
            raise AssemblyLiveError(
                "assembly_timeout", trace=tuple(trace), model_calls=model_call,
                tool_calls=tool_calls, attempts=tuple(attempts),
            )
        if cancelled is not None and cancelled():
            raise AssemblyLiveError(
                "assembly_cancelled", trace=tuple(trace), model_calls=model_call,
                tool_calls=tool_calls, attempts=tuple(attempts),
            )
        if not response.tool_calls:
            trace.append({"phase": "assembly_tool", "ok": False, "code": "assembly_tool_required"})
            input_items = [{"role": "user", "content": "Debes invocar una herramienta de montaje válida."}]
            continue
        if len(response.tool_calls) != 1:
            raise AssemblyLiveError(
                "assembly_parallel_tool_calls_rejected",
                trace=tuple(trace), model_calls=model_call,
                tool_calls=tool_calls, attempts=tuple(attempts),
            )
        call = response.tool_calls[0]
        tool_calls += 1
        if tool_calls > limits.max_tool_calls:
            raise AssemblyLiveError(
                "assembly_tool_call_budget_exhausted", trace=tuple(trace),
                model_calls=model_call, tool_calls=tool_calls,
                attempts=tuple(attempts),
            )
        try:
            if call.name == "inspeccionar_contexto_montaje":
                args = _arguments(call, InspectAssemblyContextArgs, max_bytes=limits.max_tool_payload_bytes)
                page = query_compact_measurements(
                    measurements,
                    measurement_ids=args.measurement_ids,
                    offset=args.offset,
                    limit=args.limit,
                )
                output = {"ok": True, "context": page.to_payload()}
                trace.append({"phase": "assembly_inspect", "tool": call.name, "ok": True})
            elif call.name in {"evaluar_candidato_montaje", "entregar_montaje_final"}:
                model = EvaluateAssemblyCandidateArgs if call.name == "evaluar_candidato_montaje" else FinalizeAssemblyCandidateArgs
                args = _arguments(call, model, max_bytes=limits.max_tool_payload_bytes)
                expected_revision = base_assembly_revision + len(attempts) + 1
                _candidate_matches_context(args.candidate, context, expected_revision)
                report = evaluator(args.candidate)
                if clock() - started >= limits.timeout_s:
                    raise AssemblyLiveError(
                        "assembly_timeout", trace=tuple(trace),
                        model_calls=model_call, tool_calls=tool_calls,
                        attempts=tuple(attempts),
                    )
                event = {
                    "phase": "assembly_final" if call.name == "entregar_montaje_final" else "assembly_evaluate",
                    "tool": call.name,
                    "ok": report.status == "accepted",
                    "status": report.status,
                    "provider_response_id": response.id,
                }
                trace.append(event)
                attempt = _attempt(
                    context=context, candidate=args.candidate, report=report,
                    attempt_index=len(attempts) + 1,
                    model=getattr(response, "model", None) or "unknown-model",
                    trace=trace,
                )
                if cancelled is not None and cancelled():
                    raise AssemblyLiveError(
                        "assembly_cancelled", trace=tuple(trace), model_calls=model_call,
                        tool_calls=tool_calls, attempts=tuple(attempts),
                    )
                if clock() - started >= limits.timeout_s:
                    raise AssemblyLiveError(
                        "assembly_timeout", trace=tuple(trace),
                        model_calls=model_call, tool_calls=tool_calls,
                        attempts=tuple(attempts),
                    )
                if attempt_sink is not None:
                    try:
                        attempt_sink(attempt)
                    except ValueError as exc:
                        raise AssemblyLiveError(
                            str(exc), trace=tuple(trace), model_calls=model_call,
                            tool_calls=tool_calls, attempts=tuple(attempts),
                        ) from None
                attempts.append(attempt)
                output = {
                    "ok": report.status == "accepted",
                    "report": report.model_dump(mode="json"),
                    "next_expected_assembly_revision": base_assembly_revision + len(attempts) + 1,
                    "instruction": "Corrige el candidato usando los códigos e ids exactos del informe.",
                }
                if call.name == "entregar_montaje_final" and report.status == "accepted":
                    return AssemblyAgentOutcome(
                        attempt=attempt, attempts=tuple(attempts),
                        model_calls=model_call, tool_calls=tool_calls,
                        trace=tuple(trace),
                    )
            else:
                raise ValueError("assembly_tool_unknown")
        except AssemblyLiveError:
            raise
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            code = _safe_error(exc)
            details = _safe_error_details(exc)
            trace.append({"phase": "assembly_tool", "tool": call.name, "ok": False, "code": code, "details": details})
            output = {
                "ok": False,
                "error": code,
                "details": details,
                "expected_assembly_revision": base_assembly_revision + len(attempts) + 1,
                "instruction": "Corrige los argumentos y vuelve a invocar una herramienta válida.",
            }
        input_items = [{
            "type": "function_call_output",
            "call_id": call.call_id,
            "output": json.dumps(output, ensure_ascii=False),
        }]
    raise AssemblyLiveError(
        "assembly_model_call_budget_exhausted", trace=tuple(trace),
        model_calls=limits.max_model_calls, tool_calls=tool_calls,
        attempts=tuple(attempts),
    )
__all__ = [
    "ASSEMBLY_POLICY_VERSION",
    "AssemblyAgentContext",
    "AssemblyAgentLimits",
    "AssemblyAgentOutcome",
    "AssemblyLiveError",
    "assembly_tool_schemas",
    "build_terminal_assembly_attempt",
    "run_general_assembly_agent",
]
