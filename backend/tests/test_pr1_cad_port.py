"""Regresiones del tercer bloque CAD de PR1 adaptadas al contrato vigente."""
from __future__ import annotations

import random
from pathlib import Path

import ezdxf
import pytest

from backend.app.geometria import extract_drawing
from backend.app.geometria.extraction import _line_components
from backend.app.ingesta.dxf_reader import ParsedEntity, parse_dxf
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.validador.plausibilidad import evaluate_plausibility


ROOT = Path(__file__).resolve().parents[2]
SHELF_FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _save(document, tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    document.saveas(path)
    return path


def _reference_components(lines: list[ParsedEntity], tolerance: float = 1e-6) -> list[set[str]]:
    def key(point: tuple[float, float]) -> tuple[int, int]:
        return round(point[0] / tolerance), round(point[1] / tolerance)

    remaining = set(range(len(lines)))
    result = []
    while remaining:
        seed = remaining.pop()
        indexes = {seed}
        endpoints = {key(point) for point in lines[seed].points}
        changed = True
        while changed:
            changed = False
            for index in tuple(remaining):
                if endpoints & {key(point) for point in lines[index].points}:
                    remaining.remove(index)
                    indexes.add(index)
                    endpoints.update(key(point) for point in lines[index].points)
                    changed = True
        result.append({lines[index].id for index in indexes})
    return result


def test_union_find_matches_reference_and_keeps_input_order() -> None:
    generator = random.Random(7)
    for trial in range(30):
        grid = [(generator.randint(0, 6), generator.randint(0, 6)) for _ in range(40)]
        lines = [
            ParsedEntity(
                f"line-{trial}-{index}",
                "LINE",
                "0",
                (grid[generator.randrange(40)], grid[generator.randrange(40)]),
            )
            for index in range(generator.randint(1, 60))
        ]

        actual = _line_components(lines)

        assert sorted(map(sorted, ({line.id for line in group} for group in actual))) == sorted(
            map(sorted, _reference_components(lines))
        )
        assert [group[0] for group in actual] == sorted(
            (group[0] for group in actual), key=lines.index
        )
        assert all(group == sorted(group, key=lines.index) for group in actual)


def test_exact_circle_is_assigned_by_its_region_not_nearest_label(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True)
    modelspace.add_text("FRONT", dxfattribs={"insert": (0, 120)})
    modelspace.add_lwpolyline([(200, 0), (300, 0), (300, 100), (200, 100)], close=True)
    modelspace.add_text("SIDE", dxfattribs={"insert": (200, 120)})
    circle = modelspace.add_circle((90, 50), 30)

    extraction = extract_drawing(_save(document, tmp_path, "circle-region.dxf"))

    circle_id = f"entity-{circle.dxf.handle}"
    assert circle_id in next(view.entity_ids for view in extraction.views if view.label == "FRONT")
    assert circle_id not in next(view.entity_ids for view in extraction.views if view.label == "SIDE")


def test_hidden_line_is_neutral_evidence_only(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.linetypes.add("HIDDEN_LOCAL", pattern=[0.2, 0.1, -0.1])
    layer = document.layers.add("OCULTAS")
    layer.dxf.linetype = "HIDDEN_LOCAL"
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (600, 0), (600, 900), (0, 900)], close=True)
    hidden = modelspace.add_line((18, 450), (582, 450), dxfattribs={"layer": "OCULTAS"})
    modelspace.add_line((18, 300), (300, 300), dxfattribs={"layer": "OCULTAS"})

    extraction = extract_drawing(_save(document, tmp_path, "hidden-neutral.dxf"))

    evidence = [item for item in extraction.evidence if item.id.startswith("evidence-hidden-")]
    assert len(evidence) == 1
    assert evidence[0].source_entity_ids == (f"entity-{hidden.dxf.handle}",)
    assert "not established" in evidence[0].description
    assert not any(word in evidence[0].description.lower() for word in ("shelf", "divider", "back"))


