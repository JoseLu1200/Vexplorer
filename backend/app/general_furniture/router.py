from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralAutoReviewRequest,
    GeneralDerivedResponse,
    GeneralDerivedEnvelope,
    GeneralFurnitureEnvelope,
    GeneralFurnitureRecord,
    GeneralFurnitureReviewRequest,
    GeneralHistoricalTarget,
    GeneralProposalRequest,
)
from backend.app.general_furniture.derivations import derive_general_package
from backend.app.general_furniture.live import (
    GeneralFurnitureAgentOutcome,
    GeneralVisualPage,
)
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.review import apply_general_review


@dataclass(frozen=True)
class GeneralFurnitureContext:
    run_id: str
    extraction: DrawingExtraction
    ledger_revision: str
    visual_pages: tuple[GeneralVisualPage, ...] = ()


class GeneralLiveRunner(Protocol):
    def __call__(
        self, context: GeneralFurnitureContext
    ) -> GeneralFurnitureAgentOutcome: ...


class GeneralAutoReviewRunner(Protocol):
    def __call__(
        self,
        context: GeneralFurnitureContext,
        proposal_outcome: GeneralFurnitureAgentOutcome,
        *,
        proposal_revision: int,
        previous_review,
    ): ...


def _stamp_human_provenance(
    body: GeneralFurnitureReviewRequest, actor: str
) -> GeneralFurnitureReviewRequest:
    reference = f"human:{actor}:review:{body.base_review_revision + 1}"
    components = []
    for component in body.components:
        updates = {}
        for name in ("length", "width", "thickness", "quantity", "material", "finish"):
            value = getattr(component, name)
            if value.state == "confirmed":
                updates[name] = value.model_copy(
                    update={"dependency_refs": (reference,)}
                )
        components.append(component.model_copy(update=updates))
    furniture_quantity = body.furniture_quantity
    if furniture_quantity.state == "confirmed":
        furniture_quantity = furniture_quantity.model_copy(
            update={"dependency_refs": (reference,)}
        )
    return body.model_copy(
        update={
            "reviewer_name": actor,
            "components": tuple(components),
            "furniture_quantity": furniture_quantity,
        }
    )


def _historical_target(record: GeneralFurnitureRecord) -> GeneralHistoricalTarget:
    review = record.review
    reliable = {"confirmed", "derived"}
    components = review.components if review else ()
    complete_area = bool(components) and all(
        item.length.state in reliable
        and item.width.state in reliable
        and item.quantity.state in reliable
        and item.length.value_mm is not None
        and item.width.value_mm is not None
        and item.quantity.value is not None
        for item in components
    )
    complete_volume = complete_area and all(
        item.thickness.state in reliable and item.thickness.value_mm is not None
        for item in components
    )
    areas = (
        [
            item.length.value_mm * item.width.value_mm * item.quantity.value
            for item in components
        ]
        if complete_area
        else []
    )
    lengths = (
        [item.length.value_mm * item.quantity.value for item in components]
        if complete_area
        else []
    )
    volumes = (
        [
            item.length.value_mm
            * item.width.value_mm
            * item.thickness.value_mm
            * item.quantity.value
            for item in components
        ]
        if complete_volume
        else []
    )
    complete_material = bool(components) and all(
        item.material.state in reliable and item.material.value for item in components
    )
    complete_finish = bool(components) and all(
        item.finish.state in reliable and item.finish.value for item in components
    )
    material_values = (
        {item.material.value for item in components} if complete_material else set()
    )
    finish_values = (
        {item.finish.value for item in components} if complete_finish else set()
    )
    return GeneralHistoricalTarget(
        area_mm2=sum(areas) if areas else None,
        length_mm=sum(lengths) if lengths else None,
        volume_mm3=sum(volumes) if volumes else None,
        quantity=review.furniture_quantity.value
        if review and review.furniture_quantity.state in reliable
        else None,
        material=next(iter(material_values)) if len(material_values) == 1 else None,
        finish=next(iter(finish_values)) if len(finish_values) == 1 else None,
        currency=review.currency if review else None,
        required_cost_scope=review.required_cost_scope if review else (),
        required_hours_scope=review.required_hours_scope if review else (),
        basis_revision=f"proposal:{record.proposal_revision};review:{record.review_revision}",
    )


