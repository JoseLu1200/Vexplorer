from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import ezdxf
import pytest

from backend.app.geometria.extraction import extract_drawing
from backend.app.ingesta.dxf_reader import parse_dxf
import backend.app.ingesta.dxf_reader as dxf_reader


def _save(document, tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    document.saveas(target)
    return target


def test_exact_circles_and_arcs_have_typed_geometry_not_sampled_contours(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_circle((10.0, 20.0), 5.0)
    modelspace.add_arc((40.0, 50.0), 8.0, 15.0, 125.0)

    extraction = extract_drawing(_save(document, tmp_path, "curves.dxf"))

    circle = next(item for item in extraction.entities if item.kind == "CIRCLE")
    arc = next(item for item in extraction.entities if item.kind == "ARC")
    assert circle.circular.kind == "circle"
    assert circle.circular.center_source.model_dump() == {"x": 10.0, "y": 20.0}
    assert circle.circular.radius_source == circle.circular.radius_mm == 5.0
    assert circle.circular.start_angle_deg is None
    assert arc.circular.kind == "arc"
    assert (arc.circular.start_angle_deg, arc.circular.end_angle_deg) == (15.0, 125.0)
    assert not extraction.contours
    assert not any(warning.startswith("approximated_") for warning in extraction.warnings)


def test_linetype_resolves_direct_and_bylayer_values(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.linetypes.add("TEST_DASH", pattern=[0.2, 0.1, -0.1])
    layer = document.layers.add("DASH_LAYER")
    layer.dxf.linetype = "TEST_DASH"
    modelspace = document.modelspace()
    modelspace.add_line((0.0, 0.0), (10.0, 0.0), dxfattribs={"linetype": "TEST_DASH"})
    modelspace.add_line((0.0, 10.0), (10.0, 10.0), dxfattribs={"layer": "DASH_LAYER"})

    extraction = extract_drawing(_save(document, tmp_path, "linetypes.dxf"))

    assert [item.linetype for item in extraction.entities] == ["TEST_DASH", "TEST_DASH"]


def test_nonzero_or_varying_z_is_not_silently_projected_to_xy(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_line((0.0, 0.0, 0.0), (10.0, 0.0, 5.0))
    modelspace.add_line((0.0, 5.0, 5.0), (10.0, 5.0, 5.0))

    extraction = extract_drawing(_save(document, tmp_path, "non-planar.dxf"))

    assert not extraction.entities
    assert len([warning for warning in extraction.warnings if warning.startswith("unsupported_entity_plane:LINE")]) == 2


def test_nonzero_z_linear_dimension_is_rejected_instead_of_projected_to_xy(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    dimension = document.modelspace().add_linear_dim(
        base=(0.0, 20.0, 10.0),
        p1=(0.0, 0.0, 10.0),
        p2=(100.0, 0.0, 10.0),
    )
    dimension.render()

    extraction = extract_drawing(_save(document, tmp_path, "dimension-z10.dxf"))

    assert not extraction.dimensions
    assert not any(item.kind == "DIMENSION" for item in extraction.entities)
    assert any(
        warning.startswith("unsupported_entity_plane:DIMENSION:")
        for warning in extraction.warnings
    )


def test_nested_block_transform_is_expanded_in_wcs(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    leaf = document.blocks.new("LEAF")
    leaf.add_line((0.0, 0.0), (10.0, 0.0))
    middle = document.blocks.new("MIDDLE")
    middle.add_blockref("LEAF", (5.0, 0.0), dxfattribs={"rotation": 90.0})
    document.modelspace().add_blockref(
        "MIDDLE", (100.0, 50.0),
        dxfattribs={"rotation": 90.0, "xscale": 2.0, "yscale": 2.0},
    )

    drawing = parse_dxf(_save(document, tmp_path, "nested.dxf"))

    assert len(drawing.entities) == 1
    assert drawing.entities[0].kind == "LINE"
    assert drawing.entities[0].points[0] == pytest.approx((100.0, 60.0))
    assert drawing.entities[0].points[1] == pytest.approx((80.0, 60.0))


def test_large_minsert_stops_at_budget_without_materializing_grid(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    block = document.blocks.new("CELL")
    block.add_line((0.0, 0.0), (1.0, 0.0))
    document.modelspace().add_blockref(
        "CELL", (0.0, 0.0),
        dxfattribs={"row_count": 1000, "column_count": 1000, "row_spacing": 2.0, "column_spacing": 2.0},
    )
    path = _save(document, tmp_path, "grid.dxf")

    with pytest.raises(ValueError, match="entity limit exceeded after block expansion"):
        parse_dxf(path, max_entities=50)


def test_exact_regular_circle_row_is_grouped_as_neutral_geometry_evidence(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (200, 0), (200, 100), (0, 100)], close=True)
    modelspace.add_text("FRONT", dxfattribs={"insert": (0, 120)})
    circles = [modelspace.add_circle((20 + 32 * index, 40), 2.5) for index in range(3)]

    extraction = extract_drawing(
        _save(document, tmp_path, "hole-row.dxf"), input_kind="mounted_orthographic_views",
    )

    rows = [item for item in extraction.evidence if item.id.startswith("evidence-holes-")]
    assert len(rows) == 1
    assert rows[0].kind == "geometry"
    assert set(rows[0].source_entity_ids) == {f"entity-{item.dxf.handle}" for item in circles}
    assert "system" not in rows[0].description.lower()


def test_recovered_document_is_explicitly_gated_for_review(tmp_path: Path, monkeypatch) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_line((0, 0), (10, 0))
    path = _save(document, tmp_path, "recoverable.dxf")
    monkeypatch.setattr(
        dxf_reader.ezdxf, "readfile",
        lambda _: (_ for _ in ()).throw(ezdxf.DXFStructureError("damaged")),
    )
    monkeypatch.setattr(
        dxf_reader.recover, "readfile",
        lambda _: (document, SimpleNamespace(fixes=(1,), errors=())),
    )

    extraction = extract_drawing(path)

    assert extraction.status == "needs_review"
    assert "recovered_dxf:fixes=1:errors=0" in extraction.warnings


def test_ordinate_dimension_preserves_observed_offset_without_fake_graphic(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    dimension = document.modelspace().add_ordinate_dim(
        feature_location=(125.0, 50.0), offset=(20.0, 20.0),
        origin=(25.0, 10.0), dtype=1,
    )
    dimension.render()

    extraction = extract_drawing(_save(document, tmp_path, "ordinate.dxf"))

    assert len(extraction.dimensions) == 1
    assert extraction.dimensions[0].value_mm == 100.0
    assert extraction.dimensions[0].graphic_id is None
    assert not extraction.dimension_graphics


def test_ellipse_is_bounded_visual_approximation_never_exact_contour(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_ellipse((50, 50), major_axis=(20, 0), ratio=0.5)

    extraction = extract_drawing(_save(document, tmp_path, "ellipse.dxf"))

    ellipse = next(item for item in extraction.entities if item.kind == "ELLIPSE")
    assert 4 < len(ellipse.source_points) <= 4096
    assert "approximated_curve" in "|".join(extraction.warnings)
    assert extraction.status == "needs_review"
    assert not extraction.contours


def test_tilted_circle_and_arc_ocs_are_rejected_before_xy_measurement(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    extrusion = (0.0, 1.0, 1.0)
    modelspace.add_circle((0, 0, 0), 10, dxfattribs={"extrusion": extrusion})
    modelspace.add_arc((30, 0, 0), 10, 0, 180, dxfattribs={"extrusion": extrusion})

    extraction = extract_drawing(_save(document, tmp_path, "tilted-circular.dxf"))

    assert not extraction.entities
    assert sum(warning.startswith("unsupported_entity_plane:") for warning in extraction.warnings) == 2


def test_negative_z_arc_is_rejected_because_contract_angles_are_not_ocs_typed(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_circle((0, 0), 10, dxfattribs={"extrusion": (0, 0, -1)})
    modelspace.add_arc((30, 0), 10, 15, 125, dxfattribs={"extrusion": (0, 0, -1)})

    extraction = extract_drawing(_save(document, tmp_path, "negative-z.dxf"))

    assert [item.kind for item in extraction.entities] == ["CIRCLE"]
    assert any(warning.startswith("unsupported_arc_orientation:") for warning in extraction.warnings)


def test_multiple_curves_share_one_global_point_budget(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    for offset in range(4):
        modelspace.add_ellipse((offset * 100, 0), major_axis=(20, 0), ratio=0.5)
    path = _save(document, tmp_path, "many-curves.dxf")

    with pytest.raises(ValueError, match="drawing point limit exceeded"):
        parse_dxf(path, max_points=150)


def test_global_point_budget_also_counts_exact_line_points(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    modelspace.add_line((0, 0), (1, 0))
    modelspace.add_line((0, 1), (1, 1))

    with pytest.raises(ValueError, match="drawing point limit exceeded"):
        parse_dxf(_save(document, tmp_path, "line-budget.dxf"), max_points=3)
