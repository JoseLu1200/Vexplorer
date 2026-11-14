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
from backend.app.agente.runner import AgentLimits, run_agent, run_parts_agent, run_table_agent
from backend.app.agente.tools import parts_tool_schemas, table_tool_schemas, tool_schemas
from backend.app.contratos.modelos import EmbeddingMetadata, LibraryItem, ReviewRequest, RunRequest, TableCostScope, TableDrawingFormatLink, TableDrawingManifest, TableDrawingManifestSheet
from backend.app.estimacion.service import estimate_result
from backend.app.estimacion.table_costs import estimate_table_costs, get_table_cost_catalog
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs, evaluate_table_program
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.historico.service import find_comparables
from backend.app.salida.service import export_csv, export_json
from backend.app.salida.drawing_preview import render_drawing_preview
from backend.app.salida.table_cutlist import export_table_cutlist_csv
from backend.app.salida.technical_drawings import render_table_drawings
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.servicios.explanations import explain_result
from backend.app.servicios.table_explanations import explain_table_result
from backend.app.servicios.repository import DemoRepository
from backend.app.servicios.reconstruction import reconstruct_parts_scene, reconstruct_scene
from backend.app.servicios.table_reconstruction import derive_table_drawing_plan, reconstruct_table_scene
from backend.app.semantic.descriptor import build_descriptor, descriptor_fingerprint, semantic_text
from backend.app.semantic.embeddings import EmbeddingProviderError, OpenAIEmbeddingProvider, embedding_cache_key
from backend.app.similarity.service import geometric_groups, geometric_match, semantic_groups, semantic_match

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    descriptor_version: Literal["furniture-v1", "furniture-v2", "furniture-v3"] | None = None


class GroupRequest(RequestModel):
    mode: Literal["geometric", "semantic"]
    threshold: float = Field(default=0.8, ge=-1, le=1, allow_inf_nan=False)
    descriptor_version: Literal["furniture-v1", "furniture-v2", "furniture-v3"] | None = None


class TableCostRequest(RequestModel):
    result_revision: int = Field(gt=0)
    scope: TableCostScope = Field(default_factory=TableCostScope)


class TableDerivedRequest(RequestModel):
    result_revision: int = Field(gt=0)


def _ok(data, status_code: int = 200):
    return JSONResponse({"schema_version": "0.2.0", "data": data}, status_code=status_code)


def _error(status_code: int, code: str, message: str, retryable: bool = False):
    return JSONResponse({"schema_version": "0.2.0", "error": {"code": code, "message": message, "retryable": retryable}}, status_code=status_code)


