from __future__ import annotations

from dataclasses import dataclass
from math import dist, hypot
from pathlib import Path
import re
from typing import Any, Literal

from backend.app.ingesta.dxf_reader import ParsedDrawing, ParsedEntity, parse_dxf


VIEW_LABELS = {"FRONT": "FRONT", "TOP": "TOP", "RIGHT": "SIDE", "SIDE": "SIDE"}
REGION_KINDS = {"DIMENSION", "LINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE"}
PLANAR_POLYLINE_KINDS = {"LWPOLYLINE", "POLYLINE"}
HIDDEN_LINETYPE_MARKERS = ("HIDDEN", "DASHED", "ACAD_ISO02", "ACAD_ISO03")
HIDDEN_MIN_SPAN = 0.8
MAX_EXACT_RECTANGLE_PAIR_CHECKS = 50_000
PART_VIEW_LABEL = re.compile(
    r"^PART\s+(?P<key>[A-Za-z0-9_-]+)\s+(?P<role>FRONT|TOP|SIDE)(?:\s+QTY\s+[1-9]\d*)?$",
    re.IGNORECASE,
)
ORTHOGRAPHIC_LAYER_LABEL = re.compile(
    r"^(?:(?:ORTHO|VIEW)[ _-])?(?P<role>FRONT|TOP|SIDE|RIGHT)$",
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


@dataclass(frozen=True)
class _ExactLineRectangle:
    points: tuple[tuple[float, float], ...]
    source_lines: tuple[ParsedEntity, ...]


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
    input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"],
) -> list[tuple[str, tuple[float, float]]]:
    labels = []
    for entity in drawing.entities:
        text = (entity.text or "").strip()
        if input_kind == "separated_part_views":
            match = PART_VIEW_LABEL.fullmatch(text)
            if match:
                labels.append((f"part-{match.group('key').lower()}-{match.group('role').lower()}", entity.points[0]))
            elif text.upper() in {"FRONT", "TOP", "SIDE"}:
                labels.append((f"unassociated-{entity.id}-{text.lower()}", entity.points[0]))
        else:
            normalized = text.upper()
            if normalized in VIEW_LABELS:
                text_role = VIEW_LABELS[normalized]
                layer_role = _orthographic_layer_role(entity.layer)
                if layer_role is None or layer_role == text_role:
                    labels.append((text_role, entity.points[0]))
    return labels


def _orthographic_layer_role(layer: str) -> str | None:
    """Return a role only for exact, explicitly named orthographic layers."""
    match = ORTHOGRAPHIC_LAYER_LABEL.fullmatch(layer.strip())
    if match is None:
        return None
    return VIEW_LABELS[match.group("role").upper()]


def _orthographic_layer_views(
    drawing: ParsedDrawing,
    input_kind: Literal[
        "mounted_views_legacy",
        "separated_part_views",
        "mounted_orthographic_views",
    ],
) -> dict[str, str]:
    if input_kind == "separated_part_views":
        return {}
    return {
        entity.id: role
        for entity in drawing.entities
        if (role := _orthographic_layer_role(entity.layer)) is not None
    }


def _orthographic_layer_text_conflicts(
    drawing: ParsedDrawing,
    input_kind: Literal[
        "mounted_views_legacy",
        "separated_part_views",
        "mounted_orthographic_views",
    ],
) -> tuple[str, ...]:
    if input_kind == "separated_part_views":
        return ()
    conflicts = []
    for entity in drawing.entities:
        normalized = (entity.text or "").strip().upper()
        if normalized not in VIEW_LABELS:
            continue
        layer_role = _orthographic_layer_role(entity.layer)
        text_role = VIEW_LABELS[normalized]
        if layer_role is not None and layer_role != text_role:
            conflicts.append(
                f"view_role_layer_text_conflict:{entity.id}:"
                f"layer={layer_role}:text={text_role}"
            )
    return tuple(conflicts)