def create_general_furniture_router(
    *,
    repository: GeneralFurnitureRepository,
    context_loader: Callable[[str], GeneralFurnitureContext],
    live_runner: GeneralLiveRunner | None = None,
    event_sink: Callable[[str, int, GeneralFurnitureAgentOutcome], None] | None = None,
    direct_live_enabled: bool = False,
    auto_review_runner: GeneralAutoReviewRunner | None = None,
    auto_review_event_sink: Callable[[str, object], None] | None = None,
    direct_auto_review_enabled: bool = False,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/runs/{run_id}/general", tags=["general-furniture"]
    )

    def context(run_id: str) -> GeneralFurnitureContext:
        try:
            loaded = context_loader(run_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="run_not_found") from None
        if loaded.run_id != run_id:
            raise HTTPException(status_code=409, detail="run_context_mismatch")
        if loaded.extraction.input_kind != "general_furniture":
            raise HTTPException(
                status_code=409, detail="general_furniture_context_required"
            )
        return loaded

    @router.post(
        "/proposals",
        response_model=GeneralFurnitureEnvelope,
        status_code=status.HTTP_201_CREATED,
    )
    def propose(run_id: str, body: GeneralProposalRequest) -> GeneralFurnitureEnvelope:
        loaded = context(run_id)
        outcome: GeneralFurnitureAgentOutcome | None = None
        if body.mode == "live":
            if not direct_live_enabled:
                raise HTTPException(
                    status_code=409, detail="general_live_requires_durable_job"
                )
            if live_runner is None or event_sink is None:
                raise HTTPException(status_code=503, detail="general_live_unavailable")
            outcome = live_runner(loaded)
            proposal, draft = outcome.proposal, outcome.draft
        else:
            assert body.proposal is not None
            proposal = body.proposal
            if proposal.proposal_origin != "human":
                raise HTTPException(
                    status_code=422, detail="manual_proposal_requires_human_origin"
                )
            if proposal.ledger_revision != loaded.ledger_revision:
                raise HTTPException(
                    status_code=409, detail="general_ledger_revision_mismatch"
                )
            try:
                draft = materialize_general_proposal(
                    loaded.extraction,
                    proposal,
                    allowed_document_refs=tuple(
                        item.reference for item in loaded.visual_pages
                    ),
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from None
        try:
            revision = repository.save_proposal(
                run_id,
                proposal,
                draft,
                base_proposal_revision=body.base_proposal_revision,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        if outcome is not None:
            event_sink(run_id, revision, outcome)
        return GeneralFurnitureEnvelope(data=repository.get(run_id))  # type: ignore[arg-type]

    @router.get("", response_model=GeneralFurnitureEnvelope)
    def get_record(
        run_id: str,
        proposal_revision: int | None = Query(default=None, gt=0),
        review_revision: int | None = Query(default=None, ge=0),
    ) -> GeneralFurnitureEnvelope:
        if review_revision is not None and proposal_revision is None:
            raise HTTPException(
                status_code=422,
                detail="proposal_revision_required_for_exact_review",
            )
        record = repository.get(
            run_id,
            proposal_revision=proposal_revision,
            review_revision=review_revision,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="general_proposal_not_found")
        return GeneralFurnitureEnvelope(data=record)

    @router.post("/reviews", response_model=GeneralFurnitureEnvelope)
    def review(
        run_id: str, body: GeneralFurnitureReviewRequest, request: Request
    ) -> GeneralFurnitureEnvelope:
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="general_proposal_not_found")
        actor = getattr(request.state, "actor", None)
        body = _stamp_human_provenance(body, str(actor or body.reviewer_name))
        try:
            reviewed = apply_general_review(
                run_id=run_id,
                proposal_id=record.proposal.id,
                proposal_revision=record.proposal_revision,
                draft=record.draft,
                request=body,
                previous_review=record.review,
            )
            package = derive_general_package(reviewed)
            repository.save_review(run_id, reviewed, package)
        except ValueError as exc:
            code = 409 if "revision" in str(exc) else 422
            raise HTTPException(status_code=code, detail=str(exc)) from None
        return GeneralFurnitureEnvelope(data=repository.get(run_id))  # type: ignore[arg-type]

    @router.post("/auto-review", response_model=GeneralFurnitureEnvelope)
    def auto_review(
        run_id: str, body: GeneralAutoReviewRequest
    ) -> GeneralFurnitureEnvelope:
        if not direct_auto_review_enabled:
            raise HTTPException(
                status_code=409,
                detail="general_auto_review_requires_durable_job",
            )
        if auto_review_runner is None or auto_review_event_sink is None:
            raise HTTPException(
                status_code=503, detail="general_auto_review_unavailable"
            )
        loaded = context(run_id)
        record = repository.get(run_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail="general_proposal_not_found"
            )
        if (
            body.base_proposal_revision != record.proposal_revision
            or body.base_review_revision != record.review_revision
        ):
            raise HTTPException(
                status_code=409, detail="general_furniture_revision_conflict"
            )
        proposal_outcome = GeneralFurnitureAgentOutcome(
            proposal=record.proposal,
            draft=record.draft,
            model_calls=0,
            tool_calls=0,
            trace=(),
        )
        outcome = auto_review_runner(
            loaded,
            proposal_outcome,
            proposal_revision=record.proposal_revision,
            previous_review=record.review,
        )
        try:
            if outcome.semantic_repairs:
                saved_revision = repository.save_proposal(
                    run_id,
                    outcome.effective_proposal_outcome.proposal,
                    outcome.effective_proposal_outcome.draft,
                    base_proposal_revision=record.proposal_revision,
                )
                if saved_revision != outcome.review.proposal_revision:
                    raise ValueError("general_auto_review_revision_mismatch")
            repository.save_review(run_id, outcome.review, outcome.derived)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        auto_review_event_sink(run_id, outcome)
        return GeneralFurnitureEnvelope(data=repository.get(run_id))  # type: ignore[arg-type]

    @router.get("/derived", response_model=GeneralDerivedEnvelope)
    def derived(
        run_id: str,
        proposal_revision: int = Query(gt=0),
        review_revision: int = Query(gt=0),
    ) -> GeneralDerivedEnvelope:
        record = repository.get(
            run_id, proposal_revision=proposal_revision, review_revision=review_revision
        )
        package = repository.get_derived(
            run_id, proposal_revision=proposal_revision, review_revision=review_revision
        )
        if record is None or package is None:
            raise HTTPException(status_code=404, detail="general_derived_not_found")
        if (record.proposal_revision, record.review_revision) != (
            proposal_revision,
            review_revision,
        ):
            raise HTTPException(
                status_code=409, detail="general_furniture_revision_conflict"
            )
        return GeneralDerivedEnvelope(
            data=GeneralDerivedResponse(
                package=package, historical_target=_historical_target(record)
            )
        )

    @router.get("/artifacts/{artifact_id}")
    def artifact(
        run_id: str,
        artifact_id: str,
        proposal_revision: int = Query(gt=0),
        review_revision: int = Query(gt=0),
    ) -> Response:
        package = repository.get_derived(
            run_id,
            proposal_revision=proposal_revision,
            review_revision=review_revision,
        )
        item = (
            next(
                (value for value in package.artifacts if value.id == artifact_id), None
            )
            if package
            else None
        )
        if item is None:
            raise HTTPException(status_code=404, detail="general_artifact_not_found")
        return Response(
            content=item.content,
            media_type=item.media_type,
            headers={"Content-Disposition": f'attachment; filename="{item.filename}"'},
        )

    return router
