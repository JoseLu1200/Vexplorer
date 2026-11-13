from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agente.config import EmbeddingSettings, ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.agente.runner import AgentLimits, run_agent
from backend.app.agente.tools import tool_schemas
from backend.app.contratos.modelos import EmbeddingMetadata, LibraryItem, ReviewRequest
from backend.app.estimacion.service import estimate_result
from backend.app.geometria import extract_drawing
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.historico.service import find_comparables
from backend.app.salida.service import export_csv, export_json
from backend.app.salida.drawing_preview import render_drawing_preview
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.explanations import explain_result
from backend.app.servicios.repository import DemoRepository
from backend.app.servicios.reconstruction import reconstruct_scene
from backend.app.semantic.descriptor import build_descriptor, descriptor_fingerprint, semantic_text
from backend.app.semantic.embeddings import EmbeddingProviderError, OpenAIEmbeddingProvider, embedding_cache_key
from backend.app.similarity.service import geometric_groups, geometric_match, semantic_groups, semantic_match

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunRequest(RequestModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{32}$")
    mode: Literal["live", "geometry_only", "recorded_replay"]
    input_kind: Literal["mounted_views_legacy", "separated_part_views"] = "mounted_views_legacy"


class EstimateRequest(RequestModel):
    result_revision: int = Field(gt=0)


class LibrarySaveRequest(RequestModel):
    result_revision: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=120)
    embedding_mode: Literal["offline", "openai"]


class SimilarityRequest(RequestModel):
    result_revision: int = Field(gt=0)
    mode: Literal["geometric", "semantic"]
    limit: int = Field(default=10, ge=1, le=50)


class GroupRequest(RequestModel):
    mode: Literal["geometric", "semantic"]
    threshold: float = Field(default=0.8, ge=-1, le=1, allow_inf_nan=False)


def _ok(data, status_code: int = 200):
    return JSONResponse({"schema_version": "0.2.0", "data": data}, status_code=status_code)


def _error(status_code: int, code: str, message: str, retryable: bool = False):
    return JSONResponse({"schema_version": "0.2.0", "error": {"code": code, "message": message, "retryable": retryable}}, status_code=status_code)


