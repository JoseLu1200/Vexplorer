from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingView,
    Point2D,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.orthographic_hypotheses import (
    derive_orthographic_hypotheses,
)


_FRAMES = {
    "FRONT": ((1000.0, 2000.0), (100.0, 60.0)),
    "TOP": ((3000.0, 4000.0), (100.0, 70.0)),
    "SIDE": ((5000.0, 6000.0), (70.0, 60.0)),
}


def _points(bounds: tuple[float, float, float, float]) -> tuple[Point2D, ...]:
    min_x, min_y, max_x, max_y = bounds
    return (
        Point2D(x=min_x, y=min_y),
        Point2D(x=max_x, y=min_y),
        Point2D(x=max_x, y=max_y),
        Point2D(x=min_x, y=max_y),
    )


def _drawing(
    rectangles: Iterable[
        tuple[str, str, tuple[float, float, float, float]]
    ],
    *,
    frames: dict[str, tuple[tuple[float, float], tuple[float, float]]] | None = None,
) -> DrawingExtraction:
    selected_frames = frames or _FRAMES
    entities = []
    contours = []
    entity_ids_by_role: dict[str, list[str]] = {role: [] for role in selected_frames}
    for role, name, local_bounds in rectangles:
        origin, _ = selected_frames[role]
        bounds = (
            origin[0] + local_bounds[0],
            origin[1] + local_bounds[1],
            origin[0] + local_bounds[2],
            origin[1] + local_bounds[3],
        )
        entity_id = f"entity-{name}"
        contour_id = f"contour-{name}"
        points = _points(bounds)
        entities.append(
            DrawingEntity(
                id=entity_id,
                kind="LWPOLYLINE",
                layer=f"ORTHO_{role}",
                source_points=points,
                points_mm=points,
            )
        )
        contours.append(
            DrawingContour(
                id=contour_id,
                view_id=f"view-{role.lower()}",
                source_entity_ids=(entity_id,),
                points_source=points,
                points_mm=points,
                closed=True,
            )
        )
        entity_ids_by_role[role].append(entity_id)
    views = []
    for role, (origin, spans) in selected_frames.items():
        bounds = Bounds2D(
            min_x=origin[0],
            min_y=origin[1],
            max_x=origin[0] + spans[0],
            max_y=origin[1] + spans[1],
        )
        views.append(
            DrawingView(
                id=f"view-{role.lower()}",
                label=role,
                entity_ids=tuple(entity_ids_by_role[role]),
                bounds_source=bounds,
                bounds_mm=bounds,
            )
        )
    return DrawingExtraction(
        drawing_id="drawing-orthographic-fixture",
        input_kind="mounted_orthographic_views",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=tuple(entities),
        views=tuple(views),
        contours=tuple(contours),
        dimensions=(),
        evidence=(),
        observations=(),
    )


def _piece(
    name: str,
    *,
    x: tuple[float, float],
    y: tuple[float, float],
    z: tuple[float, float],
    top_x_mirrored: bool = False,
) -> tuple[tuple[str, str, tuple[float, float, float, float]], ...]:
    top_x = (100.0 - x[1], 100.0 - x[0]) if top_x_mirrored else x
    return (
        ("FRONT", f"{name}-front", (x[0], z[0], x[1], z[1])),
        ("TOP", f"{name}-top", (top_x[0], y[0], top_x[1], y[1])),
        ("SIDE", f"{name}-side", (y[0], z[0], y[1], z[1])),
    )


def _derive(extraction: DrawingExtraction):
    return derive_orthographic_hypotheses(
        extraction, derive_geometry_measurements(extraction)
    )


