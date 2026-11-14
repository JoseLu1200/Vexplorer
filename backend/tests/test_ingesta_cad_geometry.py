from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from backend.app.geometria.extraction import extract_drawing
from backend.app.ingesta.dxf_reader import parse_dxf


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
