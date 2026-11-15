from __future__ import annotations

from pathlib import Path
import random

import ezdxf
import pytest

from backend.app.geometria import extraction as extraction_module
from backend.app.geometria.extraction import derive_rectangular_hypotheses, extract_drawing


def _rectangle(x0: float, y0: float, x1: float, y1: float):
    return (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    )


def _write_lines(
    tmp_path: Path,
    lines: list[tuple[tuple[float, float], tuple[float, float], str]],
    *,
    unit_code: int = 4,
    seed: int | None = None,
) -> Path:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = unit_code
    for layer in sorted({layer for _, _, layer in lines}):
        document.layers.add(layer)
    ordered = lines.copy()
    if seed is not None:
        random.Random(seed).shuffle(ordered)
    modelspace = document.modelspace()
    for start, end, layer in ordered:
        modelspace.add_line(start, end, dxfattribs={"layer": layer})
    path = tmp_path / f"lines-{unit_code}-{seed}.dxf"
    document.saveas(path)
    return path


def _layered(segments, layer="ORTHO_FRONT"):
    return [(start, end, layer) for start, end in segments]


def _bounds(contour):
    xs = [point.x for point in contour.points_source]
    ys = [point.y for point in contour.points_source]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.parametrize("seed", range(8))
def test_shared_corner_rectangles_are_recovered_independent_of_line_order(tmp_path, seed):
    lines = _layered(
        _rectangle(0, 0, 20, 20)
        + _rectangle(0, 0, 10, 10)
        + _rectangle(30, 0, 35, 5)
    )

    extraction = extract_drawing(_write_lines(tmp_path, lines, seed=seed))

    assert {_bounds(contour) for contour in extraction.contours} == {
        (0.0, 0.0, 10.0, 10.0),
        (0.0, 0.0, 20.0, 20.0),
        (30.0, 0.0, 35.0, 5.0),
    }
    assert all(len(contour.source_entity_ids) == 4 for contour in extraction.contours)
    assert all(
        hypothesis.quantity is None
        for hypothesis in derive_rectangular_hypotheses(extraction)
    )


def test_coincident_original_rectangles_deduplicate_geometry_and_keep_provenance(tmp_path):
    lines = _layered(_rectangle(0, 0, 20, 10) + _rectangle(0, 0, 20, 10))

    extraction = extract_drawing(_write_lines(tmp_path, lines))

    assert [_bounds(contour) for contour in extraction.contours] == [(0.0, 0.0, 20.0, 10.0)]
    assert len(extraction.contours[0].source_entity_ids) == 8


@pytest.mark.parametrize(
    "segments",
    [
        (((-5, 0), (15, 0)), ((-5, 10), (15, 10)), ((0, -5), (0, 15)), ((10, -5), (10, 15))),
        (((0, 5), (5, 10)), ((5, 10), (10, 5)), ((10, 5), (5, 0)), ((5, 0), (0, 5))),
        (((0, 0), (10, 0)), ((10, 0), (10, 5)), ((10, 5), (0, 5))),
        (
            ((0, 0), (5, 0)), ((5, 0), (10, 0)),
            ((10, 0), (10, 5)), ((10, 5), (0, 5)), ((0, 5), (0, 0)),
        ),
        (((0, 0), (0, 5)), ((0, 5), (0, 10)), ((0, 10), (0, 0)), ((0, 0), (0, 10))),
    ],
)
def test_exact_pass_does_not_synthesize_edges_or_non_axis_aligned_rectangles(tmp_path, segments):
    extraction = extract_drawing(_write_lines(tmp_path, _layered(segments)))

    assert extraction.contours == ()


def test_segments_from_different_views_do_not_form_a_rectangle(tmp_path):
    lines = [
        ((0, 0), (10, 0), "ORTHO_FRONT"),
        ((10, 5), (0, 5), "ORTHO_FRONT"),
        ((0, 0), (0, 5), "ORTHO_TOP"),
        ((10, 0), (10, 5), "ORTHO_TOP"),
    ]

    extraction = extract_drawing(_write_lines(tmp_path, lines))

    assert extraction.contours == ()


def test_corner_tolerance_is_checked_on_real_coordinates(tmp_path):
    within_tolerance = (
        ((0.0, 0.0), (10.0, 0.0)),
        ((10.0000004, 0.0000002), (10.0000004, 5.0)),
        ((10.0, 5.0000003), (0.0, 5.0000003)),
        ((-0.0000002, 5.0), (-0.0000002, 0.0)),
    )
    beyond_tolerance = (
        ((20.0, 0.0), (30.0, 0.0)),
        ((30.0000012, 0.0), (30.0000012, 5.0)),
        ((30.0, 5.0), (20.0, 5.0)),
        ((20.0, 5.0), (20.0, 0.0)),
    )

    extraction = extract_drawing(
        _write_lines(tmp_path, _layered(within_tolerance + beyond_tolerance))
    )

    assert len(extraction.contours) == 1
    min_x, min_y, max_x, max_y = _bounds(extraction.contours[0])
    assert max_x - min_x == pytest.approx(10.0, abs=1e-6)
    assert max_y - min_y == pytest.approx(5.0, abs=1e-6)


@pytest.mark.parametrize("unit_code", [4, 0])
def test_exact_rectangles_preserve_known_and_unknown_units(tmp_path, unit_code):
    lines = _layered(_rectangle(0, 0, 20, 20) + _rectangle(0, 0, 10, 10))

    extraction = extract_drawing(_write_lines(tmp_path, lines, unit_code=unit_code))

    assert len(extraction.contours) == 2
    if unit_code == 4:
        assert extraction.status == "ready"
        assert all(contour.points_mm is not None for contour in extraction.contours)
    else:
        assert extraction.status == "needs_review"
        assert all(contour.points_mm is None for contour in extraction.contours)


def test_exact_rectangle_enumeration_limit_warns_and_falls_back_without_partial_results(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(extraction_module, "MAX_EXACT_RECTANGLE_PAIR_CHECKS", 0)
    lines = _layered(_rectangle(0, 0, 20, 20) + _rectangle(0, 0, 10, 10))

    extraction = extract_drawing(_write_lines(tmp_path, lines))

    assert {_bounds(contour) for contour in extraction.contours} == {(0.0, 0.0, 20.0, 20.0)}
    assert extraction.status == "needs_review"
    assert any(
        warning.startswith("exact_rectangle_enumeration_limit:view-front:")
        for warning in extraction.warnings
    )
