from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import time
from dataclasses import asdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Header, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.agente.config import EmbeddingSettings, ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.agente.prompts import SYSTEM_PROMPT, VISION_SYSTEM_PROMPT
from backend.app.agente.replay import (
    DEFAULT_RECORDING_MAX_BYTES,
    DEFAULT_RECORDING_MAX_COUNT,
    MAX_RECORDED_TRANSCRIPT_BYTES,
    RecordingProvider,
    ReplayProvider,
    recording_fingerprint,
)
from backend.app.agente.runner import AgentLimits, run_agent, run_parts_agent, run_table_agent
from backend.app.agente.tools import parts_tool_schemas, table_tool_schemas, tool_schemas
from backend.app.contratos.modelos import DrawingExtraction, EmbeddingMetadata, LibraryItem, ReviewRequest, RunRequest, TableCostScope, TableDrawingFormatLink, TableDrawingManifest, TableDrawingManifestSheet
from backend.app.estimacion.service import estimate_result
from backend.app.estimacion.table_costs import estimate_table_costs, get_table_cost_catalog
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs, evaluate_table_program
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.ingesta.dxf_reader import parse_dxf
from backend.app.historico.service import find_comparables
from backend.app.historico.real_service import HistoricalStore
from backend.app.historico.models import ProvisionalDimension, ProvisionalQuantity, ProvisionalScenarioRow, ProvisionalScenarioSnapshot, ProvisionalText
from backend.app.api.history import create_history_router
from backend.app.general_furniture.live import GENERAL_FURNITURE_SYSTEM_PROMPT, GeneralLiveError, GeneralVisualPage, run_general_furniture_agent
from backend.app.general_furniture.autonomous import AutoReviewLimits, GENERAL_AUTO_REVIEW_PROMPT, GeneralAutonomousError, run_general_autonomous
from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.router import GeneralFurnitureContext, create_general_furniture_router
from backend.app.general_furniture.visual_evidence import render_visual_evidence
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
from backend.app.operacion.auth import PasswordFile, decode_basic_authorization
from backend.app.operacion.jobs import BoundedJobExecutor

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DOCUMENT_ID_PATTERN = re.compile(r"doc-[0-9a-f]{32}\Z")
MAX_JSON_BODY_BYTES = 5 * 1024 * 1024


class NormalizedDxfUnavailable(FileNotFoundError):
    pass


class BoundedJsonBodyMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int = MAX_JSON_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = {key.lower(): value for key, value in scope.get("headers", ())}
        bounded = (
            scope.get("type") == "http"
            and scope.get("method") in {"POST", "PUT", "PATCH"}
            and headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() == b"application/json"
        )
        if not bounded:
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        consumed = 0
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                continue
            chunk = message.get("body", b"")
            consumed += len(chunk)
            if consumed > self.max_bytes:
                if scope.get("path") == "/api/v1/history/import/json":
                    response = JSONResponse(
                        {"schema_version": "1.0.0", "data": None, "error": {"code": "history_import_too_large", "message": "El cuerpo JSON supera 5 MiB.", "retryable": False}},
                        status_code=413,
                    )
                else:
                    response = _error(413, "json_body_too_large", "El cuerpo JSON supera 5 MiB.")
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay_receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay_receive, send)


def _document_media_type(format_name: str, supplied: str | None = None) -> str:
    if format_name == "pdf":
        return "application/pdf"
    if format_name == "dxf":
        return "application/dxf"
    if format_name == "dwg":
        return supplied if supplied in {"application/acad", "application/x-acad"} else "application/octet-stream"
    return "application/octet-stream"


