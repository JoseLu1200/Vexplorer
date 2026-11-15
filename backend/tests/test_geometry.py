from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from backend.app.agente.vision import render_view
from backend.app.geometria.extraction import derive_rectangular_hypotheses, extract_drawing
from backend.app.ingesta.dxf_reader import MAX_ENTITIES, parse_dxf


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


def test_explicit_orthographic_layers_isolate_overlapping_views_and_renders(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    layer_roles = {
        "ORTHO_FRONT": "view-front",
        "VIEW_TOP": "view-top",
        "ORTHO_RIGHT": "view-side",
    }
    entity_ids_by_view = {}
    for layer, view_id in layer_roles.items():
        document.layers.add(layer)
        lines = tuple(
            modelspace.add_line(start, end, dxfattribs={"layer": layer})
            for start, end in (
                ((0, 0), (100, 0)), ((100, 0), (100, 50)),
                ((100, 50), (0, 50)), ((0, 50), (0, 0)),
            )
        )
        entity_ids_by_view[view_id] = {
            f"entity-{line.dxf.handle}" for line in lines
        }
    path = tmp_path / "overlapping-layer-views.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {(view.id, view.label) for view in extraction.views} == {
        ("view-front", "FRONT"), ("view-top", "TOP"), ("view-side", "SIDE"),
    }
    assert extraction.warnings == ()
    assert extraction.status == "ready"
    assert {contour.view_id for contour in extraction.contours} == set(layer_roles.values())
    for view in extraction.views:
        assert set(view.entity_ids) == entity_ids_by_view[view.id]
        contours = [item for item in extraction.contours if item.view_id == view.id]
        assert len(contours) == 1
        assert set(contours[0].source_entity_ids) == entity_ids_by_view[view.id]
        rendered = render_view(extraction, view.id)
        assert rendered.png.startswith(b"\x89PNG")
        assert {
            mark.source_id for mark in rendered.marks if mark.source_kind == "entity"
        } == entity_ids_by_view[view.id]


def test_orthographic_layer_names_require_exact_safe_tokens(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    for index, layer in enumerate(("ORTHO_FRONT_DETAIL", "NOT_ORTHO_TOP", "SIDEBOARD")):
        document.layers.add(layer)
        x = index * 20
        modelspace.add_lwpolyline(
            [(x, 0), (x + 10, 0), (x + 10, 10), (x, 10)],
            close=True, dxfattribs={"layer": layer},
        )
    path = tmp_path / "unsafe-layer-names.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {(view.id, view.label) for view in extraction.views} == {
        ("view-unknown", "UNKNOWN")
    }


def test_explicit_layer_role_wins_over_conflicting_text_without_false_view(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("ORTHO_FRONT")
    modelspace = document.modelspace()
    modelspace.add_lwpolyline(
        [(0, 0), (100, 0), (100, 50), (0, 50)], close=True,
        dxfattribs={"layer": "ORTHO_FRONT"},
    )
    modelspace.add_text(
        "TOP", dxfattribs={"layer": "ORTHO_FRONT"}
    ).set_placement((0, -20))
    path = tmp_path / "conflicting-layer-text.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {(view.id, view.label) for view in extraction.views} == {
        ("view-front", "FRONT")
    }
    assert all(item.view_id == "view-front" for item in extraction.contours)
    text = next(item for item in extraction.texts if item.text == "TOP")
    assert extraction.warnings == (
        f"view_role_layer_text_conflict:{text.source_entity_id}:layer=FRONT:text=TOP",
    )
    assert extraction.status == "needs_review"


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


