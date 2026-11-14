from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Literal

from backend.app.contratos.modelos import DrawingExtraction


@dataclass(frozen=True)
class GeometryMeasurement:
    """A geometric observation, never an assigned component dimension."""

    id: str
    semantic: Literal["contour_span_x", "contour_span_y", "contour_segment_length"]
    value_mm: float | None
    source_value: float
    source_unit: str
    state: Literal["observed", "unknown"]
    view_id: str
    source_contour_ids: tuple[str, ...]
    source_entity_ids: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    closed: bool
    vertex_count: int
    shape_kind: Literal["rectangle", "polygon", "polyline"]
    axis_aligned: bool
    shape_context_id: str
    segment_index: int | None
    scope: Literal["single_contour"]
    warning: str

    @property
    def binding_ref(self) -> str:
        return f"measurement:{self.id}"


def _coordinates(points: object) -> tuple[tuple[float, float], ...]:
    result = tuple((float(point.x), float(point.y)) for point in points)  # type: ignore[attr-defined]
    if len(result) > 1 and result[0] == result[-1]:
        return result[:-1]
    return result


def _shape(points: tuple[tuple[float, float], ...], closed: bool) -> tuple[str, bool]:
    pairs = list(zip(points, points[1:]))
    if closed and len(points) > 1:
        pairs.append((points[-1], points[0]))
    axis_aligned = bool(pairs) and all(
        abs(end[0] - start[0]) <= 1e-9 or abs(end[1] - start[1]) <= 1e-9
        for start, end in pairs
    )
    rectangle = (
        closed
        and len(points) == 4
        and axis_aligned
        and len({point[0] for point in points}) == 2
        and len({point[1] for point in points}) == 2
    )
    return (
        "rectangle" if rectangle else "polygon" if closed else "polyline",
        axis_aligned,
    )


def derive_geometry_measurements(
    extraction: DrawingExtraction,
) -> tuple[GeometryMeasurement, ...]:
    """Build bounded per-contour observations without assigning components or quantities."""
    evidence_by_entity: dict[str, set[str]] = {}
    for evidence in extraction.evidence:
        for entity_id in evidence.source_entity_ids:
            evidence_by_entity.setdefault(entity_id, set()).add(evidence.id)
    observations_by_contour: dict[str, set[str]] = {}
    for observation in extraction.observations:
        for contour_id in observation.contour_ids:
            observations_by_contour.setdefault(contour_id, set()).add(observation.id)

    result: list[GeometryMeasurement] = []
    for contour in sorted(extraction.contours, key=lambda item: item.id):
        source_points = _coordinates(contour.points_source)
        metric_points = (
            _coordinates(contour.points_mm) if contour.points_mm is not None else ()
        )
        if not source_points:
            continue
        shape_kind, axis_aligned = _shape(source_points, contour.closed)
        evidence_ids = tuple(
            sorted(
                {
                    evidence_id
                    for entity_id in contour.source_entity_ids
                    for evidence_id in evidence_by_entity.get(entity_id, ())
                }
            )
        )
        common = {
            "view_id": contour.view_id,
            "source_contour_ids": (contour.id,),
            "source_entity_ids": contour.source_entity_ids,
            "source_observation_ids": tuple(
                sorted(observations_by_contour.get(contour.id, ()))
            ),
            "source_evidence_ids": evidence_ids,
            "closed": contour.closed,
            "vertex_count": len(source_points),
            "shape_kind": shape_kind,
            "axis_aligned": axis_aligned,
            "shape_context_id": f"shape:{contour.id}",
            "scope": "single_contour",
        }
        source_axes = (
            ("contour_span_x", "span-x", [point[0] for point in source_points]),
            ("contour_span_y", "span-y", [point[1] for point in source_points]),
        )
        metric_axes = (
            [point[0] for point in metric_points],
            [point[1] for point in metric_points],
        )
        for axis_index, (semantic, suffix, values) in enumerate(source_axes):
            source_value = max(values) - min(values)
            if source_value <= 0:
                continue
            metric_values = metric_axes[axis_index]
            value_mm = (
                max(metric_values) - min(metric_values) if metric_values else None
            )
            result.append(
                GeometryMeasurement(
                    id=f"contour:{contour.id}:{suffix}",
                    semantic=semantic,  # type: ignore[arg-type]
                    value_mm=value_mm,
                    source_value=source_value,
                    source_unit=extraction.source_unit,
                    state="observed" if value_mm is not None else "unknown",
                    segment_index=None,
                    warning="bounding_span_not_component_dimension",
                    **common,  # type: ignore[arg-type]
                )
            )

        source_pairs = list(zip(source_points, source_points[1:]))
        metric_pairs = list(zip(metric_points, metric_points[1:]))
        if contour.closed and len(source_points) > 1:
            source_pairs.append((source_points[-1], source_points[0]))
            if metric_points:
                metric_pairs.append((metric_points[-1], metric_points[0]))
        for index, (start, end) in enumerate(source_pairs, start=1):
            source_value = hypot(end[0] - start[0], end[1] - start[1])
            if source_value <= 0:
                continue
            value_mm = None
            if index <= len(metric_pairs):
                metric_start, metric_end = metric_pairs[index - 1]
                value_mm = hypot(
                    metric_end[0] - metric_start[0], metric_end[1] - metric_start[1]
                )
            result.append(
                GeometryMeasurement(
                    id=f"contour:{contour.id}:segment-{index:03d}",
                    semantic="contour_segment_length",
                    value_mm=value_mm,
                    source_value=source_value,
                    source_unit=extraction.source_unit,
                    state="observed" if value_mm is not None else "unknown",
                    segment_index=index,
                    warning="segment_length_not_component_dimension",
                    **common,  # type: ignore[arg-type]
                )
            )
    return tuple(result)


__all__ = ["GeometryMeasurement", "derive_geometry_measurements"]
