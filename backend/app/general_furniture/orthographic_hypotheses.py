from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
from heapq import heappush, heapreplace
from itertools import product
from math import isfinite
from typing import Literal

from backend.app.contratos.modelos import DrawingExtraction
from backend.app.general_furniture.measurements import GeometryMeasurement


_AUTHORITY = "heuristic_not_physical_identity_or_quantity_or_ownership"
_TOLERANCE_MM = 0.001
_MAX_HYPOTHESES = 128
_MAX_TRIPLET_ORIENTATION_EVALUATIONS = 1_000_000
_ROLES = ("FRONT", "TOP", "SIDE")

Alignment = Literal["direct", "mirrored"]
Interval = tuple[float, float]


@dataclass(frozen=True)
class OrthographicHypothesis:
    id: str
    front_contour_id: str
    top_contour_id: str
    side_contour_id: str
    x_measurement_refs: tuple[str, str]
    y_measurement_refs: tuple[str, str]
    z_measurement_refs: tuple[str, str]
    axis_spans_mm: tuple[float, float, float]
    axis_intervals_mm: tuple[Interval, Interval, Interval]
    alignment_alternatives: tuple[str, ...]
    max_interval_error_mm: float
    tolerance_mm: float
    shared_support_contour_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    authority: Literal[
        "heuristic_not_physical_identity_or_quantity_or_ownership"
    ] = _AUTHORITY


@dataclass(frozen=True)
class OrthographicFrameAlternative:
    alignment: str
    hypothesis_ids: tuple[str, ...]


@dataclass(frozen=True)
class OrthographicHypothesisSet:
    hypotheses: tuple[OrthographicHypothesis, ...]
    warnings: tuple[str, ...]
    truncated: bool
    frame_alignment_alternatives: tuple[OrthographicFrameAlternative, ...] = ()
    frame_constraint: Literal[
        "select_one_global_frame_alignment;do_not_combine_incompatible_hypotheses"
    ] = (
        "select_one_global_frame_alignment;"
        "do_not_combine_incompatible_hypotheses"
    )
    authority: Literal[
        "heuristic_not_physical_identity_or_quantity_or_ownership"
    ] = _AUTHORITY


@dataclass(frozen=True)
class _ContourProjection:
    contour_id: str
    role: str
    local_x: Interval
    local_y: Interval
    span_x_ref: str
    span_y_ref: str
    span_x_mm: float
    span_y_mm: float


@dataclass(frozen=True)
class _ReverseKey:
    value: tuple[object, ...]

    def __lt__(self, other: _ReverseKey) -> bool:
        return self.value > other.value


def _empty(*warnings: str, truncated: bool = False) -> OrthographicHypothesisSet:
    return OrthographicHypothesisSet(
        hypotheses=(), warnings=tuple(warnings), truncated=truncated
    )


def _interval_error(left: Interval, right: Interval) -> float:
    return max(abs(left[0] - right[0]), abs(left[1] - right[1]))


def _oriented(interval: Interval, span: float, alignment: Alignment) -> Interval:
    if alignment == "direct":
        return interval
    return span - interval[1], span - interval[0]


def _valid_alignments(
    left: Interval, right: Interval, span: float
) -> tuple[tuple[Alignment, float], ...]:
    result = []
    for alignment in ("direct", "mirrored"):
        error = _interval_error(left, _oriented(right, span, alignment))
        if error <= _TOLERANCE_MM:
            result.append((alignment, error))
    return tuple(result)


def _rectangle(points) -> bool:
    coordinates = tuple((float(point.x), float(point.y)) for point in points)
    if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
        coordinates = coordinates[:-1]
    if len(coordinates) != 4 or len(set(coordinates)) != 4:
        return False
    xs = {point[0] for point in coordinates}
    ys = {point[1] for point in coordinates}
    return len(xs) == 2 and len(ys) == 2 and set(coordinates) == {
        (x, y) for x in xs for y in ys
    }


def _stable_id(*contour_ids: str) -> str:
    digest = sha256("\x00".join(sorted(contour_ids)).encode("utf-8")).hexdigest()[:16]
    return f"orthographic-hypothesis:{digest}"


def _hypothesis_order_key(item: OrthographicHypothesis) -> tuple[object, ...]:
    return (
        item.axis_spans_mm,
        item.axis_intervals_mm,
        item.max_interval_error_mm,
        item.alignment_alternatives,
        item.front_contour_id,
        item.top_contour_id,
        item.side_contour_id,
    )


