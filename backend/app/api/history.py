from __future__ import annotations

from typing import Callable, Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from backend.app.historico.models import (
    ComparableRequest,
    EstimateRequest,
    HistoricalImport,
    ProvisionalScenarioRequest,
    ProvisionalScenarioSnapshot,
)
from backend.app.historico.real_service import HistoricalStore


def _ok(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return {"schema_version": "1.0.0", "data": value, "error": None}


def _error(code: str) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "data": None,
        "error": {"code": code},
    }


def create_history_router(
    store: HistoricalStore,
    *,
    max_csv_bytes: int = 5 * 1024 * 1024,
    scenario_snapshot_loader: Callable[
        [str, int, int], ProvisionalScenarioSnapshot
    ]
    | None = None,
) -> APIRouter:
    if max_csv_bytes < 1:
        raise ValueError("max_csv_bytes must be positive")
    router = APIRouter(prefix="/api/v1/history", tags=["history"])

    def authoritative_import(request: Request, value: HistoricalImport) -> HistoricalImport:
        actor = getattr(request.state, "actor", None)
        if actor is None:
            return value
        return value.model_copy(
            update={
                "records": tuple(
                    record.model_copy(
                        update={
                            "provenance": record.provenance.model_copy(
                                update={"imported_by": str(actor)}
                            )
                        }
                    )
                    for record in value.records
                )
            }
        )

    @router.post("/import/json")
    def import_json(payload: HistoricalImport, request: Request, dry_run: bool = False):
        return _ok(
            store.import_records(
                authoritative_import(request, payload), dry_run=dry_run
            )
        )

    @router.post("/import/csv")
    @router.post("/imports")
    async def import_csv(
        request: Request,
        file: UploadFile = File(...),
        dry_run: bool = Query(default=False),
    ):
        try:
            payload = await file.read(max_csv_bytes + 1)
            if len(payload) > max_csv_bytes:
                return JSONResponse(
                    status_code=413,
                    content=_error("history_import_too_large"),
                )
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            return JSONResponse(
                status_code=422,
                content=_error("invalid_csv_encoding"),
            )
        actor = getattr(request.state, "actor", None)
        return _ok(store.import_csv(text, dry_run=dry_run, imported_by=actor))

    @router.get("/records")
    @router.get("")
    def list_records(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        origin: Literal["actual", "published", "synthetic"] | None = None,
    ):
        return _ok(store.list_records(limit=limit, offset=offset, origin=origin))

    @router.post("/comparables")
    def comparables(request: ComparableRequest):
        try:
            value = store.find_comparables(
                request.target,
                limit=request.limit,
                retrieval_method=request.retrieval_method,
                include_synthetic=request.include_synthetic,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=422,
                content=_error(str(exc)),
            )
        return _ok(value)

    @router.post("/estimate")
    def estimate(request: EstimateRequest):
        try:
            value = store.estimate(
                request.target,
                comparable_ids=request.comparable_ids,
                include_synthetic=request.include_synthetic,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=422,
                content=_error(str(exc)),
            )
        return _ok(value)

    @router.post("/scenarios")
    def provisional_scenarios(request: ProvisionalScenarioRequest):
        if scenario_snapshot_loader is None:
            return JSONResponse(
                status_code=503,
                content=_error("scenario_snapshot_loader_unavailable"),
            )
        try:
            snapshot = scenario_snapshot_loader(
                request.run_id,
                request.proposal_revision,
                request.review_revision,
            )
        except KeyError:
            return JSONResponse(
                status_code=404,
                content=_error("general_scenario_snapshot_not_found"),
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=409,
                content=_error(str(exc)),
            )
        if (
            snapshot.run_id != request.run_id
            or snapshot.proposal_revision != request.proposal_revision
            or snapshot.review_revision != request.review_revision
        ):
            return JSONResponse(
                status_code=409,
                content=_error("general_scenario_snapshot_revision_conflict"),
            )
        try:
            value = store.provisional_scenarios(
                snapshot,
                limit=request.limit,
                retrieval_method=request.retrieval_method,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=422,
                content=_error(str(exc)),
            )
        return _ok(value)

    return router
