from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from math import isfinite
from typing import Literal

from backend.app.contratos.modelos import DrawingExtraction
from backend.app.general_furniture.measurements import GeometryMeasurement


Axis = Literal["x", "y"]

_MAX_REGIONS = 24
_MAX_HYPOTHESES = 128
_MAX_MATCHES_PER_SOURCE_AXIS = 4
_MAX_INPUT_CONTOURS = 512
_MAX_INPUT_MEASUREMENTS = 4096
_MAX_PAIR_EVALUATIONS = 1_000_000
_DIMENSION_RELATIVE_TOLERANCE = 0.02
_POSITION_RELATIVE_TOLERANCE = 0.30
_REGION_JOIN_MARGIN_RATIO = 0.02


@dataclass(frozen=True)
class SourceSpatialRegion:
    id: str
    source_view_ids: tuple[str, ...]
    source_contour_ids: tuple[str, ...]
    source_entity_ids: tuple[str, ...]
    source_measurement_ids: tuple[str, ...]
    bounds_source: tuple[float, float, float, float]
    relative_center: tuple[float, float]
    candidate_label: Literal["UNKNOWN"]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionHypothesis:
    id: str
    region_ids: tuple[str, str]
    source_view_ids: tuple[str, ...]
    source_contour_ids: tuple[str, ...]
    source_entity_ids: tuple[str, ...]
    source_measurement_ids: tuple[str, str]
    candidate_labels: tuple[Literal["UNKNOWN"], Literal["UNKNOWN"]]
    candidate_axes: tuple[Axis, Axis]
    score: float
    score_kind: Literal["heuristic_not_probability"]
    reasons: tuple[str, ...]
    ambiguity_group_id: str
    ambiguity_rank: int
    ambiguity_size: int
    status: Literal["hypothesis"]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _ContourBox:
    contour_id: str
    view_id: str
    entity_ids: tuple[str, ...]
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class _Candidate:
    left_region: SourceSpatialRegion
    right_region: SourceSpatialRegion
    left_measurement: GeometryMeasurement
    right_measurement: GeometryMeasurement
    left_axis: Axis
    right_axis: Axis
    dimension_error: float
    position_error: float
    position_orientation: Literal["direct", "mirrored"]
    score: float