def test_angular_dimension_is_warned_and_never_published_as_millimetres(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    dimension = modelspace.add_angular_dim_2l(
        base=(3, 3), line1=((0, 0), (5, 0)), line2=((0, 0), (3, 3)),
    )
    dimension.render()
    path = tmp_path / "angular.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert extraction.dimensions == ()
    assert any(warning.startswith("unsupported_dimension:") for warning in extraction.warnings)


def test_overridden_dimension_text_preserves_conflict_and_abstains(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    dimension = modelspace.add_linear_dim(base=(0, 50), p1=(0, 0), p2=(600, 0))
    dimension.dimension.dxf.text = "620"
    dimension.render()
    path = tmp_path / "conflict.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert extraction.dimensions[0].value_mm is None
    assert any("dimension_text_conflict" in warning and "620" in warning for warning in extraction.warnings)


def test_dimension_scale_is_visible_and_not_silently_applied(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    dimension = modelspace.add_linear_dim(
        base=(0, 50), p1=(0, 0), p2=(600, 0), override={"dimlfac": 2},
    )
    dimension.render()
    path = tmp_path / "scaled-dimension.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert extraction.dimensions[0].value_mm is None
    assert extraction.dimension_graphics[0].display_text == "1200"
    assert any("dimension_scale_conflict" in warning and "2" in warning for warning in extraction.warnings)


def test_lwpolyline_in_non_xy_ocs_is_not_inferred_as_planar_geometry(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    polyline = modelspace.add_lwpolyline(
        [(0, 0), (600, 0), (600, 300), (0, 300)], close=True,
    )
    polyline.dxf.extrusion = (0, 1, 0)
    modelspace.add_text("FRONT").set_placement((0, -20))
    path = tmp_path / "non-xy-ocs.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert extraction.contours == ()
    assert derive_rectangular_hypotheses(extraction) == ()
    assert any(warning.startswith("unsupported_entity_plane:LWPOLYLINE:") for warning in extraction.warnings)


def test_lines_with_varying_z_do_not_form_a_false_rectangular_contour(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    corners = ((0, 0, 0), (600, 0, 0), (600, 300, 10), (0, 300, 0))
    for start, end in zip(corners, corners[1:] + corners[:1], strict=True):
        modelspace.add_line(start, end)
    modelspace.add_text("FRONT").set_placement((0, -20))
    path = tmp_path / "varying-z-lines.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert extraction.contours == ()
    assert derive_rectangular_hypotheses(extraction) == ()
    assert any(warning.startswith("unsupported_entity_plane:LINE:") for warning in extraction.warnings)


def test_trapezoid_is_not_a_rectangular_hypothesis(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (500, 0), (420, 200), (30, 200)], close=True)
    modelspace.add_text("FRONT").set_placement((0, -20))
    path = tmp_path / "trapezoid.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert len(extraction.contours) == 1
    assert derive_rectangular_hypotheses(extraction) == ()


def test_entity_limit_is_checked_before_entity_analysis(tmp_path):
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    for index in range(5):
        modelspace.add_line((index, 0), (index, 1))
    path = tmp_path / "too-many.dxf"
    document.saveas(path)

    with pytest.raises(ValueError, match="entity limit exceeded"):
        parse_dxf(path, max_entities=4)

    assert MAX_ENTITIES == 100_000


def test_linear_dimension_has_readable_anchors_instead_of_defpoint_zigzag(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    dimension = document.modelspace().add_linear_dim(
        base=(0, 50), p1=(0, 0), p2=(600, 0), angle=0,
    )
    dimension.render()
    path = tmp_path / "anchored-dimension.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)
    entity = next(item for item in parsed.entities if item.kind == "DIMENSION")

    assert entity.extension_starts == ((0.0, 0.0), (600.0, 0.0))
    assert entity.dimension_line == ((0.0, 50.0), (600.0, 50.0))
    assert entity.text_position == (300.0, 50.0)
    assert entity.display_text == "600 mm"


def test_public_dxf_text_remains_plain_data_with_layer_and_position(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("PUBLIC_NOTES")
    document.modelspace().add_text("<img src=x onerror=alert(1)>", dxfattribs={"layer": "PUBLIC_NOTES"}).set_placement((12, 34))
    path = tmp_path / "public-text.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)
    entity = next(item for item in parsed.entities if item.kind == "TEXT")

    assert entity.text == "<img src=x onerror=alert(1)>"
    assert entity.layer == "PUBLIC_NOTES"
    assert entity.points == ((12.0, 34.0),)


def test_extraction_exposes_plain_text_and_segmented_dimension_graphic(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (600, 0), (600, 300), (0, 300)], close=True)
    modelspace.add_text("FRONT").set_placement((0, 350))
    modelspace.add_text("Nota pública").set_placement((100, 200))
    dimension = modelspace.add_linear_dim(base=(0, -50), p1=(0, 0), p2=(600, 0), angle=0)
    dimension.render()
    path = tmp_path / "enriched.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    note = next(item for item in extraction.texts if item.text == "Nota pública")
    assert note.layer == "0"
    assert note.position_source.x == 100
    assert note.position_mm.x == 100
    graphic = extraction.dimension_graphics[0]
    dimension_value = extraction.dimensions[0]
    assert graphic.dimension_id == dimension_value.id
    assert dimension_value.graphic_id == graphic.id
    assert dimension_value.view_id == "view-front"
    assert graphic.dimension_start_mm.model_dump() == {"x": 0.0, "y": -50.0}
    assert graphic.dimension_end_mm.model_dump() == {"x": 600.0, "y": -50.0}
    assert graphic.extension_start_a_mm.model_dump() == {"x": 0.0, "y": 0.0}
    assert graphic.extension_start_b_mm.model_dump() == {"x": 600.0, "y": 0.0}
    assert graphic.display_text == "600 mm"


def test_unknown_units_keep_text_and_dimension_anchors_in_source_coordinates_only(tmp_path):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 0
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True)
    modelspace.add_text("FRONT").set_placement((0, 6))
    dimension = modelspace.add_linear_dim(base=(0, -1), p1=(0, 0), p2=(10, 0), angle=0)
    dimension.render()
    path = tmp_path / "unknown-unit-enriched.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert all(item.position_mm is None for item in extraction.texts)
    graphic = extraction.dimension_graphics[0]
    assert graphic.dimension_start_source.model_dump() == {"x": 0.0, "y": -1.0}
    assert graphic.dimension_start_mm is None
    assert graphic.dimension_end_mm is None
    assert graphic.display_text == "10 source-unit"


def test_demo_dimensions_are_anchored_to_their_geometric_views_not_nearest_label():
    extraction = extract_drawing(Path("data/planos_demo/estanteria_montada.dxf"))

    views_by_value = {dimension.value_mm: dimension.view_id for dimension in extraction.dimensions}
    assert views_by_value[900.0] == "view-front"
    assert views_by_value[1200.0] == "view-front"
    assert views_by_value[300.0] == "view-top"
    assert views_by_value[18.0] == "view-top"