def test_translated_frames_produce_one_three_axis_support_hypothesis() -> None:
    extraction = _drawing(
        _piece("panel", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
    )

    result = _derive(extraction)

    assert result.warnings == ()
    assert result.truncated is False
    assert len(result.hypotheses) == 1
    item = result.hypotheses[0]
    assert (
        item.front_contour_id,
        item.top_contour_id,
        item.side_contour_id,
    ) == ("contour-panel-front", "contour-panel-top", "contour-panel-side")
    assert item.axis_spans_mm == (30.0, 20.0, 50.0)
    assert item.axis_intervals_mm == (
        (10.0, 40.0),
        (5.0, 25.0),
        (0.0, 50.0),
    )
    assert item.alignment_alternatives == (
        "top_x:direct|side_y:direct|side_z:direct",
    )
    assert item.max_interval_error_mm == 0.0
    assert all(
        value.startswith("measurement:")
        for value in (
            *item.x_measurement_refs,
            *item.y_measurement_refs,
            *item.z_measurement_refs,
        )
    )
    assert item.authority == (
        "heuristic_not_physical_identity_or_quantity_or_ownership"
    )


def test_mirrored_axis_is_retained_as_explicit_alignment_alternative() -> None:
    extraction = _drawing(
        _piece(
            "panel",
            x=(10.0, 40.0),
            y=(5.0, 25.0),
            z=(0.0, 50.0),
            top_x_mirrored=True,
        )
    )

    item = _derive(extraction).hypotheses[0]

    assert item.alignment_alternatives == (
        "top_x:mirrored|side_y:direct|side_z:direct",
    )

    symmetric = _derive(
        _drawing(
            _piece(
                "symmetric",
                x=(20.0, 80.0),
                y=(10.0, 60.0),
                z=(10.0, 50.0),
            )
        )
    ).hypotheses[0]
    assert len(symmetric.alignment_alternatives) == 8
    assert any("top_x:direct" in value for value in symmetric.alignment_alternatives)
    assert any("top_x:mirrored" in value for value in symmetric.alignment_alternatives)


def test_two_candidates_can_share_one_side_projection_without_ownership() -> None:
    rectangles = (
        *_piece("narrow", x=(5.0, 25.0), y=(10.0, 30.0), z=(0.0, 50.0))[:2],
        *_piece("wide", x=(50.0, 90.0), y=(10.0, 30.0), z=(0.0, 50.0))[:2],
        ("SIDE", "shared-side", (10.0, 0.0, 30.0, 50.0)),
    )

    result = _derive(_drawing(rectangles))

    assert len(result.hypotheses) == 2
    assert {item.side_contour_id for item in result.hypotheses} == {
        "contour-shared-side"
    }
    assert all(
        item.shared_support_contour_ids == ("contour-shared-side",)
        for item in result.hypotheses
    )
    assert all("shared_projection_support" in item.warnings for item in result.hypotheses)


def test_frame_alignment_groups_prevent_mixing_incompatible_piece_mappings() -> None:
    rectangles = (
        *_piece("direct", x=(5.0, 25.0), y=(5.0, 20.0), z=(0.0, 40.0)),
        *_piece(
            "mirrored",
            x=(60.0, 90.0),
            y=(35.0, 60.0),
            z=(10.0, 55.0),
            top_x_mirrored=True,
        ),
    )

    result = _derive(_drawing(rectangles))

    assert len(result.hypotheses) == 2
    assert result.frame_constraint == (
        "select_one_global_frame_alignment;"
        "do_not_combine_incompatible_hypotheses"
    )
    assert {
        item.alignment: len(item.hypothesis_ids)
        for item in result.frame_alignment_alternatives
    } == {
        "top_x:direct|side_y:direct|side_z:direct": 1,
        "top_x:mirrored|side_y:direct|side_z:direct": 1,
    }
    assert all(
        len(item.hypothesis_ids) == 1
        for item in result.frame_alignment_alternatives
    )


def test_unknown_units_missing_roles_and_inconsistent_frames_fail_closed() -> None:
    complete = _drawing(
        _piece("panel", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
    )
    unknown_units = complete.model_copy(
        update={"coordinate_unit": "source", "source_unit": "unknown", "unit_scale_to_mm": None}
    )
    missing_side = complete.model_copy(
        update={
            "views": tuple(item for item in complete.views if item.label != "SIDE"),
            "contours": tuple(
                item for item in complete.contours if item.view_id != "view-side"
            ),
        }
    )
    bad_frames = dict(_FRAMES)
    bad_frames["TOP"] = ((3000.0, 4000.0), (120.0, 70.0))
    inconsistent = _drawing(
        _piece("panel", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0)),
        frames=bad_frames,
    )
    side_view = next(item for item in complete.views if item.label == "SIDE")
    unknown_role = complete.model_copy(
        update={
            "views": tuple(
                item.model_copy(update={"label": "UNKNOWN"})
                if item.id == side_view.id
                else item
                for item in complete.views
            )
        }
    )
    inconsistent_scale = complete.model_copy(
        update={
            "views": tuple(
                item.model_copy(
                    update={
                        "bounds_mm": Bounds2D(
                            min_x=item.bounds_mm.min_x + 1.0,
                            min_y=item.bounds_mm.min_y,
                            max_x=item.bounds_mm.max_x + 1.0,
                            max_y=item.bounds_mm.max_y,
                        )
                    }
                )
                if item.label == "TOP"
                else item
                for item in complete.views
            )
        }
    )

    assert _derive(unknown_units).warnings == ("orthographic_metric_units_required",)
    assert _derive(missing_side).warnings == ("orthographic_explicit_views_required",)
    assert _derive(unknown_role).warnings == ("orthographic_explicit_views_required",)
    assert _derive(inconsistent).warnings == ("orthographic_frame_inconsistent",)
    assert _derive(inconsistent_scale).warnings == (
        "orthographic_metric_scale_inconsistent",
    )
    assert not _derive(unknown_units).hypotheses
    assert not _derive(missing_side).hypotheses
    assert not _derive(inconsistent).hypotheses


def test_incompatible_intervals_do_not_form_a_triplet() -> None:
    rectangles = list(
        _piece("panel", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
    )
    rectangles[1] = ("TOP", "panel-top", (50.0, 5.0, 80.0, 25.0))

    result = _derive(_drawing(rectangles))

    assert result.hypotheses == ()
    assert result.warnings == ()


def test_axis_aligned_l_shape_is_not_treated_as_rectangular_support() -> None:
    extraction = _drawing(
        _piece("panel", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
    )
    points = _points((1010.0, 2000.0, 1040.0, 2050.0))
    l_shape = (
        points[0],
        points[1],
        Point2D(x=1040.0, y=2020.0),
        Point2D(x=1020.0, y=2020.0),
        Point2D(x=1020.0, y=2050.0),
        points[3],
    )
    extraction = extraction.model_copy(
        update={
            "entities": tuple(
                item.model_copy(update={"source_points": l_shape, "points_mm": l_shape})
                if item.id == "entity-panel-front"
                else item
                for item in extraction.entities
            ),
            "contours": tuple(
                item.model_copy(update={"points_source": l_shape, "points_mm": l_shape})
                if item.id == "contour-panel-front"
                else item
                for item in extraction.contours
            ),
        }
    )

    result = _derive(extraction)

    assert result.hypotheses == ()


def test_inconsistent_external_measurements_fail_closed() -> None:
    extraction = _drawing(
        _piece("panel", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
    )
    measurements = derive_geometry_measurements(extraction)
    target_index = next(
        index
        for index, item in enumerate(measurements)
        if item.id == "contour:contour-panel-front:span-x"
    )
    target = measurements[target_index]
    variants = (
        replace(target, value_mm=float("nan")),
        replace(target, value_mm=31.0),
        replace(target, state="unknown"),
        replace(target, view_id="view-top"),
    )
    for invalid in variants:
        selected = (*measurements[:target_index], invalid, *measurements[target_index + 1 :])
        result = derive_orthographic_hypotheses(extraction, selected)
        assert result.hypotheses == ()
        assert result.warnings == ("orthographic_metric_measurements_inconsistent",)

    duplicate = derive_orthographic_hypotheses(
        extraction, (*measurements, target)
    )
    assert duplicate.hypotheses == ()
    assert duplicate.warnings == ("orthographic_metric_measurements_inconsistent",)


def test_nested_contour_hypothesis_remains_materially_unclassified() -> None:
    extraction = _drawing(
        (
            *_piece("outer", x=(0.0, 100.0), y=(0.0, 70.0), z=(0.0, 60.0)),
            *_piece("inner", x=(20.0, 40.0), y=(10.0, 30.0), z=(10.0, 40.0)),
        )
    )

    result = _derive(extraction)
    inner = next(
        item for item in result.hypotheses if item.front_contour_id == "contour-inner-front"
    )

    assert "contour_material_role_unclassified" in inner.warnings
    assert "accepted" not in inner.authority


def test_geometry_is_invariant_to_input_order_and_reference_renaming() -> None:
    original = _drawing(
        _piece("first", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
    )
    renamed_rectangles = tuple(
        reversed(
            _piece("renamed", x=(10.0, 40.0), y=(5.0, 25.0), z=(0.0, 50.0))
        )
    )
    renamed = _drawing(renamed_rectangles)

    left = _derive(original).hypotheses[0]
    right = _derive(renamed).hypotheses[0]

    assert left.axis_spans_mm == right.axis_spans_mm
    assert left.alignment_alternatives == right.alignment_alternatives
    assert left.max_interval_error_mm == right.max_interval_error_mm


def test_output_cap_reports_truncation_without_silent_candidates() -> None:
    rectangles = []
    for role in ("FRONT", "TOP", "SIDE"):
        for index in range(6):
            if role == "FRONT":
                bounds = (20.0, 10.0, 80.0, 50.0)
            elif role == "TOP":
                bounds = (20.0, 15.0, 80.0, 55.0)
            else:
                bounds = (15.0, 10.0, 55.0, 50.0)
            rectangles.append((role, f"{role.lower()}-{index}", bounds))

    result = _derive(_drawing(rectangles))

    assert len(result.hypotheses) == 128
    assert result.truncated is True
    assert result.warnings == ("orthographic_hypotheses_truncated:88",)


def test_capped_selection_is_order_and_rename_invariant_by_geometry() -> None:
    rectangles = tuple(
        (role, f"original-{role.lower()}-{index}", bounds)
        for role, bounds in (
            ("FRONT", (20.0, 10.0, 80.0, 50.0)),
            ("TOP", (20.0, 15.0, 80.0, 55.0)),
            ("SIDE", (15.0, 10.0, 55.0, 50.0)),
        )
        for index in range(6)
    )
    renamed = tuple(
        (role, f"renamed-{len(rectangles) - index}", bounds)
        for index, (role, _, bounds) in enumerate(reversed(rectangles))
    )

    left = _derive(_drawing(rectangles))
    right = _derive(_drawing(renamed))

    def signatures(result):
        return tuple(
            (
                item.axis_spans_mm,
                item.axis_intervals_mm,
                item.alignment_alternatives,
                item.max_interval_error_mm,
                len(item.shared_support_contour_ids),
            )
            for item in result.hypotheses
        )

    assert signatures(left) == signatures(right)
    assert len(left.hypotheses) == len(right.hypotheses) == 128
    assert left.warnings == right.warnings == (
        "orthographic_hypotheses_truncated:88",
    )


def test_sparse_large_drawing_counts_only_real_pairwise_join_work() -> None:
    frames = {
        "FRONT": ((1000.0, 2000.0), (5000.0, 5000.0)),
        "TOP": ((7000.0, 8000.0), (5000.0, 5000.0)),
        "SIDE": ((13000.0, 14000.0), (5000.0, 5000.0)),
    }
    rectangles = tuple(
        rectangle
        for index in range(64)
        for rectangle in _piece(
            f"piece-{index}",
            x=(index * 12.0, index * 12.0 + 5.0),
            y=(index * 11.0, index * 11.0 + 4.0),
            z=(index * 10.0, index * 10.0 + 3.0),
        )
    )

    result = _derive(_drawing(rectangles, frames=frames))

    assert len(result.hypotheses) == 64
    assert result.truncated is False
    assert result.warnings == ()
    assert {
        (
            item.front_contour_id,
            item.top_contour_id,
            item.side_contour_id,
        )
        for item in result.hypotheses
    } == {
        (
            f"contour-piece-{index}-front",
            f"contour-piece-{index}-top",
            f"contour-piece-{index}-side",
        )
        for index in range(64)
    }


def test_evaluation_cap_fails_closed_and_reports_omitted_search() -> None:
    rectangles = []
    for role in ("FRONT", "TOP", "SIDE"):
        for index in range(51):
            bounds = {
                "FRONT": (20.0, 10.0, 80.0, 50.0),
                "TOP": (20.0, 15.0, 80.0, 55.0),
                "SIDE": (15.0, 10.0, 55.0, 50.0),
            }[role]
            rectangles.append((role, f"{role.lower()}-{index}", bounds))

    result = _derive(_drawing(rectangles))

    assert result.hypotheses == ()
    assert result.truncated is True
    assert result.warnings == (
        "orthographic_triplet_evaluation_budget_exceeded:1000003",
    )


def test_dense_408_per_view_fails_closed_without_materializing_pair_tables() -> None:
    rectangles = tuple(
        (role, f"dense-{role.lower()}-{index}", bounds)
        for role, bounds in (
            ("FRONT", (20.0, 10.0, 80.0, 50.0)),
            ("TOP", (20.0, 15.0, 80.0, 55.0)),
            ("SIDE", (15.0, 10.0, 55.0, 50.0)),
        )
        for index in range(408)
    )

    result = _derive(_drawing(rectangles))

    assert result.hypotheses == ()
    assert result.truncated is True
    assert result.warnings == (
        "orthographic_triplet_evaluation_budget_exceeded:1000007",
    )
