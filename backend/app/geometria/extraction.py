from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from math import dist, hypot
from pathlib import Path
from typing import Any

from backend.app.ingesta.dxf_reader import ParsedDrawing, ParsedEntity, parse_dxf


VIEW_LABELS = {"FRONT": "FRONT", "TOP": "TOP", "RIGHT": "SIDE", "SIDE": "SIDE"}
# Closed outlines that can become contours: LWPOLYLINE and classic 2D POLYLINE.
POLYGON_KINDS = {"LWPOLYLINE", "POLYLINE"}
TEXT_KINDS = {"TEXT", "MTEXT", "ATTRIB"}
# Warnings that keep the extraction in needs_review: unread content, approximations, repaired files, unread paperspace dimensions.
REVIEW_WARNING_PREFIXES = ("unsupported_", "approximated_", "recovered_", "paperspace_dimensions")
REGION_KINDS = {"DIMENSION", "LINE", "CIRCLE", "ARC", "ELLIPSE", "SPLINE", "HATCH"}
HIDDEN_LINETYPE_MARKERS = ("HIDDEN", "DASHED", "ACAD_ISO02", "ACAD_ISO03")
HIDDEN_MIN_SPAN = 0.8
HOLE_ROW_MIN_COUNT = 3
HOLE_TOLERANCE_MM = 0.1


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


def _view_labels(drawing: ParsedDrawing) -> list[tuple[str, tuple[float, float]]]:
    labels = []
    for entity in drawing.entities:
        normalized = (entity.text or "").strip().upper()
        if entity.kind in {"TEXT", "MTEXT"} and normalized in VIEW_LABELS:
            labels.append((VIEW_LABELS[normalized], entity.points[0]))
    return labels


Rect = tuple[float, float, float, float]


def _corner_rectangle(points: tuple[tuple[float, float], ...], tolerance: float) -> Rect | None:
    """Axis-aligned bounds when the points are exactly the four corners of a non-degenerate rectangle."""
    if len(points) not in (4, 5):
        return None
    min_x, min_y, max_x, max_y = _bounds(list(points)).values()
    if max_x - min_x <= tolerance or max_y - min_y <= tolerance:
        return None
    corners = {(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)}
    found = set()
    for x, y in points:
        match = next((corner for corner in corners if abs(corner[0] - x) <= tolerance and abs(corner[1] - y) <= tolerance), None)
        if match is None:
            return None
        found.add(match)
    return (min_x, min_y, max_x, max_y) if found == corners else None


def _same_span(first: tuple[float, float], second: tuple[float, float], relative: float = 1e-3) -> bool:
    size = max(first[1] - first[0], second[1] - second[0])
    return abs(first[0] - second[0]) <= relative * size and abs(first[1] - second[1]) <= relative * size


