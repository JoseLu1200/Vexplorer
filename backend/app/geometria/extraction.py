from __future__ import annotations

from dataclasses import dataclass
from math import dist
from pathlib import Path
from typing import Any

from backend.app.ingesta.dxf_reader import ParsedDrawing, ParsedEntity, parse_dxf


VIEW_LABELS = {"FRONT": "FRONT", "TOP": "TOP", "RIGHT": "SIDE", "SIDE": "SIDE"}


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


def _bounds(points: list[tuple[float, float]]) -> dict[str, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


def _view_labels(drawing: ParsedDrawing) -> list[tuple[str, tuple[float, float]]]:
    labels = []
    for entity in drawing.entities:
        normalized = (entity.text or "").strip().upper()
        if normalized in VIEW_LABELS:
            labels.append((VIEW_LABELS[normalized], entity.points[0]))
    return labels


def _assign_view(entity: ParsedEntity, labels: list[tuple[str, tuple[float, float]]]) -> str:
    if not labels or not entity.points:
        return "UNKNOWN"
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


def extraction_payload(path: Path) -> dict[str, Any]:
    drawing = parse_dxf(path)
    labels = _view_labels(drawing)
    evidence: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    contours: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    by_view: dict[str, list[str]] = {label: [] for label, _ in labels}
    by_view.setdefault("UNKNOWN", [])

    for entity in drawing.entities:
        view_label = _assign_view(entity, labels)
        points_source = [{"x": x, "y": y} for x, y in entity.points]
        points_mm = _scaled(entity.points, drawing.unit_scale_to_mm)
        entities.append({"id": entity.id, "kind": entity.kind, "layer": entity.layer, "source_points": points_source, "points_mm": points_mm})
        by_view.setdefault(view_label, []).append(entity.id)
        if entity.kind == "LWPOLYLINE" and entity.closed and len(entity.points) >= 4:
            contour_id = f"contour-{entity.id}"
            contours.append({"id": contour_id, "view_id": f"view-{view_label.lower()}", "source_entity_ids": [entity.id], "points_source": points_source, "points_mm": points_mm, "closed": True})
            evidence.append({"id": f"evidence-{contour_id}", "kind": "geometry", "source_entity_ids": [entity.id], "description": "Closed source polyline observed in drawing"})
        if entity.kind == "DIMENSION":
            evidence_id = f"evidence-dimension-{entity.id}"
            value_mm = entity.measurement * drawing.unit_scale_to_mm if entity.measurement is not None and drawing.unit_scale_to_mm is not None else None
            evidence.append({"id": evidence_id, "kind": "annotation", "source_entity_ids": [entity.id], "description": "Linear dimension annotation observed in drawing"})
            dimensions.append({"id": f"dimension-{entity.id}", "kind": "annotation", "value_mm": value_mm, "source_entity_ids": [entity.id], "evidence_ids": [evidence_id], "origin": "observed"})

    for view_label in sorted(by_view):
        view_lines = [entity for entity in drawing.entities if entity.kind == "LINE" and entity.id in by_view[view_label]]
        for index, component in enumerate(_line_components(view_lines), start=1):
            rectangle = _rectangular_line_contour(component)
            if rectangle is None:
                continue
            contour_id = f"contour-lines-{view_label.lower()}-{index}"
            source_ids = [line.id for line in component]
            contours.append({
                "id": contour_id, "view_id": f"view-{view_label.lower()}", "source_entity_ids": source_ids,
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
        views.append({"id": f"view-{label.lower()}", "label": label, "entity_ids": ids, "bounds_source": bounds_source, "bounds_mm": bounds_mm})

    status = "needs_review" if drawing.unit_scale_to_mm is None or any(warning.startswith("unsupported_") for warning in drawing.warnings) else "ready"
    observations = []
    for view in views:
        observations.append({
            "id": f"observation-{view['id']}",
            "view_id": view["id"],
            "contour_ids": [item["id"] for item in contours if item["view_id"] == view["id"]],
            "dimension_ids": [item["id"] for item in dimensions if set(item["source_entity_ids"]) & set(view["entity_ids"])],
        })
    return {
        "drawing_id": drawing.drawing_id, "status": status, "source_unit": drawing.source_unit,
        "unit_scale_to_mm": drawing.unit_scale_to_mm,
        "coordinate_unit": "mm" if drawing.unit_scale_to_mm is not None else "source",
        "synthetic": "planos_demo" in path.parts, "warnings": list(drawing.warnings), "entities": entities,
        "views": views, "contours": contours, "dimensions": dimensions, "evidence": evidence,
        "observations": observations,
    }


def extract_drawing(path: Path) -> Any:
    """Return the contract-owned Pydantic model without duplicating its schema here."""
    from backend.app.contratos.modelos import DrawingExtraction

    return DrawingExtraction.model_validate(extraction_payload(path))


def derive_rectangular_hypotheses(extraction: Any) -> tuple[GeometryHypothesis, ...]:
    """Offer generic, explicitly uncertain geometric hypotheses; never a BOM."""
    result = []
    for contour in extraction.contours:
        points = contour.points_mm
        if not points or len(points) < 4:
            continue
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        dimensions = tuple(sorted((max(xs) - min(xs), max(ys) - min(ys)), reverse=True))
        result.append(GeometryHypothesis(
            id=f"hypothesis-{contour.id}", label="panel", contour_ids=(contour.id,), observed_dimension_ids=(),
            observed_dimensions_mm=dimensions,
            quantity=None, thickness_mm=None,
            assumptions=("closed rectangular projection may represent a panel", "physical occurrence and assembly are not established"),
        ))
    return tuple(result)
