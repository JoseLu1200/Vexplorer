from __future__ import annotations

from dataclasses import dataclass
from math import dist, hypot
from pathlib import Path
import re
from typing import Any, Literal

from backend.app.ingesta.dxf_reader import ParsedDrawing, ParsedEntity, parse_dxf


VIEW_LABELS = {"FRONT": "FRONT", "TOP": "TOP", "RIGHT": "SIDE", "SIDE": "SIDE"}
PART_VIEW_LABEL = re.compile(
    r"^PART\s+(?P<key>[A-Za-z0-9_-]+)\s+(?P<role>FRONT|TOP|SIDE)(?:\s+QTY\s+[1-9]\d*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeometryHypothesis:
    id: str
    label: str
    contour_ids: tuple[str, ...]
    observed_dimension_ids: tuple[str, ...]
    observed_dimensions_mm: tuple[float, float]
    quantity: int | None
    thickness_mm: float | None
    assumptions: tuple[str, ...]
    needs_review: bool = True


def _scaled(points: tuple[tuple[float, float], ...], scale: float | None) -> list[dict[str, float]] | None:
    if scale is None:
        return None
    return [{"x": x * scale, "y": y * scale} for x, y in points]


def _point_payload(point: tuple[float, float], scale: float | None) -> tuple[dict[str, float], dict[str, float] | None]:
    source = {"x": point[0], "y": point[1]}
    metric = {"x": point[0] * scale, "y": point[1] * scale} if scale is not None else None
    return source, metric


def _bounds(points: list[tuple[float, float]]) -> dict[str, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


def _view_labels(
    drawing: ParsedDrawing,
    input_kind: Literal["mounted_views_legacy", "separated_part_views"],
) -> list[tuple[str, tuple[float, float]]]:
    labels = []
    for entity in drawing.entities:
        text = (entity.text or "").strip()
        if input_kind == "separated_part_views":
            match = PART_VIEW_LABEL.fullmatch(text)
            if match:
                labels.append((f"part-{match.group('key').lower()}-{match.group('role').lower()}", entity.points[0]))
        else:
            normalized = text.upper()
            if normalized in VIEW_LABELS:
                labels.append((VIEW_LABELS[normalized], entity.points[0]))
    return labels


def _view_id(view_key: str) -> str:
    return f"view-{view_key.lower()}"


def _view_role(view_key: str) -> str:
    if view_key.startswith("part-"):
        return view_key.rsplit("-", 1)[1].upper()
    return view_key


def _view_regions(
    drawing: ParsedDrawing, labels: list[tuple[str, tuple[float, float]]]
) -> list[tuple[str, tuple[float, float, float, float]]]:
    regions = []
    for entity in drawing.entities:
        if entity.kind != "LWPOLYLINE" or not entity.closed or len(entity.points) < 4:
            continue
        center = (
            sum(point[0] for point in entity.points) / len(entity.points),
            sum(point[1] for point in entity.points) / len(entity.points),
        )
        label = min(labels, key=lambda item: (dist(center, item[1]), item[0]))[0] if labels else "UNKNOWN"
        bounds = _bounds(list(entity.points))
        regions.append((label, (bounds["min_x"], bounds["min_y"], bounds["max_x"], bounds["max_y"])))
    return regions


def _assign_view(
    entity: ParsedEntity,
    labels: list[tuple[str, tuple[float, float]]],
    regions: list[tuple[str, tuple[float, float, float, float]]],
) -> str:
    if not labels or not entity.points:
        return "UNKNOWN"
    region_points = entity.extension_starts if entity.kind == "DIMENSION" else entity.points
    if entity.kind in {"DIMENSION", "LINE"} and region_points and regions:
        def distance_to_region(region: tuple[float, float, float, float]) -> float:
            min_x, min_y, max_x, max_y = region
            total = 0.0
            for x, y in region_points:
                dx = max(min_x - x, 0.0, x - max_x)
                dy = max(min_y - y, 0.0, y - max_y)
                total += hypot(dx, dy)
            return total

        return min(regions, key=lambda item: (distance_to_region(item[1]), item[0]))[0]
    center = (sum(p[0] for p in entity.points) / len(entity.points), sum(p[1] for p in entity.points) / len(entity.points))
    return min(labels, key=lambda item: (dist(center, item[1]), item[0]))[0]


def _line_components(lines: list[ParsedEntity], tolerance: float = 1e-6) -> list[list[ParsedEntity]]:
    def key(point: tuple[float, float]) -> tuple[int, int]:
        return (round(point[0] / tolerance), round(point[1] / tolerance))

    remaining = set(range(len(lines)))
    components: list[list[ParsedEntity]] = []
    while remaining:
        seed = remaining.pop()
        indexes = {seed}
        endpoints = {key(point) for point in lines[seed].points}
        changed = True
        while changed:
            changed = False
            for index in tuple(remaining):
                if endpoints & {key(point) for point in lines[index].points}:
                    remaining.remove(index)
                    indexes.add(index)
                    endpoints.update(key(point) for point in lines[index].points)
                    changed = True
        components.append([lines[index] for index in sorted(indexes)])
    return components


def _rectangular_line_contour(component: list[ParsedEntity], tolerance: float = 1e-6) -> tuple[tuple[float, float], ...] | None:
    if len(component) < 4:
        return None
    points = [point for line in component for point in line.points]
    min_x, min_y, max_x, max_y = _bounds(points).values()
    if max_x - min_x <= tolerance or max_y - min_y <= tolerance:
        return None
    required = {
        ((min_x, min_y), (max_x, min_y)), ((max_x, min_y), (max_x, max_y)),
        ((max_x, max_y), (min_x, max_y)), ((min_x, max_y), (min_x, min_y)),
    }
    present = set()
    for line in component:
        start, end = line.points
        for edge in required:
            (ax, ay), (bx, by) = edge
            if abs(ay - by) <= tolerance and abs(start[1] - ay) <= tolerance and abs(end[1] - ay) <= tolerance:
                if min(start[0], end[0]) <= min(ax, bx) + tolerance and max(start[0], end[0]) >= max(ax, bx) - tolerance:
                    present.add(edge)
            if abs(ax - bx) <= tolerance and abs(start[0] - ax) <= tolerance and abs(end[0] - ax) <= tolerance:
                if min(start[1], end[1]) <= min(ay, by) + tolerance and max(start[1], end[1]) >= max(ay, by) - tolerance:
                    present.add(edge)
    if present != required:
        return None
    return ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))