def _disjoint_span(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return first[1] <= second[0] or second[1] <= first[0]


def _infer_view_labels(
    drawing: ParsedDrawing,
) -> tuple[list[tuple[str, tuple[float, float]]], list[tuple[str, Rect]], dict[str, tuple[str, ...]]] | None:
    """Label three orthographic outlines by shared extents when the drawing has no text labels.

    FRONT=(W,H); TOP shares FRONT's x-span and lies apart in y; SIDE shares FRONT's y-span and lies apart in x.
    It abstains (None) unless exactly three maximal outlines admit exactly one such assignment, so no
    first-/third-angle convention is assumed and an ambiguous layout keeps every view UNKNOWN.
    """
    all_points = [point for entity in drawing.entities for point in entity.points]
    if not all_points:
        return None
    drawing_bounds = _bounds(all_points)
    extent = max(drawing_bounds["max_x"] - drawing_bounds["min_x"], drawing_bounds["max_y"] - drawing_bounds["min_y"])
    tolerance = 1e-6 * max(extent, 1.0)
    outlines: list[tuple[Rect, tuple[str, ...]]] = []
    for entity in drawing.entities:
        if entity.kind in POLYGON_KINDS and entity.closed and (rect := _corner_rectangle(entity.points, tolerance)):
            outlines.append((rect, (entity.id,)))
    lines = [entity for entity in drawing.entities if entity.kind == "LINE"]
    for component in _line_components(lines, tolerance) if lines else []:
        polygon = _rectangular_line_contour(component, tolerance)
        if polygon is not None:
            outlines.append(((polygon[0][0], polygon[0][1], polygon[2][0], polygon[2][1]), tuple(line.id for line in component)))

    def contains(outer: Rect, inner: Rect) -> bool:
        return outer[0] - tolerance <= inner[0] and outer[1] - tolerance <= inner[1] and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance

    unique: list[tuple[Rect, tuple[str, ...]]] = []
    for rect, ids in outlines:
        if not any(contains(other, rect) and contains(rect, other) for other, _ in unique):
            unique.append((rect, ids))
    maximal = [(rect, ids) for rect, ids in unique if not any(other != rect and contains(other, rect) for other, _ in unique)]
    if len(maximal) != 3:
        return None
    valid: list[tuple[int, int, int]] = []
    for front, top, side in permutations(range(3)):
        f, t, s = maximal[front][0], maximal[top][0], maximal[side][0]
        if (
            _same_span((f[0], f[2]), (t[0], t[2])) and _disjoint_span((f[1], f[3]), (t[1], t[3]))
            and _same_span((f[1], f[3]), (s[1], s[3])) and _disjoint_span((f[0], f[2]), (s[0], s[2]))
        ):
            valid.append((front, top, side))
    if len(valid) != 1:
        return None
    labels: list[tuple[str, tuple[float, float]]] = []
    regions: list[tuple[str, Rect]] = []
    outline_ids: dict[str, tuple[str, ...]] = {}
    for label, index in zip(("FRONT", "TOP", "SIDE"), valid[0], strict=True):
        rect, ids = maximal[index]
        labels.append((label, ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)))
        regions.append((label, rect))
        outline_ids[label] = ids
    return labels, regions, outline_ids


def _view_regions(
    drawing: ParsedDrawing, labels: list[tuple[str, tuple[float, float]]]
) -> list[tuple[str, tuple[float, float, float, float]]]:
    regions = []
    for entity in drawing.entities:
        if entity.kind not in POLYGON_KINDS or not entity.closed or len(entity.points) < 4:
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
    # An ordinate dimension belongs where its feature point is (defpoint2), not near its UCS origin.
    anchor_points = entity.points[1:2] if entity.ordinate_axis and len(entity.points) >= 2 else entity.points
    region_points = entity.extension_starts if entity.kind == "DIMENSION" and not entity.ordinate_axis else anchor_points
    # Region containment for every drawn primitive except polylines (whose closed outlines define the regions).
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
    center = (sum(p[0] for p in anchor_points) / len(anchor_points), sum(p[1] for p in anchor_points) / len(anchor_points))
    return min(labels, key=lambda item: (dist(center, item[1]), item[0]))[0]


def _line_components(lines: list[ParsedEntity], tolerance: float = 1e-6) -> list[list[ParsedEntity]]:
    def key(point: tuple[float, float]) -> tuple[int, int]:
        return (round(point[0] / tolerance), round(point[1] / tolerance))

    """Lines connected through shared (rounded) endpoints.

    Union-find over endpoint keys: near-linear instead of the previous repeated scan, which took minutes on
    drawings with tens of thousands of lines once blocks are expanded. Components are ordered by their first
    line index and keep their lines in input order, so contour IDs are deterministic.
    """
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
            if endpoint in owner:
                first, second = find(owner[endpoint]), find(index)
                if first != second:
                    parent[max(first, second)] = min(first, second)
            else:
                owner[endpoint] = index
    groups: dict[int, list[int]] = {}
    for index in range(len(lines)):
        groups.setdefault(find(index), []).append(index)
    return [[lines[index] for index in indexes] for indexes in sorted(groups.values(), key=lambda item: item[0])]


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


def _printable(value: str, limit: int = 80) -> str:
    return "".join(character if character.isprintable() else "?" for character in value)[:limit]