def test_hole_rows_are_context_for_scenario_without_forcing_a_piece_role(tmp_path: Path) -> None:
    document = ezdxf.readfile(SHELF_FIXTURE)
    side = next(view for view in extract_drawing(SHELF_FIXTURE).views if view.label == "SIDE")
    assert side.bounds_source is not None
    for index in range(5):
        document.modelspace().add_circle(
            (side.bounds_source.min_x + 37, side.bounds_source.min_y + 100 + 32 * index), 2.5
        )

    extraction = extract_drawing(_save(document, tmp_path, "side-hole-row.dxf"))
    row = next(item for item in extraction.evidence if item.id.startswith("evidence-holes-side-"))
    scenarios = derive_decomposition_scenarios(extraction)

    assert scenarios
    assert all(row.id in component.evidence_ids for scenario in scenarios for component in scenario.components)
    assert all(
        "taladro" not in assumption.lower()
        for scenario in scenarios
        for component in scenario.components
        for assumption in component.assumptions
    )


def test_paperspace_title_block_is_informative_but_dimension_requires_review(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.modelspace().add_line((0, 0), (10, 0))
    layout = document.layout("Layout1")
    layout.add_text("CAJETIN")
    layout.add_lwpolyline([(0, 0), (420, 0), (420, 297), (0, 297)], close=True)
    title_path = _save(document, tmp_path, "paper-title.dxf")

    title_only = extract_drawing(title_path)

    assert "paperspace_annotations:Layout1:2" in title_only.warnings
    assert title_only.status == "ready"

    layout.add_linear_dim(base=(0, 20), p1=(0, 0), p2=(100, 0)).render()
    with_dimension = extract_drawing(_save(document, tmp_path, "paper-dimension.dxf"))
    assert "paperspace_dimensions:Layout1:1" in with_dimension.warnings
    assert with_dimension.status == "needs_review"


def test_nested_paperspace_content_consumes_the_shared_entity_budget(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.modelspace().add_line((0, 0), (1, 0))
    block = document.blocks.new("TITLE")
    for index in range(5):
        block.add_line((0, index), (10, index))
    document.layout("Layout1").add_blockref("TITLE", (0, 0))
    path = _save(document, tmp_path, "paper-budget.dxf")

    with pytest.raises(ValueError, match="entity limit exceeded after block expansion"):
        parse_dxf(path, max_entities=5)


def _dimension_drawing(tmp_path: Path, *, unrelated_mask: bool) -> Path:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_text("FRONT").set_placement((300, -80))
    modelspace.add_lwpolyline([(0, 0), (650, 0), (650, 900), (0, 900)], close=True)
    if unrelated_mask:
        modelspace.add_line((600, 300), (610, 300))
    modelspace.add_linear_dim(base=(0, -40), p1=(0, 0), p2=(600, 0)).render()
    modelspace.add_linear_dim(base=(-40, 0), p1=(0, 0), p2=(0, 900), angle=90).render()
    return _save(document, tmp_path, "dimensions.dxf")


def test_dimension_attachment_uses_actual_geometry_not_unrelated_projected_vertex(tmp_path: Path) -> None:
    extraction = extract_drawing(_dimension_drawing(tmp_path, unrelated_mask=True))

    findings = [
        item for item in evaluate_plausibility(extraction)
        if item["check"] == "dimension_attached_to_geometry"
    ]

    assert sorted(item["status"] for item in findings) == ["fail", "pass"]
    assert "50" in next(item["message"] for item in findings if item["status"] == "fail")
    assert extraction.status == "ready"


def test_dimension_endpoint_on_circle_is_real_geometry(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_text("FRONT").set_placement((0, 80))
    modelspace.add_circle((50, 50), 25)
    modelspace.add_linear_dim(base=(0, 10), p1=(25, 50), p2=(75, 50)).render()
    extraction = extract_drawing(_save(document, tmp_path, "circle-dimension.dxf"))

    findings = [
        item for item in evaluate_plausibility(extraction)
        if item["check"] == "dimension_attached_to_geometry"
    ]

    assert [item["status"] for item in findings] == ["pass"]
