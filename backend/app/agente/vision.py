"""Set-of-Mark render of one ledger view for the optional vision channel.

Draws only what the ledger holds (entity and contour points), never reads the DXF or any URL, and numbers each
contour so the model can refer to "mark 3" and the backend resolves it to a contour ID. Measurements still come
from the ledger: the image is for relations (inside, repeated, aligned), not for reading values.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from backend.app.contratos.modelos import DrawingExtraction, Point2D

MAX_SIDE_PX = 1024
MARGIN_PX = 24


@dataclass(frozen=True)
class RenderedView:
    view_id: str
    png: bytes
    marks: dict[str, str]
    width_px: int
    height_px: int


def _points(points_mm: tuple[Point2D, ...] | None, points_source: tuple[Point2D, ...]) -> list[tuple[float, float]]:
    return [(point.x, point.y) for point in (points_mm if points_mm is not None else points_source)]


def render_view(extraction: DrawingExtraction, view_id: str, highlight_contour_ids: tuple[str, ...] = ()) -> RenderedView:
    view = next(item for item in extraction.views if item.id == view_id)
    entity_ids = set(view.entity_ids)
    entities = [item for item in extraction.entities if item.id in entity_ids and item.kind not in {"TEXT", "MTEXT", "ATTRIB", "DIMENSION"}]
    contours = sorted((item for item in extraction.contours if item.view_id == view_id), key=lambda item: item.id)
    polylines = [_points(item.points_mm, item.source_points) for item in entities]
    contour_points = [_points(item.points_mm, item.points_source) for item in contours]
    every = [point for line in polylines + contour_points for point in line]
    if not every:
        every = [(0.0, 0.0), (1.0, 1.0)]
    min_x, max_x = min(point[0] for point in every), max(point[0] for point in every)
    min_y, max_y = min(point[1] for point in every), max(point[1] for point in every)
    span = max(max_x - min_x, max_y - min_y, 1e-9)
    scale = (MAX_SIDE_PX - 2 * MARGIN_PX) / span
    width = int((max_x - min_x) * scale) + 2 * MARGIN_PX
    height = int((max_y - min_y) * scale) + 2 * MARGIN_PX

    def pixel(point: tuple[float, float]) -> tuple[float, float]:
        return (MARGIN_PX + (point[0] - min_x) * scale, height - MARGIN_PX - (point[1] - min_y) * scale)

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for line in polylines:
        if len(line) >= 2:
            draw.line([pixel(point) for point in line], fill=(110, 110, 110), width=1)
    highlighted = set(highlight_contour_ids)
    marks: dict[str, str] = {}
    font = ImageFont.load_default()
    for index, (contour, points) in enumerate(zip(contours, contour_points, strict=True), start=1):
        if len(points) < 2:
            continue
        closed = [*points, points[0]] if contour.closed else points
        draw.line([pixel(point) for point in closed], fill=(200, 30, 30) if contour.id in highlighted else (0, 0, 0), width=3 if contour.id in highlighted else 2)
        center = pixel((sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)))
        label = str(index)
        box = draw.textbbox(center, label, font=font)
        draw.rectangle((box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2), fill=(255, 235, 120), outline=(0, 0, 0))
        draw.text(center, label, fill=(0, 0, 0), font=font)
        marks[label] = contour.id
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return RenderedView(view_id=view_id, png=buffer.getvalue(), marks=marks, width_px=width, height_px=height)
