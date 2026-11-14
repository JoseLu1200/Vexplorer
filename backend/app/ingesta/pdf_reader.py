from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from math import ceil, isfinite
from pathlib import Path
from typing import Literal

import ezdxf
import pymupdf


MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_VECTOR_PATHS_PER_PAGE = 100_000
MAX_TOTAL_VECTOR_PATHS = 250_000
MAX_VECTOR_SEGMENTS_PER_PAGE = 200_000
MAX_TOTAL_VECTOR_SEGMENTS = 500_000
MAX_TOTAL_VECTOR_POINTS = 1_000_000
MAX_TOTAL_PREVIEW_PIXELS = 50_000_000


class PdfIngestionError(ValueError):
    pass


@dataclass(frozen=True)
class PdfScaleConfirmation:
    mm_per_pdf_point: float
    confirmed_by: str
    confirmed_at: datetime

    def __post_init__(self) -> None:
        if not isfinite(self.mm_per_pdf_point) or self.mm_per_pdf_point <= 0:
            raise ValueError("mm_per_pdf_point must be a positive finite value")
        if not self.confirmed_by.strip():
            raise ValueError("confirmed_by cannot be blank")
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must include a timezone")


@dataclass(frozen=True)
class PdfVectorSegment:
    operation: str
    points: tuple[tuple[float, float], ...]
    convertible_to_dxf: bool


@dataclass(frozen=True)
class PdfVectorPath:
    id: str
    segments: tuple[PdfVectorSegment, ...]
    source_layer: str | None
    stroke_width_points: float | None


@dataclass(frozen=True)
class PdfTextBlock:
    id: str
    bbox_points: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True)
class PdfPageIngestion:
    page_number: int
    width_points: float
    height_points: float
    width_mm: float | None
    height_mm: float | None
    rotation: int
    content_kind: Literal["vector", "raster", "mixed", "empty"]
    vector_paths: tuple[PdfVectorPath, ...]
    text_blocks: tuple[PdfTextBlock, ...]
    image_count: int
    preview_path: Path
    normalized_dxf_path: Path | None
    normalized_layer: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PdfIngestionResult:
    source_path: Path
    source_name: str
    source_media_type: str
    source_size_bytes: int
    source_sha256: str
    source_unit: Literal["unknown", "mm"]
    unit_scale_to_mm: float | None
    scale_provenance: PdfScaleConfirmation | None
    status: Literal["needs_review"]
    pages: tuple[PdfPageIngestion, ...]
    warnings: tuple[str, ...]


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _xy(value: object) -> tuple[float, float]:
    return (float(value.x), float(value.y))  # type: ignore[attr-defined]


def _segments(path: dict[str, object]) -> tuple[PdfVectorSegment, ...]:
    result: list[PdfVectorSegment] = []
    for item in path.get("items", ()):  # type: ignore[union-attr]
        operation = str(item[0])
        if operation == "l":
            points = (_xy(item[1]), _xy(item[2]))
            supported = True
        elif operation == "re":
            rect = item[1]
            points = (
                (float(rect.x0), float(rect.y0)), (float(rect.x1), float(rect.y0)),
                (float(rect.x1), float(rect.y1)), (float(rect.x0), float(rect.y1)),
            )
            supported = True
        elif operation == "qu":
            quad = item[1]
            points = (_xy(quad.ul), _xy(quad.ur), _xy(quad.lr), _xy(quad.ll))
            supported = True
        elif operation == "c":
            points = tuple(_xy(point) for point in item[1:])
            supported = False
        else:
            points = ()
            supported = False
        if points and not all(isfinite(value) for point in points for value in point):
            raise PdfIngestionError("PDF vector path contains non-finite coordinates")
        result.append(PdfVectorSegment(operation, points, supported))
    return tuple(result)


def _transform(point: tuple[float, float], height: float, scale: float) -> tuple[float, float]:
    return (point[0] * scale, (height - point[1]) * scale)


