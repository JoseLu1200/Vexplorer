from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
)
from backend.app.general_furniture.measurements import GeometryMeasurement
from backend.app.general_furniture.orthographic_hypotheses import (
    derive_orthographic_hypotheses,
)
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
class CompactOrthographicHypothesis:
    id: str
    front_contour_id: str
    top_contour_id: str
    side_contour_id: str
    x_measurement_refs: tuple[str, str]
    y_measurement_refs: tuple[str, str]
    z_measurement_refs: tuple[str, str]
    axis_spans_mm: tuple[float, float, float]
    axis_intervals_mm: tuple[
        tuple[float, float], tuple[float, float], tuple[float, float]
    ]
    alignment_alternatives: tuple[str, ...]
    max_interval_error_mm: float
    tolerance_mm: float
    shared_support_contour_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    authority: str


@dataclass(frozen=True)
class CompactOrthographicFrameAlternative:
    alignment: str
    hypothesis_ids: tuple[str, ...]


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
    orthographic_hypothesis_count: int
    spatial_regions_truncated: bool
    projection_hypotheses_truncated: bool
    orthographic_hypotheses_truncated: bool
    orthographic_warnings: tuple[str, ...]
    orthographic_frame_constraint: str
    measurement_authority: str
    projection_authority: str
    orthographic_authority: str
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
    orthographic_hypotheses: tuple[CompactOrthographicHypothesis, ...]
    orthographic_frame_alternatives: tuple[
        CompactOrthographicFrameAlternative, ...
    ]

    def to_payload(self) -> dict[str, object]:
        return {
            "metadata": asdict(self.metadata),
            "measurements": tuple(item.to_payload() for item in self.measurements),
            "regions": tuple(asdict(item) for item in self.regions),
            "projection_hypotheses": tuple(
                asdict(item) for item in self.projection_hypotheses
            ),
            "orthographic_hypotheses": tuple(
                asdict(item) for item in self.orthographic_hypotheses
            ),
            "orthographic_frame_alternatives": tuple(
                asdict(item) for item in self.orthographic_frame_alternatives
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


class CandidateRegionLike(Protocol):
    id: str
    contour_ids: tuple[str, ...]
    bounds_source: tuple[float, float, float, float]


class VisualPageLike(Protocol):
    reference: str
    source_contour_ids: tuple[str, ...]
    crop_bounds_source: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class CompactContourTopology:
    contour_id: str
    bounds_source: tuple[float, float, float, float]
    closed: bool
    axis_aligned: bool
    containment_depth: int
    container_contour_ids: tuple[str, ...]
    contained_contour_ids: tuple[str, ...]
    coincident_contour_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompactRegionVisualLink:
    region_id: str
    source_view_ids: tuple[str, ...]
    bounds_source: tuple[float, float, float, float]
    contour_ids: tuple[str, ...]
    visual_reference: str | None
    match_kind: Literal[
        "exact_contours_and_bounds", "containing_crop", "unavailable"
    ]
    topology: tuple[CompactContourTopology, ...]
    authority: Literal[
        "candidate_region_visual_link_not_semantic_view_or_physical_identity_or_quantity"
    ] = (
        "candidate_region_visual_link_not_semantic_view_or_physical_identity_or_quantity"
    )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def _bounds_close(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _contains_bounds(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    return (
        outer[0] <= inner[0] + tolerance
        and outer[1] <= inner[1] + tolerance
        and outer[2] >= inner[2] - tolerance
        and outer[3] >= inner[3] - tolerance
    )


def _strictly_contains_bounds(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> bool:
    return _contains_bounds(outer, inner) and not _bounds_close(outer, inner)


def _contour_bounds(contour) -> tuple[float, float, float, float]:
    xs = tuple(float(point.x) for point in contour.points_source)
    ys = tuple(float(point.y) for point in contour.points_source)
    return min(xs), min(ys), max(xs), max(ys)


def _axis_aligned(contour) -> bool:
    points = tuple(contour.points_source)
    pairs = list(zip(points, points[1:]))
    if contour.closed and len(points) > 1:
        pairs.append((points[-1], points[0]))
    return bool(pairs) and all(
        abs(float(end.x) - float(start.x)) <= 1e-9
        or abs(float(end.y) - float(start.y)) <= 1e-9
        for start, end in pairs
    )


def build_region_visual_links(
    extraction: DrawingExtraction,
    regions: tuple[CandidateRegionLike, ...],
    visual_pages: tuple[VisualPageLike, ...],
) -> tuple[CompactRegionVisualLink, ...]:
    """Bind candidate geometry to the smallest containing crop without asserting identity."""
    contour_by_id = {item.id: item for item in extraction.contours}
    bounds_by_id = {
        item.id: _contour_bounds(item) for item in extraction.contours
    }
    bounds_by_view: dict[
        str, dict[str, tuple[float, float, float, float]]
    ] = {}
    for contour in extraction.contours:
        bounds_by_view.setdefault(contour.view_id, {})[contour.id] = bounds_by_id[
            contour.id
        ]
    region_ids = [item.id for item in regions]
    if len(region_ids) != len(set(region_ids)):
        raise ValueError("compact_region_visual_duplicate_region_id")
    result = []
    for region in regions:
        if not region.contour_ids or not set(region.contour_ids) <= set(contour_by_id):
            raise ValueError("compact_region_visual_unknown_contour")
        region_bounds = tuple(float(value) for value in region.bounds_source)
        region_contours = set(region.contour_ids)
        candidates = []
        for page in visual_pages:
            if page.crop_bounds_source is None:
                continue
            page_bounds = tuple(float(value) for value in page.crop_bounds_source)
            page_contours = set(page.source_contour_ids)
            if (
                region_contours <= page_contours
                and _contains_bounds(page_bounds, region_bounds)
            ):
                area = max(0.0, page_bounds[2] - page_bounds[0]) * max(
                    0.0, page_bounds[3] - page_bounds[1]
                )
                exact = (
                    region_contours == page_contours
                    and _bounds_close(region_bounds, page_bounds)
                )
                candidates.append(
                    (not exact, area, len(page_contours), page.reference, page)
                )
        selected = min(candidates, default=None, key=lambda item: item[:4])
        topology = []
        for contour_id in region.contour_ids:
            bounds = bounds_by_id[contour_id]
            contour = contour_by_id[contour_id]
            peer_bounds = bounds_by_view[contour.view_id]
            containers = tuple(
                sorted(
                    other_id
                    for other_id, other_bounds in peer_bounds.items()
                    if other_id != contour_id
                    and _strictly_contains_bounds(other_bounds, bounds)
                )
            )
            contained = tuple(
                sorted(
                    other_id
                    for other_id, other_bounds in peer_bounds.items()
                    if other_id != contour_id
                    and _strictly_contains_bounds(bounds, other_bounds)
                )
            )
            coincident = tuple(
                sorted(
                    other_id
                    for other_id, other_bounds in peer_bounds.items()
                    if other_id != contour_id
                    and _bounds_close(bounds, other_bounds)
                )
            )
            topology.append(
                CompactContourTopology(
                    contour_id=contour_id,
                    bounds_source=bounds,
                    closed=contour.closed,
                    axis_aligned=_axis_aligned(contour),
                    containment_depth=len(containers),
                    container_contour_ids=containers,
                    contained_contour_ids=contained,
                    coincident_contour_ids=coincident,
                )
            )
        source_view_ids = tuple(getattr(region, "source_view_ids", ()))
        if not source_view_ids:
            view_id = getattr(region, "view_id", None)
            source_view_ids = (view_id,) if isinstance(view_id, str) else ()
        result.append(
            CompactRegionVisualLink(
                region_id=region.id,
                source_view_ids=source_view_ids,
                bounds_source=region_bounds,
                contour_ids=region.contour_ids,
                visual_reference=selected[3] if selected is not None else None,
                match_kind=(
                    "unavailable"
                    if selected is None
                    else "containing_crop"
                    if selected[0]
                    else "exact_contours_and_bounds"
                ),
                topology=tuple(topology),
            )
        )
    return tuple(result)


def build_compact_review_context(
    proposal: GeneralFurnitureProposal,
    draft: GeneralFurnitureDraft,
    *,
    allowed_target_refs: tuple[str, ...],
    required_dimension_field_review_targets: tuple[str, ...],
    required_hardware_classification_field_review_targets: tuple[object, ...],
    required_existence_field_review_targets: tuple[str, ...],
    required_evidence_disposition_review_targets: tuple[str, ...],
    allowed_source_refs: tuple[str, ...],
) -> dict[str, object]:
    """Project proposal and resolved draft once for critic review."""
    if (
        proposal.id != draft.proposal_id
        or proposal.drawing_id != draft.drawing_id
        or proposal.ledger_revision != draft.ledger_revision
        or proposal.construction_scenario_id != draft.construction_scenario_id
    ):
        raise ValueError("compact_review_context_mismatch")
    return {
        "schema_version": "compact-general-review-context-1",
        "proposal_id": proposal.id,
        "drawing_id": proposal.drawing_id,
        "ledger_revision": proposal.ledger_revision,
        "construction_scenario_id": draft.construction_scenario_id,
        "bindings": tuple(item.model_dump(mode="python") for item in proposal.bindings),
        "components": tuple(item.model_dump(mode="python") for item in draft.components),
        "premises": tuple(item.model_dump(mode="python") for item in draft.premises),
        "assumptions": draft.assumptions,
        "construction_parameters": tuple(
            item.model_dump(mode="python") for item in draft.construction_parameters
        ),
        "construction_constraints": tuple(
            item.model_dump(mode="python") for item in draft.construction_constraints
        ),
        "construction_details": tuple(
            item.model_dump(mode="python") for item in draft.construction_details
        ),
        "construction_decisions": tuple(
            item.model_dump(mode="python") for item in draft.construction_decisions
        ),
        "construction_placements": tuple(
            item.model_dump(mode="python") for item in draft.construction_placements
        ),
        "evidence_dispositions": tuple(
            item.model_dump(mode="python") for item in draft.evidence_dispositions
        ),
        "allowed_target_refs": allowed_target_refs,
        "required_dimension_field_review_targets": (
            required_dimension_field_review_targets
        ),
        "required_hardware_classification_field_review_targets": (
            required_hardware_classification_field_review_targets
        ),
        "required_existence_field_review_targets": (
            required_existence_field_review_targets
        ),
        "required_evidence_disposition_review_targets": (
            required_evidence_disposition_review_targets
        ),
        "allowed_source_refs": allowed_source_refs,
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
    orthographic = derive_orthographic_hypotheses(extraction, measurements)
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
            orthographic_hypothesis_count=len(orthographic.hypotheses),
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
            orthographic_hypotheses_truncated=orthographic.truncated,
            orthographic_warnings=orthographic.warnings,
            orthographic_frame_constraint=orthographic.frame_constraint,
            measurement_authority=(
                "ledger_geometry_observation_not_component_dimension"
            ),
            projection_authority=(
                "heuristic_not_probability_or_physical_identity"
            ),
            orthographic_authority=orthographic.authority,
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
        orthographic_hypotheses=tuple(
            CompactOrthographicHypothesis(
                id=item.id,
                front_contour_id=item.front_contour_id,
                top_contour_id=item.top_contour_id,
                side_contour_id=item.side_contour_id,
                x_measurement_refs=item.x_measurement_refs,
                y_measurement_refs=item.y_measurement_refs,
                z_measurement_refs=item.z_measurement_refs,
                axis_spans_mm=item.axis_spans_mm,
                axis_intervals_mm=item.axis_intervals_mm,
                alignment_alternatives=item.alignment_alternatives,
                max_interval_error_mm=item.max_interval_error_mm,
                tolerance_mm=item.tolerance_mm,
                shared_support_contour_ids=item.shared_support_contour_ids,
                warnings=item.warnings,
                authority=item.authority,
            )
            for item in orthographic.hypotheses
        ),
        orthographic_frame_alternatives=tuple(
            CompactOrthographicFrameAlternative(
                alignment=item.alignment,
                hypothesis_ids=item.hypothesis_ids,
            )
            for item in orthographic.frame_alignment_alternatives
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
    "CompactContourTopology",
    "CompactGeometryContext",
    "CompactMeasurement",
    "CompactMeasurementPage",
    "CompactProjectionHypothesis",
    "CompactRegion",
    "CompactRegionVisualLink",
    "build_compact_geometry_context",
    "build_compact_review_context",
    "build_region_visual_links",
    "query_compact_measurements",
]