def _frame_spans(extraction: DrawingExtraction, views_by_role) -> dict[str, tuple[float, float]] | None:
    spans = {}
    for role, view in views_by_role.items():
        bounds = view.bounds_mm
        if bounds is None:
            return None
        span_x = float(bounds.max_x - bounds.min_x)
        span_y = float(bounds.max_y - bounds.min_y)
        if not all(isfinite(value) and value > 0 for value in (span_x, span_y)):
            return None
        spans[role] = (span_x, span_y)
    if (
        abs(spans["FRONT"][0] - spans["TOP"][0]) > _TOLERANCE_MM
        or abs(spans["FRONT"][1] - spans["SIDE"][1]) > _TOLERANCE_MM
        or abs(spans["TOP"][1] - spans["SIDE"][0]) > _TOLERANCE_MM
    ):
        return None
    return spans


def _metric_scale_consistent(extraction: DrawingExtraction, views_by_role) -> bool:
    scale = float(extraction.unit_scale_to_mm)
    selected_view_ids = {view.id for view in views_by_role.values()}
    for view in views_by_role.values():
        if view.bounds_mm is None:
            return False
        source_values = (
            view.bounds_source.min_x,
            view.bounds_source.min_y,
            view.bounds_source.max_x,
            view.bounds_source.max_y,
        )
        metric_values = (
            view.bounds_mm.min_x,
            view.bounds_mm.min_y,
            view.bounds_mm.max_x,
            view.bounds_mm.max_y,
        )
        if any(
            abs(float(metric) - float(source) * scale) > _TOLERANCE_MM
            for source, metric in zip(source_values, metric_values)
        ):
            return False
    for contour in extraction.contours:
        if contour.view_id not in selected_view_ids:
            continue
        if contour.points_mm is None or len(contour.points_mm) != len(contour.points_source):
            return False
        if any(
            abs(float(metric.x) - float(source.x) * scale) > _TOLERANCE_MM
            or abs(float(metric.y) - float(source.y) * scale) > _TOLERANCE_MM
            for source, metric in zip(contour.points_source, contour.points_mm)
        ):
            return False
    return True


def _measurement_index(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
) -> dict[tuple[str, str], GeometryMeasurement] | None:
    contours = {item.id: item for item in extraction.contours}
    result = {}
    for item in measurements:
        if item.semantic not in {"contour_span_x", "contour_span_y"}:
            continue
        if len(item.source_contour_ids) != 1:
            return None
        contour = contours.get(item.source_contour_ids[0])
        if contour is None or contour.points_mm is None:
            return None
        key = (contour.id, item.semantic)
        if key in result:
            return None
        metric_values = tuple(
            float(getattr(point, "x" if item.semantic.endswith("_x") else "y"))
            for point in contour.points_mm
        )
        source_values = tuple(
            float(getattr(point, "x" if item.semantic.endswith("_x") else "y"))
            for point in contour.points_source
        )
        expected_metric = max(metric_values) - min(metric_values)
        expected_source = max(source_values) - min(source_values)
        if (
            item.state != "observed"
            or item.value_mm is None
            or not isfinite(item.value_mm)
            or item.value_mm <= 0
            or not isfinite(item.source_value)
            or item.source_value <= 0
            or item.view_id != contour.view_id
            or item.source_unit != extraction.source_unit
            or abs(float(item.value_mm) - expected_metric) > _TOLERANCE_MM
            or abs(float(item.source_value) - expected_source) > _TOLERANCE_MM
        ):
            return None
        result[key] = item
    return result


