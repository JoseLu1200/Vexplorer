from __future__ import annotations

from collections import defaultdict
from hashlib import sha256

from backend.app.contratos.modelos import DrawingContour, DrawingExtraction, MountedTableAnalysis, TableMeasure


TOLERANCE_MM = 0.1
REQUIRED_VIEWS = ("FRONT", "TOP", "SIDE")
PROFILE_SLOTS = (
    ("tabletop_thickness", "section"),
    ("support_width", "section"),
    ("support_depth", "section"),
    ("support_thickness", "section"),
)


def _rectangle_bounds(contour: DrawingContour) -> tuple[float, float, float, float] | None:
    points = contour.points_mm
    if not contour.closed or points is None or len(points) != 4:
        return None
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    expected = {(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)}
    actual = {(point.x, point.y) for point in points}
    if expected != actual or max_x - min_x <= TOLERANCE_MM or max_y - min_y <= TOLERANCE_MM:
        return None
    return min_x, min_y, max_x, max_y


def _outer_contours(extraction: DrawingExtraction) -> dict[str, tuple[DrawingContour, tuple[float, float, float, float]]]:
    labels = {view.id: view.label for view in extraction.views}
    candidates: dict[str, list[tuple[DrawingContour, tuple[float, float, float, float]]]] = defaultdict(list)
    for contour in extraction.contours:
        bounds = _rectangle_bounds(contour)
        if bounds is not None and labels.get(contour.view_id) in REQUIRED_VIEWS:
            candidates[labels[contour.view_id]].append((contour, bounds))
    return {
        label: max(values, key=lambda item: (item[1][2] - item[1][0]) * (item[1][3] - item[1][1]))
        for label, values in candidates.items()
    }


def _geometry_evidence(extraction: DrawingExtraction, entity_ids: set[str]) -> tuple[str, ...]:
    return tuple(sorted(
        item.id for item in extraction.evidence
        if item.kind == "geometry" and set(item.source_entity_ids) & entity_ids
    ))


def _dimension_semantic(extraction: DrawingExtraction, dimension_id: str) -> str | None:
    dimension = next(item for item in extraction.dimensions if item.id == dimension_id)
    graphic = next((item for item in extraction.dimension_graphics if item.dimension_id == dimension_id), None)
    view = next((item for item in extraction.views if item.id == dimension.view_id), None)
    if graphic is None or view is None or graphic.extension_start_a_mm is None or graphic.extension_start_b_mm is None:
        return None
    delta_x = abs(graphic.extension_start_b_mm.x - graphic.extension_start_a_mm.x)
    delta_y = abs(graphic.extension_start_b_mm.y - graphic.extension_start_a_mm.y)
    orientation = "x" if delta_x >= delta_y else "y"
    return {
        ("FRONT", "x"): "overall_width",
        ("FRONT", "y"): "overall_height",
        ("TOP", "x"): "overall_width",
        ("TOP", "y"): "overall_depth",
        ("SIDE", "x"): "overall_depth",
        ("SIDE", "y"): "overall_height",
    }.get((view.label, orientation))


def _overall_measure(
    extraction: DrawingExtraction,
    semantic: str,
    axis: str,
    geometry: list[tuple[float, DrawingContour]],
) -> TableMeasure:
    dimension_items = [
        item for item in extraction.dimensions
        if _dimension_semantic(extraction, item.id) == semantic
    ]
    entity_ids = {entity_id for _, contour in geometry for entity_id in contour.source_entity_ids}
    evidence_ids = set(_geometry_evidence(extraction, entity_ids))
    measurement_ids = tuple(sorted(item.id for item in dimension_items))
    view_ids = {contour.view_id for _, contour in geometry}
    for item in dimension_items:
        evidence_ids.update(item.evidence_ids)
        if item.view_id is not None:
            view_ids.add(item.view_id)
    geometry_values = [value for value, _ in geometry]
    annotation_values = [item.value_mm for item in dimension_items]
    conflict = any(value is None for value in annotation_values)
    resolved_values = geometry_values + [value for value in annotation_values if value is not None]
    if resolved_values and max(resolved_values) - min(resolved_values) > TOLERANCE_MM:
        conflict = True
    if conflict:
        return TableMeasure(
            id=f"table-measure-{semantic}", semantic=semantic, axis=axis,
            value_mm=None, state="conflict", measurement_ids=measurement_ids,
            view_ids=tuple(sorted(view_ids)), evidence_ids=tuple(sorted(evidence_ids)),
            source_entity_ids=tuple(sorted(entity_ids)), geometry_relation="dimension_annotation",
        )
    if resolved_values:
        return TableMeasure(
            id=f"table-measure-{semantic}", semantic=semantic, axis=axis,
            value_mm=resolved_values[0], state="observed", measurement_ids=measurement_ids,
            view_ids=tuple(sorted(view_ids)), evidence_ids=tuple(sorted(evidence_ids)),
            source_entity_ids=tuple(sorted(entity_ids)), geometry_relation="dimension_annotation",
        )
    return TableMeasure(
        id=f"table-measure-{semantic}", semantic=semantic, axis=axis,
        value_mm=None, state="unknown", geometry_relation="dimension_annotation",
    )


