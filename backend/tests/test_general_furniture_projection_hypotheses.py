from __future__ import annotations

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingView,
    Point2D,
)
from backend.app.general_furniture.measurements import (
    GeometryMeasurement,
    derive_geometry_measurements,
)
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
) -> DrawingExtraction:
    entities = tuple(
        DrawingEntity(
            id=f"entity-{name}",
            kind="LWPOLYLINE",
            layer="geometry",
            source_points=_points(min_x, min_y, max_x, max_y),
            points_mm=_points(min_x, min_y, max_x, max_y),
        )
        for name, min_x, min_y, max_x, max_y in rectangles
    )
    contours = tuple(
        DrawingContour(
            id=f"contour-{name}",
            view_id="view-unknown",
            source_entity_ids=(f"entity-{name}",),
            points_source=_points(min_x, min_y, max_x, max_y),
            points_mm=_points(min_x, min_y, max_x, max_y),
            closed=True,
        )
        for name, min_x, min_y, max_x, max_y in rectangles
    )
    min_x = min(item[1] for item in rectangles)
    min_y = min(item[2] for item in rectangles)
    max_x = max(item[3] for item in rectangles)
    max_y = max(item[4] for item in rectangles)
    bounds = Bounds2D(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)
    return DrawingExtraction(
        drawing_id="drawing-synthetic",
        input_kind="general_furniture",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=entities,
        views=(
            DrawingView(
                id="view-unknown",
                label="UNKNOWN",
                entity_ids=tuple(item.id for item in entities),
                bounds_source=bounds,
                bounds_mm=bounds,
            ),
        ),
        contours=contours,
        dimensions=(),
        evidence=(),
        observations=(),
    )


def test_regions_group_nearby_contours_without_claiming_semantic_views() -> None:
    extraction = _drawing(
        (
            ("a-outer", 0.0, 0.0, 100.0, 60.0),
            ("a-inner", 10.0, 10.0, 90.0, 50.0),
            ("b-outer", 220.0, 0.0, 320.0, 60.0),
            ("b-inner", 230.0, 10.0, 310.0, 50.0),
            ("c-outer", 440.0, 0.0, 540.0, 60.0),
            ("c-inner", 450.0, 10.0, 530.0, 50.0),
        )
    )
    measurements = derive_geometry_measurements(extraction)

    regions = derive_source_spatial_regions(extraction, measurements)

    assert [item.bounds_source for item in regions] == [
        (0.0, 0.0, 100.0, 60.0),
        (220.0, 0.0, 320.0, 60.0),
        (440.0, 0.0, 540.0, 60.0),
    ]
    assert regions[0].source_view_ids == ("view-unknown",)
    assert regions[0].source_contour_ids == ("contour-a-inner", "contour-a-outer")
    assert regions[0].source_entity_ids == ("entity-a-inner", "entity-a-outer")
    assert set(regions[0].source_measurement_ids) == {
        item.id
        for item in measurements
        if item.source_contour_ids[0] in regions[0].source_contour_ids
    }
    assert regions[0].candidate_label == "UNKNOWN"
    assert "spatial_region_not_semantic_view" in regions[0].warnings
    assert "contour_interior_not_classified" in regions[0].warnings


def test_region_ids_and_order_do_not_depend_on_input_contour_order() -> None:
    extraction = _drawing(
        (
            ("left", 0.0, 0.0, 100.0, 40.0),
            ("middle", 220.0, 0.0, 320.0, 40.0),
            ("right", 440.0, 0.0, 540.0, 40.0),
        )
    )
    reversed_extraction = extraction.model_copy(
        update={
            "entities": tuple(reversed(extraction.entities)),
            "contours": tuple(reversed(extraction.contours)),
        }
    )

    expected = derive_source_spatial_regions(
        extraction, derive_geometry_measurements(extraction)
    )
    actual = derive_source_spatial_regions(
        reversed_extraction, derive_geometry_measurements(reversed_extraction)
    )

    assert actual == expected


