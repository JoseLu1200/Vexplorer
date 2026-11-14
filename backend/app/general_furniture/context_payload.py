from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from backend.app.contratos.modelos import DrawingExtraction
from backend.app.general_furniture.measurements import GeometryMeasurement
from backend.app.general_furniture.projection_hypotheses import (
    ProjectionHypothesis,
    SourceSpatialRegion,
)


@dataclass(frozen=True)
class CompactMeasurement:
    id: str
    binding_ref: str
    semantic: str
    value_mm: float | None
    source_value: float
    source_unit: str
    state: Literal["observed", "unknown"]
    view_ids: tuple[str, ...]
    contour_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    closed: bool
    vertex_count: int
    shape_kind: str
    axis_aligned: bool
    shape_context_id: str
    segment_index: int | None
    scope: str
    warning: str

    def to_payload(self, *, include_details: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "binding_ref": self.binding_ref,
            "semantic": self.semantic,
            "value_mm": self.value_mm,
            "source_value": self.source_value,
            "source_unit": self.source_unit,
            "state": self.state,
            "view_ids": self.view_ids,
            "contour_ids": self.contour_ids,
            "entity_ids": self.entity_ids,
            "observation_ids": self.observation_ids,
            "evidence_ids": self.evidence_ids,
        }
        if include_details:
            payload.update(
                {
                    "closed": self.closed,
                    "vertex_count": self.vertex_count,
                    "shape_kind": self.shape_kind,
                    "axis_aligned": self.axis_aligned,
                    "shape_context_id": self.shape_context_id,
                    "segment_index": self.segment_index,
                    "scope": self.scope,
                    "warning": self.warning,
                }
            )
        return payload


@dataclass(frozen=True)
class CompactRegion:
    id: str
    source_view_ids: tuple[str, ...]
    bounds_source: tuple[float, float, float, float]
    contour_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompactProjectionHypothesis:
    id: str
    region_ids: tuple[str, str]
    axes: tuple[str, str]
    score: float
    ambiguity_group_id: str
    ambiguity_rank: int
    ambiguity_size: int
    measurement_refs: tuple[str, str]


@dataclass(frozen=True)
class CompactContextMetadata:
    schema_version: Literal["compact-geometry-context-1"]
    source_unit: str
    coordinate_unit: str
    measurement_count: int
    initial_span_count: int
    queryable_segment_count: int
    region_count: int
    hypothesis_count: int
    spatial_regions_truncated: bool
    projection_hypotheses_truncated: bool
    measurement_authority: str
    projection_authority: str
    region_authority: str
    quantity_authority: str
    contour_interior_authority: str
    segment_access: str
    initial_measurement_scope: Literal["contour_spans_only"]
    references_resolved: Literal[True]


@dataclass(frozen=True)
class CompactGeometryContext:
    metadata: CompactContextMetadata
    measurements: tuple[CompactMeasurement, ...]
    regions: tuple[CompactRegion, ...]
    projection_hypotheses: tuple[CompactProjectionHypothesis, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "metadata": asdict(self.metadata),
            "measurements": tuple(item.to_payload() for item in self.measurements),
            "regions": tuple(asdict(item) for item in self.regions),
            "projection_hypotheses": tuple(
                asdict(item) for item in self.projection_hypotheses
            ),
        }


@dataclass(frozen=True)
class CompactMeasurementPage:
    items: tuple[CompactMeasurement, ...]
    total: int
    offset: int
    returned_count: int
    next_offset: int | None
    truncated: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "items": tuple(
                item.to_payload(include_details=True) for item in self.items
            ),
            "total": self.total,
            "offset": self.offset,
            "returned_count": self.returned_count,
            "next_offset": self.next_offset,
            "truncated": self.truncated,
        }


def _compact_measurement(item: GeometryMeasurement) -> CompactMeasurement:
    return CompactMeasurement(
        id=item.id,
        binding_ref=item.binding_ref,
        semantic=item.semantic,
        value_mm=item.value_mm,
        source_value=item.source_value,
        source_unit=item.source_unit,
        state=item.state,
        view_ids=(item.view_id,),
        contour_ids=item.source_contour_ids,
        entity_ids=item.source_entity_ids,
        observation_ids=item.source_observation_ids,
        evidence_ids=item.source_evidence_ids,
        closed=item.closed,
        vertex_count=item.vertex_count,
        shape_kind=item.shape_kind,
        axis_aligned=item.axis_aligned,
        shape_context_id=item.shape_context_id,
        segment_index=item.segment_index,
        scope=item.scope,
        warning=item.warning,
    )


def _measurement_index(
    measurements: tuple[GeometryMeasurement, ...],
) -> dict[str, GeometryMeasurement]:
    if len(measurements) > 4096:
        raise ValueError("compact_context_input_budget_exceeded")
    result = {item.id: item for item in measurements}
    if len(result) != len(measurements):
        raise ValueError("compact_context_duplicate_measurement_id")
    return result