def _section_measures(
    extraction: DrawingExtraction,
    outer: dict[str, tuple[DrawingContour, tuple[float, float, float, float]]],
) -> tuple[TableMeasure, ...]:
    entities = {item.id: item for item in extraction.entities}
    views = {item.id: item for item in extraction.views}
    candidates: dict[tuple[str, int], dict[str, set[str]]] = {}

    def add(value: float, relation: str, view_id: str, entity_ids: set[str]) -> None:
        key = (relation, round(value / TOLERANCE_MM))
        item = candidates.setdefault(key, {"views": set(), "entities": set(), "evidence": set()})
        item["views"].add(view_id)
        item["entities"].update(entity_ids)
        item["evidence"].update(_geometry_evidence(extraction, entity_ids))

    for label, (contour, bounds) in outer.items():
        min_x, min_y, max_x, max_y = bounds
        width, height = max_x - min_x, max_y - min_y
        view = views[contour.view_id]
        horizontal: list[tuple[float, str]] = []
        vertical: list[tuple[float, str]] = []
        for entity_id in view.entity_ids:
            entity = entities[entity_id]
            if entity.kind != "LINE" or entity.points_mm is None or len(entity.points_mm) != 2:
                continue
            first, second = entity.points_mm
            if abs(first.y - second.y) <= TOLERANCE_MM and abs(first.x - second.x) >= 0.8 * width:
                if min_y + TOLERANCE_MM < first.y < max_y - TOLERANCE_MM:
                    horizontal.append((first.y, entity_id))
            if abs(first.x - second.x) <= TOLERANCE_MM and abs(first.y - second.y) >= 0.8 * height:
                if min_x + TOLERANCE_MM < first.x < max_x - TOLERANCE_MM:
                    vertical.append((first.x, entity_id))
        for y, entity_id in horizontal:
            gap = max_y - y
            if gap <= 0.25 * height:
                add(gap, "offset_from_max_y", view.id, {entity_id, *contour.source_entity_ids})
        left = [(x - min_x, entity_id) for x, entity_id in vertical if x - min_x <= 0.25 * width]
        right = [(max_x - x, entity_id) for x, entity_id in vertical if max_x - x <= 0.25 * width]
        matched: set[str] = set()
        for left_gap, left_id in left:
            counterpart = next(
                ((right_gap, right_id) for right_gap, right_id in right if abs(left_gap - right_gap) <= TOLERANCE_MM),
                None,
            )
            if counterpart is not None:
                add(left_gap, "opposite_offsets", view.id, {left_id, counterpart[1], *contour.source_entity_ids})
                matched.update((left_id, counterpart[1]))
        for gap, entity_id in left:
            if entity_id not in matched:
                add(gap, "offset_from_min_x", view.id, {entity_id, *contour.source_entity_ids})
        for gap, entity_id in right:
            if entity_id not in matched:
                add(gap, "offset_from_max_x", view.id, {entity_id, *contour.source_entity_ids})

    result = []
    for index, ((relation, bucket), refs) in enumerate(sorted(candidates.items()), start=1):
        result.append(TableMeasure(
            id=f"table-measure-section-{index}", semantic="unknown", axis="section",
            value_mm=bucket * TOLERANCE_MM, state="observed",
            view_ids=tuple(sorted(refs["views"])), evidence_ids=tuple(sorted(refs["evidence"])),
            source_entity_ids=tuple(sorted(refs["entities"])), geometry_relation=relation,
        ))
    return tuple(result)


def analyze_mounted_table(extraction: DrawingExtraction) -> MountedTableAnalysis:
    if extraction.input_kind != "mounted_orthographic_views":
        raise ValueError("mounted table analysis requires mounted_orthographic_views input")
    outer = _outer_contours(extraction)
    geometry = {
        "overall_width": [
            (bounds[2] - bounds[0], contour)
            for label, (contour, bounds) in outer.items() if label in ("FRONT", "TOP")
        ],
        "overall_height": [
            (bounds[3] - bounds[1], contour)
            for label, (contour, bounds) in outer.items() if label in ("FRONT", "SIDE")
        ],
        "overall_depth": [
            ((bounds[2] - bounds[0]) if label == "SIDE" else (bounds[3] - bounds[1]), contour)
            for label, (contour, bounds) in outer.items() if label in ("TOP", "SIDE")
        ],
    }
    measures = [
        _overall_measure(extraction, "overall_width", "width", geometry["overall_width"]),
        _overall_measure(extraction, "overall_height", "height", geometry["overall_height"]),
        _overall_measure(extraction, "overall_depth", "depth", geometry["overall_depth"]),
    ]
    measures.extend(_section_measures(extraction, outer))
    measures.extend(
        TableMeasure(
            id=f"table-measure-slot-{semantic}", semantic=semantic, axis=axis,
            value_mm=None, state="unknown", slot_origin="profile_required_slot",
            geometry_relation="profile_required_slot",
        )
        for semantic, axis in PROFILE_SLOTS
    )
    missing = [label for label in REQUIRED_VIEWS if label not in outer]
    warnings = list(extraction.warnings)
    warnings.extend(f"missing_required_view:{label}" for label in missing)
    warnings.extend(
        f"profile_measure_unknown:{item.semantic}"
        for item in measures if item.slot_origin == "profile_required_slot"
    )
    if any(item.state == "conflict" for item in measures):
        warnings.append("table_measure_conflict")
    ledger_revision = sha256(
        f"{extraction.drawing_id}|rectangular_table_v1|{','.join(item.id for item in measures)}".encode("utf-8")
    ).hexdigest()
    return MountedTableAnalysis(
        drawing_id=extraction.drawing_id, ledger_revision=ledger_revision,
        measures=tuple(measures), admitted_measurement_ids=tuple(item.id for item in measures),
        state="needs_review" if warnings or any(item.state != "observed" for item in measures) else "ready",
        warnings=tuple(warnings),
    )