def _infer_mounted_view_labels(
    drawing: ParsedDrawing,
    *,
    tolerance: float = 1e-6,
) -> list[tuple[str, tuple[float, float], str]]:
    """Infer only an unambiguous aligned FRONT/TOP/SIDE envelope triple."""
    candidates: list[tuple[ParsedEntity, dict[str, float]]] = []
    for entity in drawing.entities:
        if entity.kind not in PLANAR_POLYLINE_KINDS or not entity.closed or len(entity.points) != 4:
            continue
        bounds = _bounds(list(entity.points))
        corners = {
            (bounds["min_x"], bounds["min_y"]),
            (bounds["max_x"], bounds["min_y"]),
            (bounds["max_x"], bounds["max_y"]),
            (bounds["min_x"], bounds["max_y"]),
        }
        if set(entity.points) != corners:
            continue
        candidates.append((entity, bounds))

    maximal = []
    for entity, bounds in candidates:
        contained = any(
            other.id != entity.id
            and other_bounds["min_x"] <= bounds["min_x"] + tolerance
            and other_bounds["min_y"] <= bounds["min_y"] + tolerance
            and other_bounds["max_x"] >= bounds["max_x"] - tolerance
            and other_bounds["max_y"] >= bounds["max_y"] - tolerance
            and (
                other_bounds["min_x"] < bounds["min_x"] - tolerance
                or other_bounds["min_y"] < bounds["min_y"] - tolerance
                or other_bounds["max_x"] > bounds["max_x"] + tolerance
                or other_bounds["max_y"] > bounds["max_y"] + tolerance
            )
            for other, other_bounds in candidates
        )
        if not contained:
            maximal.append((entity, bounds))
    if len(maximal) != 3:
        return []

    solutions: list[dict[str, tuple[ParsedEntity, dict[str, float]]]] = []
    for front_entity, front in maximal:
        remaining = [(entity, bounds) for entity, bounds in maximal if entity.id != front_entity.id]
        for top_entity, top in remaining:
            side_entity, side = next(item for item in remaining if item[0].id != top_entity.id)
            same_width = (
                abs((front["max_x"] - front["min_x"]) - (top["max_x"] - top["min_x"])) <= tolerance
                and abs(front["min_x"] - top["min_x"]) <= tolerance
            )
            same_height = (
                abs((front["max_y"] - front["min_y"]) - (side["max_y"] - side["min_y"])) <= tolerance
                and abs(front["min_y"] - side["min_y"]) <= tolerance
            )
            if same_width and same_height:
                solutions.append({
                    "FRONT": (front_entity, front),
                    "TOP": (top_entity, top),
                    "SIDE": (side_entity, side),
                })
    if len(solutions) != 1:
        return []

    result = []
    for role, (entity, bounds) in solutions[0].items():
        center = (
            (bounds["min_x"] + bounds["max_x"]) / 2.0,
            (bounds["min_y"] + bounds["max_y"]) / 2.0,
        )
        result.append((role, center, entity.id))
    return result


def _view_id(view_key: str) -> str:
    return f"view-{view_key.lower()}"


def _view_role(view_key: str) -> str:
    if view_key.startswith(("part-", "unassociated-")):
        return view_key.rsplit("-", 1)[1].upper()
    return view_key


