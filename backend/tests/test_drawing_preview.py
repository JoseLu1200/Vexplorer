"""Native CAD display remains separate from decomposition and metric evidence."""
from pathlib import Path
from xml.etree import ElementTree as ET

import ezdxf
import pytest


def test_native_preview_renders_curves_blocks_text_and_dimensions(tmp_path: Path):
    from backend.app.salida.drawing_preview import render_drawing_preview

    doc = ezdxf.new("R2010")
    doc.units = 0
    block = doc.blocks.new("part")
    block.add_circle((0, 0), 20)
    block.add_arc((50, 0), 10, 0, 90)
    space = doc.modelspace()
    space.add_blockref("part", (100, 50))
    space.add_text('<script>alert("CAD")</script>', dxfattribs={"height": 5})
    space.add_linear_dim(base=(0, -20), p1=(0, 0), p2=(100, 0)).render()
    path = tmp_path / "display.dxf"
    doc.saveas(path)
    before = path.read_bytes()
    root = ET.fromstring(render_drawing_preview(path))
    assert root.tag.endswith("svg")
    assert "viewBox" in root.attrib
    assert len([item for item in root.iter() if item.tag.endswith("path")]) >= 4
    assert not {"script", "image", "foreignObject", "a"} & {
        item.tag.rsplit("}", 1)[-1] for item in root.iter()
    }
    assert not any("href" in key or key.startswith("on") for item in root.iter() for key in item.attrib)
    assert path.read_bytes() == before


def test_native_preview_rejects_recursive_blocks_before_rendering(tmp_path: Path):
    from backend.app.salida.drawing_preview import render_drawing_preview

    doc = ezdxf.new()
    block = doc.blocks.new("recursive")
    block.add_blockref("recursive", (0, 0))
    doc.modelspace().add_blockref("recursive", (0, 0))
    path = tmp_path / "cycle.dxf"
    doc.saveas(path)
    with pytest.raises(ValueError, match="preview_complexity_limit"):
        render_drawing_preview(path)


def test_native_preview_rejects_invalid_dxf_without_exposing_path(tmp_path: Path):
    from backend.app.salida.drawing_preview import render_drawing_preview

    path = tmp_path / "private-name.dxf"
    path.write_text("not a DXF", encoding="utf-8")
    with pytest.raises(ValueError, match="^invalid_dxf$"):
        render_drawing_preview(path)