def test_correspondences_keep_multiple_matches_explicitly_ambiguous() -> None:
    extraction = _drawing(
        (
            ("source", 0.0, 0.0, 100.0, 60.0),
            ("candidate-one", 220.0, 0.0, 320.0, 60.0),
            ("candidate-two", 220.0, 0.0, 320.0, 60.0),
            ("different", 440.0, 0.0, 510.0, 30.0),
        )
    )
    measurements = derive_geometry_measurements(extraction)

    hypotheses = derive_projection_hypotheses(extraction, measurements)

    source_measurement_id = "contour:contour-source:span-x"
    matches = [
        item
        for item in hypotheses
        if item.source_measurement_ids[0] == source_measurement_id
        and item.candidate_axes == ("x", "x")
    ]
    assert len(matches) == 2
    assert len({item.ambiguity_group_id for item in matches}) == 1
    assert {item.ambiguity_rank for item in matches} == {1, 2}
    assert {item.ambiguity_size for item in matches} == {2}
    assert all(item.status == "hypothesis" for item in matches)
    assert all(item.candidate_labels == ("UNKNOWN", "UNKNOWN") for item in matches)
    assert all(item.score_kind == "heuristic_not_probability" for item in matches)
    assert all("physical_identity_unconfirmed" in item.warnings for item in matches)
    assert all(item.source_view_ids == ("view-unknown",) for item in matches)
    assert {
        item.source_measurement_ids[1] for item in matches
    } == {
        "contour:contour-candidate-one:span-x",
        "contour:contour-candidate-two:span-x",
    }


def test_no_span_measurements_means_no_correspondence_candidates() -> None:
    extraction = _drawing(
        (
            ("left", 0.0, 0.0, 100.0, 40.0),
            ("right", 220.0, 0.0, 320.0, 40.0),
        )
    )
    segment_measurements = tuple(
        item
        for item in derive_geometry_measurements(extraction)
        if item.semantic == "contour_segment_length"
    )

    assert derive_projection_hypotheses(extraction, segment_measurements) == ()


def test_measurement_references_must_close_against_the_extraction() -> None:
    extraction = _drawing(
        (
            ("left", 0.0, 0.0, 100.0, 40.0),
            ("right", 220.0, 0.0, 320.0, 40.0),
        )
    )
    measurement = derive_geometry_measurements(extraction)[0]
    invalid = GeometryMeasurement(
        **{
            **measurement.__dict__,
            "id": "measurement-invalid-reference",
            "source_contour_ids": ("contour-missing",),
        }
    )

    try:
        derive_source_spatial_regions(extraction, (invalid,))
    except ValueError as exc:
        assert str(exc) == "projection_measurement_unknown_contour"
    else:
        raise AssertionError("an unknown source contour must be rejected")


def test_regions_and_hypotheses_have_explicit_output_budgets() -> None:
    extraction = _drawing(
        tuple(
            (f"item-{index:02d}", index * 100.0, 0.0, index * 100.0 + 10.0, 10.0)
            for index in range(30)
        )
    )
    measurements = derive_geometry_measurements(extraction)

    regions = derive_source_spatial_regions(extraction, measurements)
    hypotheses = derive_projection_hypotheses(extraction, measurements)

    assert len(regions) == 24
    assert all("spatial_region_set_truncated:6" in item.warnings for item in regions)
    assert len(hypotheses) == 128
    assert all("projection_candidate_set_truncated" in item.warnings for item in hypotheses)


def test_input_budget_rejects_unbounded_contour_pairing() -> None:
    extraction = _drawing(
        tuple(
            (f"item-{index:03d}", index * 10.0, 0.0, index * 10.0 + 1.0, 1.0)
            for index in range(513)
        )
    )
    measurements = derive_geometry_measurements(extraction)

    try:
        derive_source_spatial_regions(extraction, measurements)
    except ValueError as exc:
        assert str(exc) == "projection_input_budget_exceeded"
    else:
        raise AssertionError("unbounded contour pairing must be rejected")