def _stable_id(prefix: str, *values: str) -> str:
    digest = sha256("\x00".join(values).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _validate_measurements(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
) -> None:
    ids = [item.id for item in measurements]
    if len(ids) != len(set(ids)):
        raise ValueError("projection_measurement_duplicate_id")
    views = {item.id for item in extraction.views}
    contours = {item.id: item for item in extraction.contours}
    entities = {item.id for item in extraction.entities}
    for item in measurements:
        if item.view_id not in views:
            raise ValueError("projection_measurement_unknown_view")
        if not item.source_contour_ids or not set(item.source_contour_ids) <= set(
            contours
        ):
            raise ValueError("projection_measurement_unknown_contour")
        if not set(item.source_entity_ids) <= entities:
            raise ValueError("projection_measurement_unknown_entity")
        if any(contours[value].view_id != item.view_id for value in item.source_contour_ids):
            raise ValueError("projection_measurement_view_mismatch")
        values = (item.source_value,)
        if item.value_mm is not None:
            values = (*values, item.value_mm)
        if any(not isfinite(value) or value <= 0 for value in values):
            raise ValueError("projection_measurement_invalid_value")


def _contour_boxes(extraction: DrawingExtraction) -> tuple[_ContourBox, ...]:
    boxes: list[_ContourBox] = []
    for contour in sorted(extraction.contours, key=lambda item: item.id):
        points = contour.points_source
        if not points:
            continue
        xs = tuple(float(point.x) for point in points)
        ys = tuple(float(point.y) for point in points)
        boxes.append(
            _ContourBox(
                contour_id=contour.id,
                view_id=contour.view_id,
                entity_ids=tuple(sorted(contour.source_entity_ids)),
                bounds=(min(xs), min(ys), max(xs), max(ys)),
            )
        )
    return tuple(boxes)


def _boxes_touch(
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


def _components(
    boxes: tuple[_ContourBox, ...], margin: float
) -> tuple[tuple[_ContourBox, ...], ...]:
    parent = list(range(len(boxes)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left_index, left in enumerate(boxes):
        for right_index in range(left_index + 1, len(boxes)):
            if _boxes_touch(left.bounds, boxes[right_index].bounds, margin):
                union(left_index, right_index)
    grouped: dict[int, list[_ContourBox]] = {}
    for index, box in enumerate(boxes):
        grouped.setdefault(find(index), []).append(box)
    return tuple(
        tuple(sorted(group, key=lambda item: item.contour_id))
        for _, group in sorted(grouped.items())
    )


def _union_bounds(
    boxes: tuple[_ContourBox, ...],
) -> tuple[float, float, float, float]:
    return (
        min(item.bounds[0] for item in boxes),
        min(item.bounds[1] for item in boxes),
        max(item.bounds[2] for item in boxes),
        max(item.bounds[3] for item in boxes),
    )


def _relative_center(
    bounds: tuple[float, float, float, float],
    parent: tuple[float, float, float, float],
) -> tuple[float, float]:
    center_x = (bounds[0] + bounds[2]) / 2
    center_y = (bounds[1] + bounds[3]) / 2
    span_x = parent[2] - parent[0]
    span_y = parent[3] - parent[1]
    return (
        0.5 if span_x <= 1e-12 else (center_x - parent[0]) / span_x,
        0.5 if span_y <= 1e-12 else (center_y - parent[1]) / span_y,
    )


def _spatial_order(
    regions: list[SourceSpatialRegion],
) -> list[SourceSpatialRegion]:
    ordered: list[SourceSpatialRegion] = []
    view_ids = sorted({item.source_view_ids[0] for item in regions})
    for view_id in view_ids:
        selected = [item for item in regions if item.source_view_ids == (view_id,)]
        x_spread = (
            max(item.relative_center[0] for item in selected)
            - min(item.relative_center[0] for item in selected)
        )
        y_spread = (
            max(item.relative_center[1] for item in selected)
            - min(item.relative_center[1] for item in selected)
        )
        if x_spread >= y_spread:
            selected.sort(
                key=lambda item: (
                    item.bounds_source[0],
                    item.bounds_source[1],
                    item.id,
                )
            )
        else:
            selected.sort(
                key=lambda item: (
                    item.bounds_source[1],
                    item.bounds_source[0],
                    item.id,
                )
            )
        ordered.extend(selected)
    return ordered


def _axis(measurement: GeometryMeasurement) -> Axis | None:
    if measurement.semantic == "contour_span_x":
        return "x"
    if measurement.semantic == "contour_span_y":
        return "y"
    return None


def _contour_center_in_region(
    extraction: DrawingExtraction,
    measurement: GeometryMeasurement,
    region: SourceSpatialRegion,
    axis: Axis,
) -> float:
    contour_ids = set(measurement.source_contour_ids)
    selected = [item for item in extraction.contours if item.id in contour_ids]
    coordinates = [
        float(getattr(point, axis))
        for contour in selected
        for point in contour.points_source
    ]
    minimum = region.bounds_source[0 if axis == "x" else 1]
    maximum = region.bounds_source[2 if axis == "x" else 3]
    span = maximum - minimum
    if not coordinates or span <= 1e-12:
        return 0.5
    return ((min(coordinates) + max(coordinates)) / 2 - minimum) / span


def _candidate_value(
    left: GeometryMeasurement, right: GeometryMeasurement
) -> tuple[float, float, Literal["metric_mm", "source_coordinate"]]:
    if left.value_mm is not None and right.value_mm is not None:
        return left.value_mm, right.value_mm, "metric_mm"
    return left.source_value, right.source_value, "source_coordinate"


def _build_candidate(
    extraction: DrawingExtraction,
    left_region: SourceSpatialRegion,
    right_region: SourceSpatialRegion,
    left: GeometryMeasurement,
    right: GeometryMeasurement,
) -> _Candidate | None:
    left_axis = _axis(left)
    right_axis = _axis(right)
    if left_axis is None or right_axis is None:
        return None
    left_value, right_value, _ = _candidate_value(left, right)
    dimension_error = abs(left_value - right_value) / max(left_value, right_value)
    if dimension_error > _DIMENSION_RELATIVE_TOLERANCE:
        return None
    left_position = _contour_center_in_region(
        extraction, left, left_region, left_axis
    )
    right_position = _contour_center_in_region(
        extraction, right, right_region, right_axis
    )
    direct_error = abs(left_position - right_position)
    mirrored_error = abs(left_position - (1.0 - right_position))
    position_error = min(direct_error, mirrored_error)
    if position_error > _POSITION_RELATIVE_TOLERANCE:
        return None
    orientation: Literal["direct", "mirrored"] = (
        "direct" if direct_error <= mirrored_error else "mirrored"
    )
    dimension_score = 1.0 - dimension_error / _DIMENSION_RELATIVE_TOLERANCE
    position_score = 1.0 - position_error / _POSITION_RELATIVE_TOLERANCE
    return _Candidate(
        left_region=left_region,
        right_region=right_region,
        left_measurement=left,
        right_measurement=right,
        left_axis=left_axis,
        right_axis=right_axis,
        dimension_error=dimension_error,
        position_error=position_error,
        position_orientation=orientation,
        score=round(0.8 * dimension_score + 0.2 * position_score, 6),
    )


def derive_source_spatial_regions(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
) -> tuple[SourceSpatialRegion, ...]:
    """Group source-coordinate contours without asserting semantic view identity."""
    if (
        len(extraction.contours) > _MAX_INPUT_CONTOURS
        or len(measurements) > _MAX_INPUT_MEASUREMENTS
    ):
        raise ValueError("projection_input_budget_exceeded")
    _validate_measurements(extraction, measurements)
    measurements_by_contour: dict[str, set[str]] = {}
    for measurement in measurements:
        for contour_id in measurement.source_contour_ids:
            measurements_by_contour.setdefault(contour_id, set()).add(measurement.id)
    views = {item.id: item for item in extraction.views}
    regions: list[SourceSpatialRegion] = []
    all_boxes = _contour_boxes(extraction)
    for view_id in sorted(views):
        view = views[view_id]
        boxes = tuple(item for item in all_boxes if item.view_id == view_id)
        if not boxes:
            continue
        view_span = max(
            float(view.bounds_source.max_x - view.bounds_source.min_x),
            float(view.bounds_source.max_y - view.bounds_source.min_y),
            1.0,
        )
        parent_bounds = (
            float(view.bounds_source.min_x),
            float(view.bounds_source.min_y),
            float(view.bounds_source.max_x),
            float(view.bounds_source.max_y),
        )
        for component in _components(
            boxes, view_span * _REGION_JOIN_MARGIN_RATIO
        ):
            contour_ids = tuple(item.contour_id for item in component)
            entity_ids = tuple(
                sorted({value for item in component for value in item.entity_ids})
            )
            measurement_ids = tuple(
                sorted(
                    {
                        value
                        for contour_id in contour_ids
                        for value in measurements_by_contour.get(contour_id, ())
                    }
                )
            )
            bounds = _union_bounds(component)
            regions.append(
                SourceSpatialRegion(
                    id=_stable_id("projection-region", view_id, *contour_ids),
                    source_view_ids=(view_id,),
                    source_contour_ids=contour_ids,
                    source_entity_ids=entity_ids,
                    source_measurement_ids=measurement_ids,
                    bounds_source=bounds,
                    relative_center=_relative_center(bounds, parent_bounds),
                    candidate_label="UNKNOWN",
                    warnings=(
                        "spatial_region_not_semantic_view",
                        "contour_interior_not_classified",
                    ),
                )
            )
    regions = _spatial_order(regions)
    omitted = max(0, len(regions) - _MAX_REGIONS)
    if omitted:
        regions = sorted(
            regions,
            key=lambda item: (
                -(
                    (item.bounds_source[2] - item.bounds_source[0])
                    * (item.bounds_source[3] - item.bounds_source[1])
                ),
                item.id,
            ),
        )[:_MAX_REGIONS]
        regions = _spatial_order(regions)
        regions = [
            replace(
                item,
                warnings=(*item.warnings, f"spatial_region_set_truncated:{omitted}"),
            )
            for item in regions
        ]
    return tuple(regions)


def derive_projection_hypotheses(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
) -> tuple[ProjectionHypothesis, ...]:
    """Rank geometric correspondences while retaining ambiguous alternatives."""
    regions = derive_source_spatial_regions(extraction, measurements)
    measurements_by_id = {item.id: item for item in measurements}
    span_count_by_region = {
        region.id: sum(
            _axis(measurements_by_id[value]) is not None
            for value in region.source_measurement_ids
        )
        for region in regions
    }
    pair_evaluations = sum(
        span_count_by_region[left.id] * span_count_by_region[right.id]
        for left_index, left in enumerate(regions)
        for right in regions[left_index + 1 :]
    )
    if pair_evaluations > _MAX_PAIR_EVALUATIONS:
        raise ValueError("projection_input_budget_exceeded")
    raw: list[_Candidate] = []
    for left_index, left_region in enumerate(regions):
        left_measurements = tuple(
            measurements_by_id[value]
            for value in left_region.source_measurement_ids
            if _axis(measurements_by_id[value]) is not None
        )
        for right_region in regions[left_index + 1 :]:
            right_measurements = tuple(
                measurements_by_id[value]
                for value in right_region.source_measurement_ids
                if _axis(measurements_by_id[value]) is not None
            )
            for left in left_measurements:
                for right in right_measurements:
                    candidate = _build_candidate(
                        extraction, left_region, right_region, left, right
                    )
                    if candidate is not None:
                        raw.append(candidate)

    grouped: dict[str, list[_Candidate]] = {}
    for item in raw:
        group_id = _stable_id(
            "projection-ambiguity",
            item.left_region.id,
            item.left_measurement.id,
            item.left_axis,
        )
        grouped.setdefault(group_id, []).append(item)
    selected: list[tuple[str, _Candidate]] = []
    for group_id, items in sorted(grouped.items()):
        ordered = sorted(
            items,
            key=lambda item: (
                -item.score,
                item.right_region.id,
                item.right_measurement.id,
                item.right_axis,
            ),
        )[:_MAX_MATCHES_PER_SOURCE_AXIS]
        selected.extend((group_id, item) for item in ordered)
    selected.sort(
        key=lambda pair: (
            -pair[1].score,
            pair[0],
            pair[1].right_region.id,
            pair[1].right_measurement.id,
        )
    )
    truncated = len(selected) > _MAX_HYPOTHESES
    selected = selected[:_MAX_HYPOTHESES]
    selected_groups: dict[str, list[_Candidate]] = {}
    for group_id, item in selected:
        selected_groups.setdefault(group_id, []).append(item)

    result: list[ProjectionHypothesis] = []
    ranks: dict[str, int] = {}
    for group_id, item in selected:
        ranks[group_id] = ranks.get(group_id, 0) + 1
        _, _, basis = _candidate_value(
            item.left_measurement, item.right_measurement
        )
        contour_ids = tuple(
            sorted(
                {
                    *item.left_measurement.source_contour_ids,
                    *item.right_measurement.source_contour_ids,
                }
            )
        )
        entity_ids = tuple(
            sorted(
                {
                    *item.left_measurement.source_entity_ids,
                    *item.right_measurement.source_entity_ids,
                }
            )
        )
        view_ids = tuple(
            sorted(
                {
                    item.left_measurement.view_id,
                    item.right_measurement.view_id,
                }
            )
        )
        warnings = (
            "heuristic_not_probability",
            "physical_identity_unconfirmed",
            "quantity_unconfirmed",
            "contour_interior_not_classified",
        )
        if truncated:
            warnings = (*warnings, "projection_candidate_set_truncated")
        result.append(
            ProjectionHypothesis(
                id=_stable_id(
                    "projection-hypothesis",
                    item.left_region.id,
                    item.right_region.id,
                    item.left_measurement.id,
                    item.right_measurement.id,
                    item.left_axis,
                    item.right_axis,
                ),
                region_ids=(item.left_region.id, item.right_region.id),
                source_view_ids=view_ids,
                source_contour_ids=contour_ids,
                source_entity_ids=entity_ids,
                source_measurement_ids=(
                    item.left_measurement.id,
                    item.right_measurement.id,
                ),
                candidate_labels=("UNKNOWN", "UNKNOWN"),
                candidate_axes=(item.left_axis, item.right_axis),
                score=item.score,
                score_kind="heuristic_not_probability",
                reasons=(
                    f"span_values_within_relative_tolerance:{item.dimension_error:.6f}",
                    f"relative_position_consistent_{item.position_orientation}:{item.position_error:.6f}",
                    f"comparison_basis:{basis}",
                ),
                ambiguity_group_id=group_id,
                ambiguity_rank=ranks[group_id],
                ambiguity_size=len(selected_groups[group_id]),
                status="hypothesis",
                warnings=warnings,
            )
        )
    return tuple(result)


__all__ = [
    "ProjectionHypothesis",
    "SourceSpatialRegion",
    "derive_projection_hypotheses",
    "derive_source_spatial_regions",
]
