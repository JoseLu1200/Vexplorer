from __future__ import annotations

from pathlib import Path

import ezdxf

from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"
VIEW_WORDS = {"FRONT", "TOP", "RIGHT", "SIDE"}


def _without_view_labels(tmp_path: Path, name: str = "unlabeled.dxf") -> Path:
    document = ezdxf.readfile(FIXTURE)
    modelspace = document.modelspace()
    for entity in list(modelspace):
        if entity.dxftype() == "TEXT" and entity.dxf.text.strip().upper() in VIEW_WORDS:
            modelspace.delete_entity(entity)
    path = tmp_path / name
    document.saveas(path)
    return path


def _view_by_contour(extraction) -> dict[str, str]:
    labels = {view.id: view.label for view in extraction.views}
    return {contour.id: labels[contour.view_id] for contour in extraction.contours}


def test_unlabeled_views_are_inferred_with_same_contours_and_scenarios(tmp_path: Path) -> None:
    original = extract_drawing(FIXTURE)
    inferred = extract_drawing(_without_view_labels(tmp_path))

    assert _view_by_contour(inferred) == _view_by_contour(original)
    assert {view.label for view in inferred.views} == {"FRONT", "TOP", "SIDE"}
    scenarios = lambda extraction: [(item.id, [(c.role, c.quantity, c.length_mm, c.width_mm) for c in item.components]) for item in derive_decomposition_scenarios(extraction)]
    assert scenarios(inferred) == scenarios(original) != []


def test_inference_is_flagged_as_hypothesis_not_ready(tmp_path: Path) -> None:
    original = extract_drawing(FIXTURE)
    inferred = extract_drawing(_without_view_labels(tmp_path))

    assert "view_labels_inferred_from_alignment" in inferred.warnings
    assert inferred.status == "needs_review"
    assert "view_labels_inferred_from_alignment" not in original.warnings
    association = [item for item in inferred.evidence if item.kind == "view_association"]
    assert len(association) == 3 and all(item.source_entity_ids for item in association)


def test_labeled_drawing_never_uses_inference() -> None:
    extraction = extract_drawing(FIXTURE)

    assert "view_labels_inferred_from_alignment" not in extraction.warnings
    assert not [item for item in extraction.evidence if item.kind == "view_association"]


def test_two_outlines_stay_unknown_and_unsupported(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (900, 0), (900, 1200), (0, 1200)], close=True)
    modelspace.add_lwpolyline([(0, -500), (900, -500), (900, -200), (0, -200)], close=True)
    path = tmp_path / "two.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {view.label for view in extraction.views} == {"UNKNOWN"}
    assert "view_labels_inferred_from_alignment" not in extraction.warnings
    assert derive_decomposition_scenarios(extraction) == ()


def test_row_layout_without_shared_extents_is_ambiguous_and_unknown(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    for index in range(3):
        x = index * 1000.0
        modelspace.add_lwpolyline([(x, 0), (x + 900, 0), (x + 900, 1200), (x, 1200)], close=True)
    path = tmp_path / "row.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {view.label for view in extraction.views} == {"UNKNOWN"}
    assert derive_decomposition_scenarios(extraction) == ()


def test_line_only_outlines_are_inferred_and_inner_rectangles_are_not_views(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()

    def box(x0: float, y0: float, x1: float, y1: float) -> None:
        for start, end in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            modelspace.add_line(start, end)

    box(0, 0, 900, 1200)
    box(100, 100, 400, 300)  # inner rectangle inside FRONT: must not count as a fourth view
    box(0, -500, 900, -200)
    box(1200, 0, 1500, 1200)
    path = tmp_path / "lines.dxf"
    document.saveas(path)

    extraction = extract_drawing(path)

    assert {view.label for view in extraction.views} == {"FRONT", "TOP", "SIDE"}
    assert "view_labels_inferred_from_alignment" in extraction.warnings
