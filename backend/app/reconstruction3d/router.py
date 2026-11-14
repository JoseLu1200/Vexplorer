from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4
from threading import RLock
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field

from .artifacts import export_package
from .models import AssemblyProposal, RefinementRequest
from .service import ReconstructionError, reconstruct


class ReconstructionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intended_use: str = Field(default="", max_length=240)


_STATUS_LOCK = RLock()
_MAX_JOBS_PER_RUN = 3
_JOB_STORAGE_RESERVATION_BYTES = 16 * 1024 * 1024
_MAX_RECONSTRUCTION_STORAGE_BYTES = 256 * 1024 * 1024


def _read(path):
    with _STATUS_LOCK:
        return json.loads(path.read_text(encoding="utf8"))


def _write(path: Path, value: dict) -> None:
    with _STATUS_LOCK:
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8"
        )
        temp.replace(path)


def create_reconstruction_router(
    *, root: Path, context_loader, provider, executor, admission_callback=None
) -> APIRouter:
    router = APIRouter()
    store = root / "reconstruction"
    store.mkdir(parents=True, exist_ok=True)
    # Jobs persist across process restart, but never pretend an interrupted call completed.
    for path in store.glob("*/status.json"):
        state = _read(path)
        if state.get("status") in ("queued", "running"):
            _write(
                path, {**state, "status": "interrupted", "error": "server_restarted"}
            )

    def folder(job_id):
        if re.fullmatch(r"[a-f0-9]{32}", job_id) is None:
            raise HTTPException(404, "job_not_found")
        path = store / job_id
        if not (path / "status.json").exists():
            raise HTTPException(404, "job_not_found")
        return path

    def request_hash(value: BaseModel) -> str:
        return sha256(
            json.dumps(
                value.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()

    def stored_jobs() -> list[tuple[Path, dict]]:
        values = []
        for status_path in store.glob("*/status.json"):
            try:
                values.append((status_path.parent, _read(status_path)))
            except (OSError, ValueError):
                continue
        return values

    def charged_storage(jobs: list[tuple[Path, dict]]) -> int:
        total = 0
        for path, state in jobs:
            actual = sum(
                item.stat().st_size for item in path.rglob("*") if item.is_file()
            )
            if state.get("status") in {"queued", "running"}:
                actual = max(actual, int(state.get("reserved_storage_bytes", 0)))
            total += actual
        return total

    def folder_size(path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    @router.post("/api/v1/runs/{run_id}/reconstruction", status_code=202)
    def submit(
        run_id: str,
        body: ReconstructionRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if provider is None:
            raise HTTPException(503, "reconstruction_model_unavailable")
        try:
            context = context_loader(run_id)
        except KeyError:
            raise HTTPException(404, "general_run_not_found") from None
        pages = context.visual_pages[:4]
        if not pages:
            raise HTTPException(422, "original_visual_evidence_required")
        images = []
        for page in pages:
            with Image.open(io.BytesIO(page.content)) as source:
                image = source.convert("RGB")
                image.thumbnail((960, 960))
                images.append(image)
        columns = 2 if len(images) > 1 else 1
        rows = (len(images) + columns - 1) // columns
        canvas = Image.new("RGB", (columns * 960, rows * 1000), "white")
        draw = ImageDraw.Draw(canvas)
        layout = []
        for index, image in enumerate(images):
            x = (index % columns) * 960
            y = (index // columns) * 1000
            draw.rectangle((x, y, x + 959, y + 999), outline="#64748b", width=3)
            label = (
                f"SOURCE VIEW {index + 1}/{len(images)} - same object, not extra parts"
            )
            draw.text(
                (x + 12, y + 10),
                label,
                fill="black",
                font=ImageFont.load_default(size=20),
            )
            canvas.paste(image, (x, y + 40))
            layout.append(
                {
                    "label": label,
                    "image_bounds_px": [
                        x,
                        y + 40,
                        x + image.width,
                        y + 40 + image.height,
                    ],
                }
            )
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        content = buffer.getvalue()
        if len(content) > 4 * 1024 * 1024:
            raise HTTPException(422, "source_image_too_large")
        dimensions = [
            d.model_dump(mode="json")
            for d in context.extraction.dimensions
            if d.value_mm is not None
        ]
        unit = "mm" if dimensions else "relative"
        state = {
            "run_id": run_id,
            "ledger_revision": context.ledger_revision,
            "status": "queued",
            "source_sha256": sha256(content).hexdigest(),
            "source_refs": [p.reference for p in pages],
            "original_image_sha256": [p.sha256 for p in pages],
            "unit": unit,
            "intended_use_from_user": body.intended_use,
            "certified_for_manufacturing": False,
            "parent_job_id": None,
            "revision": 1,
            "clarifications": [],
            "envelope_mm": {},
        }
        return enqueue(
            content,
            state,
            {
                "dimensions": dimensions,
                "allowed_component_source_refs": ["input"],
                "composite_views": layout,
            },
            http_request=http_request,
            mode="submit",
            idempotency_key=idempotency_key,
            canonical_request_hash=request_hash(body),
        )

    def enqueue(
        content,
        metadata,
        source_context,
        *,
        http_request: Request,
        mode: Literal["submit", "refine"],
        idempotency_key: str | None,
        canonical_request_hash: str,
    ):
        if admission_callback is not None and not idempotency_key:
            raise HTTPException(428, "idempotency_key_required")
        if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
            raise HTTPException(422, "invalid_idempotency_key")
        operation_identity = (
            f"submit:{metadata['run_id']}"
            if mode == "submit"
            else f"refine:{metadata['parent_job_id']}"
        )
        serialized_context = json.dumps(
            source_context, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        if len(content) + len(serialized_context) > _JOB_STORAGE_RESERVATION_BYTES:
            raise HTTPException(422, "reconstruction_input_storage_exceeded")
        with _STATUS_LOCK:
            jobs = stored_jobs()
            for _, existing in jobs:
                if existing.get("operation_identity") != operation_identity:
                    continue
                same_request = existing.get("request_hash") == canonical_request_hash
                same_key = (
                    idempotency_key is not None
                    and existing.get("idempotency_key") == idempotency_key
                )
                if same_key:
                    if not same_request:
                        raise HTTPException(409, "idempotency_key_conflict")
                    return existing
                if mode == "refine":
                    if same_request:
                        return existing
                    raise HTTPException(409, "parent_already_refined")
            if sum(
                existing.get("run_id") == metadata["run_id"] for _, existing in jobs
            ) >= _MAX_JOBS_PER_RUN:
                raise HTTPException(409, "reconstruction_call_limit_reached")
            if (
                charged_storage(jobs) + _JOB_STORAGE_RESERVATION_BYTES
                > _MAX_RECONSTRUCTION_STORAGE_BYTES
            ):
                raise HTTPException(507, "reconstruction_storage_exhausted")
            if not executor.reserve():
                raise HTTPException(429, "job_queue_full")
            job_id = uuid4().hex
            dest = store / job_id
            staging = store / f".{job_id}.tmp"
            state = {
                **metadata,
                "job_id": job_id,
                "status": "queued",
                "refinement_supported": True,
                "context_sha256": sha256(
                    json.dumps(source_context, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest(),
                "operation_identity": operation_identity,
                "idempotency_key": idempotency_key,
                "request_hash": canonical_request_hash,
                "reserved_storage_bytes": _JOB_STORAGE_RESERVATION_BYTES,
            }
            try:
                staging.mkdir()
                (staging / "source.png").write_bytes(content)
                _write(staging / "input-context.json", source_context)
                _write(staging / "status.json", state)
                if admission_callback is not None:
                    admission_callback(http_request, mode, job_id)
                staging.replace(dest)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                executor.release()
                raise

        def process():
            try:
                def ensure_job_storage() -> None:
                    if folder_size(dest) > _JOB_STORAGE_RESERVATION_BYTES:
                        raise ReconstructionError("reconstruction_job_storage_exceeded")

                def write_baseline(value) -> None:
                    _write(dest / "baseline.json", value)
                    ensure_job_storage()

                _write(dest / "status.json", {**state, "status": "running"})
                outcome = reconstruct(
                    content,
                    provider=provider,
                    known_unit=state["unit"],
                    intended_use=state["intended_use_from_user"],
                    source_context=source_context,
                    clarifications=state["clarifications"],
                    envelope_mm=state["envelope_mm"],
                    on_baseline=write_baseline,
                )
                _write(dest / "outcome.json", outcome)
                ensure_job_storage()
                export_package(
                    AssemblyProposal.model_validate(outcome["proposal"]),
                    dest / "artifacts",
                )
                ensure_job_storage()
                _write(
                    dest / "artifacts" / "revision.json",
                    {
                        **state,
                        "status": outcome["status"],
                        "user_declarations": outcome["user_declarations"],
                        "geometry_provenance": "generated_design_hypothesis",
                        "proposal": outcome["proposal"],
                        "checks": outcome["checks"],
                    },
                )
                files = sorted(
                    p.relative_to(dest / "artifacts").as_posix()
                    for p in (dest / "artifacts").rglob("*")
                    if p.is_file()
                )
                _write(
                    dest / "status.json",
                    {
                        **state,
                        "status": outcome["status"],
                        "outcome": outcome,
                        "artifacts": files,
                    },
                )
                ensure_job_storage()
            except Exception as exc:
                code = (
                    str(exc)
                    if isinstance(exc, ReconstructionError)
                    else "execution_failed"
                )
                if code == "reconstruction_job_storage_exceeded":
                    shutil.rmtree(dest / "artifacts", ignore_errors=True)
                    for oversized in ("outcome.json", "baseline.json"):
                        (dest / oversized).unlink(missing_ok=True)
                _write(
                    dest / "status.json",
                    {
                        **state,
                        "status": "failed",
                        "error": code,
                        "partial_result_available": (dest / "baseline.json").exists(),
                        "baseline": _read(dest / "baseline.json")
                        if (dest / "baseline.json").exists()
                        else None,
                        "error_type": type(exc).__name__,
                    },
                )

        try:
            executor.submit_reserved(process)
        except Exception as exc:
            _write(dest / "status.json", {
                **state,
                "status": "failed",
                "error": "job_submission_failed",
                "error_type": type(exc).__name__,
                "retryable": True,
            })
            raise HTTPException(503, "job_submission_failed") from exc
        return state

    @router.post("/api/v1/reconstruction/{job_id}/refine", status_code=202)
    def refine(
        job_id: str,
        body: RefinementRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if provider is None:
            raise HTTPException(503, "reconstruction_model_unavailable")
        dest = folder(job_id)
        parent = _read(dest / "status.json")
        if parent["status"] in ("queued", "running"):
            raise HTTPException(409, "parent_not_finished")
        if (
            not parent.get("refinement_supported")
            or not (dest / "input-context.json").exists()
        ):
            raise HTTPException(409, "regenerate_original_to_enable_refinement")
        if parent.get("revision", 1) >= _MAX_JOBS_PER_RUN:
            raise HTTPException(409, "refinement_limit_reached")
        proposal = (
            (parent.get("outcome") or {}).get("proposal")
            or parent.get("baseline")
            or {}
        )
        questions = set(proposal.get("missing_information", [])) | {
            a["question"] for a in parent.get("clarifications", [])
        }
        if any(answer.question not in questions for answer in body.answers):
            raise HTTPException(422, "question_not_in_parent")
        answers = {a["question"]: a["answer"] for a in parent.get("clarifications", [])}
        answers.update({a.question: a.answer for a in body.answers})
        if len(answers) > 32:
            raise HTTPException(422, "too_many_accumulated_answers")
        try:
            content = (dest / "source.png").read_bytes()
            source_context = _read(dest / "input-context.json")
        except (OSError, ValueError):
            raise HTTPException(409, "frozen_input_unavailable") from None
        context_hash = sha256(
            json.dumps(source_context, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if sha256(content).hexdigest() != parent[
            "source_sha256"
        ] or context_hash != parent.get("context_sha256"):
            raise HTTPException(409, "frozen_input_changed")
        envelope = {
            **parent.get("envelope_mm", {}),
            **body.envelope_mm.model_dump(exclude_none=True),
        }
        metadata = {
            key: parent[key]
            for key in (
                "run_id",
                "ledger_revision",
                "source_sha256",
                "source_refs",
                "original_image_sha256",
            )
        }
        metadata.update(
            {
                "unit": "mm" if envelope else parent["unit"],
                "intended_use_from_user": body.intended_use
                or parent.get("intended_use_from_user", ""),
                "parent_job_id": job_id,
                "revision": parent.get("revision", 1) + 1,
                "clarifications": [
                    {"question": q, "answer": a} for q, a in answers.items()
                ],
                "envelope_mm": envelope,
                "certified_for_manufacturing": False,
            }
        )
        return enqueue(
            content,
            metadata,
            source_context,
            http_request=http_request,
            mode="refine",
            idempotency_key=idempotency_key,
            canonical_request_hash=request_hash(body),
        )

    @router.get("/api/v1/reconstruction/{job_id}")
    def status(job_id: str):
        return _read(folder(job_id) / "status.json")

    @router.get("/api/v1/reconstruction/{job_id}/source.png")
    def source(job_id: str):
        path = folder(job_id) / "source.png"
        if not path.exists():
            raise HTTPException(404, "source_not_found")
        return FileResponse(path, media_type="image/png")

    @router.get("/api/v1/reconstruction/{job_id}/artifacts/{filename:path}")
    def artifact(job_id: str, filename: str):
        dest = folder(job_id)
        state = _read(dest / "status.json")
        if filename not in state.get("artifacts", []):
            raise HTTPException(404, "artifact_not_found")
        path = (dest / "artifacts" / filename).resolve()
        if not path.is_relative_to((dest / "artifacts").resolve()):
            raise HTTPException(404, "artifact_not_found")
        return FileResponse(path)

    return router