def _json_safe(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


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


class PdfPageSelectionRequest(RequestModel):
    mm_per_pdf_point: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    confirmed_by: str | None = Field(default=None, min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


def _ok(data, status_code: int = 200):
    return JSONResponse({"schema_version": "0.2.0", "data": data}, status_code=status_code)


def _error(status_code: int, code: str, message: str, retryable: bool = False):
    return JSONResponse({"schema_version": "0.2.0", "error": {"code": code, "message": message, "retryable": retryable}}, status_code=status_code)


def create_app(data_dir: Path | None = None, frontend_dir: Path | None = None, embedding_provider=None, agent_provider=None, general_reviewer_provider=None) -> FastAPI:
    environment = os.getenv("VEXPLORER_ENV", "local")
    if environment not in {"local", "production"}:
        raise ValueError("invalid_vexplorer_environment")
    root_path = os.getenv("VEXPLORER_ROOT_PATH", "")
    if root_path and re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)+", root_path) is None:
        raise ValueError("invalid_root_path")
    configured_data_dir = os.getenv("VEXPLORER_DATA_DIR")
    if environment == "production" and data_dir is None and not configured_data_dir:
        raise ValueError("production_data_dir_required")
    root = data_dir or Path(configured_data_dir or ".vexplorer-data")
    password_file = None
    allowed_origins: frozenset[str] = frozenset()
    if environment == "production":
        users_path = os.getenv("VEXPLORER_USERS_FILE")
        if not users_path:
            raise ValueError("production_users_file_required")
        password_file = PasswordFile.load(Path(users_path))
        origins = tuple(
            item.strip().rstrip("/")
            for item in os.getenv("VEXPLORER_ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        )
        if not origins or any(not item.startswith("https://") for item in origins):
            raise ValueError("production_allowed_origins_required")
        allowed_origins = frozenset(origins)
    try:
        job_max_pending = int(os.getenv("VEXPLORER_JOB_MAX_PENDING", "8"))
        max_storage_bytes = int(os.getenv("VEXPLORER_MAX_STORAGE_BYTES", str(1024 * 1024 * 1024)))
        recording_max_count = int(os.getenv("VEXPLORER_RECORDING_MAX_COUNT", str(DEFAULT_RECORDING_MAX_COUNT)))
        recording_max_bytes = int(os.getenv("VEXPLORER_RECORDING_MAX_BYTES", str(DEFAULT_RECORDING_MAX_BYTES)))
        general_job_timeout_s = float(os.getenv("VEXPLORER_GENERAL_JOB_TIMEOUT_SECONDS", "300"))
        general_review_max_calls = int(os.getenv("VEXPLORER_GENERAL_REVIEW_MAX_CALLS", "5"))
        general_review_max_repairs = int(os.getenv("VEXPLORER_GENERAL_REVIEW_MAX_REPAIRS", "2"))
        general_review_max_output_tokens = int(os.getenv("VEXPLORER_GENERAL_REVIEW_MAX_OUTPUT_TOKENS", "16384"))
    except ValueError as exc:
        raise ValueError("invalid_numeric_production_limit") from exc
    if max_storage_bytes < MAX_UPLOAD_BYTES:
        raise ValueError("max_storage_below_upload_limit")
    if recording_max_count <= 0 or recording_max_bytes < MAX_RECORDED_TRANSCRIPT_BYTES:
        raise ValueError("invalid_recording_storage_policy")
    if not 1 <= general_review_max_calls <= 5 or not 0 <= general_review_max_repairs <= 2 or not 256 <= general_review_max_output_tokens <= 16384 or not 30 <= general_job_timeout_s <= 600:
        raise ValueError("invalid_general_review_policy")
    documents_dir = root / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = root / ".document-staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    upload_lock = Lock()
    repository = DemoRepository(root / "vexplorer.sqlite3")
    repository.interrupt_unfinished_jobs()
    repository.release_stale_agent_recording_reservations()
    job_executor = BoundedJobExecutor(job_max_pending)
    if environment == "production" and not os.getenv("VEXPLORER_COST_CATALOG"):
        raise ValueError("production_cost_catalog_required")
    table_cost_catalog_value = get_table_cost_catalog()
    settings = ProviderSettings.from_env()
    live_available = agent_provider is not None or settings.available
    embedding_settings = EmbeddingSettings.from_env()
    semantic_provider = embedding_provider
    if semantic_provider is None and embedding_settings.available:
        semantic_provider = OpenAIEmbeddingProvider(api_key=embedding_settings.api_key or "", model=embedding_settings.model, dimensions=embedding_settings.dimensions, base_url=embedding_settings.base_url)
    history_db = Path(os.getenv("VEXPLORER_HISTORY_DB", str(root / "history.sqlite3")))
    historical_store = HistoricalStore(history_db, embedding_provider=semantic_provider)
    general_furniture_db = root / "general_furniture.sqlite3"
    general_furniture_repository = GeneralFurnitureRepository(general_furniture_db)
    general_agent_provider = agent_provider
    if general_agent_provider is None and settings.available:
        general_agent_provider = OpenAIResponsesProvider(settings, instructions=GENERAL_FURNITURE_SYSTEM_PROMPT)
    review_model = os.getenv("VEXPLORER_GENERAL_REVIEW_MODEL") or settings.model
    review_settings = ProviderSettings(
        api_key=settings.api_key, model=review_model, base_url=settings.base_url,
        max_output_tokens=general_review_max_output_tokens, vision_enabled=True,
    )
    general_review_provider = general_reviewer_provider
    if general_review_provider is None and agent_provider is not None:
        general_review_provider = agent_provider
    if general_review_provider is None and review_settings.available:
        general_review_provider = OpenAIResponsesProvider(review_settings, instructions=GENERAL_AUTO_REVIEW_PROMPT)
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        job_executor.shutdown()

    app = FastAPI(title="Vexplorer", version="0.2.0", lifespan=lifespan)
    app.root_path = root_path
    app.state.repository = repository
    app.state.job_executor = job_executor
    app.state.historical_store = historical_store
    app.state.history_db = history_db
    app.state.general_furniture_repository = general_furniture_repository
    app.state.general_furniture_db = general_furniture_db
    app.state.general_review_model = review_model
    authentication_failures: dict[str, list[float]] = {}
    app.add_middleware(BoundedJsonBodyMiddleware)

    def document_manifest_path(document_id: str) -> Path:
        return documents_dir / f"{document_id}.manifest.json"

    def load_document_manifest(document_id: str) -> dict | None:
        if DOCUMENT_ID_PATTERN.fullmatch(document_id) is None:
            return None
        path = document_manifest_path(document_id)
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                return None
            return value if isinstance(value, dict) else None
        legacy = documents_dir / f"{document_id}.dxf"
        if not legacy.is_file():
            return None
        digest = hashlib.sha256(legacy.read_bytes()).hexdigest()
        return {
            "document_id": document_id,
            "original_filename": legacy.name,
            "size_bytes": legacy.stat().st_size,
            "sha256": digest,
            "source_kind": "uploaded",
            "source": {"filename": legacy.name, "media_type": "application/dxf", "format": "dxf", "size_bytes": legacy.stat().st_size, "sha256": digest, "unit": "unknown"},
            "ingestion": {"state": "ready", "capabilities": {"geometry_analysis": True}, "warnings": [], "errors": []},
            "artifacts": {
                "original": {"url": f"/api/v1/documents/{document_id}/original", "media_type": "application/dxf"},
                "normalized_dxf": {"url": f"/api/v1/documents/{document_id}/normalized.dxf", "media_type": "application/dxf", "sha256": digest},
                "preview": {"url": f"/api/v1/documents/{document_id}/preview.svg", "media_type": "image/svg+xml"},
            },
            "audit": {"uploaded_by": None},
        }

    def normalized_document_path(document_id: str) -> Path | None:
        manifest = load_document_manifest(document_id)
        if manifest is None or manifest.get("artifacts", {}).get("normalized_dxf") is None:
            return None
        path = documents_dir / f"{document_id}.dxf"
        return path if path.is_file() else None

    def used_document_storage_bytes() -> int:
        return sum(
            item.stat().st_size
            for item in documents_dir.rglob("*")
            if item.is_file() and not item.name.endswith(".manifest.json")
        )

    def general_visual_pages(document_id: str | None, extraction: DrawingExtraction) -> tuple[GeneralVisualPage, ...]:
        if document_id is None:
            return ()
        manifest = load_document_manifest(document_id)
        if manifest is None:
            return ()
        source = manifest.get("source", {})
        source_refs = (f"document:{document_id}",)
        if source.get("format") == "pdf":
            page_number = source.get("page_number") or manifest.get("ingestion", {}).get("selected_page")
            parent_id = source.get("parent_document_id", document_id)
            if not isinstance(page_number, int) or DOCUMENT_ID_PATTERN.fullmatch(str(parent_id)) is None:
                return ()
            source_path = documents_dir / f"{parent_id}.source.pdf"
            artifacts = render_visual_evidence(
                source_path, selected_pdf_page=page_number, source_document_refs=source_refs,
                max_artifacts=4, max_total_png_bytes=16 * 1024 * 1024,
            )
        else:
            source_path = normalized_document_path(document_id)
            if source_path is None:
                return ()
            artifacts = render_visual_evidence(
                source_path, extraction=extraction, source_document_refs=source_refs,
                max_artifacts=4, max_total_png_bytes=16 * 1024 * 1024,
            )
        return tuple(GeneralVisualPage(
            reference=item.reference, media_type=item.media_type,
            sha256=item.image_sha256, content=item.content,
            source_view_ids=item.source_view_ids,
            source_contour_ids=item.source_contour_ids,
            source_document_refs=item.source_document_refs,
            crop_bounds_source=item.crop_bounds_source,
            marks=item.marks,
            warnings=item.warnings,
        ) for item in artifacts)

    def general_furniture_context(run_id: str) -> GeneralFurnitureContext:
        run = repository.get_run(run_id)
        if run.input_kind != "general_furniture":
            raise KeyError(run_id)
        extraction = repository.get_extraction(run_id)
        return GeneralFurnitureContext(
            run_id=run_id, extraction=extraction, ledger_revision=run.candidate_revision,
            visual_pages=general_visual_pages(run.document_id, extraction),
        )

    def execute_general_live(context: GeneralFurnitureContext):
        if general_agent_provider is None:
            raise RuntimeError("general_live_unavailable")
        return run_general_furniture_agent(
            context.extraction, ledger_revision=context.ledger_revision,
            provider=general_agent_provider, visual_pages=context.visual_pages,
        )

    def execute_general_autonomous(
        context: GeneralFurnitureContext, proposal_outcome, *, timeout_s: float,
        proposal_revision: int = 1, previous_review=None, checkpoint_sink=None,
    ):
        if general_review_provider is None:
            raise RuntimeError("general_auto_review_unavailable")
        proposer_model = next(
            (item.get("provider_model") for item in reversed(proposal_outcome.trace) if item.get("provider_model")),
            settings.model or f"injected:{type(general_agent_provider).__name__}",
        )
        return run_general_autonomous(
            context, proposal_outcome, reviewer_provider=general_review_provider,
            proposer_model=proposer_model,
            limits=AutoReviewLimits(
                max_model_calls=general_review_max_calls,
                max_tool_calls=general_review_max_calls,
                max_validation_repairs=general_review_max_repairs,
                max_semantic_repairs=1,
                timeout_s=timeout_s,
            ),
            proposal_revision=proposal_revision,
            previous_review=previous_review,
            checkpoint_sink=checkpoint_sink,
        )

    def record_general_live_events(run_id: str, proposal_revision: int, outcome) -> None:
        for item in outcome.trace:
            repository.append_event(run_id, "general_tool_completed", {
                "tool_name": item.get("tool"), "ok": bool(item.get("ok")),
                "summary": item.get("summary"), "proposal_origin": outcome.proposal.proposal_origin,
                "provider_response_id": item.get("provider_response_id"),
                "provider_model": item.get("provider_model"),
                "provider_call_id": item.get("provider_call_id"),
                "provider_duration_ms": item.get("provider_duration_ms"),
                "provider_input_tokens": item.get("provider_input_tokens"),
                "provider_output_tokens": item.get("provider_output_tokens"),
                "provider_total_tokens": item.get("provider_total_tokens"),
            })
        repository.append_event(run_id, "general_proposal_committed", {
            "proposal_id": outcome.proposal.id, "proposal_revision": proposal_revision,
            "proposal_origin": outcome.proposal.proposal_origin,
            "provider_model": settings.model or f"injected:{type(general_agent_provider).__name__}",
            "model_calls": outcome.model_calls, "tool_calls": outcome.tool_calls,
        })

    def record_general_auto_review_events(run_id: str, outcome) -> None:
        provenance = outcome.review.machine_provenance
        construction = getattr(outcome.derived, "construction", None)
        construction_validation = outcome.review.construction_validation
        for item in outcome.trace:
            event_payload = {
                "tool_name": item.get("tool"), "ok": bool(item.get("ok")),
                "summary": item.get("summary"), "reviewer_kind": "machine",
                "phase": item.get("phase"), "status": item.get("status"),
                "provider_response_id": item.get("provider_response_id"),
                "provider_model": item.get("provider_model"),
                "provider_call_id": item.get("provider_call_id"),
                "provider_input_tokens": item.get("provider_input_tokens"),
                "provider_output_tokens": item.get("provider_output_tokens"),
                "provider_total_tokens": item.get("provider_total_tokens"),
            }
            repository.append_event(run_id, "general_auto_review_tool_completed", event_payload)
            if item.get("phase") in {"general_auto_critique", "general_auto_semantic_repair", "general_auto_review"}:
                repository.append_event(run_id, item["phase"], event_payload)
        event_type = "general_auto_review_abstained" if outcome.status == "abstained" else "general_auto_review_completed"
        repository.append_event(run_id, event_type, {
            "proposal_revision": outcome.review.proposal_revision,
            "review_revision": outcome.review.review_revision,
            "status": outcome.status, "reviewer_kind": "machine",
            "provider_model": provenance.model if provenance else None,
            "review_relation": provenance.review_relation if provenance else None,
            "model_calls": outcome.model_calls, "tool_calls": outcome.tool_calls,
            "semantic_repairs": outcome.semantic_repairs,
            "cost_tracking": "token_usage_only",
            "construction_scenario_id": outcome.review.construction_scenario_id,
            "construction_validation_status": (
                construction_validation.status if construction_validation else None
            ),
            "construction_basis_revision": (
                construction.basis_revision if construction else None
            ),
            "construction_piece_count": (
                len(construction.pieces) if construction else 0
            ),
        })

    def record_general_auto_review_failure(run_id: str, exc: GeneralAutonomousError) -> None:
        for item in exc.trace:
            repository.append_event(run_id, "general_auto_review_tool_completed", {
                "tool_name": item.get("tool"), "ok": bool(item.get("ok")),
                "summary": item.get("summary"), "phase": item.get("phase"),
                "provider_response_id": item.get("provider_response_id"),
                "provider_model": item.get("provider_model"),
                "provider_call_id": item.get("provider_call_id"),
                "provider_input_tokens": item.get("provider_input_tokens"),
                "provider_output_tokens": item.get("provider_output_tokens"),
                "provider_total_tokens": item.get("provider_total_tokens"),
                "reviewer_kind": "machine",
            })
        repository.append_event(run_id, "general_auto_review_failed", {
            "code": exc.code, "reviewer_kind": "machine",
            "model_calls": exc.model_calls, "tool_calls": exc.tool_calls,
        })

    def persist_general_auto_checkpoint(run_id: str, checkpoint) -> None:
        event = checkpoint.trace_event
        repository.append_event(run_id, f"general_auto_{checkpoint.phase}_checkpoint", {
            "proposal_revision": checkpoint.proposal_revision,
            "tool_name": event.get("tool"), "ok": bool(event.get("ok")),
            "summary": event.get("summary"), "phase": event.get("phase"),
            "provider_response_id": event.get("provider_response_id"),
            "provider_model": event.get("provider_model"),
            "provider_call_id": event.get("provider_call_id"),
            "status": event.get("status"), "actor_kind": "machine",
        })
        if checkpoint.phase == "semantic_repair":
            saved_revision = general_furniture_repository.save_proposal(
                run_id, checkpoint.proposal_outcome.proposal, checkpoint.proposal_outcome.draft,
                base_proposal_revision=checkpoint.proposal_revision - 1,
            )
            if saved_revision != checkpoint.proposal_revision:
                raise ValueError("general_auto_review_revision_mismatch")
            repository.append_event(run_id, "general_auto_semantic_repair_committed", {
                "proposal_id": checkpoint.proposal_outcome.proposal.id,
                "proposal_revision": saved_revision,
                "proposal_origin": checkpoint.proposal_outcome.proposal.proposal_origin,
                "actor_kind": "machine",
            })

    def run_general_live(context: GeneralFurnitureContext):
        return execute_general_live(context)

    def run_general_auto_review(context, proposal_outcome, *, proposal_revision, previous_review):
        return execute_general_autonomous(
            context, proposal_outcome, timeout_s=general_job_timeout_s,
            proposal_revision=proposal_revision, previous_review=previous_review,
        )

    def load_provisional_scenario_snapshot(run_id: str, proposal_revision: int, review_revision: int) -> ProvisionalScenarioSnapshot:
        record = general_furniture_repository.get(run_id, proposal_revision=proposal_revision, review_revision=review_revision)
        package = general_furniture_repository.get_derived(run_id, proposal_revision=proposal_revision, review_revision=review_revision)
        if record is None or record.review is None or package is None:
            raise KeyError(run_id)
        review = record.review
        if (record.proposal_revision, record.review_revision, package.proposal_revision, package.review_revision) != (proposal_revision, review_revision, proposal_revision, review_revision):
            raise ValueError("general_scenario_snapshot_revision_conflict")
        if review.reviewer_kind != "machine" or review.auto_review_status is None:
            raise ValueError("general_scenario_machine_review_required")
        checks = {item.id: item for item in review.machine_checks}
        field_reviews = {item.target_ref: item for item in review.machine_field_reviews}
        bom_rows = {item.component_id: item for item in package.bom_rows}
        by_component: dict[str, list] = {}
        for occurrence in review.scenario_occurrences:
            by_component.setdefault(occurrence.component_id, []).append(occurrence)

        def metadata(component_id: str, name: str):
            item = field_reviews.get(f"component:{component_id}.{name}")
            return (item.status, item.check_ids) if item is not None else ("abstained", ())

        rows = []
        for component in review.components:
            occurrences = by_component.get(component.id, [])
            if not occurrences or component.quantity.state != "hypothesis":
                continue
            bom = bom_rows.get(component.id)
            occurrence_ids = tuple(item.id for item in occurrences)
            if bom is None or bom.occurrence_status != "provisional" or set(bom.scenario_occurrence_ids) != set(occurrence_ids):
                raise ValueError("general_scenario_snapshot_derived_mismatch")

            def dimension(name: str) -> ProvisionalDimension:
                value = getattr(component, name)
                status, check_ids = metadata(component.id, name)
                return ProvisionalDimension(value_mm=value.value_mm, state=value.state, review_status=status, check_ids=check_ids, dependency_refs=value.dependency_refs, evidence_ids=value.evidence_ids)

            def text_value(name: str) -> ProvisionalText:
                value = getattr(component, name)
                status, check_ids = metadata(component.id, name)
                return ProvisionalText(value=value.value, state=value.state, review_status=status, check_ids=check_ids, dependency_refs=value.dependency_refs, evidence_ids=value.evidence_ids)

            quantity_status, field_check_ids = metadata(component.id, "quantity")
            occurrence_check_ids = tuple(dict.fromkeys(check_id for item in occurrences for check_id in item.check_ids))
            check_ids = tuple(dict.fromkeys((*field_check_ids, *occurrence_check_ids)))
            premise_refs = tuple(dict.fromkeys(ref for item in occurrences for ref in item.premise_refs))
            occurrence_sources = tuple(dict.fromkeys(ref for item in occurrences for ref in item.source_refs))
            source_refs = tuple(dict.fromkeys((
                *occurrence_sources,
                *(f"view:{value}" for value in component.source_view_ids),
                *(f"observation:{value}" for value in component.source_observation_ids),
                *(f"contour:{value}" for value in component.source_contour_ids),
                *(f"evidence:{value}" for value in component.source_evidence_ids),
                *(f"dimension:{value}" for value in component.source_dimension_ids),
                *component.source_document_refs,
            )))
            rows.append(ProvisionalScenarioRow(
                component_id=component.id, occurrence_status="provisional", scenario_occurrence_ids=occurrence_ids,
                quantity=ProvisionalQuantity(value=component.quantity.value, state=component.quantity.state, review_status=quantity_status, check_ids=check_ids, check_kinds=tuple(dict.fromkeys(checks[item].kind for item in check_ids if item in checks)), premise_refs=premise_refs, source_refs=occurrence_sources),
                length=dimension("length"), width=dimension("width"), thickness=dimension("thickness"),
                material=text_value("material"), finish=text_value("finish"), source_refs=source_refs,
            ))
        return ProvisionalScenarioSnapshot(run_id=run_id, proposal_revision=proposal_revision, review_revision=review_revision, auto_review_status=review.auto_review_status, rows=tuple(rows))

    @app.middleware("http")
    async def private_access(request: Request, call_next):
        request.state.actor = None
        if environment == "production" and request.url.path not in {"/api/v1/health", "/health"}:
            client_key = request.client.host if request.client is not None else "unknown"
            now = time.monotonic()
            recent = [item for item in authentication_failures.get(client_key, ()) if now - item < 60]
            authentication_failures[client_key] = recent
            if len(recent) >= 10:
                return _error(429, "authentication_rate_limited", "Demasiados intentos de autenticación.", True)
            credentials = decode_basic_authorization(request.headers.get("Authorization"))
            actor = await run_in_threadpool(password_file.authenticate, *credentials) if credentials is not None and password_file is not None else None
            if actor is None:
                recent.append(now)
                response = _error(401, "authentication_required", "Se requieren credenciales individuales.")
                response.headers["WWW-Authenticate"] = 'Basic realm="Vexplorer", charset="UTF-8"'
                return response
            authentication_failures.pop(client_key, None)
            request.state.actor = actor
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                origin = request.headers.get("Origin")
                if origin is not None and origin.rstrip("/") not in allowed_origins:
                    return _error(403, "origin_not_allowed", "Origen no autorizado.")
        return await call_next(request)

    @app.get("/health")
    @app.get("/api/v1/health")
    def health():
        return _ok({"status": "ok"})

    @app.get("/api/v1/session")
    def session(request: Request):
        actor = request.state.actor
        return _ok({
            "authenticated": actor is not None,
            "username": actor,
            "environment": environment,
        })

    @app.get("/api/v1/config")
    def config():
        all_tools = tool_schemas() + parts_tool_schemas() + table_tool_schemas(include_vision=settings.vision_enabled)
        replay_available = repository.has_agent_recordings()
        recording_capacity = repository.agent_recording_capacity_available(
            max_count=recording_max_count,
            max_bytes=recording_max_bytes,
            reserved_bytes=MAX_RECORDED_TRANSCRIPT_BYTES,
        )
        effective_live_available = live_available and recording_capacity
        unavailable_reason = (
            None if effective_live_available
            else settings.unavailable_reason if not live_available
            else "recording_storage_exhausted:maintenance_or_increase_quota_required"
        )
        semantic_capability = {"available": semantic_provider is not None, "provider": "openai", "model": getattr(semantic_provider, "model", embedding_settings.model), "dimensions": getattr(semantic_provider, "dimensions", embedding_settings.dimensions), "unavailable_reason": None if semantic_provider is not None else embedding_settings.unavailable_reason, "offline_mode": "geometric"}
        capabilities = {
            "live_available": effective_live_available,
            "recorded_replay_available": replay_available,
            "replay_available": replay_available,
            "semantic": semantic_capability,
            "documents": {"formats": ["dxf", "dwg", "pdf"], "preserves_original": True, "normalized_dxf_formats": ["dxf", "dwg"], "pdf": {"normalization": "per_vector_page", "measurement": "requires_confirmed_scale", "raster_manual_review": True}},
            "general_furniture": {
                "available": True, "live_available": general_agent_provider is not None,
                "visual_pdf_pages": True,
                "autonomous_review": {
                    "available": general_review_provider is not None,
                    "default_for_model_generated_live": True,
                    "reviewer_model": review_model or (f"injected:{type(general_review_provider).__name__}" if general_review_provider is not None else None),
                    "human_required": False, "cost_tracking": "token_usage_only",
                    "max_visual_artifacts": 4, "max_png_bytes_per_artifact": 4 * 1024 * 1024,
                    "limits": {
                        "max_model_calls": general_review_max_calls,
                        "max_validation_repairs": general_review_max_repairs,
                        "job_timeout_s": general_job_timeout_s,
                    },
                },
                "construction_completion": {
                    "available": True,
                    "dimension_states": [
                        "observed", "deduced", "estimated", "unknown", "conflict",
                    ],
                    "max_parameters": 32,
                    "max_components": 64,
                    "max_constraints": 128,
                    "max_details": 128,
                    "max_expression_depth": 8,
                    "piece_drawing_formats": ["svg", "dxf"],
                    "exact_snapshot_queries": True,
                },
            },
            "history": {"available": _module_available("backend.app.api.history")},
            "evaluation": {"available": False, "reason": "offline_private_reference"},
        }
        return _ok({"environment": environment, "root_path": root_path, "authenticated": environment == "production", "run_submission": {"jobs": True, "legacy_sync": environment == "local", "poll_interval_ms": 500}, "events": {"kind": "completed_history", "streaming": False}, "provider": "openai_responses", "model": settings.model, "live_available": effective_live_available, "unavailable_reason": unavailable_reason, "recorded_replay_available": replay_available, "recorded_replay_availability_endpoint": f"{root_path}/api/v1/replay-availability", "recordings": {"max_count": recording_max_count, "max_bytes": recording_max_bytes, "reservation_bytes": MAX_RECORDED_TRANSCRIPT_BYTES, "capacity_available": recording_capacity, "unavailable_reason": None if recording_capacity else "recording_storage_exhausted:maintenance_or_increase_quota_required"}, "modes": ["geometry_only"] + (["live"] if effective_live_available else []) + (["recorded_replay"] if replay_available else []), "modality": "structured_vector_evidence_with_opt_in_vision" if settings.vision_enabled else "structured_vector_evidence_without_vision", "vision": {"enabled": settings.vision_enabled, "default": False, "source": "ledger_rendered_png", "authority": "context_only_not_measurement_source", "limits": {"max_views": 3, "max_dimension_px": 1024, "max_png_bytes_per_view": 2_000_000}}, "limits": {"max_model_calls": 15, "max_tool_calls": 30, "timeout_s": 120, "max_output_tokens": settings.max_output_tokens}, "tools": [{"name": item["name"], "description": item["description"]} for item in all_tools], "semantic": semantic_capability, "capabilities": capabilities})

    @app.get("/api/v1/table-cost-catalog")
    def table_cost_catalog():
        return _ok(table_cost_catalog_value.model_dump(mode="json"))

    app.include_router(create_history_router(
        historical_store, scenario_snapshot_loader=load_provisional_scenario_snapshot,
    ))
    app.include_router(create_general_furniture_router(
        repository=general_furniture_repository,
        context_loader=general_furniture_context,
        live_runner=run_general_live if general_agent_provider is not None else None,
        event_sink=record_general_live_events if general_agent_provider is not None else None,
        direct_live_enabled=False,
        auto_review_runner=run_general_auto_review if general_review_provider is not None else None,
        auto_review_event_sink=record_general_auto_review_events if general_review_provider is not None else None,
        direct_auto_review_enabled=False,
    ))

    @app.post("/api/v1/documents")
    async def upload_document(http_request: Request, file: UploadFile = File(...)):
        filename = Path(file.filename or "").name
        format_name = Path(filename).suffix.lower().removeprefix(".")
        if format_name not in {"dxf", "dwg", "pdf"}:
            return _error(415, "unsupported_format", "Se admiten archivos DXF, DWG y PDF.")
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            return _error(413, "upload_too_large", "El archivo supera 20 MiB.")
        document_id = f"doc-{uuid4().hex}"
        stage = staging_dir / document_id
        source_media_type = _document_media_type(format_name, file.content_type)
        source_sha256 = hashlib.sha256(content).hexdigest()

        def ingest_and_persist() -> tuple[str, dict | None]:
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True)
            source = stage / f"source.{format_name}"
            source.write_bytes(content)
            artifact_stage = stage / "artifacts"
            normalized_stage: Path | None = None
            preview: dict | None = None
            pages: list[dict] = []
            warnings: list[str] = []
            state = "ready"
            source_unit = "unknown"
            try:
                if format_name == "dxf":
                    parse_dxf(source)
                    normalized_stage = source
                    preview = {"url": f"/api/v1/documents/{document_id}/preview.svg", "media_type": "image/svg+xml"}
                elif format_name == "dwg":
                    from backend.app.ingesta import convert_dwg_to_dxf

                    artifact_stage.mkdir()
                    result = convert_dwg_to_dxf(
                        source,
                        artifact_stage,
                    )
                    normalized_stage = Path(result.dxf_path)
                    warnings.extend(result.warnings)
                    preview = {"url": f"/api/v1/documents/{document_id}/preview.svg", "media_type": "image/svg+xml"}
                else:
                    from backend.app.ingesta import ingest_pdf

                    artifact_stage.mkdir()
                    result = ingest_pdf(source, artifact_stage)
                    state = result.status
                    source_unit = result.source_unit
                    warnings.extend(result.warnings)
                    for page in result.pages:
                        page_number = page.page_number
                        page_value = {
                            "page_number": page_number,
                            "width_points": page.width_points,
                            "height_points": page.height_points,
                            "width_mm": page.width_mm,
                            "height_mm": page.height_mm,
                            "rotation": page.rotation,
                            "content_kind": page.content_kind,
                            "vector_path_count": len(page.vector_paths),
                            "text_block_count": len(page.text_blocks),
                            "image_count": page.image_count,
                            "warnings": list(page.warnings),
                            "preview": {"url": f"/api/v1/documents/{document_id}/pages/{page_number}/preview.png", "media_type": "image/png"},
                            "normalized_dxf": ({"url": f"/api/v1/documents/{document_id}/pages/{page_number}/normalized.dxf", "media_type": "application/dxf", "unit": source_unit} if page.normalized_dxf_path is not None else None),
                        }
                        pages.append(page_value)
                    if pages:
                        preview = pages[0]["preview"]
            except Exception as exc:
                shutil.rmtree(stage, ignore_errors=True)
                code = str(exc)
                if format_name == "dxf":
                    return "invalid_dxf", None
                if format_name == "dwg":
                    error_name = type(exc).__name__
                    mapped = {"DwgConverterUnavailable": "dwg_converter_unavailable", "DwgConversionFailed": "dwg_conversion_failed", "DwgOutputInvalid": "dwg_output_invalid"}
                    return mapped.get(error_name, "dwg_conversion_failed"), None
                return "invalid_pdf", None

            artifact_bytes = sum(item.stat().st_size for item in stage.rglob("*") if item.is_file())
            if format_name == "dwg" and normalized_stage is not None:
                artifact_bytes += normalized_stage.stat().st_size
            with upload_lock:
                if used_document_storage_bytes() + artifact_bytes > max_storage_bytes:
                    shutil.rmtree(stage, ignore_errors=True)
                    return "quota", None
                final_source = documents_dir / (f"{document_id}.dxf" if format_name == "dxf" else f"{document_id}.source.{format_name}")
                final_artifacts = documents_dir / f"{document_id}-artifacts"
                try:
                    source.replace(final_source)
                    if artifact_stage.exists():
                        artifact_stage.replace(final_artifacts)
                    if normalized_stage is not None and format_name != "dxf":
                        normalized_relative = normalized_stage.resolve().relative_to(artifact_stage.resolve())
                        normalized_final = final_artifacts / normalized_relative
                        shutil.copyfile(normalized_final, documents_dir / f"{document_id}.dxf")
                except Exception:
                    final_source.unlink(missing_ok=True)
                    (documents_dir / f"{document_id}.dxf").unlink(missing_ok=True)
                    shutil.rmtree(final_artifacts, ignore_errors=True)
                    shutil.rmtree(stage, ignore_errors=True)
                    return "persistence_failed", None
                finally:
                    shutil.rmtree(stage, ignore_errors=True)

                original_url = f"/api/v1/documents/{document_id}/original"
                normalized = None
                normalized_path = documents_dir / f"{document_id}.dxf"
                if normalized_path.is_file():
                    normalized = {"url": f"/api/v1/documents/{document_id}/normalized.dxf", "media_type": "application/dxf", "sha256": hashlib.sha256(normalized_path.read_bytes()).hexdigest()}
                manifest = {
                    "document_id": document_id,
                    "original_filename": filename,
                    "size_bytes": len(content),
                    "sha256": source_sha256,
                    "source_kind": "uploaded",
                    "source": {"filename": filename, "media_type": source_media_type, "format": format_name, "size_bytes": len(content), "sha256": source_sha256, "unit": source_unit},
                    "ingestion": {"state": state, "capabilities": {"geometry_analysis": normalized is not None and format_name != "pdf", "page_geometry_analysis": any(page.get("normalized_dxf") is not None for page in pages), "page_review": format_name == "pdf"}, "warnings": warnings, "errors": []},
                    "artifacts": {"original": {"url": original_url, "media_type": source_media_type}, "normalized_dxf": normalized, "preview": preview, "pages": pages},
                    "audit": {"uploaded_by": http_request.state.actor, "uploaded_at": datetime.now(UTC).isoformat()},
                }
                document_manifest_path(document_id).write_text(json.dumps(_json_safe(manifest), ensure_ascii=False, sort_keys=True), encoding="utf-8")
                return "stored", manifest

        persisted, manifest = await run_in_threadpool(ingest_and_persist)
        if persisted == "quota":
            return _error(507, "storage_quota_exceeded", "La cuota persistente de documentos está agotada.")
        if persisted == "invalid_dxf":
            return _error(422, "invalid_dxf", "El archivo no es un DXF válido dentro de los límites admitidos.")
        if persisted != "stored":
            status = 503 if persisted in {"dwg_converter_unavailable", "dwg_conversion_timeout"} else 422
            return _error(status, persisted, "No se pudo ingerir el documento.", status == 503)
        return _ok(manifest, 201)

    @app.get("/api/v1/documents/{document_id}")
    def get_document(document_id: str):
        if DOCUMENT_ID_PATTERN.fullmatch(document_id) is None:
            return _error(422, "invalid_document_id", "Identificador de documento inválido.")
        manifest = load_document_manifest(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        return _ok(manifest)

    @app.get("/api/v1/documents/{document_id}/original")
    def get_document_original(document_id: str):
        manifest = load_document_manifest(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        format_name = manifest["source"]["format"]
        source_document_id = manifest["source"].get("parent_document_id", document_id)
        if DOCUMENT_ID_PATTERN.fullmatch(source_document_id) is None:
            return _error(409, "document_provenance_invalid", "La procedencia del documento no es válida.")
        path = documents_dir / (f"{source_document_id}.dxf" if format_name == "dxf" else f"{source_document_id}.source.{format_name}")
        if not path.is_file():
            return _error(404, "document_artifact_not_found", "El original no está disponible.")
        return FileResponse(path, media_type=manifest["source"]["media_type"], filename=manifest["source"]["filename"], headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/documents/{document_id}/normalized.dxf")
    def get_document_normalized(document_id: str):
        path = normalized_document_path(document_id)
        if path is None:
            return _error(404, "normalized_dxf_unavailable", "El documento no tiene un DXF normalizado.")
        return FileResponse(path, media_type="application/dxf", filename=f"{document_id}.dxf", headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/documents/{document_id}/pages/{page_number}/preview.png")
    def get_pdf_page_preview(document_id: str, page_number: int):
        manifest = load_document_manifest(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        pages = manifest.get("artifacts", {}).get("pages", [])
        if not any(page.get("page_number") == page_number for page in pages):
            return _error(404, "document_page_not_found", "Página inexistente.")
        path = documents_dir / f"{document_id}-artifacts" / f"page-{page_number:04d}.png"
        if not path.is_file():
            return _error(404, "document_artifact_not_found", "La previsualización no está disponible.")
        return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/v1/documents/{document_id}/pages/{page_number}/normalized.dxf")
    def get_pdf_page_dxf(document_id: str, page_number: int):
        manifest = load_document_manifest(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        pages = manifest.get("artifacts", {}).get("pages", [])
        page = next((item for item in pages if item.get("page_number") == page_number), None)
        if page is None or page.get("normalized_dxf") is None:
            return _error(404, "normalized_dxf_unavailable", "La página no tiene un DXF normalizado.")
        path = documents_dir / f"{document_id}-artifacts" / f"page-{page_number:04d}.dxf"
        if not path.is_file():
            return _error(404, "document_artifact_not_found", "El artefacto de página no está disponible.")
        return FileResponse(path, media_type="application/dxf", filename=f"{document_id}-page-{page_number}.dxf", headers={"X-Content-Type-Options": "nosniff"})

    @app.post("/api/v1/documents/{document_id}/pages/{page_number}/select")
    @app.post("/api/v1/documents/{document_id}/pdf-pages/{page_number}/normalize")
    def select_pdf_page(document_id: str, page_number: int, selection: PdfPageSelectionRequest, http_request: Request):
        manifest = load_document_manifest(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        if manifest.get("source", {}).get("format") != "pdf":
            return _error(409, "pdf_page_selection_required", "La selección de página solo se aplica a PDF.")
        actor = http_request.state.actor or selection.confirmed_by
        if selection.mm_per_pdf_point is not None and not actor:
            return _error(422, "scale_confirmation_actor_required", "La escala requiere una persona responsable.")
        current_pages = manifest.get("artifacts", {}).get("pages", [])
        selected_page = next((page for page in current_pages if page.get("page_number") == page_number), None)
        if selected_page is None:
            return _error(404, "document_page_not_found", "Página inexistente.")

        def select() -> tuple[str, dict | None]:
            child_id = f"doc-{uuid4().hex}"
            parent_artifact_dir = documents_dir / f"{document_id}-artifacts"
            selected_path = parent_artifact_dir / f"page-{page_number:04d}.dxf"
            child_page = dict(selected_page)
            scale_provenance = None
            generated_artifacts: Path | None = None
            if selection.mm_per_pdf_point is not None:
                from backend.app.ingesta import PdfScaleConfirmation, ingest_pdf

                source = documents_dir / f"{document_id}.source.pdf"
                scale_provenance = {
                    "mm_per_pdf_point": selection.mm_per_pdf_point,
                    "confirmed_by": actor,
                    "confirmed_at": datetime.now(UTC).isoformat(),
                }
                generated_artifacts = staging_dir / f"{document_id}-scale-{uuid4().hex}"
                try:
                    result = ingest_pdf(
                        source,
                        generated_artifacts,
                        scale=PdfScaleConfirmation(
                            mm_per_pdf_point=selection.mm_per_pdf_point,
                            confirmed_by=actor or "",
                            confirmed_at=datetime.now(UTC),
                        ),
                    )
                except Exception:
                    shutil.rmtree(generated_artifacts, ignore_errors=True)
                    return "invalid_pdf", None
                scaled_page = next(page for page in result.pages if page.page_number == page_number)
                child_page = {
                    "page_number": scaled_page.page_number,
                    "width_points": scaled_page.width_points,
                    "height_points": scaled_page.height_points,
                    "width_mm": scaled_page.width_mm,
                    "height_mm": scaled_page.height_mm,
                    "rotation": scaled_page.rotation,
                    "content_kind": scaled_page.content_kind,
                    "vector_path_count": len(scaled_page.vector_paths),
                    "text_block_count": len(scaled_page.text_blocks),
                    "image_count": scaled_page.image_count,
                    "warnings": list(scaled_page.warnings),
                    "preview": selected_page["preview"],
                    "normalized_dxf": ({"url": f"/api/v1/documents/{child_id}/normalized.dxf", "media_type": "application/dxf", "unit": "mm"} if scaled_page.normalized_dxf_path is not None else None),
                }
                selected_path = generated_artifacts / f"page-{page_number:04d}.dxf"
            has_vector_dxf = selected_path.is_file()
            selected_size = selected_path.stat().st_size if has_vector_dxf else 0
            with upload_lock:
                if used_document_storage_bytes() + selected_size > max_storage_bytes:
                    if generated_artifacts is not None:
                        shutil.rmtree(generated_artifacts, ignore_errors=True)
                    return "quota", None
                child_normalized = documents_dir / f"{child_id}.dxf"
                normalized = None
                if has_vector_dxf:
                    temporary_normalized = documents_dir / f".{child_id}.selected.dxf"
                    shutil.copyfile(selected_path, temporary_normalized)
                    temporary_normalized.replace(child_normalized)
                    normalized_sha = hashlib.sha256(child_normalized.read_bytes()).hexdigest()
                    normalized = {"url": f"/api/v1/documents/{child_id}/normalized.dxf", "media_type": "application/dxf", "sha256": normalized_sha, "source_page": page_number, "unit": "mm" if scale_provenance else "unknown"}
                child = {
                    "document_id": child_id,
                    "original_filename": manifest["original_filename"],
                    "size_bytes": manifest["size_bytes"],
                    "sha256": manifest["sha256"],
                    "source_kind": "pdf_page_derivative",
                    "source": {**manifest["source"], "parent_document_id": document_id, "page_number": page_number, "unit": "mm" if selection.mm_per_pdf_point is not None else "unknown"},
                    "ingestion": {"state": "ready" if scale_provenance is not None and has_vector_dxf else "needs_review", "capabilities": {"geometry_analysis": has_vector_dxf, "visual_general_review": True, "page_review": True}, "warnings": list(child_page.get("warnings", [])), "errors": [], "selected_page": page_number, "scale_provenance": scale_provenance},
                    "artifacts": {"original": {"url": f"/api/v1/documents/{child_id}/original", "media_type": "application/pdf"}, "normalized_dxf": normalized, "preview": child_page["preview"], "pages": [child_page]},
                    "audit": {"uploaded_by": manifest.get("audit", {}).get("uploaded_by"), "selected_by": actor, "selected_at": datetime.now(UTC).isoformat(), "selection_reason": selection.reason},
                }
                document_manifest_path(child_id).write_text(json.dumps(_json_safe(child), ensure_ascii=False, sort_keys=True), encoding="utf-8")
                if generated_artifacts is not None:
                    shutil.rmtree(generated_artifacts, ignore_errors=True)
                return "selected", child

        state, updated = select()
        if state == "quota":
            return _error(507, "storage_quota_exceeded", "La cuota persistente de documentos está agotada.")
        if state != "selected":
            return _error(422, state, "No se pudo seleccionar la página PDF.")
        return _ok(updated)

    @app.get("/api/v1/documents/{document_id}/drawing")
    def get_document_drawing(
        document_id: str,
        input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views", "general_furniture"] = Query(
            default="mounted_views_legacy"
        ),
    ):
        if re.fullmatch(r"doc-[0-9a-f]{32}", document_id) is None:
            return _error(422, "invalid_document_id", "Identificador de documento inválido.")
        manifest = load_document_manifest(document_id)
        path = normalized_document_path(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        if path is None:
            return _error(409, "normalized_dxf_unavailable", "El documento requiere revisión y no puede entrar al análisis DXF.")
        try:
            extraction = extract_drawing(path, input_kind=input_kind)
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        return _ok(extraction.model_dump(mode="json"))

    @app.get("/api/v1/documents/{document_id}/preview.svg")
    def get_document_preview(document_id: str):
        if re.fullmatch(r"doc-[0-9a-f]{32}", document_id) is None:
            return _error(422, "invalid_document_id", "Identificador de documento inválido.")
        manifest = load_document_manifest(document_id)
        path = normalized_document_path(document_id)
        if manifest is None:
            return _error(404, "document_not_found", "Documento inexistente.")
        if path is None:
            return _error(409, "normalized_dxf_unavailable", "El documento no tiene una previsualización vectorial DXF.")
        try:
            svg = render_drawing_preview(path)
        except ValueError as exc:
            code = str(exc) if str(exc) in ("preview_complexity_limit", "invalid_dxf") else "invalid_dxf"
            return _error(422, code, "No se pudo generar la previsualización SVG.")
        return Response(svg, media_type="image/svg+xml", headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"})

    def _prepare_run(request: RunRequest):
        if request.mode == "live" and not live_available:
            raise RuntimeError("live_provider_unavailable")
        manifest = load_document_manifest(request.document_id)
        if manifest is None:
            raise FileNotFoundError(request.document_id)
        path = normalized_document_path(request.document_id)
        if path is None and request.input_kind != "general_furniture":
            raise NormalizedDxfUnavailable(request.document_id)
        if path is None:
            extraction = DrawingExtraction(
                drawing_id=f"drawing-{manifest['sha256'][:16]}", input_kind="general_furniture",
                status="needs_review", source_unit="unknown", unit_scale_to_mm=None,
                coordinate_unit="source", entities=(), views=(), contours=(), dimensions=(),
                evidence=(), observations=(), warnings=("raster_or_unconverted_source_visual_review_only",),
            )
            document_sha256 = manifest["sha256"]
        else:
            extraction = extract_drawing(path, input_kind=request.input_kind)
            document_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if request.input_kind == "separated_part_views":
            part_analysis = extract_separated_parts(extraction)
            assembly_candidates = derive_assembly_candidates(part_analysis)
            scenarios = ()
            table_analysis = None
            table_programs = ()
            evaluated_table_program = None
            comparison_candidates = assembly_candidates
            schemas = parts_tool_schemas()
        elif request.input_kind == "mounted_orthographic_views":
            part_analysis = None
            assembly_candidates = ()
            scenarios = ()
            table_analysis = analyze_mounted_table(extraction)
            comparison_candidates = catalog_table_programs(table_analysis)
            available_programs = comparison_candidates if request.proposal_mode == "catalog_baseline" else ()
            table_programs = tuple(item for item in available_programs if item.table_template_id == request.table_template_id)
            if request.proposal_mode == "catalog_baseline" and len(table_programs) != 1:
                raise ValueError("table_template_unavailable")
            evaluated_table_program = evaluate_table_program(table_analysis, table_programs[0]) if table_programs else None
            schemas = table_tool_schemas(include_vision=settings.vision_enabled)
        elif request.input_kind == "general_furniture":
            part_analysis = None
            assembly_candidates = ()
            scenarios = ()
            table_analysis = None
            table_programs = ()
            evaluated_table_program = None
            comparison_candidates = ()
            schemas = ()
        else:
            part_analysis = None
            assembly_candidates = ()
            scenarios = derive_decomposition_scenarios(extraction)
            table_analysis = None
            table_programs = ()
            evaluated_table_program = None
            comparison_candidates = scenarios
            schemas = tool_schemas()
        limits = AgentLimits()
        fingerprint = recording_fingerprint({
            "request": request.model_copy(update={"mode": "live"}).model_dump(mode="json"),
            "document_sha256": document_sha256,
            "extraction": extraction.model_dump(mode="json"),
            "part_analysis": part_analysis.model_dump(mode="json") if part_analysis else None,
            "assembly_candidates": [item.model_dump(mode="json") for item in assembly_candidates],
            "scenarios": [item.model_dump(mode="json") for item in scenarios],
            "table_analysis": table_analysis.model_dump(mode="json") if table_analysis else None,
            "comparison_candidates": [item.model_dump(mode="json") for item in comparison_candidates],
            "provider": {"model": settings.model, "max_output_tokens": settings.max_output_tokens},
            "prompt": VISION_SYSTEM_PROMPT if settings.vision_enabled else SYSTEM_PROMPT,
            "tools": schemas,
            "limits": asdict(limits),
            "registry_version": "pr1-replay-v1",
            "vision": {"enabled": settings.vision_enabled, "renderer_version": "ledger-set-of-mark-v1"},
        })
        return (extraction, part_analysis, assembly_candidates, scenarios, table_analysis,
                table_programs, evaluated_table_program, comparison_candidates, limits, fingerprint)

    @app.post("/api/v1/replay-availability")
    def replay_availability(request: RunRequest):
        if request.mode != "recorded_replay":
            return _error(422, "recorded_replay_mode_required", "La consulta requiere mode recorded_replay.")
        if request.input_kind == "general_furniture":
            return _ok({"available": False, "document_id": request.document_id, "input_kind": request.input_kind, "reason": "general_furniture_replay_unavailable"})
        try:
            *_, fingerprint = _prepare_run(request)
        except NormalizedDxfUnavailable:
            return _error(409, "normalized_dxf_unavailable", "El documento no tiene un DXF normalizado utilizable.")
        except FileNotFoundError:
            return _error(404, "document_not_found", "Documento inexistente.")
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo preparar el documento: {type(exc).__name__}.")
        recording = repository.find_agent_recording(fingerprint)
        return _ok({"available": recording is not None, "document_id": request.document_id, "input_kind": request.input_kind})

    def _execute_run(request: RunRequest, *, actor: str | None = None):
        if request.mode == "live" and not live_available:
            return _error(503, "live_provider_unavailable", settings.unavailable_reason or "Proveedor no disponible.", True)
        try:
            (extraction, part_analysis, assembly_candidates, scenarios, table_analysis,
             table_programs, evaluated_table_program, comparison_candidates, limits, fingerprint) = _prepare_run(request)
        except NormalizedDxfUnavailable:
            return _error(409, "normalized_dxf_unavailable", "El documento no tiene un DXF normalizado utilizable.")
        except FileNotFoundError:
            return _error(404, "document_not_found", "Documento inexistente.")
        except ValueError as exc:
            if str(exc) == "table_template_unavailable":
                return _error(422, "table_template_unavailable", "La plantilla de mesa solicitada no está disponible para este ledger.")
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        except Exception as exc:
            return _error(422, "invalid_dxf", f"No se pudo extraer el DXF: {type(exc).__name__}.")
        if request.input_kind == "mounted_views_legacy" and not scenarios:
            return _error(422, "unsupported_geometry", "Las vistas no respaldan escenarios rectangulares coherentes.")
        trace_events: tuple[dict, ...] = ()
        agent_selected_scenario_id = None
        agent_selected_assembly_candidate_id = None
        agent_selected_table_program_id = None
        recording_draft = None
        source_recording = None
        recording_reservation_id = None
        if request.mode in {"live", "recorded_replay"} and request.input_kind != "general_furniture":
            try:
                if request.mode == "live":
                    recording_reservation_id = f"recording-reservation-{uuid4().hex}"
                    repository.reserve_agent_recording(
                        recording_reservation_id,
                        fingerprint=fingerprint,
                        actor=actor or "local-demo",
                        max_count=recording_max_count,
                        max_bytes=recording_max_bytes,
                        reserved_bytes=MAX_RECORDED_TRANSCRIPT_BYTES,
                    )
                    recording_model = settings.model or f"injected:{type(agent_provider).__name__}"
                    provider = RecordingProvider(
                        agent_provider or OpenAIResponsesProvider(settings),
                        provider_model=recording_model,
                    )
                else:
                    source_recording = repository.find_agent_recording(fingerprint)
                    if source_recording is None:
                        return _error(409, "recorded_replay_unavailable", "No existe una grabación real para este documento y configuración.")
                    provider = ReplayProvider(
                        source_recording.transcript_json,
                        source_recording.transcript_sha256,
                        source_recording.output_sha256,
                    )
                if request.input_kind == "mounted_orthographic_views":
                    outcome = run_table_agent(
                        extraction, table_analysis, provider, limits,
                        vision_enabled=settings.vision_enabled,
                        comparison_candidates=comparison_candidates,
                    )
                    table_programs = (outcome.program,)
                    evaluated_table_program = evaluate_table_program(table_analysis, outcome.program)
                    agent_selected_table_program_id = outcome.program.id
                elif request.input_kind == "separated_part_views":
                    outcome = run_parts_agent(extraction, part_analysis, assembly_candidates, provider, limits)
                    assembly_candidates = tuple(sorted(
                        assembly_candidates,
                        key=lambda item: item.id != outcome.selected_assembly_candidate_id,
                    ))
                    agent_selected_assembly_candidate_id = outcome.selected_assembly_candidate_id
                else:
                    outcome = run_agent(extraction, scenarios, provider, limits)
                    scenarios = tuple(sorted(scenarios, key=lambda item: item.id != outcome.selected_scenario_id))
                    agent_selected_scenario_id = outcome.selected_scenario_id
                if request.mode == "live":
                    recording_draft = provider.finalize(outcome)
                else:
                    provider.assert_complete(outcome)
            except Exception as exc:
                if recording_reservation_id is not None:
                    repository.release_agent_recording_reservation(recording_reservation_id)
                if str(exc) == "recording_storage_exhausted":
                    return _error(429, "recording_storage_exhausted", "No hay capacidad reservable para otra grabación live.", True)
                if request.mode == "recorded_replay":
                    return _error(409, "recorded_replay_stale", f"La grabación no coincide con el estado actual: {type(exc).__name__}.")
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
                "provider_response_id": action.provider_response_id,
                "provider_model": action.provider_model,
                "provider_call_id": action.provider_call_id,
                "provider_duration_ms": action.provider_duration_ms,
                "provider_input_tokens": action.provider_input_tokens,
                "provider_output_tokens": action.provider_output_tokens,
                "provider_total_tokens": action.provider_total_tokens,
                "provenance": request.mode,
                "source_live_run_id": source_recording.source_live_run_id if source_recording else None,
                "source_result_revision": source_recording.source_result_revision if source_recording else None,
            } for action in outcome.actions)
        run_id = f"run-{uuid4().hex}"
        general_outcome = None
        general_auto_outcome = None
        general_started = None
        if request.input_kind == "general_furniture" and request.mode == "live":
            general_started = time.monotonic()
            general_context = GeneralFurnitureContext(
                run_id=run_id, extraction=extraction, ledger_revision=extraction.drawing_id,
                visual_pages=general_visual_pages(request.document_id, extraction),
            )
            try:
                general_outcome = execute_general_live(general_context)
            except GeneralLiveError as exc:
                return JSONResponse({
                    "schema_version": "0.2.0",
                    "error": {
                        "code": "general_live_provider_failed",
                        "reason_code": exc.code,
                        "message": "La propuesta general live falló de forma acotada.",
                        "retryable": True,
                        "model_calls": exc.model_calls,
                        "tool_calls": exc.tool_calls,
                        "trace": list(exc.trace),
                    },
                }, status_code=502)
            except Exception as exc:
                return _error(502, "general_live_provider_failed", f"La propuesta general live falló: {type(exc).__name__}.", True)
        try:
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
                recording_draft=recording_draft,
                recording_fingerprint=fingerprint if recording_draft is not None else None,
                recording_actor=actor or "local-demo",
                recording_reservation_id=recording_reservation_id,
                replay_source_recording_id=source_recording.recording_id if source_recording else None,
            )
        except Exception:
            if recording_reservation_id is not None:
                repository.release_agent_recording_reservation(recording_reservation_id)
            raise
        if general_outcome is not None:
            general_revision = general_furniture_repository.save_proposal(
                run_id, general_outcome.proposal, general_outcome.draft,
                base_proposal_revision=0,
            )
            record_general_live_events(run_id, general_revision, general_outcome)
            repository.append_event(run_id, "general_auto_review_started", {
                "proposal_revision": general_revision, "reviewer_kind": "machine",
                "reviewer_model": review_model or f"injected:{type(general_review_provider).__name__}",
                "visual_artifacts": [{
                    "reference": item.reference, "sha256": item.sha256,
                    "source_view_ids": item.source_view_ids,
                    "source_contour_ids": item.source_contour_ids,
                    "crop_bounds_source": item.crop_bounds_source,
                    "marks": [asdict(mark) for mark in item.marks],
                } for item in general_context.visual_pages],
            })
            remaining = general_job_timeout_s - (time.monotonic() - (general_started or time.monotonic()))
            if remaining <= 0:
                error = {"code": "general_auto_review_failed", "message": "La revisión autónoma agotó el plazo total del trabajo.", "retryable": True, "run_id": run_id}
                repository.append_event(run_id, "general_auto_review_failed", error)
                return JSONResponse({"schema_version": "0.2.0", "run_id": run_id, "error": error}, status_code=504)
            try:
                general_auto_outcome = execute_general_autonomous(
                    general_context, general_outcome, timeout_s=remaining,
                    checkpoint_sink=lambda checkpoint: persist_general_auto_checkpoint(run_id, checkpoint),
                )
            except GeneralAutonomousError as exc:
                record_general_auto_review_failure(run_id, exc)
                error = {"code": exc.code, "message": "La revisión autónoma falló de forma acotada.", "retryable": True, "run_id": run_id}
                return JSONResponse({"schema_version": "0.2.0", "run_id": run_id, "error": error}, status_code=502)
            except Exception as exc:
                code = "general_auto_review_unavailable" if str(exc) == "general_auto_review_unavailable" else "general_auto_review_failed"
                status = 503 if code == "general_auto_review_unavailable" else 502
                error = {"code": code, "message": f"La revisión autónoma falló: {type(exc).__name__}.", "retryable": True, "run_id": run_id}
                repository.append_event(run_id, "general_auto_review_failed", {"code": code, "reviewer_kind": "machine"})
                return JSONResponse({"schema_version": "0.2.0", "run_id": run_id, "error": error}, status_code=status)
            if general_auto_outcome is not None:
                if general_auto_outcome.semantic_repairs:
                    general_revision += general_auto_outcome.semantic_repairs
                    if general_revision != general_auto_outcome.review.proposal_revision:
                        raise ValueError("general_auto_review_revision_mismatch")
                general_furniture_repository.save_review(
                    run_id, general_auto_outcome.review, general_auto_outcome.derived,
                )
                record_general_auto_review_events(run_id, general_auto_outcome)
        return _ok({"run": run.model_dump(mode="json"), "result": repository.get_result(run_id).model_dump(mode="json")}, 201)

    @app.post("/api/v1/runs")
    def create_run(request: RunRequest):
        if environment == "production":
            return _error(409, "use_jobs_endpoint", "Producción requiere el endpoint durable de trabajos.")
        return _execute_run(request)

    @app.post("/api/v1/jobs")
    def submit_job(
        request: RunRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if environment == "production" and not idempotency_key:
            return _error(428, "idempotency_key_required", "Idempotency-Key es obligatorio en producción.")
        if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
            return _error(422, "invalid_idempotency_key", "Idempotency-Key no es válido.")
        request_json = request.model_dump_json()
        if idempotency_key is not None:
            try:
                replay = repository.get_idempotent_job(
                    request_json,
                    actor=http_request.state.actor,
                    idempotency_key=idempotency_key,
                )
            except ValueError as exc:
                return _error(409, str(exc), "Idempotency-Key ya fue usado para otra solicitud.")
            if replay is not None:
                return _ok(replay, 202)
        if not job_executor.reserve():
            return _error(429, "job_capacity_exhausted", "La cola de trabajos está completa.", True)
        job_id = f"job-{uuid4().hex}"
        try:
            job, created = repository.reserve_job(
                job_id,
                request_json,
                actor=http_request.state.actor,
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            job_executor.release()
            return _error(409, str(exc), "Idempotency-Key ya fue usado para otra solicitud.")
        if not created:
            job_executor.release()
            return _ok(job, 202)

        def process() -> None:
            try:
                repository.start_job(job_id)
                response = _execute_run(request, actor=http_request.state.actor)
                payload = json.loads(response.body)
                if response.status_code == 201:
                    repository.finish_job(job_id, run_id=payload["data"]["run"]["id"])
                else:
                    repository.finish_job(job_id, run_id=payload.get("run_id"), error=payload.get("error") or {
                        "code": "job_failed", "message": "El trabajo no terminó.", "retryable": False
                    })
            except Exception as exc:
                repository.finish_job(job_id, error={
                    "code": "job_failed",
                    "message": f"El trabajo falló de forma segura: {type(exc).__name__}.",
                    "retryable": False,
                })

        job_executor.submit_reserved(process)
        return _ok(job, 202)

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str):
        if re.fullmatch(r"job-[0-9a-f]{32}", job_id) is None:
            return _error(422, "invalid_job_id", "Identificador de trabajo inválido.")
        try:
            return _ok(repository.get_job(job_id))
        except KeyError:
            return _error(404, "job_not_found", "Trabajo inexistente.")

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
            url = f"{root_path}/api/v1/runs/{run_id}/table-drawings/{artifact.sheet_id}.{artifact.format}?result_revision={result.result_revision}&program_hash={plan.program_hash}"
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
    def review_run(
        run_id: str,
        review: ReviewRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if environment == "production" and not idempotency_key:
            return _error(428, "idempotency_key_required", "Idempotency-Key es obligatorio en producción.")
        try:
            result = repository.review(
                run_id,
                review,
                idempotency_key=idempotency_key,
                actor=http_request.state.actor,
            )
            return _ok(result.model_dump(mode="json"), 201)
        except KeyError:
            return _error(404, "run_not_found", "Ejecución inexistente.")
        except ValueError as exc:
            code = str(exc)
            return _error(409 if code in {"stale_result_revision", "idempotency_key_conflict"} else 422, code, "La revisión no es aplicable.")

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
            value = estimate_table_costs(result.evaluated_table_program, result_revision=result.result_revision, scope=request.scope, catalog=table_cost_catalog_value)
            repository.save_table_cost_estimate(run_id, value)
        except ValueError as exc:
            return _error(422, str(exc), "No se pudo calcular el coste de mesa.")
        return _ok(value.model_dump(mode="json"), 201)

    @app.get("/api/v1/runs/{run_id}/table-costs")
    def get_table_costs(run_id: str, result_revision: int = Query(..., gt=0), estimate_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$")):
        try:
            value = repository.get_table_cost_estimate(run_id, result_revision, estimate_id)
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