def _view_regions(
    drawing: ParsedDrawing, labels: list[tuple[str, tuple[float, float]]]
) -> list[tuple[str, tuple[float, float, float, float]]]:
    regions = []
    for entity in drawing.entities:
        if entity.kind not in PLANAR_POLYLINE_KINDS or not entity.closed or len(entity.points) < 4:
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
    if entity.kind == "DIMENSION":
        region_points = entity.extension_starts or entity.points
    elif entity.kind == "CIRCLE" and entity.circular is not None:
        region_points = (entity.circular["center_source"],)
    else:
        region_points = entity.points
    if entity.kind in REGION_KINDS and region_points and regions:
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

    parent = list(range(len(lines)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    owner: dict[tuple[int, int], int] = {}
    for index, line in enumerate(lines):
        for point in line.points:
            endpoint = key(point)
            previous = owner.get(endpoint)
            if previous is None:
                owner[endpoint] = index
                continue
            first, second = find(previous), find(index)
            if first != second:
                parent[max(first, second)] = min(first, second)

    groups: dict[int, list[int]] = {}
    for index in range(len(lines)):
        groups.setdefault(find(index), []).append(index)
    ordered = sorted(groups.values(), key=lambda indexes: indexes[0])
    return [[lines[index] for index in indexes] for indexes in ordered]


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


def _coordinate_clusters(values: list[float], tolerance: float) -> dict[float, float]:
    """Snap only coordinates whose full cluster span is within tolerance."""
    result: dict[float, float] = {}
    ordered = sorted(set(values))
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end] - ordered[start] <= tolerance:
            end += 1
        cluster = ordered[start:end]
        representative = (cluster[0] + cluster[-1]) / 2.0
        for value in cluster:
            result[value] = representative
        start = end
    return result


def _line_matches_exact_edge(
    line: ParsedEntity,
    edge: tuple[tuple[float, float], tuple[float, float]],
    tolerance: float,
) -> bool:
    if len(line.points) != 2:
        return False
    start, end = line.points
    (ax, ay), (bx, by) = edge
    if abs(ay - by) <= tolerance:
        return (
            abs(start[1] - ay) <= tolerance
            and abs(end[1] - ay) <= tolerance
            and abs(min(start[0], end[0]) - min(ax, bx)) <= tolerance
            and abs(max(start[0], end[0]) - max(ax, bx)) <= tolerance
        )
    if abs(ax - bx) <= tolerance:
        return (
            abs(start[0] - ax) <= tolerance
            and abs(end[0] - ax) <= tolerance
            and abs(min(start[1], end[1]) - min(ay, by)) <= tolerance
            and abs(max(start[1], end[1]) - max(ay, by)) <= tolerance
        )
    return False


def _exact_rectangular_line_contours(
    lines: list[ParsedEntity],
    *,
    tolerance: float = 1e-6,
    max_pair_checks: int | None = None,
) -> tuple[tuple[_ExactLineRectangle, ...], int | None]:
    """Find rectangles supported by four complete original LINE entities."""
    if max_pair_checks is None:
        max_pair_checks = MAX_EXACT_RECTANGLE_PAIR_CHECKS
    x_coordinates = [point[0] for line in lines for point in line.points]
    y_coordinates = [point[1] for line in lines for point in line.points]
    x_snap = _coordinate_clusters(x_coordinates, tolerance)
    y_snap = _coordinate_clusters(y_coordinates, tolerance)
    horizontal: dict[tuple[float, float], dict[float, list[ParsedEntity]]] = {}
    vertical: dict[tuple[float, float], dict[float, list[ParsedEntity]]] = {}
    for line in lines:
        if len(line.points) != 2:
            continue
        start, end = line.points
        dx = abs(end[0] - start[0])
        dy = abs(end[1] - start[1])
        if dx <= tolerance and dy <= tolerance:
            continue
        if dy <= tolerance:
            x0, x1 = sorted((x_snap[start[0]], x_snap[end[0]]))
            y0, y1 = y_snap[start[1]], y_snap[end[1]]
            if abs(y1 - y0) > tolerance or x1 - x0 <= tolerance:
                continue
            horizontal.setdefault((x0, x1), {}).setdefault((y0 + y1) / 2.0, []).append(line)
        elif dx <= tolerance:
            y0, y1 = sorted((y_snap[start[1]], y_snap[end[1]]))
            x0, x1 = x_snap[start[0]], x_snap[end[0]]
            if abs(x1 - x0) > tolerance or y1 - y0 <= tolerance:
                continue
            vertical.setdefault((y0, y1), {}).setdefault((x0 + x1) / 2.0, []).append(line)

    pair_checks = sum(
        len(levels) * (len(levels) - 1) // 2
        for levels in horizontal.values()
    )
    if pair_checks > max_pair_checks:
        return (), pair_checks

    rectangles: dict[tuple[float, float, float, float], _ExactLineRectangle] = {}
    for (x0, x1), levels in sorted(horizontal.items()):
        y_values = sorted(levels)
        for lower_index, y0 in enumerate(y_values):
            for y1 in y_values[lower_index + 1:]:
                side_levels = vertical.get((y0, y1))
                if side_levels is None or x0 not in side_levels or x1 not in side_levels:
                    continue
                points = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
                edges = tuple(zip(points, points[1:] + points[:1], strict=True))
                side_groups = (
                    levels[y0], side_levels[x1], levels[y1], side_levels[x0],
                )
                matched_groups = [
                    [line for line in group if _line_matches_exact_edge(line, edge, tolerance)]
                    for group, edge in zip(side_groups, edges, strict=True)
                ]
                if any(not group for group in matched_groups):
                    continue
                witnesses = {group[0].id for group in matched_groups}
                if len(witnesses) != 4:
                    continue
                source_lines = tuple(sorted(
                    {line.id: line for group in matched_groups for line in group}.values(),
                    key=lambda line: line.id,
                ))
                rectangles[(x0, y0, x1, y1)] = _ExactLineRectangle(
                    points=points,
                    source_lines=source_lines,
                )
    return tuple(rectangles[key] for key in sorted(rectangles)), None


def _same_rectangle(
    left: tuple[tuple[float, float], ...],
    right: tuple[tuple[float, float], ...],
    tolerance: float = 1e-6,
) -> bool:
    left_bounds = _bounds(list(left))
    right_bounds = _bounds(list(right))
    return all(abs(left_bounds[key] - right_bounds[key]) <= tolerance for key in left_bounds)


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


def _hidden_line_evidence(
    drawing: ParsedDrawing,
    view_of: dict[str, str],
    contours: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    boxes = []
    for contour in contours:
        if not contour["closed"]:
            continue
        xs = [point["x"] for point in contour["points_source"]]
        ys = [point["y"] for point in contour["points_source"]]
        boxes.append(
            (
                contour["view_id"],
                contour["id"],
                min(xs),
                min(ys),
                max(xs),
                max(ys),
            )
        )
    result = []
    for entity in drawing.entities:
        if (
            entity.kind != "LINE"
            or not entity.linetype
            or not any(marker in entity.linetype.upper() for marker in HIDDEN_LINETYPE_MARKERS)
        ):
            continue
        (x1, y1), (x2, y2) = entity.points
        horizontal = abs(y1 - y2) <= 1e-9
        vertical = abs(x1 - x2) <= 1e-9
        if horizontal == vertical:
            continue
        view_id = _view_id(view_of.get(entity.id, "UNKNOWN"))
        holders = [
            box
            for box in boxes
            if box[0] == view_id
            and box[2] <= min(x1, x2)
            and max(x1, x2) <= box[4]
            and box[3] <= min(y1, y2)
            and max(y1, y2) <= box[5]
        ]
        if not holders:
            continue
        _, contour_id, min_x, min_y, max_x, max_y = min(
            holders,
            key=lambda box: ((box[4] - box[2]) * (box[5] - box[3]), box[1]),
        )
        extent = max_x - min_x if horizontal else max_y - min_y
        across = max_y - min_y if horizontal else max_x - min_x
        if extent <= 0 or across <= 0:
            continue
        span = (abs(x2 - x1) if horizontal else abs(y2 - y1)) / extent
        if span < HIDDEN_MIN_SPAN:
            continue
        position = (y1 - min_y) / across if horizontal else (x1 - min_x) / across
        orientation = "horizontal" if horizontal else "vertical"
        axis = "height" if horizontal else "width"
        result.append(
            {
                "id": f"evidence-hidden-{entity.id}",
                "kind": "geometry",
                "source_entity_ids": [entity.id],
                "description": (
                    f"Hidden-type line ({entity.linetype[:40]}), {orientation}, spanning "
                    f"{span:.0%} of contour {contour_id} at {position:.0%} of its {axis}; "
                    "what it represents is not established"
                ),
            }
        )
    return result


def extraction_payload(
    path: Path,
    *,
    input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"] = "mounted_views_legacy",
) -> dict[str, Any]:
    drawing = parse_dxf(path)
    layer_views = _orthographic_layer_views(drawing, input_kind)
    layer_text_conflicts = _orthographic_layer_text_conflicts(drawing, input_kind)
    labels = _view_labels(drawing, input_kind)
    inferred_labels: list[tuple[str, tuple[float, float], str]] = []
    if (
        not labels
        and not layer_views
        and input_kind in {"mounted_views_legacy", "mounted_orthographic_views"}
    ):
        inferred_labels = _infer_mounted_view_labels(drawing)
        labels = [(role, center) for role, center, _ in inferred_labels]
    regions = _view_regions(drawing, labels)
    evidence: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    contours: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    dimension_graphics: list[dict[str, Any]] = []
    geometry_warnings: list[str] = []
    by_view: dict[str, list[str]] = {label: [] for label, _ in labels}
    for role in layer_views.values():
        by_view.setdefault(role, [])
    by_view.setdefault("UNKNOWN", [])

    for role, _, entity_id in inferred_labels:
        evidence.append({
            "id": f"evidence-inferred-view-{role.lower()}",
            "kind": "view_association",
            "source_entity_ids": [entity_id],
            "description": "Orthographic view role inferred from a unique aligned envelope triple",
        })

    for entity in drawing.entities:
        view_label = layer_views.get(entity.id) or _assign_view(entity, labels, regions)
        points_source = [{"x": x, "y": y} for x, y in entity.points]
        points_mm = _scaled(entity.points, drawing.unit_scale_to_mm)
        circular = None
        if entity.circular is not None:
            center_x, center_y = entity.circular["center_source"]
            circular = {
                **entity.circular,
                "center_source": {"x": center_x, "y": center_y},
                "center_mm": (
                    {"x": center_x * drawing.unit_scale_to_mm, "y": center_y * drawing.unit_scale_to_mm}
                    if drawing.unit_scale_to_mm is not None else None
                ),
                "radius_mm": (
                    entity.circular["radius_source"] * drawing.unit_scale_to_mm
                    if drawing.unit_scale_to_mm is not None else None
                ),
            }
        entities.append({
            "id": entity.id, "kind": entity.kind, "layer": entity.layer,
            "source_points": points_source, "points_mm": points_mm,
            "linetype": entity.linetype, "circular": circular,
        })
        by_view.setdefault(view_label, []).append(entity.id)
        if entity.kind in {"LINE", "CIRCLE", "ARC"}:
            evidence.append({
                "id": f"evidence-geometry-{entity.id}", "kind": "geometry",
                "source_entity_ids": [entity.id], "description": "Geometric segment observed in drawing",
            })
        if entity.kind in {"TEXT", "MTEXT", "ATTRIB"} and entity.text is not None:
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
        if entity.kind in PLANAR_POLYLINE_KINDS and entity.closed and len(entity.points) >= 4:
            contour_id = f"contour-{entity.id}"
            contours.append({"id": contour_id, "view_id": _view_id(view_label), "source_entity_ids": [entity.id], "points_source": points_source, "points_mm": points_mm, "closed": True})
            evidence.append({"id": f"evidence-{contour_id}", "kind": "geometry", "source_entity_ids": [entity.id], "description": "Closed source polyline observed in drawing"})
        if entity.kind == "DIMENSION" and entity.measurement is not None:
            evidence_id = f"evidence-dimension-{entity.id}"
            dimension_id = f"dimension-{entity.id}"
            graphic_id = f"graphic-{entity.id}"
            has_graphic = bool(entity.extension_starts and entity.dimension_line and entity.text_position and entity.display_text is not None)
            value_mm = entity.measurement * drawing.unit_scale_to_mm if not entity.dimension_conflict and drawing.unit_scale_to_mm is not None else None
            evidence.append({"id": evidence_id, "kind": "annotation", "source_entity_ids": [entity.id], "description": "Linear dimension annotation observed in drawing"})
            dimensions.append({
                "id": dimension_id, "kind": "annotation", "value_mm": value_mm,
                "source_entity_ids": [entity.id], "evidence_ids": [evidence_id], "origin": "observed",
                "view_id": _view_id(view_label), "graphic_id": graphic_id if has_graphic else None,
            })
            if has_graphic:
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

    if drawing.unit_scale_to_mm is not None:
        row_index = 0
        for view_label, entity_ids in sorted(by_view.items()):
            if view_label == "UNKNOWN":
                continue
            view_entity_ids = set(entity_ids)
            circles = [
                entity for entity in drawing.entities
                if entity.id in view_entity_ids and entity.kind == "CIRCLE" and entity.circular is not None
            ]
            seen_rows: set[tuple[str, ...]] = set()
            radius_groups: dict[int, list[ParsedEntity]] = {}
            for circle in circles:
                radius_groups.setdefault(round(circle.circular["radius_source"] * 1_000_000), []).append(circle)
            for group in radius_groups.values():
                for primary_axis, secondary_axis in ((0, 1), (1, 0)):
                    aligned: dict[int, list[ParsedEntity]] = {}
                    for circle in group:
                        center = circle.circular["center_source"]
                        aligned.setdefault(round(center[secondary_axis] * 1_000_000), []).append(circle)
                    for candidates in aligned.values():
                        ordered = sorted(candidates, key=lambda item: item.circular["center_source"][primary_axis])
                        if len(ordered) < 3:
                            continue
                        coordinates = [item.circular["center_source"][primary_axis] for item in ordered]
                        gaps = [right - left for left, right in zip(coordinates, coordinates[1:])]
                        if min(gaps) <= 1e-6 or max(gaps) - min(gaps) > 1e-6:
                            continue
                        source_ids = tuple(sorted(item.id for item in ordered))
                        if source_ids in seen_rows:
                            continue
                        seen_rows.add(source_ids)
                        row_index += 1
                        evidence.append({
                            "id": f"evidence-holes-{view_label.lower()}-{row_index}",
                            "kind": "geometry", "source_entity_ids": source_ids,
                            "description": "Regular collinear row of equal exact circles observed in one view",
                        })

    for view_label in sorted(by_view):
        view_entity_ids = set(by_view[view_label])
        view_lines = [
            entity
            for entity in drawing.entities
            if entity.kind == "LINE" and entity.id in view_entity_ids
        ]
        exact_rectangles, required_checks = _exact_rectangular_line_contours(view_lines)
        if required_checks is not None:
            geometry_warnings.append(
                f"exact_rectangle_enumeration_limit:{_view_id(view_label)}:"
                f"checks={required_checks}:limit={MAX_EXACT_RECTANGLE_PAIR_CHECKS}"
            )
        unmatched_exact = list(exact_rectangles)
        for index, component in enumerate(_line_components(view_lines), start=1):
            rectangle = _rectangular_line_contour(component)
            if rectangle is None:
                continue
            exact_match = next(
                (candidate for candidate in unmatched_exact if _same_rectangle(candidate.points, rectangle)),
                None,
            )
            if exact_match is not None:
                unmatched_exact.remove(exact_match)
                rectangle = exact_match.points
                source_ids = [line.id for line in exact_match.source_lines]
                description = "Axis-aligned closed contour supported by four exact source lines"
            else:
                source_ids = [line.id for line in component]
                description = "Axis-aligned closed contour derived from connected source lines"
            contour_id = f"contour-lines-{view_label.lower()}-{index}"
            contours.append({
                "id": contour_id, "view_id": _view_id(view_label), "source_entity_ids": source_ids,
                "points_source": [{"x": x, "y": y} for x, y in rectangle],
                "points_mm": _scaled(rectangle, drawing.unit_scale_to_mm), "closed": True,
            })
            evidence.append({
                "id": f"evidence-{contour_id}", "kind": "geometry", "source_entity_ids": source_ids,
                "description": description,
            })
        for exact_index, candidate in enumerate(unmatched_exact, start=1):
            contour_id = f"contour-lines-{view_label.lower()}-exact-{exact_index}"
            source_ids = [line.id for line in candidate.source_lines]
            contours.append({
                "id": contour_id,
                "view_id": _view_id(view_label),
                "source_entity_ids": source_ids,
                "points_source": [{"x": x, "y": y} for x, y in candidate.points],
                "points_mm": _scaled(candidate.points, drawing.unit_scale_to_mm),
                "closed": True,
            })
            evidence.append({
                "id": f"evidence-{contour_id}",
                "kind": "geometry",
                "source_entity_ids": source_ids,
                "description": "Axis-aligned closed contour supported by four exact source lines",
            })

    view_of = {entity_id: label for label, ids in by_view.items() for entity_id in ids}
    evidence.extend(_hidden_line_evidence(drawing, view_of, contours))

    views = []
    for label in sorted(by_view):
        ids = by_view[label]
        id_set = set(ids)
        view_points = [point for entity in drawing.entities if entity.id in id_set for point in entity.points]
        if not view_points:
            continue
        bounds_source = _bounds(view_points)
        bounds_mm = {key: value * drawing.unit_scale_to_mm for key, value in bounds_source.items()} if drawing.unit_scale_to_mm is not None else None
        views.append({"id": _view_id(label), "label": _view_role(label), "entity_ids": ids, "bounds_source": bounds_source, "bounds_mm": bounds_mm})

    status = "needs_review" if inferred_labels or layer_text_conflicts or geometry_warnings or drawing.unit_scale_to_mm is None or any(
        warning.startswith(("unsupported_", "recovered_dxf", "approximated_", "curve_point_limit"))
        or warning.startswith("paperspace_dimensions")
        or "conflict" in warning or "override" in warning
        for warning in drawing.warnings
    ) else "ready"
    observations = []
    view_entity_sets = {view["id"]: set(view["entity_ids"]) for view in views}
    for view in views:
        observations.append({
            "id": f"observation-{view['id']}",
            "view_id": view["id"],
            "contour_ids": [item["id"] for item in contours if item["view_id"] == view["id"]],
            "dimension_ids": [
                item["id"]
                for item in dimensions
                if set(item["source_entity_ids"]) & view_entity_sets[view["id"]]
            ],
        })
    return {
        "drawing_id": drawing.drawing_id, "input_kind": input_kind, "status": status, "source_unit": drawing.source_unit,
        "unit_scale_to_mm": drawing.unit_scale_to_mm,
        "coordinate_unit": "mm" if drawing.unit_scale_to_mm is not None else "source",
        "synthetic": "planos_demo" in path.parts,
        "warnings": [
            *drawing.warnings,
            *layer_text_conflicts,
            *geometry_warnings,
            *(["view_labels_inferred_from_alignment"] if inferred_labels else []),
        ],
        "entities": entities,
        "views": views, "contours": contours, "dimensions": dimensions, "evidence": evidence,
        "observations": observations, "texts": texts, "dimension_graphics": dimension_graphics,
    }


def extract_drawing(
    path: Path,
    *,
    input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"] = "mounted_views_legacy",
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