def _hidden_line_evidence(drawing: ParsedDrawing, view_of: dict[str, str], contours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hidden-type axis-aligned lines spanning most of a closed contour of their view, described as drawn.

    Neutral wording on purpose: a hidden line inside an outline is often a shelf, divider or back seen through the
    front, but no calibration case backs that reading yet, so it never feeds quantities or scenarios.
    """
    boxes = []
    for contour in contours:
        if not contour["closed"]:
            continue
        xs = [point["x"] for point in contour["points_source"]]
        ys = [point["y"] for point in contour["points_source"]]
        boxes.append((contour["view_id"], contour["id"], min(xs), min(ys), max(xs), max(ys)))
    result = []
    for entity in drawing.entities:
        if entity.kind != "LINE" or not entity.linetype or not any(marker in entity.linetype for marker in HIDDEN_LINETYPE_MARKERS):
            continue
        (x1, y1), (x2, y2) = entity.points
        horizontal, vertical = abs(y1 - y2) <= 1e-9, abs(x1 - x2) <= 1e-9
        if horizontal == vertical:
            continue
        view_id = f"view-{view_of.get(entity.id, 'UNKNOWN').lower()}"
        holders = [box for box in boxes if box[0] == view_id and box[2] <= min(x1, x2) and max(x1, x2) <= box[4] and box[3] <= min(y1, y2) and max(y1, y2) <= box[5]]
        if not holders:
            continue
        _, contour_id, min_x, min_y, max_x, max_y = min(holders, key=lambda box: ((box[4] - box[2]) * (box[5] - box[3]), box[1]))
        extent = (max_x - min_x) if horizontal else (max_y - min_y)
        across = (max_y - min_y) if horizontal else (max_x - min_x)
        if extent <= 0 or across <= 0:
            continue
        span = (abs(x2 - x1) if horizontal else abs(y2 - y1)) / extent
        if span < HIDDEN_MIN_SPAN:
            continue
        position = ((y1 - min_y) / across) if horizontal else ((x1 - min_x) / across)
        orientation, axis = ("horizontal", "height") if horizontal else ("vertical", "width")
        result.append({
            "id": f"evidence-hidden-{entity.id}", "kind": "geometry", "source_entity_ids": [entity.id],
            "description": (
                f"Hidden-type line ({_printable(entity.linetype, 40)}), {orientation}, spanning {span:.0%} of contour {contour_id} "
                f"at {position:.0%} of its {axis}; what it represents is not established"
            ),
        })
    return result


def _hole_row_evidence(drawing: ParsedDrawing, view_of: dict[str, str]) -> list[dict[str, Any]]:
    """Rows of >= 3 equal circles aligned on one axis, with their pitch, as deterministic geometric evidence.

    Reports what is drawn (diameter, pitch, whether all spacings are multiples of the pitch); it does not decide
    what the holes are. Comparing against a drilling system belongs to the validator's workshop catalog.
    Only with resolved units, so every figure is in millimetres.
    """
    scale = drawing.unit_scale_to_mm
    if scale is None:
        return []
    groups: dict[tuple[str, int], list[tuple[float, float, str]]] = {}
    for entity in drawing.entities:
        if entity.kind != "CIRCLE" or entity.circle is None:
            continue
        x, y, radius = (value * scale for value in entity.circle)
        groups.setdefault((view_of.get(entity.id, "UNKNOWN"), round(2 * radius / HOLE_TOLERANCE_MM)), []).append((x, y, entity.id))
    rows: list[tuple[str, float, str, float, list[tuple[float, str]]]] = []
    for (view, diameter_key), circles in groups.items():
        for axis in ("x", "y"):
            lines: dict[int, list[tuple[float, str]]] = {}
            for x, y, entity_id in circles:
                along, across = (x, y) if axis == "x" else (y, x)
                lines.setdefault(round(across / HOLE_TOLERANCE_MM), []).append((along, entity_id))
            for across_key, members in lines.items():
                if len(members) >= HOLE_ROW_MIN_COUNT:
                    rows.append((view, diameter_key * HOLE_TOLERANCE_MM, axis, across_key * HOLE_TOLERANCE_MM, sorted(members)))
    result = []
    counters: dict[str, int] = {}
    for view, diameter, axis, across, members in sorted(rows, key=lambda row: (row[0], row[1], row[2], row[3])):
        spacings = [second[0] - first[0] for first, second in zip(members, members[1:])]
        pitch = min(spacings)
        if pitch <= HOLE_TOLERANCE_MM:
            continue
        regular = all(abs(spacing / pitch - round(spacing / pitch)) * pitch <= HOLE_TOLERANCE_MM for spacing in spacings)
        counters[view] = counters.get(view, 0) + 1
        other = "y" if axis == "x" else "x"
        spacing_text = "all multiples of the pitch" if regular else "irregular"
        result.append({
            "id": f"evidence-holes-{view.lower()}-{counters[view]}", "kind": "geometry",
            "source_entity_ids": [entity_id for _, entity_id in members],
            "description": (
                f"Row of {len(members)} circles diameter {diameter:.1f} mm in view {view}, along {axis} at {other}={across:.1f} mm, "
                f"pitch {pitch:.1f} mm, spacings {spacing_text}, span {members[-1][0] - members[0][0]:.1f} mm"
            ),
        })
    return result


def extraction_payload(path: Path) -> dict[str, Any]:
    drawing = parse_dxf(path)
    labels = _view_labels(drawing)
    inferred = _infer_view_labels(drawing) if not labels else None
    if inferred is not None:
        labels, regions, inferred_outline_ids = inferred
    else:
        regions = _view_regions(drawing, labels)
        inferred_outline_ids = {}
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
        entities.append({"id": entity.id, "kind": entity.kind, "layer": entity.layer, "source_points": points_source, "points_mm": points_mm, "linetype": entity.linetype})
        by_view.setdefault(view_label, []).append(entity.id)
        if entity.kind in TEXT_KINDS and entity.text is not None:
            position_source, position_mm = _point_payload(entity.points[0], drawing.unit_scale_to_mm)
            texts.append({
                "id": f"text-{entity.id}", "source_entity_id": entity.id,
                "view_id": f"view-{view_label.lower()}", "layer": entity.layer, "text": entity.text,
                "position_source": position_source, "position_mm": position_mm,
            })
        if entity.kind in POLYGON_KINDS and entity.closed and len(entity.points) >= 4:
            contour_id = f"contour-{entity.id}"
            contours.append({"id": contour_id, "view_id": f"view-{view_label.lower()}", "source_entity_ids": [entity.id], "points_source": points_source, "points_mm": points_mm, "closed": True})
            evidence.append({"id": f"evidence-{contour_id}", "kind": "geometry", "source_entity_ids": [entity.id], "description": "Closed source polyline observed in drawing"})
        if entity.kind == "DIMENSION" and entity.measurement is not None:
            evidence_id = f"evidence-dimension-{entity.id}"
            dimension_id = f"dimension-{entity.id}"
            has_graphic = bool(entity.extension_starts and entity.dimension_line and entity.text_position and entity.display_text is not None)
            graphic_id = f"graphic-{entity.id}"
            value_mm = entity.measurement * drawing.unit_scale_to_mm if not entity.dimension_conflict and drawing.unit_scale_to_mm is not None else None
            description = (
                f"Ordinate dimension ({entity.ordinate_axis.upper()} from its origin) observed in drawing"
                if entity.ordinate_axis else "Linear dimension annotation observed in drawing"
            )
            evidence.append({"id": evidence_id, "kind": "annotation", "source_entity_ids": [entity.id], "description": description})
            dimensions.append({
                "id": dimension_id, "kind": "annotation", "value_mm": value_mm,
                "source_entity_ids": [entity.id], "evidence_ids": [evidence_id], "origin": "observed",
                "view_id": f"view-{view_label.lower()}", "graphic_id": graphic_id if has_graphic else None,
            })
            if has_graphic:
                start_a_source, start_a_mm = _point_payload(entity.extension_starts[0], drawing.unit_scale_to_mm)
                start_b_source, start_b_mm = _point_payload(entity.extension_starts[1], drawing.unit_scale_to_mm)
                dimension_start_source, dimension_start_mm = _point_payload(entity.dimension_line[0], drawing.unit_scale_to_mm)
                dimension_end_source, dimension_end_mm = _point_payload(entity.dimension_line[1], drawing.unit_scale_to_mm)
                text_position_source, text_position_mm = _point_payload(entity.text_position, drawing.unit_scale_to_mm)
                dimension_graphics.append({
                    "id": graphic_id, "dimension_id": dimension_id, "source_entity_id": entity.id,
                    "view_id": f"view-{view_label.lower()}", "layer": entity.layer,
                    "display_text": entity.display_text, "raw_text": entity.text or "",
                    "extension_start_a_source": start_a_source, "extension_start_a_mm": start_a_mm,
                    "extension_start_b_source": start_b_source, "extension_start_b_mm": start_b_mm,
                    "dimension_start_source": dimension_start_source, "dimension_start_mm": dimension_start_mm,
                    "dimension_end_source": dimension_end_source, "dimension_end_mm": dimension_end_mm,
                    "text_position_source": text_position_source, "text_position_mm": text_position_mm,
                })

    for view_label in sorted(by_view):
        view_ids = set(by_view[view_label])
        view_lines = [entity for entity in drawing.entities if entity.kind == "LINE" and entity.id in view_ids]
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

    view_of = {entity_id: label for label, ids in by_view.items() for entity_id in ids}
    evidence.extend(_hole_row_evidence(drawing, view_of))
    evidence.extend(_hidden_line_evidence(drawing, view_of, contours))
    for reference in drawing.block_references:
        if reference.primitive_ids:
            evidence.append({
                "id": f"evidence-block-{reference.id}", "kind": "geometry", "source_entity_ids": list(reference.primitive_ids),
                "description": f"Block reference with {len(reference.primitive_ids)} expanded primitives at nesting depth {reference.depth}; untrusted block name: {_printable(reference.name)}",
            })
    for entity in drawing.entities:
        if entity.kind == "HATCH":
            evidence.append({
                "id": f"evidence-hatch-{entity.id}", "kind": "geometry", "source_entity_ids": [entity.id],
                "description": f"Hatch boundary observed; untrusted pattern name: {_printable(entity.hatch_pattern or 'unknown')}",
            })

    warnings = list(drawing.warnings)
    if inferred_outline_ids:
        warnings.append("view_labels_inferred_from_alignment")
        for label, outline_ids in inferred_outline_ids.items():
            evidence.append({
                "id": f"evidence-view-inferred-{label.lower()}", "kind": "view_association", "source_entity_ids": list(outline_ids),
                "description": f"View {label} inferred from shared extents of three orthographic outlines; no text label was present",
            })

    views = []
    for label in sorted(by_view):
        ids = by_view[label]
        id_set = set(ids)
        view_points = [point for entity in drawing.entities if entity.id in id_set for point in entity.points]
        if not view_points:
            continue
        bounds_source = _bounds(view_points)
        bounds_mm = {key: value * drawing.unit_scale_to_mm for key, value in bounds_source.items()} if drawing.unit_scale_to_mm is not None else None
        views.append({"id": f"view-{label.lower()}", "label": label, "entity_ids": ids, "bounds_source": bounds_source, "bounds_mm": bounds_mm})

    status = "needs_review" if drawing.unit_scale_to_mm is None or inferred_outline_ids or any(
        warning.startswith(REVIEW_WARNING_PREFIXES) or "conflict" in warning or "override" in warning
        for warning in drawing.warnings
    ) else "ready"
    observations = []
    view_entity_sets = {view["id"]: set(view["entity_ids"]) for view in views}
    for view in views:
        observations.append({
            "id": f"observation-{view['id']}",
            "view_id": view["id"],
            "contour_ids": [item["id"] for item in contours if item["view_id"] == view["id"]],
            "dimension_ids": [item["id"] for item in dimensions if set(item["source_entity_ids"]) & view_entity_sets[view["id"]]],
        })
    return {
        "drawing_id": drawing.drawing_id, "status": status, "source_unit": drawing.source_unit,
        "unit_scale_to_mm": drawing.unit_scale_to_mm,
        "coordinate_unit": "mm" if drawing.unit_scale_to_mm is not None else "source",
        "synthetic": "planos_demo" in path.parts, "warnings": warnings, "entities": entities,
        "views": views, "contours": contours, "dimensions": dimensions, "evidence": evidence,
        "observations": observations, "texts": texts, "dimension_graphics": dimension_graphics,
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
