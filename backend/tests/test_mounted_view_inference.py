from __future__ import annotations

from pathlib import Path

import ezdxf

from backend.app.geometria.extraction import extract_drawing


FIXTURE = Path("data/planos_demo/mesa_demo_001.dxf")


def _without_orientation_labels(tmp_path: Path) -> Path:
    document = ezdxf.readfile(FIXTURE)
    modelspace = document.modelspace()
    for entity in tuple(modelspace):
        if entity.dxftype() == "TEXT" and entity.dxf.text.strip().upper() in {"FRONT", "TOP", "SIDE"}:
            modelspace.delete_entity(entity)
    target = tmp_path / "unlabelled-table.dxf"
    document.saveas(target)
    return target


def test_unlabelled_orthographic_triple_is_inferred_only_for_mounted_input(tmp_path: Path) -> None:
    path = _without_orientation_labels(tmp_path)

    mounted = extract_drawing(path, input_kind="mounted_orthographic_views")
    separated = extract_drawing(path, input_kind="separated_part_views")

    assert {view.label for view in mounted.views} == {"FRONT", "TOP", "SIDE"}
    assert "view_labels_inferred_from_alignment" in mounted.warnings
    assert mounted.status == "needs_review"
    inferred = [item for item in mounted.evidence if item.kind == "view_association"]
    assert len(inferred) == 3
    assert all(item.source_entity_ids for item in inferred)

    assert {view.label for view in separated.views} == {"UNKNOWN"}
    assert "view_labels_inferred_from_alignment" not in separated.warnings


def test_unlabelled_row_of_three_equal_outlines_stays_unknown(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    for offset in (0.0, 200.0, 400.0):
        modelspace.add_lwpolyline(
            [(offset, 0.0), (offset + 100.0, 0.0), (offset + 100.0, 50.0), (offset, 50.0)],
            close=True,
        )
    target = tmp_path / "ambiguous-row.dxf"
    document.saveas(target)

    extraction = extract_drawing(target, input_kind="mounted_orthographic_views")

    assert {view.label for view in extraction.views} == {"UNKNOWN"}
    assert "view_labels_inferred_from_alignment" not in extraction.warnings
