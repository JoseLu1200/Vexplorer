from __future__ import annotations

from dataclasses import asdict, replace
import json

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingView,
    Point2D,
)
from backend.app.general_furniture.context_payload import (
    build_compact_geometry_context,
    query_compact_measurements,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.projection_hypotheses import (
    derive_projection_hypotheses,
    derive_source_spatial_regions,
)


def _points(
    min_x: float, min_y: float, max_x: float, max_y: float
) -> tuple[Point2D, ...]:
    return (
        Point2D(x=min_x, y=min_y),
        Point2D(x=max_x, y=min_y),
        Point2D(x=max_x, y=max_y),
        Point2D(x=min_x, y=max_y),
    )


def _drawing(
    rectangles: tuple[tuple[str, float, float, float, float], ...],
    *,
    resolved_units: bool = True,
) -> DrawingExtraction:
    entities = tuple(
        DrawingEntity(
            id=f"entity-{name}",
            kind="LWPOLYLINE",
            layer="geometry",
            source_points=_points(min_x, min_y, max_x, max_y),
            points_mm=(
                _points(min_x, min_y, max_x, max_y) if resolved_units else None
            ),
        )
        for name, min_x, min_y, max_x, max_y in rectangles
    )
    contours = tuple(
        DrawingContour(
            id=f"contour-{name}",
            view_id="view-unknown",
            source_entity_ids=(f"entity-{name}",),
            points_source=_points(min_x, min_y, max_x, max_y),
            points_mm=(
                _points(min_x, min_y, max_x, max_y) if resolved_units else None
            ),
            closed=True,
        )
        for name, min_x, min_y, max_x, max_y in rectangles
    )
    bounds = Bounds2D(
        min_x=min(item[1] for item in rectangles),
        min_y=min(item[2] for item in rectangles),
        max_x=max(item[3] for item in rectangles),
        max_y=max(item[4] for item in rectangles),
    )
    return DrawingExtraction(
        drawing_id="drawing-context-payload",
        input_kind="general_furniture",
        status="ready" if resolved_units else "needs_review",
        source_unit="mm" if resolved_units else "unknown",
        unit_scale_to_mm=1.0 if resolved_units else None,
        coordinate_unit="mm" if resolved_units else "source",
        entities=entities,
        views=(
            DrawingView(
                id="view-unknown",
                label="UNKNOWN",
                entity_ids=tuple(item.id for item in entities),
                bounds_source=bounds,
                bounds_mm=bounds if resolved_units else None,
            ),
        ),
        contours=contours,
        dimensions=(),
        evidence=(),
        observations=(),
    )


def _context(extraction: DrawingExtraction):
    measurements = derive_geometry_measurements(extraction)
    regions = derive_source_spatial_regions(extraction, measurements)
    hypotheses = derive_projection_hypotheses(extraction, measurements)
    return (
        measurements,
        regions,
        hypotheses,
        build_compact_geometry_context(
            extraction, measurements, regions, hypotheses
        ),
    )


def test_initial_context_preserves_exact_span_values_and_resolvable_refs() -> None:
    extraction = _drawing(
        (
            ("left", 0.0, 0.0, 100.0, 60.0),
            ("middle", 220.0, 0.0, 320.0, 60.0),
            ("right", 440.0, 0.0, 500.0, 30.0),
        )
    )
    measurements, regions, hypotheses, context = _context(extraction)
    payload = context.to_payload()
    spans = {
        item.id: item
        for item in measurements
        if item.semantic in ("contour_span_x", "contour_span_y")
    }

    assert context.metadata.measurement_count == len(measurements)
    assert context.metadata.initial_span_count == len(spans)
    assert context.metadata.queryable_segment_count == len(measurements) - len(spans)
    assert set(item["id"] for item in payload["measurements"]) == set(spans)
    for item in payload["measurements"]:
        original = spans[item["id"]]
        assert item["binding_ref"] == original.binding_ref
        assert item["value_mm"] == original.value_mm
        assert item["source_value"] == original.source_value
        assert item["source_unit"] == original.source_unit
        assert tuple(item["contour_ids"]) == original.source_contour_ids
        assert tuple(item["entity_ids"]) == original.source_entity_ids
        assert tuple(item["view_ids"]) == (original.view_id,)

    region_ids = {item.id for item in regions}
    measurement_ids = set(spans)
    assert all(
        set(item["region_ids"]) <= region_ids
        and set(item["measurement_refs"]) <= measurement_ids
        for item in payload["projection_hypotheses"]
    )
    assert payload["metadata"]["region_count"] == len(regions)
    assert payload["metadata"]["hypothesis_count"] == len(hypotheses)


def test_unknown_units_keep_source_values_without_fabricating_metric_values() -> None:
    extraction = _drawing(
        (
            ("left", 0.0, 0.0, 100.0, 60.0),
            ("right", 220.0, 0.0, 320.0, 60.0),
        ),
        resolved_units=False,
    )
    _, _, _, context = _context(extraction)

    assert context.metadata.source_unit == "unknown"
    assert context.metadata.coordinate_unit == "source"
    assert all(item.value_mm is None for item in context.measurements)
    assert all(item.state == "unknown" for item in context.measurements)
    assert {item.source_value for item in context.measurements} == {60.0, 100.0}


def test_segment_query_is_exact_bounded_and_never_silently_drops_ids() -> None:
    extraction = _drawing((("panel", 0.0, 0.0, 100.0, 60.0),))
    measurements = derive_geometry_measurements(extraction)
    segment_ids = tuple(
        item.id for item in measurements if item.semantic == "contour_segment_length"
    )

    first_page = query_compact_measurements(measurements, offset=0, limit=2)
    selected = query_compact_measurements(
        measurements, measurement_ids=(segment_ids[3], segment_ids[0]), limit=2
    )

    assert first_page.total == len(measurements)
    assert first_page.returned_count == 2
    assert first_page.truncated is True
    assert first_page.next_offset == 2
    assert tuple(item.id for item in selected.items) == (segment_ids[3], segment_ids[0])
    assert selected.total == 2
    assert selected.truncated is False
    assert selected.items[0].segment_index == 4
    assert selected.to_payload()["items"][0]["warning"] == (
        "segment_length_not_component_dimension"
    )

    try:
        query_compact_measurements(
            measurements, measurement_ids=("measurement-missing",)
        )
    except ValueError as exc:
        assert str(exc) == "compact_context_unknown_measurement_id"
    else:
        raise AssertionError("unknown requested IDs must be rejected")


def test_ambiguity_and_truncation_metadata_survive_compaction() -> None:
    extraction = _drawing(
        (
            ("source", 0.0, 0.0, 100.0, 60.0),
            ("candidate-one", 220.0, 0.0, 320.0, 60.0),
            ("candidate-two", 220.0, 0.0, 319.0, 60.0),
        )
    )
    measurements = derive_geometry_measurements(extraction)
    regions = derive_source_spatial_regions(extraction, measurements)
    hypotheses = derive_projection_hypotheses(extraction, measurements)
    marked_regions = (
        replace(
            regions[0],
            warnings=(*regions[0].warnings, "spatial_region_set_truncated:2"),
        ),
        *regions[1:],
    )
    marked_hypotheses = (
        replace(
            hypotheses[0],
            warnings=(*hypotheses[0].warnings, "projection_candidate_set_truncated"),
        ),
        *hypotheses[1:],
    )

    context = build_compact_geometry_context(
        extraction, measurements, marked_regions, marked_hypotheses
    )

    assert context.metadata.spatial_regions_truncated is True
    assert context.metadata.projection_hypotheses_truncated is True
    assert context.metadata.hypothesis_count == len(marked_hypotheses)
    assert {
        (item.ambiguity_group_id, item.ambiguity_rank, item.ambiguity_size)
        for item in context.projection_hypotheses
    } == {
        (item.ambiguity_group_id, item.ambiguity_rank, item.ambiguity_size)
        for item in marked_hypotheses
    }
    assert {
        (item.id, item.score) for item in context.projection_hypotheses
    } == {(item.id, item.score) for item in marked_hypotheses}


def test_compact_initial_payload_reduces_repeated_geometry_by_at_least_60_percent() -> None:
    extraction = _drawing(
        tuple(
            (f"panel-{index:02d}", index * 300.0, 0.0, index * 300.0 + 100.0, 60.0)
            for index in range(12)
        )
    )
    measurements, regions, hypotheses, context = _context(extraction)
    legacy = {
        "measurements": [asdict(item) for item in measurements],
        "regions": [asdict(item) for item in regions],
        "projection_hypotheses": [asdict(item) for item in hypotheses],
    }
    legacy_size = len(json.dumps(legacy, separators=(",", ":")))
    compact_size = len(json.dumps(context.to_payload(), separators=(",", ":")))

    assert compact_size <= legacy_size * 0.40