def _validate_references(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
    regions: tuple[SourceSpatialRegion, ...],
    hypotheses: tuple[ProjectionHypothesis, ...],
) -> None:
    measurement_index = _measurement_index(measurements)
    views = {item.id for item in extraction.views}
    contours = {item.id for item in extraction.contours}
    entities = {item.id for item in extraction.entities}
    observations = {item.id for item in extraction.observations}
    evidence = {item.id for item in extraction.evidence}
    for item in measurements:
        if (
            item.view_id not in views
            or not set(item.source_contour_ids) <= contours
            or not set(item.source_entity_ids) <= entities
            or not set(item.source_observation_ids) <= observations
            or not set(item.source_evidence_ids) <= evidence
        ):
            raise ValueError("compact_context_unresolved_measurement_ref")
    region_ids = [item.id for item in regions]
    if len(region_ids) != len(set(region_ids)):
        raise ValueError("compact_context_duplicate_region_id")
    for item in regions:
        if (
            not set(item.source_view_ids) <= views
            or not set(item.source_contour_ids) <= contours
            or not set(item.source_entity_ids) <= entities
            or not set(item.source_measurement_ids) <= set(measurement_index)
        ):
            raise ValueError("compact_context_unresolved_region_ref")
    hypothesis_ids = [item.id for item in hypotheses]
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        raise ValueError("compact_context_duplicate_hypothesis_id")
    span_ids = {
        item.id
        for item in measurements
        if item.semantic in ("contour_span_x", "contour_span_y")
    }
    for item in hypotheses:
        if not set(item.region_ids) <= set(region_ids) or not set(
            item.source_measurement_ids
        ) <= span_ids:
            raise ValueError("compact_context_unresolved_hypothesis_ref")


def build_compact_geometry_context(
    extraction: DrawingExtraction,
    measurements: tuple[GeometryMeasurement, ...],
    regions: tuple[SourceSpatialRegion, ...],
    hypotheses: tuple[ProjectionHypothesis, ...],
) -> CompactGeometryContext:
    _validate_references(extraction, measurements, regions, hypotheses)
    spans = tuple(
        _compact_measurement(item)
        for item in measurements
        if item.semantic in ("contour_span_x", "contour_span_y")
    )
    segments = tuple(
        item for item in measurements if item.semantic == "contour_segment_length"
    )
    return CompactGeometryContext(
        metadata=CompactContextMetadata(
            schema_version="compact-geometry-context-1",
            source_unit=extraction.source_unit,
            coordinate_unit=extraction.coordinate_unit,
            measurement_count=len(measurements),
            initial_span_count=len(spans),
            queryable_segment_count=len(segments),
            region_count=len(regions),
            hypothesis_count=len(hypotheses),
            spatial_regions_truncated=any(
                warning.startswith("spatial_region_set_truncated:")
                for item in regions
                for warning in item.warnings
            ),
            projection_hypotheses_truncated=any(
                warning == "projection_candidate_set_truncated"
                for item in hypotheses
                for warning in item.warnings
            ),
            measurement_authority=(
                "ledger_geometry_observation_not_component_dimension"
            ),
            projection_authority=(
                "heuristic_not_probability_or_physical_identity"
            ),
            region_authority="source_coordinate_group_not_semantic_view",
            quantity_authority="unconfirmed",
            contour_interior_authority="not_classified",
            segment_access="query_compact_measurements",
            initial_measurement_scope="contour_spans_only",
            references_resolved=True,
        ),
        measurements=spans,
        regions=tuple(
            CompactRegion(
                id=item.id,
                source_view_ids=item.source_view_ids,
                bounds_source=item.bounds_source,
                contour_ids=item.source_contour_ids,
            )
            for item in regions
        ),
        projection_hypotheses=tuple(
            CompactProjectionHypothesis(
                id=item.id,
                region_ids=item.region_ids,
                axes=item.candidate_axes,
                score=item.score,
                ambiguity_group_id=item.ambiguity_group_id,
                ambiguity_rank=item.ambiguity_rank,
                ambiguity_size=item.ambiguity_size,
                measurement_refs=item.source_measurement_ids,
            )
            for item in hypotheses
        ),
    )


def query_compact_measurements(
    measurements: tuple[GeometryMeasurement, ...],
    *,
    measurement_ids: tuple[str, ...] = (),
    offset: int = 0,
    limit: int = 64,
) -> CompactMeasurementPage:
    if offset < 0 or limit < 1 or limit > 64:
        raise ValueError("compact_context_invalid_page")
    index = _measurement_index(measurements)
    if len(measurement_ids) != len(set(measurement_ids)):
        raise ValueError("compact_context_duplicate_query_id")
    if measurement_ids:
        missing = tuple(value for value in measurement_ids if value not in index)
        if missing:
            raise ValueError("compact_context_unknown_measurement_id")
        selected = tuple(index[value] for value in measurement_ids)
    else:
        selected = measurements
    page = selected[offset : offset + limit]
    next_offset = offset + len(page)
    truncated = next_offset < len(selected)
    return CompactMeasurementPage(
        items=tuple(_compact_measurement(item) for item in page),
        total=len(selected),
        offset=offset,
        returned_count=len(page),
        next_offset=next_offset if truncated else None,
        truncated=truncated,
    )


__all__ = [
    "CompactGeometryContext",
    "CompactMeasurement",
    "CompactMeasurementPage",
    "CompactProjectionHypothesis",
    "CompactRegion",
    "build_compact_geometry_context",
    "query_compact_measurements",
]
