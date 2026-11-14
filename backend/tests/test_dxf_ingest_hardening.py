from __future__ import annotations

import ezdxf

from backend.app.ingesta.dxf_reader import parse_dxf
from backend.app.geometria.extraction import extract_drawing


def _new_mm_doc():
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    return document


def test_2d_polyline_is_parsed_cleanly(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    msp.add_polyline2d([(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)], close=True)
    path = tmp_path / "poly2d.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert len(parsed.entities) == 1
    entity = parsed.entities[0]
    assert entity.kind == "POLYLINE"
    assert entity.closed is True
    assert entity.points == ((0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0))
    assert parsed.warnings == ()


def test_2d_polylines_feed_mounted_view_inference_contours_and_observations(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    msp.add_polyline2d([(0, 0), (100, 0), (100, 80), (0, 80)], close=True)
    msp.add_polyline2d([(0, 120), (100, 120), (100, 160), (0, 160)], close=True)
    msp.add_polyline2d([(140, 0), (180, 0), (180, 80), (140, 80)], close=True)
    path = tmp_path / "poly2d-orthographic.dxf"
    document.saveas(path)

    extraction = extract_drawing(path, input_kind="mounted_orthographic_views")

    assert {view.label for view in extraction.views} == {"FRONT", "TOP", "SIDE"}
    assert len(extraction.contours) == 3
    assert all(contour.source_entity_ids for contour in extraction.contours)
    assert all(observation.contour_ids for observation in extraction.observations)
    assert "view_labels_inferred_from_alignment" in extraction.warnings


def test_2d_polyline_with_bulge_is_rejected(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    msp.add_polyline2d([(0.0, 0.0, 0.0, 0.0, 0.5), (10.0, 0.0, 0.0, 0.0, 0.0)], format="xyseb")
    path = tmp_path / "poly2d_bulge.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert parsed.entities == ()
    assert any(warning.startswith("unsupported_bulge:") for warning in parsed.warnings)


def test_2d_polyline_in_tilted_ocs_is_rejected(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    msp.add_polyline2d(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        dxfattribs={"extrusion": (0.0, 1.0, 0.0)},
    )
    path = tmp_path / "poly2d_tilted.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert parsed.entities == ()
    assert any(warning.startswith("unsupported_entity_plane:POLYLINE:") for warning in parsed.warnings)


def test_3d_polyline_is_rejected_with_warning_and_not_flattened(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    msp.add_polyline3d([(0.0, 0.0, 0.0), (10.0, 0.0, 5.0), (10.0, 10.0, 5.0)])
    path = tmp_path / "poly3d.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert parsed.entities == ()
    assert any(warning.startswith("unsupported_entity_plane:POLYLINE:") for warning in parsed.warnings)


def test_polyface_mesh_is_rejected_with_warning(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    mesh = msp.add_polyface()
    mesh.append_face([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)])
    path = tmp_path / "polyface.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert parsed.entities == ()
    assert any(warning.startswith("unsupported_entity_plane:POLYLINE:") for warning in parsed.warnings)


def test_3dface_and_solid_emit_unsupported_entity_warnings(tmp_path):
    document = _new_mm_doc()
    msp = document.modelspace()
    msp.add_3dface([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 2.0), (0.0, 10.0, 2.0)])
    msp.add_solid([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
    path = tmp_path / "3dface_solid.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert parsed.entities == ()
    assert any(warning.startswith("unsupported_entity:3DFACE:") for warning in parsed.warnings)
    assert any(warning.startswith("unsupported_entity:SOLID:") for warning in parsed.warnings)


def test_tilted_3d_insert_block_emits_warning_and_skips_expansion(tmp_path):
    document = _new_mm_doc()
    block = document.blocks.new(name="PART_BLOCK")
    block.add_line((0.0, 0.0), (20.0, 0.0))

    msp = document.modelspace()
    msp.add_blockref("PART_BLOCK", (0.0, 0.0), dxfattribs={"extrusion": (0.0, 1.0, 0.0)})
    msp.add_blockref("PART_BLOCK", (100.0, 0.0))
    path = tmp_path / "tilted_insert.dxf"
    document.saveas(path)

    parsed = parse_dxf(path)

    assert len(parsed.entities) == 1
    assert parsed.entities[0].kind == "LINE"
    assert parsed.entities[0].points == ((100.0, 0.0), (120.0, 0.0))
    assert any(warning.startswith("unsupported_block_transform:") for warning in parsed.warnings)
