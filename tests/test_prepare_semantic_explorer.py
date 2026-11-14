import json

import ezdxf
import pytest

from tools.prepare_semantic_explorer import prepare_drawings


def test_new_drawing_uses_neutral_geometry_and_retains_content_identity(tmp_path):
    path = tmp_path / "SECRET-customer-table.dxf"
    doc = ezdxf.new()
    doc.modelspace().add_lwpolyline(
        [(0, 0), (500, 0), (500, 300), (0, 300)], close=True
    )
    doc.modelspace().add_text("SECRET-CUSTOMER")
    doc.saveas(path)
    manifest = prepare_drawings([path], tmp_path / "prepared")
    value = json.loads(manifest.read_text())
    sample = value["samples"][0]
    assert "SECRET" not in sample["text"]
    assert len(sample["features"]) == 27
    assert sample.get("label") is None
    assert sample["id"].startswith("drawing-")
    assert (manifest.parent / sample["image_path"]).is_file()
    with pytest.raises(ValueError, match="exists"):
        prepare_drawings([path], tmp_path / "prepared")


def test_repeated_input_is_deduplicated_by_content(tmp_path):
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (5, 2))
    path = tmp_path / "drawing.dxf"
    doc.saveas(path)
    manifest = prepare_drawings([path, path], tmp_path / "prepared")
    assert len(json.loads(manifest.read_text())["samples"]) == 1