def _write_page_dxf(
    target: Path,
    *,
    page_number: int,
    height_points: float,
    paths: tuple[PdfVectorPath, ...],
    texts: tuple[PdfTextBlock, ...],
    scale: PdfScaleConfirmation | None,
) -> Path | None:
    convertible = any(segment.convertible_to_dxf for path in paths for segment in path.segments)
    if not convertible and not texts:
        return None
    factor = scale.mm_per_pdf_point if scale is not None else 1.0
    document = ezdxf.new("R2018")
    document.header["$INSUNITS"] = 4 if scale is not None else 0
    layer = f"PDF_PAGE_{page_number:04d}"
    document.layers.add(layer)
    modelspace = document.modelspace()
    for path in paths:
        for segment in path.segments:
            if not segment.convertible_to_dxf:
                continue
            points = [_transform(point, height_points, factor) for point in segment.points]
            if segment.operation == "l":
                modelspace.add_line(points[0], points[1], dxfattribs={"layer": layer})
            else:
                modelspace.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
    for block in texts:
        x0, y0, _, _ = block.bbox_points
        modelspace.add_text(
            block.text.replace("\n", " ").strip()[:4096],
            dxfattribs={"layer": layer, "insert": _transform((x0, y0), height_points, factor)},
        )
    document.saveas(target)
    return target


