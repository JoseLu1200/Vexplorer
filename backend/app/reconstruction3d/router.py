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
from .models import AssemblyProposal
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
        if not executor.reserve():
            raise HTTPException(429, "job_queue_full")
        job_id = uuid4().hex
        dest = store / job_id
        state = {
            "job_id": job_id,
            "run_id": run_id,
            "ledger_revision": context.ledger_revision,
            "status": "queued",
            "source_sha256": sha256(content).hexdigest(),
            "source_refs": [p.reference for p in pages],
            "original_image_sha256": [p.sha256 for p in pages],
            "unit": unit,
            "intended_use_from_user": body.intended_use,
            "certified_for_manufacturing": False,
        }
        try:
            dest.mkdir()
            (dest / "source.png").write_bytes(content)
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
                    known_unit=unit,
                    intended_use=body.intended_use,
                    source_context={
                        "dimensions": dimensions,
                        "allowed_component_source_refs": ["input"],
                        "composite_views": layout,
                    },
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
