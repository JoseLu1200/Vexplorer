from __future__ import annotations

from backend.app.contratos.modelos import Bounds2D, DrawingContour, DrawingEntity, DrawingExtraction, DrawingObservation, DrawingView, Evidence, Point2D
from backend.app.general_furniture.measurements import derive_geometry_measurements


def _extraction(*, metric: bool = True, closed: bool = True) -> DrawingExtraction:
    points = tuple(Point2D(x=x, y=y) for x, y in ((10, 20), (110, 20), (110, 70), (10, 70)))
    bounds = Bounds2D(min_x=10, min_y=20, max_x=110, max_y=70)
    entity = DrawingEntity(
        id="entity-panel", kind="LWPOLYLINE", layer="PARTS",
        source_points=points, points_mm=points if metric else None,
    )
    contour = DrawingContour(
        id="contour-panel", view_id="view-front", source_entity_ids=(entity.id,),
        points_source=points, points_mm=points if metric else None, closed=closed,
    )
    return DrawingExtraction(
        drawing_id="drawing-general", input_kind="general_furniture",
        status="ready" if metric else "needs_review",
        source_unit="mm" if metric else "unknown", unit_scale_to_mm=1 if metric else None,
        coordinate_unit="mm" if metric else "source", entities=(entity,),
        views=(DrawingView(
            id="view-front", label="FRONT", entity_ids=(entity.id,),
            bounds_source=bounds, bounds_mm=bounds if metric else None,
        ),),
        contours=(contour,), dimensions=(),
        evidence=(Evidence(
            id="evidence-panel", kind="geometry", source_entity_ids=(entity.id,),
            description="Source polyline observed",
        ),),
        observations=(DrawingObservation(
            id="observation-front", view_id="view-front",
            contour_ids=(contour.id,), dimension_ids=(),
        ),),
    )


def test_metric_contour_yields_stable_spans_and_segments_with_provenance() -> None:
    measurements = derive_geometry_measurements(_extraction())
    by_id = {item.id: item for item in measurements}

    assert by_id["contour:contour-panel:span-x"].value_mm == 100
    assert by_id["contour:contour-panel:span-y"].value_mm == 50
    assert by_id["contour:contour-panel:segment-001"].value_mm == 100
    assert by_id["contour:contour-panel:segment-002"].value_mm == 50
    assert len([item for item in measurements if item.semantic == "contour_segment_length"]) == 4
    assert all(item.state == "observed" and item.source_unit == "mm" for item in measurements)
    assert all(item.view_id == "view-front" for item in measurements)
    assert all(item.source_observation_ids == ("observation-front",) for item in measurements)
    assert all(item.source_evidence_ids == ("evidence-panel",) for item in measurements)
    assert all(item.shape_kind == "rectangle" and item.axis_aligned for item in measurements)
    assert all(item.scope == "single_contour" for item in measurements)
    assert all("not_component_dimension" in item.warning for item in measurements)


def test_unknown_units_preserve_source_geometry_but_never_emit_millimetres() -> None:
    measurements = derive_geometry_measurements(_extraction(metric=False))

    assert measurements
    assert {item.state for item in measurements} == {"unknown"}
    assert all(item.value_mm is None and item.source_unit == "unknown" for item in measurements)
    assert next(item for item in measurements if item.semantic == "contour_span_x").source_value == 100


def test_open_contour_has_no_synthetic_closing_segment_or_quantity() -> None:
    measurements = derive_geometry_measurements(_extraction(closed=False))

    segments = [item for item in measurements if item.semantic == "contour_segment_length"]
    assert len(segments) == 3
    assert all(item.shape_kind == "polyline" and not item.closed for item in measurements)
    assert all(not hasattr(item, "quantity") for item in measurements)