def _projections(
    extraction: DrawingExtraction,
    views_by_role,
    measurement_index: dict[tuple[str, str], GeometryMeasurement],
) -> dict[str, tuple[_ContourProjection, ...]] | None:
    role_by_view = {view.id: role for role, view in views_by_role.items()}
    result: dict[str, list[_ContourProjection]] = {role: [] for role in _ROLES}
    for contour in extraction.contours:
        role = role_by_view.get(contour.view_id)
        if role is None or not contour.closed or contour.points_mm is None:
            continue
        points = tuple(contour.points_mm)
        if len(points) < 4 or not _rectangle(points):
            continue
        span_x = measurement_index.get((contour.id, "contour_span_x"))
        span_y = measurement_index.get((contour.id, "contour_span_y"))
        if (
            span_x is None
            or span_y is None
            or span_x.shape_kind != "rectangle"
            or span_y.shape_kind != "rectangle"
            or not span_x.axis_aligned
            or not span_y.axis_aligned
        ):
            return None
        view_bounds = views_by_role[role].bounds_mm
        assert view_bounds is not None
        xs = tuple(float(point.x) for point in points)
        ys = tuple(float(point.y) for point in points)
        result[role].append(
            _ContourProjection(
                contour_id=contour.id,
                role=role,
                local_x=(min(xs) - float(view_bounds.min_x), max(xs) - float(view_bounds.min_x)),
                local_y=(min(ys) - float(view_bounds.min_y), max(ys) - float(view_bounds.min_y)),
                span_x_ref=span_x.binding_ref,
                span_y_ref=span_y.binding_ref,
                span_x_mm=float(span_x.value_mm),
                span_y_mm=float(span_y.value_mm),
            )
        )
    return {
        role: tuple(
            sorted(
                items,
                key=lambda item: (
                    item.local_x,
                    item.local_y,
                    item.span_x_mm,
                    item.span_y_mm,
                    item.contour_id,
                ),
            )
        )
        for role, items in result.items()
    }


