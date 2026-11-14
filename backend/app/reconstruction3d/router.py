from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import re
from uuid import uuid4
from threading import RLock

from fastapi import APIRouter, HTTPException
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
    *, root: Path, context_loader, provider, executor
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

    @router.post("/api/v1/runs/{run_id}/reconstruction", status_code=202)
    def submit(run_id: str, body: ReconstructionRequest):
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
        )

    def enqueue(content, metadata, source_context):
        if not executor.reserve():
            raise HTTPException(429, "job_queue_full")
        job_id = uuid4().hex
        dest = store / job_id
        state = {
            **metadata,
            "job_id": job_id,
            "status": "queued",
            "refinement_supported": True,
            "context_sha256": sha256(
                json.dumps(source_context, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest(),
        }
        try:
            dest.mkdir()
            (dest / "source.png").write_bytes(content)
            _write(dest / "input-context.json", source_context)
            _write(dest / "status.json", state)
        except Exception:
            executor.release()
            raise

        def process():
            try:
                _write(dest / "status.json", {**state, "status": "running"})
                outcome = reconstruct(
                    content,
                    provider=provider,
                    known_unit=state["unit"],
                    intended_use=state["intended_use_from_user"],
                    source_context=source_context,
                    clarifications=state["clarifications"],
                    envelope_mm=state["envelope_mm"],
                    on_baseline=lambda p: _write(dest / "baseline.json", p),
                )
                _write(dest / "outcome.json", outcome)
                export_package(
                    AssemblyProposal.model_validate(outcome["proposal"]),
                    dest / "artifacts",
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
            except Exception as exc:
                code = (
                    str(exc)
                    if isinstance(exc, ReconstructionError)
                    else "execution_failed"
                )
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

        executor.submit_reserved(process)
        return state

    @router.post("/api/v1/reconstruction/{job_id}/refine", status_code=202)
    def refine(job_id: str, body: RefinementRequest):
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
        if parent.get("revision", 1) >= 11:
            raise HTTPException(409, "refinement_limit_reached")
        proposal = (
            (parent.get("outcome") or {}).get("proposal")
            or parent.get("baseline")
            or {}
        )
        questions = set(proposal.get("missing_information", []))
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
        return enqueue(content, metadata, source_context)

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
