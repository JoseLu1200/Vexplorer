from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.agente.runner import AgentLimits, run_agent
from backend.app.agente.tools import tool_schemas
from backend.app.contratos.modelos import ReviewRequest
from backend.app.estimacion.service import estimate_result
from backend.app.geometria import extract_drawing
from backend.app.historico.service import find_comparables
from backend.app.salida.service import export_csv, export_json
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.explanations import explain_result
from backend.app.servicios.repository import DemoRepository

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(RequestModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{32}$")
    mode: Literal["live", "geometry_only", "recorded_replay"]


class EstimateRequest(RequestModel):
    result_revision: int = Field(gt=0)


def _ok(data, status_code: int = 200):
    return JSONResponse({"schema_version": "0.2.0", "data": data}, status_code=status_code)


def _error(status_code: int, code: str, message: str, retryable: bool = False):
    return JSONResponse({"schema_version": "0.2.0", "error": {"code": code, "message": message, "retryable": retryable}}, status_code=status_code)


def create_app(data_dir: Path | None = None, frontend_dir: Path | None = None) -> FastAPI:
    root = data_dir or Path(".vexplorer-data")
    documents_dir = root / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    repository = DemoRepository(root / "vexplorer.sqlite3")
    settings = ProviderSettings.from_env()
    app = FastAPI(title="Vexplorer", version="0.2.0")

    @app.get("/api/v1/health")
    def health():
        return _ok({"status": "ok"})

    @app.get("/api/v1/config")
    def config():
        return _ok({"provider": "openai_responses", "model": settings.model, "live_available": settings.available, "unavailable_reason": settings.unavailable_reason, "recorded_replay_available": False, "modes": ["geometry_only"] + (["live"] if settings.available else []), "modality": "structured_vector_evidence_without_vision", "limits": {"max_model_calls": 15, "max_tool_calls": 30, "timeout_s": 120}, "tools": [{"name": item["name"], "description": item["description"]} for item in tool_schemas()]})

    @app.post("/api/v1/documents")
    async def upload_document(file: UploadFile = File(...)):
        filename = Path(file.filename or "").name
        if Path(filename).suffix.lower() != ".dxf":
            return _error(415, "unsupported_format", "La demo admite exclusivamente DXF.")
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            return _error(413, "upload_too_large", "El archivo supera 20 MiB.")
        document_id = f"doc-{uuid4().hex}"
        (documents_dir / f"{document_id}.dxf").write_bytes(content)
        return _ok({"document_id": document_id, "original_filename": filename, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "source_kind": "uploaded"}, 201)

    @app.get("/api/v1/documents/{document_id}/drawing")
    def get_document_drawing(document_id: str):
        if re.fullmatch(r"doc-[0-9a-f]{32}", document_id) is None:
            return _error(422, "invalid_document_id", "Identificador de documento inválido.")
        path = documents_dir / f"{document_id}.dxf"
        if not path.is_file():
            return _error(404, "document_not_found", "Documento inexistente.")
        try:
            extraction = extract_drawing(path)
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        return _ok(extraction.model_dump(mode="json"))

    @app.post("/api/v1/runs")
    def create_run(request: RunRequest):
        if request.mode == "recorded_replay":
            return _error(409, "recorded_replay_unavailable", "No existe una grabación real autorizada para replay.")
        if request.mode == "live" and not settings.available:
            return _error(503, "live_provider_unavailable", settings.unavailable_reason or "Proveedor no disponible.", True)
        path = documents_dir / f"{request.document_id}.dxf"
        if not path.is_file():
            return _error(404, "document_not_found", "Documento inexistente.")
        try:
            extraction = extract_drawing(path)
            scenarios = derive_decomposition_scenarios(extraction)
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        if not scenarios:
            return _error(422, "unsupported_geometry", "Las vistas no respaldan escenarios rectangulares coherentes.")
        trace_events: tuple[dict, ...] = ()
        agent_selected_scenario_id = None
        if request.mode == "live":
            try:
                outcome = run_agent(extraction, scenarios, OpenAIResponsesProvider(settings), AgentLimits())
            except Exception as exc:
                return _error(502, "live_provider_failed", f"La ejecución live falló sin fallback: {type(exc).__name__}.", True)
            scenarios = tuple(sorted(scenarios, key=lambda item: item.id != outcome.selected_scenario_id))
            agent_selected_scenario_id = outcome.selected_scenario_id
            trace_events = tuple({"tool_name": action.tool_name, "ok": action.ok, "evidence_ids": action.evidence_ids, "summary": action.summary, "selected_scenario_id": action.selected_scenario_id} for action in outcome.actions)
        run_id = f"run-{uuid4().hex}"
        run = repository.create_run(run_id, request.mode, extraction, scenarios, trace_events, agent_selected_scenario_id)
        return _ok({"run": run.model_dump(mode="json"), "result": repository.get_result(run_id).model_dump(mode="json")}, 201)

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str):
        try:
            run, result = repository.get_run(run_id), repository.get_result(run_id)
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")
        try:
            estimate = repository.get_estimate(run_id, result.result_revision).model_dump(mode="json")
        except KeyError:
            estimate = None
        return _ok({"run": run.model_dump(mode="json"), "result": result.model_dump(mode="json"), "estimate": estimate})

    @app.get("/api/v1/runs/{run_id}/revisions")
    def get_revisions(run_id: str):
        try:
            values = repository.get_results(run_id)
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")
        return _ok([item.model_dump(mode="json") for item in values])

    @app.get("/api/v1/runs/{run_id}/explanations")
    def get_explanations(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
            extraction = repository.get_extraction(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        return _ok(explain_result(extraction, result).model_dump(mode="json"))

    @app.get("/api/v1/runs/{run_id}/ledger")
    @app.get("/api/v1/runs/{run_id}/drawing")
    def get_extraction(run_id: str):
        try:
            return _ok(repository.get_extraction(run_id).model_dump(mode="json"))
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")

    @app.post("/api/v1/runs/{run_id}/reviews")
    def review_run(run_id: str, request: ReviewRequest):
        try:
            result = repository.review(run_id, request)
            repository.append_event(run_id, "human_review_committed", {"result_revision": result.result_revision, "reviewer_name": request.reviewer_name, "selected_scenario_id": request.scenario_id})
            return _ok(result.model_dump(mode="json"), 201)
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")
        except ValueError as exc:
            code = str(exc)
            return _error(409 if code == "stale_result_revision" else 422, code, "La revisión no es aplicable.")

    @app.get("/api/v1/runs/{run_id}/comparables")
    def comparables(run_id: str, limit: int = Query(default=3, ge=1, le=3)):
        try:
            result = repository.get_result(run_id)
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")
        return _ok([item.model_dump(mode="json") for item in find_comparables(result, limit)])

    @app.post("/api/v1/runs/{run_id}/estimate")
    def estimate(run_id: str, request: EstimateRequest):
        try:
            result = repository.get_result(run_id, request.result_revision)
            value = estimate_result(result, find_comparables(result))
            repository.save_estimate(run_id, value)
            repository.append_event(run_id, "estimate_committed", {"result_revision": value.result_revision, "total": value.total, "currency": value.currency})
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        except ValueError as exc:
            return _error(422, str(exc), "No hay evidencia suficiente para estimar.")
        return _ok(value.model_dump(mode="json"), 201)

    @app.get("/api/v1/runs/{run_id}/exports")
    def exports(run_id: str, format: Literal["json", "csv"] = Query(...)):
        try:
            result = repository.get_result(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Resultado inexistente.")
        if format == "json":
            try:
                estimate_value = repository.get_estimate(run_id, result.result_revision).model_dump(mode="json")
            except KeyError:
                estimate_value = None
            bundle = {"schema_version": "0.2.0", "result_revision": result.result_revision, "result": result.model_dump(mode="json"), "comparables": [item.model_dump(mode="json") for item in find_comparables(result)], "estimate": estimate_value, "events": list(repository.get_events(run_id))}
            payload, media = json.dumps(bundle, ensure_ascii=False, indent=2), "application/json"
        else:
            payload, media = export_csv(result), "text/csv; charset=utf-8"
        return Response(payload, media_type=media, headers={"Content-Disposition": f'attachment; filename="{run_id}-r{result.result_revision}.{format}"'})

    @app.get("/api/v1/runs/{run_id}/events")
    def events(run_id: str):
        try:
            records = repository.get_events(run_id)
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")
        body = "".join(f"id: {item['sequence']}\nevent: {item['event_type']}\ndata: {json.dumps({'schema_version': '0.2.0', 'run_id': run_id, **item}, ensure_ascii=False)}\n\n" for item in records)
        return PlainTextResponse(body, media_type="text/event-stream")

    static_root = frontend_dir or Path(__file__).resolve().parents[2] / "frontend"
    if (static_root / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")
    else:
        @app.get("/")
        def root_status():
            return _ok({"status": "api_ready", "frontend": "not_present"})
    return app


app = create_app()