def create_app(data_dir: Path | None = None, frontend_dir: Path | None = None, embedding_provider=None, agent_provider=None) -> FastAPI:
    root = data_dir or Path(".vexplorer-data")
    documents_dir = root / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    repository = DemoRepository(root / "vexplorer.sqlite3")
    settings = ProviderSettings.from_env()
    live_available = agent_provider is not None or settings.available
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
        all_tools = tool_schemas() + parts_tool_schemas() + table_tool_schemas(include_vision=settings.vision_enabled)
        return _ok({"provider": "openai_responses", "model": settings.model, "live_available": live_available, "unavailable_reason": None if live_available else settings.unavailable_reason, "recorded_replay_available": False, "modes": ["geometry_only"] + (["live"] if live_available else []), "modality": "structured_vector_evidence_with_opt_in_vision" if settings.vision_enabled else "structured_vector_evidence_without_vision", "vision": {"enabled": settings.vision_enabled, "default": False, "source": "ledger_rendered_png", "authority": "context_only_not_measurement_source", "limits": {"max_views": 3, "max_dimension_px": 1024, "max_png_bytes_per_view": 2_000_000}}, "limits": {"max_model_calls": 15, "max_tool_calls": 30, "timeout_s": 120, "max_output_tokens": settings.max_output_tokens}, "tools": [{"name": item["name"], "description": item["description"]} for item in all_tools], "semantic": {"available": semantic_provider is not None, "provider": "openai", "model": getattr(semantic_provider, "model", embedding_settings.model), "dimensions": getattr(semantic_provider, "dimensions", embedding_settings.dimensions), "unavailable_reason": None if semantic_provider is not None else embedding_settings.unavailable_reason, "offline_mode": "geometric"}})

    @app.get("/api/v1/table-cost-catalog")
    def table_cost_catalog():
        return _ok(get_table_cost_catalog().model_dump(mode="json"))

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
        input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"] = Query(
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
        if request.mode == "live" and not live_available:
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
                table_analysis = None
                table_programs = ()
                evaluated_table_program = None
            elif request.input_kind == "mounted_orthographic_views":
                part_analysis = None
                assembly_candidates = ()
                scenarios = ()
                table_analysis = analyze_mounted_table(extraction)
                available_programs = catalog_table_programs(table_analysis) if request.proposal_mode == "catalog_baseline" else ()
                table_programs = tuple(item for item in available_programs if item.table_template_id == request.table_template_id)
                if request.proposal_mode == "catalog_baseline" and len(table_programs) != 1:
                    return _error(422, "table_template_unavailable", "La plantilla de mesa solicitada no está disponible para este ledger.")
                evaluated_table_program = evaluate_table_program(table_analysis, table_programs[0]) if table_programs else None
            else:
                part_analysis = None
                assembly_candidates = ()
                scenarios = derive_decomposition_scenarios(extraction)
                table_analysis = None
                table_programs = ()
                evaluated_table_program = None
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        if request.input_kind == "mounted_views_legacy" and not scenarios:
            return _error(422, "unsupported_geometry", "Las vistas no respaldan escenarios rectangulares coherentes.")
        trace_events: tuple[dict, ...] = ()
        agent_selected_scenario_id = None
        agent_selected_assembly_candidate_id = None
        agent_selected_table_program_id = None
        if request.mode == "live":
            try:
                provider = agent_provider or OpenAIResponsesProvider(settings)
                if request.input_kind == "mounted_orthographic_views":
                    outcome = run_table_agent(extraction, table_analysis, provider, AgentLimits(), vision_enabled=settings.vision_enabled)
                    table_programs = (outcome.program,)
                    evaluated_table_program = evaluate_table_program(table_analysis, outcome.program)
                    agent_selected_table_program_id = outcome.program.id
                elif request.input_kind == "separated_part_views":
                    outcome = run_parts_agent(extraction, part_analysis, assembly_candidates, provider, AgentLimits())
                    assembly_candidates = tuple(sorted(
                        assembly_candidates,
                        key=lambda item: item.id != outcome.selected_assembly_candidate_id,
                    ))
                    agent_selected_assembly_candidate_id = outcome.selected_assembly_candidate_id
                else:
                    outcome = run_agent(extraction, scenarios, provider, AgentLimits())
                    scenarios = tuple(sorted(scenarios, key=lambda item: item.id != outcome.selected_scenario_id))
                    agent_selected_scenario_id = outcome.selected_scenario_id
            except Exception as exc:
                return _error(502, "live_provider_failed", f"La ejecución live falló sin fallback: {type(exc).__name__}.", True)
            trace_events = tuple({
                "tool_name": action.tool_name,
                "ok": action.ok,
                "evidence_ids": action.evidence_ids,
                "summary": action.summary,
                "selected_scenario_id": action.selected_scenario_id if request.input_kind == "mounted_views_legacy" else None,
                "selected_assembly_candidate_id": action.selected_scenario_id if request.input_kind == "separated_part_views" else None,
                "selected_table_program_id": agent_selected_table_program_id if request.input_kind == "mounted_orthographic_views" and action.tool_name == "proponer_descomposicion" else None,
                "artifact_sha256": action.artifact_sha256,
                "mark_count": action.mark_count,
                "view_id": action.view_id,
            } for action in outcome.actions)
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
            agent_selected_assembly_candidate_id,
            table_analysis,
            table_programs,
            agent_selected_table_program_id,
            evaluated_table_program,
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

    @app.get("/api/v1/runs/{run_id}/table")
    def get_table(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        if result.input_semantics != "mounted_orthographic_views" or result.table_analysis is None:
            return _error(409, "table_analysis_unavailable", "La ejecución no contiene vistas ortográficas de mesa.")
        return _ok({
            "result_revision": result.result_revision,
            "state": result.state,
            "table_analysis": result.table_analysis.model_dump(mode="json"),
            "table_programs": [item.model_dump(mode="json") for item in result.table_programs],
            "selected_table_program_id": result.selected_table_program_id,
            "evaluated_table_program": result.evaluated_table_program.model_dump(mode="json") if result.evaluated_table_program is not None else None,
        })

    @app.post("/api/v1/runs/{run_id}/table-drawings")
    def generate_table_drawings(run_id: str, request: TableDerivedRequest):
        try:
            result = repository.get_result(run_id, request.result_revision)
            extraction = repository.get_extraction(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        if result.input_semantics != "mounted_orthographic_views" or result.table_analysis is None or result.evaluated_table_program is None:
            return _error(409, "table_evaluation_unavailable", "La revisión no contiene una mesa evaluada.")
        plan = derive_table_drawing_plan(extraction, result.table_analysis, result.evaluated_table_program, result_revision=result.result_revision)
        exports = render_table_drawings(plan)
        by_sheet = {item.sheet_id: item for item in plan.sheets}
        links_by_sheet: dict[str, list[TableDrawingFormatLink]] = {item.sheet_id: [] for item in plan.sheets}
        for artifact in exports.artifacts:
            url = f"/api/v1/runs/{run_id}/table-drawings/{artifact.sheet_id}.{artifact.format}?result_revision={result.result_revision}&program_hash={plan.program_hash}"
            links_by_sheet[artifact.sheet_id].append(TableDrawingFormatLink(format=artifact.format, media_type=artifact.media_type, url=url))
        manifest = TableDrawingManifest(
            run_id=run_id, result_revision=result.result_revision, program_hash=plan.program_hash,
            sheets=tuple(TableDrawingManifestSheet(
                sheet_id=sheet.sheet_id, kind=sheet.kind, title=sheet.title, component_id=sheet.component_id,
                page=sheet.page, result_revision=result.result_revision, program_hash=plan.program_hash,
                status=sheet.status, warnings=sheet.warnings,
                formats=tuple(sorted(links_by_sheet[sheet.sheet_id], key=lambda item: item.format)),
            ) for sheet in sorted(by_sheet.values(), key=lambda item: item.page)),
        )
        repository.save_table_drawings(run_id, manifest, exports)
        repository.append_event(run_id, "table_drawings_committed", {"result_revision": result.result_revision, "program_hash": plan.program_hash, "sheet_count": len(manifest.sheets)})
        return _ok(manifest.model_dump(mode="json"), 201)

    @app.get("/api/v1/runs/{run_id}/table-drawings")
    def get_table_drawings(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            manifest = repository.get_table_drawing_manifest(run_id, result_revision)
        except KeyError:
            return _error(404, "table_drawings_not_found", "No existen planos persistidos para esa revisión.")
        return _ok(manifest.model_dump(mode="json"))

    @app.get("/api/v1/runs/{run_id}/table-drawings/{sheet_id}.{format}")
    def get_table_drawing_artifact(run_id: str, sheet_id: str, format: Literal["svg", "dxf"], result_revision: int = Query(..., gt=0), program_hash: str = Query(..., pattern=r"^[0-9a-f]{64}$")):
        try:
            content, media_type, filename = repository.get_table_drawing_artifact(run_id, result_revision, sheet_id, format, program_hash)
        except KeyError:
            return _error(404, "table_drawing_artifact_not_found", "Artefacto inexistente.")
        except ValueError as exc:
            return _error(409, str(exc), "El artefacto pertenece a otra revisión de programa.")
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/runs/{run_id}/explanations")
    def get_explanations(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
            extraction = repository.get_extraction(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        explanation = explain_table_result(result) if result.input_semantics == "mounted_orthographic_views" else explain_result(extraction, result)
        return _ok(explanation.model_dump(mode="json"))

    @app.get("/api/v1/runs/{run_id}/scene")
    def get_scene(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            result = repository.get_result(run_id, result_revision)
            extraction = repository.get_extraction(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        if result.input_semantics == "mounted_orthographic_views" and result.table_analysis is not None:
            scene = reconstruct_table_scene(extraction, result.table_analysis, result)
        elif result.input_semantics == "separated_part_views" and result.part_analysis is not None:
            scene = reconstruct_parts_scene(extraction, result.part_analysis, result)
        else:
            scene = reconstruct_scene(extraction, result)
        return _ok(scene.model_dump(mode="json"))

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
            repository.append_event(run_id, "human_review_committed", {"result_revision": result.result_revision, "reviewer_name": request.reviewer_name, "selected_scenario_id": request.scenario_id, "selected_assembly_candidate_id": request.assembly_candidate_id, "selected_table_program_id": request.table_program_id})
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
    def list_library(descriptor_version: Literal["furniture-v1", "furniture-v2", "furniture-v3"] | None = None):
        items = repository.get_library_items()
        if descriptor_version is None:
            return _ok([item.model_dump(mode="json") for item in items])
        selected = [item for item in items if item.descriptor.descriptor_version == descriptor_version]
        return _ok({"items": [item.model_dump(mode="json") for item in selected], "descriptor_version": descriptor_version, "excluded_count": len(items) - len(selected)})

    @app.post("/api/v1/runs/{run_id}/similarity")
    def similar(run_id: str, request: SimilarityRequest):
        try:
            result = repository.get_result(run_id, request.result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        all_candidates = [item for item in repository.get_library_items() if item.run_id != run_id]
        descriptor_version = request.descriptor_version or build_descriptor(result).descriptor_version
        candidates = [item for item in all_candidates if item.descriptor.descriptor_version == descriptor_version]
        excluded_count = len(all_candidates) - len(candidates)
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
        payload = [item.model_dump(mode="json") for item in matches[:request.limit]]
        if request.descriptor_version is not None:
            return _ok({"matches": payload, "descriptor_version": descriptor_version, "excluded_count": excluded_count})
        return _ok(payload)

    @app.post("/api/v1/library/groups")
    def groups(request: GroupRequest):
        all_items = repository.get_library_items()
        items = tuple(item for item in all_items if request.descriptor_version is None or item.descriptor.descriptor_version == request.descriptor_version)
        excluded_count = len(all_items) - len(items)
        if request.mode == "semantic":
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
            try:
                values = geometric_groups(items, request.threshold)
            except ValueError as exc:
                return _error(409, str(exc), "Los descriptores pertenecen a espacios incompatibles.")
        payload = [item.model_dump(mode="json") for item in values]
        if request.descriptor_version is not None:
            return _ok({"groups": payload, "descriptor_version": request.descriptor_version, "excluded_count": excluded_count})
        return _ok(payload)

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

    @app.post("/api/v1/runs/{run_id}/table-costs")
    def calculate_table_costs(run_id: str, request: TableCostRequest):
        try:
            result = repository.get_result(run_id, request.result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        if result.input_semantics != "mounted_orthographic_views" or result.evaluated_table_program is None:
            return _error(409, "table_evaluation_unavailable", "La revisión no contiene una mesa evaluada.")
        if result.state != "completed" or result.evaluated_table_program.state != "completed":
            return _error(409, "table_revision_not_accepted", "La mesa debe estar revisada antes de calcular costes.")
        try:
            value = estimate_table_costs(result.evaluated_table_program, result_revision=result.result_revision, scope=request.scope)
            repository.save_table_cost_estimate(run_id, value)
            repository.append_event(run_id, "table_cost_committed", {"result_revision": value.result_revision, "program_hash": value.program_hash, "total_state": value.total_state})
        except ValueError as exc:
            return _error(422, str(exc), "No se pudo calcular el coste de mesa.")
        return _ok(value.model_dump(mode="json"), 201)

    @app.get("/api/v1/runs/{run_id}/table-costs")
    def get_table_costs(run_id: str, result_revision: int = Query(..., gt=0)):
        try:
            value = repository.get_table_cost_estimate(run_id, result_revision)
        except KeyError:
            return _error(404, "table_cost_not_found", "No existe coste persistido para esa revisión.")
        return _ok(value.model_dump(mode="json"))

    @app.get("/api/v1/runs/{run_id}/exports")
    def exports(run_id: str, format: Literal["json", "csv", "table_cutlist"] = Query(...)):
        try:
            result = repository.get_result(run_id)
        except KeyError:
            return _error(404, "result_not_found", "Resultado inexistente.")
        if format == "json":
            is_table = result.input_semantics == "mounted_orthographic_views"
            try:
                estimate_value = (repository.get_table_cost_estimate(run_id, result.result_revision) if is_table else repository.get_estimate(run_id, result.result_revision)).model_dump(mode="json")
            except KeyError:
                estimate_value = None
            extraction = repository.get_extraction(run_id)
            try:
                descriptor = build_descriptor(result)
            except ValueError:
                descriptor = None
            try:
                library_item = repository.get_library_item(run_id)
                if library_item.result_revision != result.result_revision:
                    library_item = None
            except KeyError:
                library_item = None
            if is_table and result.table_analysis is not None:
                scene = reconstruct_table_scene(extraction, result.table_analysis, result)
                explanations = explain_table_result(result) if result.evaluated_table_program is not None else None
                comparables_value = []
                try:
                    drawing_manifest = repository.get_table_drawing_manifest(run_id, result.result_revision).model_dump(mode="json")
                except KeyError:
                    drawing_manifest = None
            elif result.input_semantics == "separated_part_views" and result.part_analysis is not None:
                scene = reconstruct_parts_scene(extraction, result.part_analysis, result)
                explanations = explain_result(extraction, result)
                comparables_value = [item.model_dump(mode="json") for item in find_comparables(result)]
                drawing_manifest = None
            else:
                scene = reconstruct_scene(extraction, result)
                explanations = explain_result(extraction, result)
                comparables_value = [item.model_dump(mode="json") for item in find_comparables(result)]
                drawing_manifest = None
            bundle = {"schema_version": "0.5.0" if is_table else "0.2.0", "result_revision": result.result_revision, "result": result.model_dump(mode="json"), "scene": scene.model_dump(mode="json"), "explanations": explanations.model_dump(mode="json") if explanations is not None else None, "descriptor": descriptor.model_dump(mode="json") if descriptor is not None else None, "library_item": library_item.model_dump(mode="json") if library_item else None, "comparables": comparables_value, "estimate": estimate_value, "table_drawings": drawing_manifest, "events": list(repository.get_events(run_id))}
            payload, media = json.dumps(bundle, ensure_ascii=False, indent=2), "application/json"
        elif format == "csv":
            payload, media = export_csv(result), "text/csv; charset=utf-8"
        else:
            if result.input_semantics != "mounted_orthographic_views" or result.evaluated_table_program is None:
                return _error(409, "table_evaluation_unavailable", "La revisión no contiene una mesa evaluada.")
            try:
                payload = export_table_cutlist_csv(result.evaluated_table_program, result_revision=result.result_revision)
            except ValueError as exc:
                return _error(409, str(exc), "La lista de corte requiere una revisión de mesa aceptada.")
            media = "text/csv; charset=utf-8"
        extension = "csv" if format == "table_cutlist" else format
        return Response(payload, media_type=media, headers={"Content-Disposition": f'attachment; filename="{run_id}-r{result.result_revision}.{extension}"'})

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