def ingest_pdf(
    source: Path,
    artifact_dir: Path,
    *,
    scale: PdfScaleConfirmation | None = None,
    raster_dpi: int = 144,
    max_pages: int = MAX_PDF_PAGES,
    max_vectors_per_page: int = MAX_VECTOR_PATHS_PER_PAGE,
    max_total_vectors: int = MAX_TOTAL_VECTOR_PATHS,
    max_segments_per_page: int = MAX_VECTOR_SEGMENTS_PER_PAGE,
    max_total_segments: int = MAX_TOTAL_VECTOR_SEGMENTS,
    max_total_vector_points: int = MAX_TOTAL_VECTOR_POINTS,
    max_total_preview_pixels: int = MAX_TOTAL_PREVIEW_PIXELS,
    max_source_bytes: int = MAX_PDF_BYTES,
) -> PdfIngestionResult:
    """Extract PDF evidence and per-page DXFs without inferring scale or raster geometry."""
    source = source.resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise PdfIngestionError("PDF source must be an existing .pdf file")
    size = source.stat().st_size
    if size <= 0 or size > max_source_bytes:
        raise PdfIngestionError(f"PDF source size outside allowed range: {size} bytes")
    if any(limit <= 0 for limit in (
        raster_dpi, max_pages, max_vectors_per_page, max_total_vectors,
        max_segments_per_page, max_total_segments, max_total_vector_points,
        max_total_preview_pixels,
    )):
        raise ValueError("PDF limits and raster_dpi must be positive")
    try:
        document = pymupdf.open(source)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise PdfIngestionError("cannot open PDF") from exc
    try:
        if document.needs_pass:
            raise PdfIngestionError("encrypted PDF requires a password and is not supported")
        if document.page_count > max_pages:
            raise PdfIngestionError(f"PDF page limit exceeded: {document.page_count} > {max_pages}")

        page_inputs: list[tuple[object, list[dict[str, object]], list[tuple[object, ...]], int]] = []
        total_vectors = 0
        total_segments = 0
        total_points = 0
        total_pixels = 0
        for page in document:
            drawings = page.get_drawings()
            if len(drawings) > max_vectors_per_page:
                raise PdfIngestionError(
                    f"PDF vector path limit exceeded on page {page.number + 1}: "
                    f"{len(drawings)} > {max_vectors_per_page}"
                )
            total_vectors += len(drawings)
            if total_vectors > max_total_vectors:
                raise PdfIngestionError(f"PDF total vector path limit exceeded: {total_vectors} > {max_total_vectors}")
            segment_count = sum(len(path.get("items", ())) for path in drawings)
            if segment_count > max_segments_per_page:
                raise PdfIngestionError(
                    f"PDF vector segment limit exceeded on page {page.number + 1}: "
                    f"{segment_count} > {max_segments_per_page}"
                )
            point_count = sum(
                max(0, len(item) - 1)
                for path in drawings
                for item in path.get("items", ())
            )
            total_segments += segment_count
            total_points += point_count
            if total_segments > max_total_segments:
                raise PdfIngestionError(
                    f"PDF total vector segment limit exceeded: {total_segments} > {max_total_segments}"
                )
            if total_points > max_total_vector_points:
                raise PdfIngestionError(
                    f"PDF total vector point limit exceeded: {total_points} > {max_total_vector_points}"
                )
            pixel_width = ceil(float(page.rect.width) * raster_dpi / 72)
            pixel_height = ceil(float(page.rect.height) * raster_dpi / 72)
            total_pixels += pixel_width * pixel_height
            if total_pixels > max_total_preview_pixels:
                raise PdfIngestionError(
                    f"PDF preview pixel limit exceeded: {total_pixels} > {max_total_preview_pixels}"
                )
            text_blocks = page.get_text("blocks", sort=False)
            page_inputs.append((page, drawings, text_blocks, len(page.get_image_info())))

        artifact_dir = artifact_dir.resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        pages: list[PdfPageIngestion] = []
        warnings: list[str] = [] if scale is not None else ["source_unit_unknown"]
        for page, drawings, raw_text_blocks, image_count in page_inputs:
            page_number = int(page.number) + 1  # type: ignore[attr-defined]
            width = float(page.mediabox.width)  # type: ignore[attr-defined]
            height = float(page.mediabox.height)  # type: ignore[attr-defined]
            paths = tuple(
                PdfVectorPath(
                    id=f"pdf-page-{page_number}-path-{index}",
                    segments=_segments(raw_path),
                    source_layer=(str(raw_path.get("layer") or "").strip() or None),
                    stroke_width_points=(
                        float(raw_path["width"]) if raw_path.get("width") is not None else None
                    ),
                )
                for index, raw_path in enumerate(drawings, start=1)
            )
            text_blocks = tuple(
                PdfTextBlock(
                    id=f"pdf-page-{page_number}-text-{index}",
                    bbox_points=tuple(float(value) for value in block[:4]),
                    text=str(block[4]).strip(),
                )
                for index, block in enumerate(raw_text_blocks, start=1)
                if int(block[6]) == 0 and str(block[4]).strip()
            )
            has_vector = bool(paths or text_blocks)
            if has_vector and image_count:
                kind: Literal["vector", "raster", "mixed", "empty"] = "mixed"
            elif has_vector:
                kind = "vector"
            elif image_count:
                kind = "raster"
            else:
                kind = "empty"
            page_warnings: list[str] = []
            unsupported = sum(
                not segment.convertible_to_dxf for path in paths for segment in path.segments
            )
            if unsupported:
                page_warnings.append(f"unsupported_vector_operations:{unsupported}")
            if image_count:
                page_warnings.append(
                    f"raster_page_has_no_vector_geometry:{page_number}"
                )
            visible_text = " ".join(block.text for block in text_blocks).upper()
            if scale is not None and ("DO NOT SCALE" in visible_text or "NO ESCALAR" in visible_text):
                page_warnings.append(
                    f"scale_conflicts_with_document_note:page={page_number}:do_not_scale"
                )
            preview = artifact_dir / f"page-{page_number:04d}.png"
            page.get_pixmap(dpi=raster_dpi, alpha=False).save(preview)  # type: ignore[attr-defined]
            normalized = _write_page_dxf(
                artifact_dir / f"page-{page_number:04d}.dxf",
                page_number=page_number,
                height_points=height,
                paths=paths,
                texts=text_blocks,
                scale=scale,
            )
            warnings.extend(page_warnings)
            pages.append(PdfPageIngestion(
                page_number=page_number,
                width_points=width,
                height_points=height,
                width_mm=width * scale.mm_per_pdf_point if scale is not None else None,
                height_mm=height * scale.mm_per_pdf_point if scale is not None else None,
                rotation=int(page.rotation),  # type: ignore[attr-defined]
                content_kind=kind,
                vector_paths=paths,
                text_blocks=text_blocks,
                image_count=image_count,
                preview_path=preview,
                normalized_dxf_path=normalized,
                normalized_layer=f"PDF_PAGE_{page_number:04d}",
                warnings=tuple(page_warnings),
            ))
    finally:
        document.close()

    return PdfIngestionResult(
        source_path=source,
        source_name=source.name,
        source_media_type="application/pdf",
        source_size_bytes=size,
        source_sha256=_digest(source),
        source_unit="mm" if scale is not None else "unknown",
        unit_scale_to_mm=scale.mm_per_pdf_point if scale is not None else None,
        scale_provenance=scale,
        status="needs_review",
        pages=tuple(pages),
        warnings=tuple(warnings),
    )