def create_app(data_dir: Path | None = None, frontend_dir: Path | None = None, embedding_provider=None) -> FastAPI:
    root = data_dir or Path(".vexplorer-data")
    documents_dir = root / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    repository = DemoRepository(root / "vexplorer.sqlite3")
    settings = ProviderSettings.from_env()
    embedding_settings = EmbeddingSettings.from_env()
    semantic_provider = embedding_provider
    if semantic_provider is None and embedding_settings.available:
        semantic_provider = OpenAIEmbeddingProvider(api_key=embedding_settings.api_key or "", model=embedding_settings.model, dimensions=embedding_settings.dimensions, base_url=embedding_settings.base_url)
    app = FastAPI(title="Vexplorer", version="0.2.0")

    @app.get("/api/v1/health")
    def health():
        return _ok({"status": "ok"})

    @app.get("/api/v1/config")
    def config():
        return _ok({"provider": "openai_responses", "model": settings.model, "live_available": settings.available, "unavailable_reason": settings.unavailable_reason, "recorded_replay_available": False, "modes": ["geometry_only"] + (["live"] if settings.available else []), "modality": "structured_vector_evidence_without_vision", "limits": {"max_model_calls": 15, "max_tool_calls": 30, "timeout_s": 120}, "tools": [{"name": item["name"], "description": item["description"]} for item in tool_schemas()], "semantic": {"available": semantic_provider is not None, "provider": "openai", "model": getattr(semantic_provider, "model", embedding_settings.model), "dimensions": getattr(semantic_provider, "dimensions", embedding_settings.dimensions), "unavailable_reason": None if semantic_provider is not None else embedding_settings.unavailable_reason, "offline_mode": "geometric"}})

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
    def get_document_drawing(
        document_id: str,
        input_kind: Literal["mounted_views_legacy", "separated_part_views"] = Query(
            default="mounted_views_legacy"
        ),
    ):
        if re.fullmatch(r"doc-[0-9a-f]{32}", document_id) is None:
            return _error(422, "invalid_document_id", "Identificador de documento inválido.")
        path = documents_dir / f"{document_id}.dxf"
        if not path.is_file():
            return _error(404, "document_not_found", "Documento inexistente.")
        try:
            extraction = extract_drawing(path, input_kind=input_kind)
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        return _ok(extraction.model_dump(mode="json"))

    @app.get("/api/v1/documents/{document_id}/preview.svg")
    def get_document_preview(document_id: str):
        if re.fullmatch(r"doc-[0-9a-f]{32}", document_id) is None:
            return _error(422, "invalid_document_id", "Identificador de documento inválido.")
        path = documents_dir / f"{document_id}.dxf"
        if not path.is_file():
            return _error(404, "document_not_found", "Documento inexistente.")
        try:
            svg = render_drawing_preview(path)
        except ValueError as exc:
            code = str(exc) if str(exc) in ("preview_complexity_limit", "invalid_dxf") else "invalid_dxf"
            return _error(422, code, "No se pudo generar la previsualización SVG.")
        return Response(svg, media_type="image/svg+xml", headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"})

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
            extraction = extract_drawing(path, input_kind=request.input_kind)
            if request.input_kind == "separated_part_views":
                part_analysis = extract_separated_parts(extraction)
                assembly_candidates = derive_assembly_candidates(part_analysis)
                scenarios = ()
            else:
                part_analysis = None
                assembly_candidates = ()
                scenarios = derive_decomposition_scenarios(extraction)
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        if request.input_kind == "mounted_views_legacy" and not scenarios:
            return _error(422, "unsupported_geometry", "Las vistas no respaldan escenarios rectangulares coherentes.")
        trace_events: tuple[dict, ...] = ()
        agent_selected_scenario_id = None
        if request.mode == "live" and request.input_kind == "separated_part_views":
            return _error(409, "parts_live_unavailable", "El bucle live para piezas separadas no está disponible en esta revisión.")
        if request.mode == "live":
            try:
                outcome = run_agent(extraction, scenarios, OpenAIResponsesProvider(settings), AgentLimits())
            except Exception as exc:
                return _error(502, "live_provider_failed", f"La ejecución live falló sin fallback: {type(exc).__name__}.", True)
            scenarios = tuple(sorted(scenarios, key=lambda item: item.id != outcome.selected_scenario_id))
            agent_selected_scenario_id = outcome.selected_scenario_id
            trace_events = tuple({"tool_name": action.tool_name, "ok": action.ok, "evidence_ids": action.evidence_ids, "summary": action.summary, "selected_scenario_id": action.selected_scenario_id} for action in outcome.actions)
        run_id = f"run-{uuid4().hex}"
        run = repository.create_run(
            run_id,
            request.mode,
            extraction,
            scenarios,
            trace_events,
            agent_selected_scenario_id,
            request.document_id,
            part_analysis,
            assembly_candidates,
        )
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

    @app.get("/api/v1/runs/{run_id}/parts")
    def get_parts(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        if result.input_semantics != "separated_part_views" or result.part_analysis is None:
            return _error(409, "parts_analysis_unavailable", "La ejecución no contiene vistas de piezas separadas.")
        return _ok({
            "part_analysis": result.part_analysis.model_dump(mode="json"),
            "assembly_candidates": [item.model_dump(mode="json") for item in result.assembly_candidates],
            "selected_assembly_candidate_id": result.selected_assembly_candidate_id,
        })

    @app.get("/api/v1/runs/{run_id}/explanations")
    def get_explanations(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
            extraction = repository.get_extraction(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        return _ok(explain_result(extraction, result).model_dump(mode="json"))

    @app.get("/api/v1/runs/{run_id}/scene")
    def get_scene(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
            extraction = repository.get_extraction(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        return _ok(reconstruct_scene(extraction, result).model_dump(mode="json"))

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

    @app.post("/api/v1/runs/{run_id}/library")
    def save_to_library(run_id: str, request: LibrarySaveRequest):
        try:
            result = repository.get_result(run_id, request.result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        descriptor = build_descriptor(result)
        embedding = None
        if request.embedding_mode == "openai":
            if semantic_provider is None:
                return _error(503, "semantic_provider_unavailable", embedding_settings.unavailable_reason or "El proveedor semántico no está configurado.", True)
            model = semantic_provider.model
            dimensions = semantic_provider.dimensions
            text = semantic_text(descriptor)
            cache_key = embedding_cache_key(descriptor.descriptor_version, model, dimensions, text)
            try:
                repository.get_embedding(cache_key, model, dimensions, descriptor.descriptor_version)
                status = "cache"
            except KeyError:
                try:
                    generated = semantic_provider.embed(text)
                except EmbeddingProviderError as exc:
                    code = str(exc)
                    status_code = 409 if code == "embedding_space_incompatible" else 502
                    return _error(status_code, code, "El proveedor no devolvió un embedding utilizable.", True)
                repository.save_embedding(cache_key, generated.model, generated.dimensions, descriptor.descriptor_version, generated.vector)
                status = "generated"
            except (ValueError, EmbeddingProviderError) as exc:
                return _error(409, str(exc), "El caché pertenece a un espacio de embedding incompatible.")
            embedding = EmbeddingMetadata(model=model, dimensions=dimensions, descriptor_version=descriptor.descriptor_version, cache_key=cache_key, status=status)
        item = LibraryItem(id=f"library-{run_id}", run_id=run_id, result_revision=result.result_revision, label=request.label, descriptor=descriptor, descriptor_fingerprint=descriptor_fingerprint(descriptor), created_at=datetime.now(UTC).isoformat(), embedding=embedding)
        repository.save_library_item(item)
        repository.append_event(run_id, "library_item_saved", {"result_revision": result.result_revision, "embedding_mode": request.embedding_mode})
        return _ok(item.model_dump(mode="json"), 201)

    @app.get("/api/v1/library")
    def list_library():
        return _ok([item.model_dump(mode="json") for item in repository.get_library_items()])

    @app.post("/api/v1/runs/{run_id}/similarity")
    def similar(run_id: str, request: SimilarityRequest):
        try:
            result = repository.get_result(run_id, request.result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        candidates = [item for item in repository.get_library_items() if item.run_id != run_id]
        if request.mode == "semantic":
            try:
                query = repository.get_library_item(run_id)
                if query.result_revision != request.result_revision or query.embedding is None:
                    raise KeyError(run_id)
                query_vector = repository.get_embedding(query.embedding.cache_key, query.embedding.model, query.embedding.dimensions, query.embedding.descriptor_version)
                matches = []
                for item in candidates:
                    if item.embedding is None:
                        continue
                    candidate_vector = repository.get_embedding(item.embedding.cache_key, item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version)
                    matches.append(semantic_match(query, query_vector, item, candidate_vector))
            except KeyError:
                return _error(409, "semantic_embedding_missing", "La revisión no tiene un embedding semántico compatible.")
            except (ValueError, EmbeddingProviderError) as exc:
                return _error(409, str(exc), "Los embeddings pertenecen a espacios incompatibles o son inválidos.")
            if candidates and not matches:
                return _error(409, "embedding_space_incompatible", "No hay candidatos en el mismo espacio de embedding.")
        else:
            descriptor = build_descriptor(result)
            matches = [geometric_match(descriptor, item) for item in candidates]
        matches.sort(key=lambda item: (-item.score, item.library_item_id))
        return _ok([item.model_dump(mode="json") for item in matches[:request.limit]])

    @app.post("/api/v1/library/groups")
    def groups(request: GroupRequest):
        if request.mode == "semantic":
            items = repository.get_library_items()
            try:
                vectors = {
                    item.id: repository.get_embedding(item.embedding.cache_key, item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version)
                    for item in items if item.embedding is not None
                }
                values = semantic_groups(items, vectors, request.threshold)
            except KeyError:
                return _error(409, "semantic_embedding_missing", "La biblioteca no tiene todos los embeddings semánticos requeridos.")
            except (ValueError, EmbeddingProviderError) as exc:
                code = str(exc)
                return _error(409, code, "Los embeddings faltan, son inválidos o pertenecen a espacios incompatibles.")
        else:
            values = geometric_groups(repository.get_library_items(), request.threshold)
        return _ok([item.model_dump(mode="json") for item in values])

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
            extraction = repository.get_extraction(run_id)
            descriptor = build_descriptor(result)
            try:
                library_item = repository.get_library_item(run_id)
                if library_item.result_revision != result.result_revision:
                    library_item = None
            except KeyError:
                library_item = None
            bundle = {"schema_version": "0.2.0", "result_revision": result.result_revision, "result": result.model_dump(mode="json"), "scene": reconstruct_scene(extraction, result).model_dump(mode="json"), "explanations": explain_result(extraction, result).model_dump(mode="json"), "descriptor": descriptor.model_dump(mode="json"), "library_item": library_item.model_dump(mode="json") if library_item else None, "comparables": [item.model_dump(mode="json") for item in find_comparables(result)], "estimate": estimate_value, "events": list(repository.get_events(run_id))}
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
