from __future__ import annotations

import ezdxf

from backend.app.geometria.extraction import derive_rectangular_hypotheses, extract_drawing


def _drawing(tmp_path, *, unit_code: int, sizes=((1.0, 0.5),), labels=("FRONT",)):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = unit_code
    modelspace = document.modelspace()
    for index, ((width, height), label) in enumerate(zip(sizes, labels, strict=True)):
        x = index * 1000.0
        modelspace.add_lwpolyline([(x, 0), (x + width, 0), (x + width, height), (x, height)], close=True)
        modelspace.add_text(label).set_placement((x, -20))
    path = tmp_path / "drawing.dxf"
    document.saveas(path)
    return path


def test_one_inch_is_normalized_to_25_4_mm(tmp_path):
    extraction = extract_drawing(_drawing(tmp_path, unit_code=1))

    assert extraction.source_unit == "in"
    assert extraction.unit_scale_to_mm == 25.4
    assert extraction.contours[0].points_mm[1].x == 25.4


def test_unknown_units_preserve_source_and_do_not_claim_metric_values(tmp_path):
    extraction = extract_drawing(_drawing(tmp_path, unit_code=0))

    assert extraction.status == "needs_review"
    assert extraction.unit_scale_to_mm is None
    assert extraction.contours[0].points_source[1].x == 1.0
    assert extraction.contours[0].points_mm is None


def test_three_views_do_not_become_a_quantity(tmp_path):
    extraction = extract_drawing(_drawing(
        tmp_path,
        unit_code=4,
        sizes=((600, 400), (600, 18), (400, 18)),
        labels=("FRONT", "TOP", "RIGHT"),
    ))
    hypotheses = derive_rectangular_hypotheses(extraction)

    assert {view.label for view in extraction.views} == {"FRONT", "TOP", "SIDE"}
    assert len(hypotheses) == 3
    assert all(hypothesis.quantity is None for hypothesis in hypotheses)
    assert all(hypothesis.thickness_mm is None for hypothesis in hypotheses)


def test_geometry_changes_with_input_dimensions_without_fixture_constants(tmp_path):
    first = derive_rectangular_hypotheses(extract_drawing(
        _drawing(tmp_path, unit_code=4, sizes=((700, 350),)),
    ))[0]

    second_dir = tmp_path / "second"
    second_dir.mkdir()
    second = derive_rectangular_hypotheses(extract_drawing(
        _drawing(second_dir, unit_code=4, sizes=((910, 275),)),
    ))[0]

    assert first.observed_dimensions_mm == (700.0, 350.0)
    assert second.observed_dimensions_mm == (910.0, 275.0)
    assert first.quantity is None and second.quantity is None


def test_connected_lines_form_a_traceable_contour(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    for start, end in (((0, 0), (300, 0)), ((300, 0), (300, 120)), ((300, 120), (0, 120)), ((0, 120), (0, 0))):
        modelspace.add_line(start, end)
    modelspace.add_text("FRONT").set_placement((0, -20))
    path = tmp_path / "lines.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert len(extraction.contours) == 1
    assert len(extraction.contours[0].source_entity_ids) == 4
    assert derive_rectangular_hypotheses(extraction)[0].observed_dimensions_mm == (300.0, 120.0)
