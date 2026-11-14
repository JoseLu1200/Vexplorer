"""Bounded source-bound visual context for autonomous general-furniture review.

Raster pixels are presentation evidence only.  Source coordinates and ledger
references remain metadata and are the only bridge back to observed geometry.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from math import cos, floor, hypot, radians, sin
from pathlib import Path
from typing import Literal

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from backend.app.agente.vision import RenderedView, VisionMark
from backend.app.contratos.modelos import Bounds2D, DrawingExtraction, Point2D


_AUTHORITY = "visual_context_not_measurement_source"
_MARGIN_PX = 24


@dataclass(frozen=True, kw_only=True)
class VisualEvidenceArtifact:
    reference: str
    media_type: Literal["image/png"]
    content: bytes
    source_sha256: str
    image_sha256: str
    width_px: int
    height_px: int
    source_view_ids: tuple[str, ...]
    source_contour_ids: tuple[str, ...]
    source_document_refs: tuple[str, ...]
    crop_bounds_source: tuple[float, float, float, float]
    marks: tuple[VisionMark, ...]
    warnings: tuple[str, ...]
    authority: Literal["visual_context_not_measurement_source"] = _AUTHORITY


def _source_digest(path: Path, max_source_bytes: int) -> tuple[str, int]:
    if max_source_bytes <= 0:
        raise ValueError("visual_evidence_budget_exceeded")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("visual_evidence_source_unavailable") from exc
    if size <= 0 or size > max_source_bytes:
        raise ValueError("visual_evidence_budget_exceeded")
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), size


def _refs(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) != len(set(values)) or any(not item.strip() for item in values):
        raise ValueError("invalid_source_document_refs")
    return values


def _point_xy(point: Point2D) -> tuple[float, float]:
    return float(point.x), float(point.y)


def _selected_points(extraction: DrawingExtraction, entity: object) -> tuple[Point2D, ...]:
    metric = getattr(entity, "points_mm")
    return metric if extraction.coordinate_unit == "mm" and metric is not None else getattr(entity, "source_points")


def _clean_view(
    extraction: DrawingExtraction, view_id: str, max_dimension_px: int
) -> RenderedView:
    """Draw literal ledger geometry without SoM labels or structural inference."""
    view = next(item for item in extraction.views if item.id == view_id)
    bounds = view.bounds_mm if extraction.coordinate_unit == "mm" else view.bounds_source
    span_x = max(float(bounds.max_x - bounds.min_x), 1e-9)
    span_y = max(float(bounds.max_y - bounds.min_y), 1e-9)
    scale = (max_dimension_px - 2 * _MARGIN_PX) / max(span_x, span_y)
    width = max(2 * _MARGIN_PX + 1, floor(span_x * scale + 0.5) + 2 * _MARGIN_PX)
    height = max(2 * _MARGIN_PX + 1, floor(span_y * scale + 0.5) + 2 * _MARGIN_PX)

    def pixel(point: Point2D) -> tuple[float, float]:
        return (
            _MARGIN_PX + (float(point.x) - float(bounds.min_x)) * scale,
            height - _MARGIN_PX - (float(point.y) - float(bounds.min_y)) * scale,
        )

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def draw_dashed(points: tuple[tuple[float, float], ...]) -> None:
        for start, end in zip(points, points[1:]):
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = hypot(dx, dy)
            if length <= 0:
                continue
            offset = 0.0
            while offset < length:
                stop = min(offset + 7.0, length)
                draw.line(
                    (
                        (start[0] + dx * offset / length, start[1] + dy * offset / length),
                        (start[0] + dx * stop / length, start[1] + dy * stop / length),
                    ),
                    fill=(110, 120, 130),
                    width=1,
                )
                offset += 11.0

    entity_ids = set(view.entity_ids)
    for entity in sorted(
        (item for item in extraction.entities if item.id in entity_ids),
        key=lambda item: item.id,
    ):
        circular = entity.circular
        if circular is not None:
            center = (
                circular.center_mm
                if extraction.coordinate_unit == "mm"
                else circular.center_source
            )
            radius = (
                circular.radius_mm
                if extraction.coordinate_unit == "mm"
                else circular.radius_source
            )
            if center is None or radius is None:
                continue
            start = float(circular.start_angle_deg or 0.0)
            sweep = (
                360.0
                if circular.kind == "circle"
                else (float(circular.end_angle_deg) - start) % 360.0
            )
            points = tuple(
                Point2D(
                    x=float(center.x) + float(radius) * cos(radians(start + sweep * index / 64)),
                    y=float(center.y) + float(radius) * sin(radians(start + sweep * index / 64)),
                )
                for index in range(65)
            )
        else:
            points = _selected_points(extraction, entity)
        pixels = tuple(pixel(point) for point in points)
        if len(pixels) >= 2:
            if entity.linetype:
                draw_dashed(pixels)
            else:
                draw.line(pixels, fill=(110, 120, 130), width=1)
        elif pixels:
            x, y = pixels[0]
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(110, 120, 130))
    for contour in sorted(
        (item for item in extraction.contours if item.view_id == view_id),
        key=lambda item: item.id,
    ):
        points = (
            contour.points_mm
            if extraction.coordinate_unit == "mm" and contour.points_mm is not None
            else contour.points_source
        )
        pixels = tuple(pixel(point) for point in points)
        if contour.closed and pixels and pixels[0] != pixels[-1]:
            pixels = (*pixels, pixels[0])
        if len(pixels) >= 2:
            draw.line(pixels, fill=(25, 35, 45), width=2)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    png = buffer.getvalue()
    return RenderedView(
        view_id=view_id,
        png=png,
        width_px=width,
        height_px=height,
        sha256=sha256(png).hexdigest(),
        marks=(),
    )


@dataclass(frozen=True)
class _SpatialRegion:
    bounds: tuple[float, float, float, float]
    contour_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]


def _overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    margin: float,
) -> bool:
    return not (
        left[2] + margin < right[0]
        or right[2] + margin < left[0]
        or left[3] + margin < right[1]
        or right[3] + margin < left[1]
    )


def _spatial_regions(
    extraction: DrawingExtraction, view_id: str
) -> tuple[_SpatialRegion, ...]:
    view = next(item for item in extraction.views if item.id == view_id)
    contours = [item for item in extraction.contours if item.view_id == view_id]
    if len(contours) < 2:
        return ()
    boxes = []
    for contour in contours:
        points = contour.points_source
        boxes.append(
            (
                min(float(point.x) for point in points),
                min(float(point.y) for point in points),
                max(float(point.x) for point in points),
                max(float(point.y) for point in points),
                {contour.id},
                set(contour.source_entity_ids),
            )
        )
    margin = 0.02 * max(
        float(view.bounds_source.max_x - view.bounds_source.min_x),
        float(view.bounds_source.max_y - view.bounds_source.min_y),
        1.0,
    )
    changed = True
    while changed:
        changed = False
        merged = []
        while boxes:
            current = boxes.pop(0)
            match = next(
                (
                    index
                    for index, candidate in enumerate(boxes)
                    if _overlap(current[:4], candidate[:4], margin)
                ),
                None,
            )
            if match is None:
                merged.append(current)
                continue
            candidate = boxes.pop(match)
            boxes.insert(
                0,
                (
                    min(current[0], candidate[0]),
                    min(current[1], candidate[1]),
                    max(current[2], candidate[2]),
                    max(current[3], candidate[3]),
                    current[4] | candidate[4],
                    current[5] | candidate[5],
                ),
            )
            changed = True
        boxes = merged
    if len(boxes) < 2:
        return ()
    return tuple(
        _SpatialRegion(
            bounds=(box[0], box[1], box[2], box[3]),
            contour_ids=tuple(sorted(box[4])),
            entity_ids=tuple(sorted(box[5])),
        )
        for box in sorted(boxes, key=lambda item: (item[1], item[0], item[3], item[2]))
    )


def _region_extraction(
    extraction: DrawingExtraction, view_id: str, region: _SpatialRegion
) -> DrawingExtraction:
    view = next(item for item in extraction.views if item.id == view_id)
    entity_ids = set(region.entity_ids)
    bounds = Bounds2D(
        min_x=region.bounds[0],
        min_y=region.bounds[1],
        max_x=region.bounds[2],
        max_y=region.bounds[3],
    )
    metric_bounds = (
        Bounds2D(
            min_x=bounds.min_x * extraction.unit_scale_to_mm,
            min_y=bounds.min_y * extraction.unit_scale_to_mm,
            max_x=bounds.max_x * extraction.unit_scale_to_mm,
            max_y=bounds.max_y * extraction.unit_scale_to_mm,
        )
        if extraction.unit_scale_to_mm is not None
        else None
    )
    filtered_view = view.model_copy(
        update={
            "entity_ids": tuple(sorted(entity_ids)),
            "bounds_source": bounds,
            "bounds_mm": metric_bounds,
        }
    )
    return extraction.model_copy(
        update={
            "entities": tuple(item for item in extraction.entities if item.id in entity_ids),
            "views": (filtered_view,),
            "contours": tuple(
                item for item in extraction.contours if item.id in region.contour_ids
            ),
            "texts": tuple(
                item for item in extraction.texts if item.source_entity_id in entity_ids
            ),
            "dimension_graphics": tuple(
                item
                for item in extraction.dimension_graphics
                if item.source_entity_id in entity_ids
            ),
        }
    )


def _cad_annotation_layer(
    rendered: RenderedView,
    extraction: DrawingExtraction,
    view_id: str,
) -> tuple[bytes, tuple[str, ...]]:
    """Overlay only typed source annotations; never infer geometry from pixels."""
    view = next(item for item in extraction.views if item.id == view_id)
    bounds = view.bounds_mm if extraction.coordinate_unit == "mm" else view.bounds_source
    span_x = max(float(bounds.max_x - bounds.min_x), 1e-9)
    span_y = max(float(bounds.max_y - bounds.min_y), 1e-9)
    drawable_width = max(rendered.width_px - 2 * _MARGIN_PX, 1)
    drawable_height = max(rendered.height_px - 2 * _MARGIN_PX, 1)
    scale = min(drawable_width / span_x, drawable_height / span_y)

    def pixel(point: Point2D) -> tuple[float, float]:
        return (
            _MARGIN_PX + (float(point.x) - float(bounds.min_x)) * scale,
            rendered.height_px
            - _MARGIN_PX
            - (float(point.y) - float(bounds.min_y)) * scale,
        )

    image = Image.open(BytesIO(rendered.png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    rendered_annotations = 0
    for item in sorted(
        (item for item in extraction.dimension_graphics if item.view_id == view_id),
        key=lambda item: item.id,
    ):
        points = (
            (item.extension_start_a_mm, item.extension_start_a_source),
            (item.extension_start_b_mm, item.extension_start_b_source),
            (item.dimension_start_mm, item.dimension_start_source),
            (item.dimension_end_mm, item.dimension_end_source),
        )
        selected = tuple(
            metric if extraction.coordinate_unit == "mm" else source
            for metric, source in points
        )
        draw.line((pixel(selected[0]), pixel(selected[2])), fill=(35, 70, 170), width=1)
        draw.line((pixel(selected[1]), pixel(selected[3])), fill=(35, 70, 170), width=1)
        draw.line((pixel(selected[2]), pixel(selected[3])), fill=(35, 70, 170), width=1)
        text_point = (
            item.text_position_mm
            if extraction.coordinate_unit == "mm"
            else item.text_position_source
        )
        draw.text(pixel(text_point), item.display_text[:200], fill=(20, 45, 130), font=font)
        rendered_annotations += 1
    for item in sorted(
        (item for item in extraction.texts if item.view_id == view_id),
        key=lambda item: item.id,
    ):
        point = (
            item.position_mm
            if extraction.coordinate_unit == "mm"
            else item.position_source
        )
        if point is not None:
            draw.text(pixel(point), item.text[:200], fill=(70, 35, 120), font=font)
            rendered_annotations += 1
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    warnings = (
        (f"source_annotations_rendered:{rendered_annotations}",)
        if rendered_annotations
        else ()
    )
    return buffer.getvalue(), warnings


def _contour_marks(
    content: bytes,
    extraction: DrawingExtraction,
    view_id: str,
    *,
    width_px: int,
    height_px: int,
) -> tuple[bytes, tuple[VisionMark, ...]]:
    """Add one visible, artifact-scoped label per source contour."""
    view = next(item for item in extraction.views if item.id == view_id)
    bounds = view.bounds_mm if extraction.coordinate_unit == "mm" else view.bounds_source
    span_x = max(float(bounds.max_x - bounds.min_x), 1e-9)
    span_y = max(float(bounds.max_y - bounds.min_y), 1e-9)
    scale = min(
        max(width_px - 2 * _MARGIN_PX, 1) / span_x,
        max(height_px - 2 * _MARGIN_PX, 1) / span_y,
    )

    def pixel(point: Point2D) -> tuple[float, float]:
        return (
            _MARGIN_PX + (float(point.x) - float(bounds.min_x)) * scale,
            height_px - _MARGIN_PX - (float(point.y) - float(bounds.min_y)) * scale,
        )

    image = Image.open(BytesIO(content)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    marks = []
    for index, contour in enumerate(
        sorted(
            (item for item in extraction.contours if item.view_id == view_id),
            key=lambda item: item.id,
        ),
        start=1,
    ):
        points = (
            contour.points_mm
            if extraction.coordinate_unit == "mm" and contour.points_mm is not None
            else contour.points_source
        )
        anchor = pixel(
            Point2D(
                x=sum(float(point.x) for point in points) / len(points),
                y=sum(float(point.y) for point in points) / len(points),
            )
        )
        mark = VisionMark(
            mark_id=f"M{index:03d}",
            source_kind="contour",
            source_id=contour.id,
        )
        marks.append(mark)
        box = draw.textbbox(anchor, mark.mark_id, font=font, anchor="mm")
        draw.rectangle(
            (box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1),
            fill=(255, 235, 115),
            outline=(25, 35, 45),
        )
        draw.text(anchor, mark.mark_id, fill=(10, 15, 20), font=font, anchor="mm")
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue(), tuple(marks)


def _cad_artifacts(
    source: Path,
    extraction: DrawingExtraction,
    *,
    source_sha256: str,
    source_document_refs: tuple[str, ...],
    max_views: int,
    max_artifacts: int,
    max_dimension_px: int,
    max_total_pixels: int,
    max_total_png_bytes: int,
) -> tuple[VisualEvidenceArtifact, ...]:
    if extraction.drawing_id != f"drawing-{source_sha256[:16]}":
        raise ValueError("visual_evidence_source_mismatch")
    views = tuple(sorted(extraction.views, key=lambda item: item.id))
    if not views:
        raise ValueError("visual_evidence_geometry_unavailable")
    if len(views) > max_views:
        raise ValueError("visual_evidence_budget_exceeded")
    if len(views) > max_artifacts:
        raise ValueError("visual_evidence_budget_exceeded")
    regions_by_view = {
        view.id: _spatial_regions(extraction, view.id) for view in views
    }
    region_candidates = [
        (view.id, index, region)
        for view in views
        for index, region in enumerate(regions_by_view[view.id], start=1)
    ]
    region_slots = max_artifacts - len(views)
    if len(region_candidates) > region_slots:
        region_candidates.sort(key=lambda item: (
            -len(item[2].contour_ids),
            item[0], item[1], item[2].bounds,
        ))
    selected_regions = region_candidates[:region_slots]
    artifact_count = len(views) + len(selected_regions)
    truncation_warning = (
        f"spatial_region_crops_truncated:{len(selected_regions)}_of_{len(region_candidates)}"
        if len(selected_regions) < len(region_candidates)
        else None
    )
    # Worst-case allocation is checked before render_view allocates any image.
    if artifact_count * max_dimension_px * max_dimension_px > max_total_pixels:
        raise ValueError("visual_evidence_budget_exceeded")

    artifacts: list[VisualEvidenceArtifact] = []
    used_png_bytes = 0
    for view in views:
        rendered = _clean_view(extraction, view.id, max_dimension_px)
        content, warnings = _cad_annotation_layer(rendered, extraction, view.id)
        content, overview_marks = _contour_marks(
            content,
            extraction,
            view.id,
            width_px=rendered.width_px,
            height_px=rendered.height_px,
        )
        used_png_bytes += len(content)
        if used_png_bytes > max_total_png_bytes:
            raise ValueError("visual_evidence_budget_exceeded")
        bounds = view.bounds_source
        contour_ids = tuple(
            sorted(item.id for item in extraction.contours if item.view_id == view.id)
        )
        artifacts.append(
            VisualEvidenceArtifact(
                reference=f"{source_sha256}:view:{view.id}:overview",
                media_type="image/png",
                content=content,
                source_sha256=source_sha256,
                image_sha256=sha256(content).hexdigest(),
                width_px=rendered.width_px,
                height_px=rendered.height_px,
                source_view_ids=(view.id,),
                source_contour_ids=contour_ids,
                source_document_refs=source_document_refs,
                crop_bounds_source=(
                    float(bounds.min_x),
                    float(bounds.min_y),
                    float(bounds.max_x),
                    float(bounds.max_y),
                ),
                marks=overview_marks,
                warnings=(
                    "clean_source_overview",
                    *(
                        (
                            "source_linetypes_preserved:"
                            + ",".join(
                                sorted(
                                    {
                                        item.linetype
                                        for item in extraction.entities
                                        if item.id in view.entity_ids and item.linetype
                                    }
                                )
                            ),
                        )
                        if any(
                            item.id in view.entity_ids and item.linetype
                            for item in extraction.entities
                        )
                        else ()
                    ),
                    *warnings,
                    *((truncation_warning,) if truncation_warning else ()),
                ),
            )
        )
    for view_id, index, region in selected_regions:
        selected = _region_extraction(extraction, view_id, region)
        region_rendered = _clean_view(selected, view_id, max_dimension_px)
        region_content, annotation_warnings = _cad_annotation_layer(
            region_rendered, selected, view_id
        )
        region_content, region_marks = _contour_marks(
            region_content,
            selected,
            view_id,
            width_px=region_rendered.width_px,
            height_px=region_rendered.height_px,
        )
        used_png_bytes += len(region_content)
        if used_png_bytes > max_total_png_bytes:
            raise ValueError("visual_evidence_budget_exceeded")
        artifacts.append(
            VisualEvidenceArtifact(
                reference=f"{source_sha256}:view:{view_id}:region-{index:03d}",
                media_type="image/png",
                content=region_content,
                source_sha256=source_sha256,
                image_sha256=sha256(region_content).hexdigest(),
                width_px=region_rendered.width_px,
                height_px=region_rendered.height_px,
                source_view_ids=(view_id,),
                source_contour_ids=region.contour_ids,
                source_document_refs=source_document_refs,
                crop_bounds_source=region.bounds,
                marks=region_marks,
                warnings=(
                    "spatial_region_not_semantic_view",
                    *annotation_warnings,
                ),
            )
        )
    return tuple(artifacts)


def _pdf_artifact(
    source: Path,
    page_number: int,
    *,
    source_sha256: str,
    source_document_refs: tuple[str, ...],
    max_dimension_px: int,
    max_total_pixels: int,
    max_total_png_bytes: int,
) -> tuple[VisualEvidenceArtifact, ...]:
    try:
        document = pymupdf.open(source)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValueError("visual_evidence_source_unavailable") from exc
    try:
        if document.needs_pass:
            raise ValueError("visual_evidence_source_unavailable")
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("selected_pdf_page_out_of_range")
        page = document[page_number - 1]
        width_points = float(page.rect.width)
        height_points = float(page.rect.height)
        scale = max_dimension_px / max(width_points, height_points)
        width_px = max(1, floor(width_points * scale + 0.5))
        height_px = max(1, floor(height_points * scale + 0.5))
        if width_px * height_px > max_total_pixels:
            raise ValueError("visual_evidence_budget_exceeded")
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        content = pixmap.tobytes("png")
    finally:
        document.close()
    if len(content) > max_total_png_bytes:
        raise ValueError("visual_evidence_budget_exceeded")
    return (
        VisualEvidenceArtifact(
            reference=f"{source_sha256}:pdf-page:{page_number:04d}",
            media_type="image/png",
            content=content,
            source_sha256=source_sha256,
            image_sha256=sha256(content).hexdigest(),
            width_px=width_px,
            height_px=height_px,
            source_view_ids=(f"pdf-page-{page_number:04d}",),
            source_contour_ids=(),
            source_document_refs=source_document_refs,
            crop_bounds_source=(0.0, 0.0, width_points, height_points),
            marks=(),
            warnings=("pdf_visual_context_only",),
        ),
    )


def render_visual_evidence(
    source_path: Path,
    *,
    extraction: DrawingExtraction | None = None,
    selected_pdf_page: int | None = None,
    source_document_refs: tuple[str, ...] = (),
    max_views: int = 8,
    max_artifacts: int = 4,
    max_dimension_px: int = 1024,
    max_total_pixels: int = 8 * 1024 * 1024,
    max_total_png_bytes: int = 8 * 1024 * 1024,
    max_source_bytes: int = 20 * 1024 * 1024,
) -> tuple[VisualEvidenceArtifact, ...]:
    """Render bounded visual context from normalized DXF or one actual PDF page."""
    if max_dimension_px < 2 * _MARGIN_PX + 1 or any(
        value <= 0
        for value in (
            max_views,
            max_artifacts,
            max_dimension_px,
            max_total_pixels,
            max_total_png_bytes,
            max_source_bytes,
        )
    ):
        raise ValueError("visual_evidence_budget_exceeded")
    source = source_path.resolve()
    suffix = source.suffix.lower()
    if suffix == ".dwg":
        raise ValueError("normalized_dxf_required_for_dwg")
    source_document_refs = _refs(source_document_refs)
    source_sha256, _ = _source_digest(source, max_source_bytes)
    if suffix == ".pdf":
        if selected_pdf_page is None:
            raise ValueError("selected_pdf_page_required")
        return _pdf_artifact(
            source,
            selected_pdf_page,
            source_sha256=source_sha256,
            source_document_refs=source_document_refs,
            max_dimension_px=max_dimension_px,
            max_total_pixels=max_total_pixels,
            max_total_png_bytes=max_total_png_bytes,
        )
    if suffix != ".dxf":
        raise ValueError("visual_evidence_source_type_unsupported")
    if extraction is None:
        raise ValueError("drawing_extraction_required")
    return _cad_artifacts(
        source,
        extraction,
        source_sha256=source_sha256,
        source_document_refs=source_document_refs,
        max_views=max_views,
        max_artifacts=max_artifacts,
        max_dimension_px=max_dimension_px,
        max_total_pixels=max_total_pixels,
        max_total_png_bytes=max_total_png_bytes,
    )