def derive_orthographic_hypotheses(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
) -> OrthographicHypothesisSet:
    """Derive bounded three-view support without asserting a physical piece."""
    if (
        extraction.coordinate_unit != "mm"
        or extraction.unit_scale_to_mm is None
        or not isfinite(extraction.unit_scale_to_mm)
        or extraction.unit_scale_to_mm <= 0
    ):
        return _empty("orthographic_metric_units_required")
    if "view_labels_inferred_from_alignment" in extraction.warnings:
        return _empty("orthographic_explicit_views_required")
    views_by_role = {
        role: tuple(view for view in extraction.views if view.label == role)
        for role in _ROLES
    }
    if any(len(items) != 1 for items in views_by_role.values()):
        return _empty("orthographic_explicit_views_required")
    selected_views = {role: items[0] for role, items in views_by_role.items()}
    if not _metric_scale_consistent(extraction, selected_views):
        return _empty("orthographic_metric_scale_inconsistent")
    spans = _frame_spans(extraction, selected_views)
    if spans is None:
        return _empty("orthographic_frame_inconsistent")
    measurement_index = _measurement_index(extraction, measurements)
    if measurement_index is None:
        return _empty("orthographic_metric_measurements_inconsistent")
    projections = _projections(extraction, selected_views, measurement_index)
    if projections is None:
        return _empty("orthographic_metric_measurements_required")
    front_projections = projections["FRONT"]
    top_projections = projections["TOP"]
    side_projections = projections["SIDE"]
    evaluation_count = 0
    selected_heap: list[tuple[_ReverseKey, OrthographicHypothesis]] = []
    support_counts: Counter[str] = Counter()
    hypothesis_count = 0
    for top in top_projections:
        compatible_sides = []
        for side in side_projections:
            evaluation_count += 2
            if evaluation_count > _MAX_TRIPLET_ORIENTATION_EVALUATIONS:
                return _empty(
                    "orthographic_triplet_evaluation_budget_exceeded:"
                    f"{evaluation_count}",
                    truncated=True,
                )
            side_y = _valid_alignments(
                top.local_y, side.local_x, spans["TOP"][1]
            )
            if side_y:
                compatible_sides.append((side, side_y))
        for front in front_projections:
            evaluation_count += 2
            if evaluation_count > _MAX_TRIPLET_ORIENTATION_EVALUATIONS:
                return _empty(
                    "orthographic_triplet_evaluation_budget_exceeded:"
                    f"{evaluation_count}",
                    truncated=True,
                )
            top_x = _valid_alignments(
                front.local_x, top.local_x, spans["FRONT"][0]
            )
            if not top_x:
                continue
            for side, side_y in compatible_sides:
                evaluation_count += 3
                if evaluation_count > _MAX_TRIPLET_ORIENTATION_EVALUATIONS:
                    return _empty(
                        "orthographic_triplet_evaluation_budget_exceeded:"
                        f"{evaluation_count}",
                        truncated=True,
                    )
                side_z = _valid_alignments(
                    front.local_y, side.local_y, spans["FRONT"][1]
                )
                if not side_z:
                    continue
                orientation_count = len(top_x) * len(side_y) * len(side_z)
                evaluation_count += orientation_count
                if evaluation_count > _MAX_TRIPLET_ORIENTATION_EVALUATIONS:
                    return _empty(
                        "orthographic_triplet_evaluation_budget_exceeded:"
                        f"{evaluation_count}",
                        truncated=True,
                    )
                alternatives = []
                errors = []
                for x_choice, y_choice, z_choice in product(top_x, side_y, side_z):
                    alternatives.append(
                        f"top_x:{x_choice[0]}|side_y:{y_choice[0]}|side_z:{z_choice[0]}"
                    )
                    errors.append(max(x_choice[1], y_choice[1], z_choice[1]))
                hypothesis = OrthographicHypothesis(
                    id=_stable_id(
                        front.contour_id, top.contour_id, side.contour_id
                    ),
                    front_contour_id=front.contour_id,
                    top_contour_id=top.contour_id,
                    side_contour_id=side.contour_id,
                    x_measurement_refs=(front.span_x_ref, top.span_x_ref),
                    y_measurement_refs=(top.span_y_ref, side.span_x_ref),
                    z_measurement_refs=(front.span_y_ref, side.span_y_ref),
                    axis_spans_mm=(
                        front.span_x_mm,
                        top.span_y_mm,
                        front.span_y_mm,
                    ),
                    axis_intervals_mm=(front.local_x, top.local_y, front.local_y),
                    alignment_alternatives=tuple(sorted(alternatives)),
                    max_interval_error_mm=round(max(errors), 9),
                    tolerance_mm=_TOLERANCE_MM,
                    shared_support_contour_ids=(),
                    warnings=(
                        "heuristic_projection_compatibility_only",
                        "contour_material_role_unclassified",
                        "quantity_unconfirmed",
                        "ownership_unconfirmed",
                    ),
                )
                hypothesis_count += 1
                support_counts.update(
                    (
                        hypothesis.front_contour_id,
                        hypothesis.top_contour_id,
                        hypothesis.side_contour_id,
                    )
                )
                hypothesis_key = _ReverseKey(_hypothesis_order_key(hypothesis))
                if len(selected_heap) < _MAX_HYPOTHESES:
                    heappush(selected_heap, (hypothesis_key, hypothesis))
                elif hypothesis_key.value < selected_heap[0][0].value:
                    heapreplace(selected_heap, (hypothesis_key, hypothesis))

    ordered_hypotheses = sorted(
        (hypothesis for _, hypothesis in selected_heap),
        key=_hypothesis_order_key,
    )
    selected_hypotheses = [
        replace(
            item,
            shared_support_contour_ids=tuple(
                contour_id
                for contour_id in (
                    item.front_contour_id,
                    item.top_contour_id,
                    item.side_contour_id,
                )
                if support_counts[contour_id] > 1
            ),
            warnings=(
                *item.warnings,
                *(("shared_projection_support",) if any(
                    support_counts[contour_id] > 1
                    for contour_id in (
                        item.front_contour_id,
                        item.top_contour_id,
                        item.side_contour_id,
                    )
                ) else ()),
            ),
        )
        for item in ordered_hypotheses
    ]
    omitted = max(0, hypothesis_count - len(selected_hypotheses))
    selected_hypothesis_tuple = tuple(selected_hypotheses)
    alignments = sorted(
        {
            alignment
            for item in selected_hypothesis_tuple
            for alignment in item.alignment_alternatives
        }
    )
    return OrthographicHypothesisSet(
        hypotheses=selected_hypothesis_tuple,
        warnings=(
            (f"orthographic_hypotheses_truncated:{omitted}",) if omitted else ()
        ),
        truncated=bool(omitted),
        frame_alignment_alternatives=tuple(
            OrthographicFrameAlternative(
                alignment=alignment,
                hypothesis_ids=tuple(
                    item.id
                    for item in selected_hypothesis_tuple
                    if alignment in item.alignment_alternatives
                ),
            )
            for alignment in alignments
        ),
    )


__all__ = [
    "OrthographicHypothesis",
    "OrthographicHypothesisSet",
    "OrthographicFrameAlternative",
    "derive_orthographic_hypotheses",
]