def _rectangle_dimensions(points: Any, tolerance: float = 1e-6) -> tuple[float, float] | None:
    if len(points) != 4:
        return None
    vectors = [
        (points[(index + 1) % 4].x - points[index].x, points[(index + 1) % 4].y - points[index].y)
        for index in range(4)
    ]
    lengths = [hypot(x, y) for x, y in vectors]
    if any(length <= tolerance for length in lengths):
        return None
    for index in range(4):
        current = vectors[index]
        following = vectors[(index + 1) % 4]
        dot = current[0] * following[0] + current[1] * following[1]
        if abs(dot) > tolerance * lengths[index] * lengths[(index + 1) % 4]:
            return None
    if abs(lengths[0] - lengths[2]) > tolerance * max(lengths[0], lengths[2]):
        return None
    if abs(lengths[1] - lengths[3]) > tolerance * max(lengths[1], lengths[3]):
        return None
    return tuple(sorted((lengths[0], lengths[1]), reverse=True))


def extraction_payload(
    path: Path,
    *,
    input_kind: Literal["mounted_views_legacy", "separated_part_views"] = "mounted_views_legacy",
) -> dict[str, Any]:
    drawing = parse_dxf(path)
    labels = _view_labels(drawing, input_kind)
    regions = _view_regions(drawing, labels)
    evidence: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    contours: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    dimension_graphics: list[dict[str, Any]] = []
    by_view: dict[str, list[str]] = {label: [] for label, _ in labels}
    by_view.setdefault("UNKNOWN", [])

    for entity in drawing.entities:
        view_label = _assign_view(entity, labels, regions)
        points_source = [{"x": x, "y": y} for x, y in entity.points]
        points_mm = _scaled(entity.points, drawing.unit_scale_to_mm)
        entities.append({"id": entity.id, "kind": entity.kind, "layer": entity.layer, "source_points": points_source, "points_mm": points_mm})
        by_view.setdefault(view_label, []).append(entity.id)
        if entity.kind in {"TEXT", "MTEXT"} and entity.text is not None:
            position_source, position_mm = _point_payload(entity.points[0], drawing.unit_scale_to_mm)
            texts.append({
                "id": f"text-{entity.id}", "source_entity_id": entity.id,
                "view_id": _view_id(view_label), "layer": entity.layer, "text": entity.text,
                "position_source": position_source, "position_mm": position_mm,
            })
            evidence.append({
                "id": f"evidence-text-{entity.id}", "kind": "annotation",
                "source_entity_ids": [entity.id], "description": "Public text annotation observed in drawing",
            })
        if entity.kind == "LWPOLYLINE" and entity.closed and len(entity.points) >= 4:
            contour_id = f"contour-{entity.id}"
            contours.append({"id": contour_id, "view_id": _view_id(view_label), "source_entity_ids": [entity.id], "points_source": points_source, "points_mm": points_mm, "closed": True})
            evidence.append({"id": f"evidence-{contour_id}", "kind": "geometry", "source_entity_ids": [entity.id], "description": "Closed source polyline observed in drawing"})
        if entity.kind == "DIMENSION" and entity.measurement is not None:
            evidence_id = f"evidence-dimension-{entity.id}"
            dimension_id = f"dimension-{entity.id}"
            graphic_id = f"graphic-{entity.id}"
            value_mm = entity.measurement * drawing.unit_scale_to_mm if not entity.dimension_conflict and drawing.unit_scale_to_mm is not None else None
            evidence.append({"id": evidence_id, "kind": "annotation", "source_entity_ids": [entity.id], "description": "Linear dimension annotation observed in drawing"})
            dimensions.append({
                "id": dimension_id, "kind": "annotation", "value_mm": value_mm,
                "source_entity_ids": [entity.id], "evidence_ids": [evidence_id], "origin": "observed",
                "view_id": _view_id(view_label), "graphic_id": graphic_id,
            })
            if entity.extension_starts and entity.dimension_line and entity.text_position and entity.display_text is not None:
                start_a_source, start_a_mm = _point_payload(entity.extension_starts[0], drawing.unit_scale_to_mm)
                start_b_source, start_b_mm = _point_payload(entity.extension_starts[1], drawing.unit_scale_to_mm)
                dimension_start_source, dimension_start_mm = _point_payload(entity.dimension_line[0], drawing.unit_scale_to_mm)
                dimension_end_source, dimension_end_mm = _point_payload(entity.dimension_line[1], drawing.unit_scale_to_mm)
                text_position_source, text_position_mm = _point_payload(entity.text_position, drawing.unit_scale_to_mm)
                dimension_graphics.append({
                    "id": graphic_id, "dimension_id": dimension_id, "source_entity_id": entity.id,
                    "view_id": _view_id(view_label), "layer": entity.layer,
                    "display_text": entity.display_text, "raw_text": entity.text or "",
                    "extension_start_a_source": start_a_source, "extension_start_a_mm": start_a_mm,
                    "extension_start_b_source": start_b_source, "extension_start_b_mm": start_b_mm,
                    "dimension_start_source": dimension_start_source, "dimension_start_mm": dimension_start_mm,
                    "dimension_end_source": dimension_end_source, "dimension_end_mm": dimension_end_mm,
                    "text_position_source": text_position_source, "text_position_mm": text_position_mm,
                })

    for view_label in sorted(by_view):
        view_lines = [entity for entity in drawing.entities if entity.kind == "LINE" and entity.id in by_view[view_label]]
        for index, component in enumerate(_line_components(view_lines), start=1):
            rectangle = _rectangular_line_contour(component)
            if rectangle is None:
                continue
            contour_id = f"contour-lines-{view_label.lower()}-{index}"
            source_ids = [line.id for line in component]
            contours.append({
                "id": contour_id, "view_id": _view_id(view_label), "source_entity_ids": source_ids,
                "points_source": [{"x": x, "y": y} for x, y in rectangle],
                "points_mm": _scaled(rectangle, drawing.unit_scale_to_mm), "closed": True,
            })
            evidence.append({
                "id": f"evidence-{contour_id}", "kind": "geometry", "source_entity_ids": source_ids,
                "description": "Axis-aligned closed contour derived from connected source lines",
            })

    views = []
    for label in sorted(by_view):
        ids = by_view[label]
        view_points = [point for entity in drawing.entities if entity.id in ids for point in entity.points]
        if not view_points:
            continue
        bounds_source = _bounds(view_points)
        bounds_mm = {key: value * drawing.unit_scale_to_mm for key, value in bounds_source.items()} if drawing.unit_scale_to_mm is not None else None
        views.append({"id": _view_id(label), "label": _view_role(label), "entity_ids": ids, "bounds_source": bounds_source, "bounds_mm": bounds_mm})

    status = "needs_review" if drawing.unit_scale_to_mm is None or any(
        warning.startswith("unsupported_") or "conflict" in warning or "override" in warning
        for warning in drawing.warnings
    ) else "ready"
    observations = []
    for view in views:
        observations.append({
            "id": f"observation-{view['id']}",
            "view_id": view["id"],
            "contour_ids": [item["id"] for item in contours if item["view_id"] == view["id"]],
            "dimension_ids": [item["id"] for item in dimensions if set(item["source_entity_ids"]) & set(view["entity_ids"])],
        })
    return {
        "drawing_id": drawing.drawing_id, "input_kind": input_kind, "status": status, "source_unit": drawing.source_unit,
        "unit_scale_to_mm": drawing.unit_scale_to_mm,
        "coordinate_unit": "mm" if drawing.unit_scale_to_mm is not None else "source",
        "synthetic": "planos_demo" in path.parts, "warnings": list(drawing.warnings), "entities": entities,
        "views": views, "contours": contours, "dimensions": dimensions, "evidence": evidence,
        "observations": observations, "texts": texts, "dimension_graphics": dimension_graphics,
    }


def extract_drawing(
    path: Path,
    *,
    input_kind: Literal["mounted_views_legacy", "separated_part_views"] = "mounted_views_legacy",
) -> Any:
    """Return the contract-owned Pydantic model without duplicating its schema here."""
    from backend.app.contratos.modelos import DrawingExtraction

    return DrawingExtraction.model_validate(extraction_payload(path, input_kind=input_kind))


def derive_rectangular_hypotheses(extraction: Any) -> tuple[GeometryHypothesis, ...]:
    """Offer generic, explicitly uncertain geometric hypotheses; never a BOM."""
    result = []
    for contour in extraction.contours:
        points = contour.points_mm
        if not points or len(points) < 4:
            continue
        dimensions = _rectangle_dimensions(points)
        if dimensions is None:
            continue
        result.append(GeometryHypothesis(
            id=f"hypothesis-{contour.id}", label="panel", contour_ids=(contour.id,), observed_dimension_ids=(),
            observed_dimensions_mm=dimensions,
            quantity=None, thickness_mm=None,
            assumptions=("closed rectangular projection may represent a panel", "physical occurrence and assembly are not established"),
        ))
    return tuple(result)
