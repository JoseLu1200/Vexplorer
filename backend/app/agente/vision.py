"""Set-of-Mark PNG renderer for public drawing-ledger geometry.

Adapted from Pablo Loureiro's optional vision renderer in commit 26dbd15.
This module never opens drawings, paths, or URLs and exposes no measurements.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from math import ceil, cos, radians, sin
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from backend.app.contratos.modelos import DrawingExtraction, Point2D


_MARGIN_PX = 24
_MIN_DIMENSION_PX = 2 * _MARGIN_PX + 1
_CURVE_SEGMENTS_FULL = 64
_ANNOTATION_KINDS = frozenset({"TEXT", "MTEXT", "ATTRIB", "DIMENSION"})


@dataclass(frozen=True)
class VisionMark:
    mark_id: str
    source_kind: Literal["contour", "entity"]
    source_id: str


@dataclass(frozen=True, kw_only=True)
class RenderedView:
    view_id: str
    png: bytes
    media_type: Literal["image/png"] = "image/png"
    width_px: int
    height_px: int
    sha256: str
    marks: tuple[VisionMark, ...]


def _coordinates(points_mm: tuple[Point2D, ...] | None, points_source: tuple[Point2D, ...]) -> tuple[tuple[float, float], ...]:
    selected = points_mm if points_mm is not None else points_source
    return tuple((float(point.x), float(point.y)) for point in selected)


def _curve_spec(entity) -> tuple[float, float, float, float, float, int] | None:
    circular = entity.circular
    if circular is None:
        return None
    metric = entity.points_mm is not None
    center = circular.center_mm if metric else circular.center_source
    radius = circular.radius_mm if metric else circular.radius_source
    if center is None or radius is None:
        return None
    if circular.kind == "circle":
        start, sweep = 0.0, 360.0
    else:
        if circular.start_angle_deg is None or circular.end_angle_deg is None:
            return None
        start = float(circular.start_angle_deg)
        sweep = (float(circular.end_angle_deg) - start) % 360.0
        if sweep == 0:
            return None
    segments = max(2, ceil(_CURVE_SEGMENTS_FULL * sweep / 360.0))
    return float(center.x), float(center.y), float(radius), start, sweep, segments


def _curve_coordinates(entity) -> tuple[tuple[float, float], ...] | None:
    spec = _curve_spec(entity)
    if spec is None:
        return None
    center_x, center_y, radius, start, sweep, segments = spec
    return tuple(
        (
            center_x + radius * cos(radians(start + sweep * index / segments)),
            center_y + radius * sin(radians(start + sweep * index / segments)),
        )
        for index in range(segments + 1)
    )


def render_view(
    extraction: DrawingExtraction,
    view_id: str,
    *,
    max_contours: int = 100,
    max_entities: int = 500,
    max_points: int = 20_000,
    max_dimension_px: int = 1024,
    max_png_bytes: int = 2_000_000,
) -> RenderedView:
    """Render one declared public view with deterministic ledger-backed marks."""
    if any(
        limit <= 0
        for limit in (max_contours, max_entities, max_points, max_png_bytes)
    ) or max_dimension_px < _MIN_DIMENSION_PX:
        raise ValueError("vision_budget_exceeded")

    view = next((candidate for candidate in extraction.views if candidate.id == view_id), None)
    if view is None:
        raise ValueError("unknown_view")
    if len(view.entity_ids) > max_entities or len(set(view.entity_ids)) != len(view.entity_ids):
        raise ValueError("vision_budget_exceeded")

    public_entity_ids = set(view.entity_ids)
    entities_by_id = {}
    for entity in extraction.entities:
        if entity.id in public_entity_ids:
            entities_by_id[entity.id] = entity
    if set(entities_by_id) != public_entity_ids:
        raise ValueError("vision_geometry_unavailable")

    contour_count = 0
    point_count = 0
    for entity in entities_by_id.values():
        point_count += len(entity.points_mm if entity.points_mm is not None else entity.source_points)
        curve = _curve_spec(entity)
        if entity.circular is not None and curve is None:
            raise ValueError("vision_geometry_unavailable")
        if curve is not None:
            point_count += curve[-1] + 1
        if point_count > max_points:
            raise ValueError("vision_budget_exceeded")

    for contour in extraction.contours:
        if contour.view_id != view_id:
            continue
        contour_count += 1
        if contour_count > max_contours:
            raise ValueError("vision_budget_exceeded")
        if not set(contour.source_entity_ids) <= public_entity_ids:
            raise ValueError("vision_geometry_unavailable")
        point_count += len(contour.points_mm if contour.points_mm is not None else contour.points_source)
        if point_count > max_points:
            raise ValueError("vision_budget_exceeded")

    # Only after all ledger budgets and references pass do we materialize
    # coordinate tuples or allocate a raster image.
    entities = tuple(
        sorted(
            (
                entity
                for entity in entities_by_id.values()
                if entity.kind.upper() not in _ANNOTATION_KINDS
            ),
            key=lambda item: item.id,
        )
    )
    contours = tuple(
        sorted(
            (contour for contour in extraction.contours if contour.view_id == view_id),
            key=lambda item: item.id,
        )
    )
    entity_lines = tuple(
        (
            entity,
            _curve_coordinates(entity)
            or _coordinates(entity.points_mm, entity.source_points),
        )
        for entity in entities
    )
    contour_lines = tuple(
        (contour, _coordinates(contour.points_mm, contour.points_source))
        for contour in contours
    )
    if not entity_lines and not contour_lines:
        raise ValueError("vision_geometry_unavailable")

    all_points = [
        point
        for _, line in (*entity_lines, *contour_lines)
        for point in line
    ]
    if not all_points:
        raise ValueError("vision_geometry_unavailable")
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    span_x = max_x - min_x
    span_y = max_y - min_y
    span = max(span_x, span_y, 1e-9)
    scale = (max_dimension_px - 2 * _MARGIN_PX) / span
    width = min(max_dimension_px, max(_MIN_DIMENSION_PX, ceil(span_x * scale) + 2 * _MARGIN_PX))
    height = min(max_dimension_px, max(_MIN_DIMENSION_PX, ceil(span_y * scale) + 2 * _MARGIN_PX))

    def pixel(point: tuple[float, float]) -> tuple[float, float]:
        return (
            _MARGIN_PX + (point[0] - min_x) * scale,
            height - _MARGIN_PX - (point[1] - min_y) * scale,
        )

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for _, line in entity_lines:
        pixels = tuple(pixel(point) for point in line)
        if len(pixels) >= 2:
            draw.line(pixels, fill=(120, 130, 140), width=1)
        elif pixels:
            x, y = pixels[0]
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(120, 130, 140))
    for contour, line in contour_lines:
        pixels = tuple(pixel(point) for point in line)
        if len(pixels) >= 2:
            if contour.closed and pixels[0] != pixels[-1]:
                pixels = (*pixels, pixels[0])
            draw.line(pixels, fill=(25, 35, 45), width=2)

    marked_sources = tuple(
        [("contour", contour.id, line) for contour, line in contour_lines]
        + [("entity", entity.id, line) for entity, line in entity_lines]
    )
    font = ImageFont.load_default()
    marks = []
    for index, (source_kind, source_id, line) in enumerate(marked_sources, start=1):
        mark = VisionMark(
            mark_id=f"M{index:03d}", source_kind=source_kind, source_id=source_id
        )
        marks.append(mark)
        anchor = pixel(
            (
                sum(point[0] for point in line) / len(line),
                sum(point[1] for point in line) / len(line),
            )
        )
        box = draw.textbbox(anchor, mark.mark_id, font=font, anchor="mm")
        draw.rectangle(
            (box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1),
            fill=(255, 235, 115),
            outline=(25, 35, 45),
        )
        draw.text(anchor, mark.mark_id, fill=(10, 15, 20), font=font, anchor="mm")

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    png = buffer.getvalue()
    if len(png) > max_png_bytes:
        raise ValueError("vision_budget_exceeded")
    return RenderedView(
        view_id=view_id,
        png=png,
        width_px=width,
        height_px=height,
        sha256=sha256(png).hexdigest(),
        marks=tuple(marks),
    )
