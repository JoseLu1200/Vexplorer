from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response

from .models import ReviewRequest, SearchRequest
from .review import ReviewAssistant
from .service import ExplorerService
from .store import ExplorerStore


def install_explorer(app, repository, root: Path) -> None:
    enabled = os.getenv("VEXPLORER_EXPLORER_ENABLED", "0") == "1"
    store = ExplorerStore(root / "semantic_explorer.sqlite3") if enabled else None
    service = ExplorerService(repository, store) if store else None
    reviewer = (
        ReviewAssistant(
            store,
            os.getenv("VEXPLORER_JEV_API_KEY"),
            int(os.getenv("VEXPLORER_JEV_DAILY_ATTEMPTS", "0")),
        )
        if store
        else None
    )
    app.state.explorer_store = store
    router = APIRouter(prefix="/api/v1/semantic-explorer", tags=["semantic-explorer"])

    def handle(operation):
        if service is None:
            return JSONResponse(
                {
                    "error": {
                        "code": "explorer_disabled",
                        "message": "El explorador no está habilitado en esta instancia.",
                    }
                },
                status_code=503,
            )
        try:
            return {"data": operation(), "error": None}
        except KeyError:
            return JSONResponse(
                {
                    "error": {
                        "code": "explorer_not_found",
                        "message": "El espacio o elemento ya no está disponible. Actualiza el mapa.",
                    }
                },
                status_code=404,
            )
        except ValueError as exc:
            known = str(exc)
            code = (
                known
                if known
                in {
                    "stale_snapshot",
                    "review_pending",
                    "review_budget_exhausted",
                    "review_unavailable",
                    "review_evidence_missing",
                    "corrupt_release",
                    "corrupt_image",
                }
                else "explorer_data_invalid"
            )
            return JSONResponse(
                {
                    "error": {
                        "code": code,
                        "message": "No se pudo completar la operación. Actualiza el mapa o revisa la configuración y los artefactos.",
                    }
                },
                status_code=409
                if code in {"stale_snapshot", "review_pending"}
                else 503,
            )

    @router.get("/spaces")
    def spaces():
        return handle(
            lambda: (
                service.list_spaces()
                | {
                    "review": {
                        "available": reviewer.available,
                        "model": "jev-1.14.0",
                        "daily_attempt_limit": reviewer.daily_limit,
                    }
                }
            )
        )

    @router.get("/snapshot")
    def snapshot(space: str = Query(max_length=200)):
        return handle(lambda: service.snapshot(space))

    @router.post("/search")
    def neighbors(request: SearchRequest):
        return handle(lambda: service.search(request))

    @router.get("/image")
    def image(
        space: str = Query(max_length=200),
        snapshot_id: str = Query(pattern=r"^[a-f0-9]{64}$"),
        member_id: str = Query(pattern=r"^[a-zA-Z0-9_.:-]{1,160}$"),
    ):
        def content():
            service.checked(space, snapshot_id)
            if not space.startswith("corpus:"):
                raise KeyError(space)
            raw = store.image(space.removeprefix("corpus:"), member_id)
            service.checked(space, snapshot_id)
            return raw

        result = handle(content)
        if isinstance(result, JSONResponse):
            return result
        return Response(
            result["data"],
            media_type="image/png",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    @router.post("/review")
    def review(request: ReviewRequest):
        def run():
            bundle = service.checked(request.space, request.snapshot_id)
            entry = next((e for e in bundle.entries if e.id == request.member_id), None)
            if entry is None or not request.space.startswith("corpus:"):
                raise KeyError(request.member_id)
            image = store.image(
                request.space.removeprefix("corpus:"), request.member_id
            )
            result = reviewer.review(
                entry,
                image,
                tuple(e.category for e in bundle.entries if e.category),
                request.snapshot_id,
            )
            service.checked(request.space, request.snapshot_id)
            return result

        return handle(run)

    app.include_router(router)
