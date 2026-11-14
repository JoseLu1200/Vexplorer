"""Tercer bloque: rendimiento de componentes, taladros en laterales, cotas sobre geometría, líneas ocultas y paquete."""
from __future__ import annotations

import random
import tomllib
from pathlib import Path

import ezdxf

from backend.app.geometria import extract_drawing
from backend.app.geometria.extraction import _line_components
from backend.app.ingesta.dxf_reader import ParsedEntity
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.validador.plausibilidad import check_plausibility

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _reference_components(lines: list[ParsedEntity], tolerance: float = 1e-6) -> list[set[str]]:
    """The previous quadratic implementation, kept as the behavioural reference."""
    def key(point):
        return (round(point[0] / tolerance), round(point[1] / tolerance))

    remaining = set(range(len(lines)))
    components = []
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
        components.append({lines[index].id for index in indexes})
    return components


def test_union_find_components_match_the_reference_on_random_lines() -> None:
    generator = random.Random(7)
    for trial in range(30):
        grid = [(generator.randint(0, 6), generator.randint(0, 6)) for _ in range(40)]
        lines = [ParsedEntity(f"l{trial}-{index}", "LINE", "0", (grid[generator.randrange(40)], grid[generator.randrange(40)])) for index in range(generator.randint(1, 60))]
        fast = _line_components(lines)
        assert sorted(map(sorted, ({line.id for line in component} for component in fast))) == sorted(map(sorted, _reference_components(lines)))
        assert [component[0] for component in fast] == sorted((component[0] for component in fast), key=lines.index)


def _with_side_holes(tmp_path: Path) -> Path:
    document = ezdxf.readfile(FIXTURE)
    side = next(view for view in extract_drawing(FIXTURE).views if view.label == "SIDE").bounds_source
    for index in range(5):
        document.modelspace().add_circle((side.min_x + 37, side.min_y + 100 + 32 * index), 2.5)
    path = tmp_path / "side-holes.dxf"
    document.saveas(path)
    return path


def test_hole_rows_inside_the_side_outline_become_side_panel_evidence(tmp_path: Path) -> None:
    extraction = extract_drawing(_with_side_holes(tmp_path))
    rows = [item for item in extraction.evidence if item.id.startswith("evidence-holes-")]
    assert len(rows) == 1 and rows[0].id.startswith("evidence-holes-side-")  # circles are assigned to the SIDE region

    for scenario in derive_decomposition_scenarios(extraction):
        for proposal in scenario.components:
            if proposal.role == "side_panel":
                assert rows[0].id in proposal.evidence_ids
                assert any("fila(s) de taladros" in item for item in proposal.assumptions)
            else:
                assert rows[0].id not in proposal.evidence_ids
            assert proposal.thickness_mm is None


def _stretched(tmp_path: Path) -> Path:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_text("FRONT").set_placement((300, -80))
    modelspace.add_lwpolyline([(0, 0), (650, 0), (650, 900), (0, 900)], close=True)
    # Non-associative dimension left at the old width of 600 after the outline was stretched to 650.
    modelspace.add_linear_dim(base=(0, -40), p1=(0, 0), p2=(600, 0)).render()
    modelspace.add_linear_dim(base=(-40, 0), p1=(0, 0), p2=(0, 900), angle=90).render()
    path = tmp_path / "stretched.dxf"
    document.saveas(path)
    return path


def test_dimension_not_resting_on_geometry_is_a_finding_only(tmp_path: Path) -> None:
    extraction = extract_drawing(_stretched(tmp_path))

    findings = [item for item in check_plausibility(extraction, ()) if item.check == "dimension_attached_to_geometry"]

    assert sorted(item.status for item in findings) == ["fail", "pass"]
    failed = next(item for item in findings if item.status == "fail")
    assert "50.0 mm" in failed.message and failed.evidence_ids
    assert extraction.status == "ready"  # findings never change the extraction status


def test_every_demo_dimension_rests_on_geometry() -> None:
    for path in sorted((ROOT / "data" / "planos_demo").glob("*.dxf")):
        findings = [item for item in check_plausibility(extract_drawing(path), ()) if item.check == "dimension_attached_to_geometry"]
        assert all(item.status == "pass" for item in findings), path.name


def test_hidden_lines_inside_an_outline_are_neutral_evidence(tmp_path: Path) -> None:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("OCULTAS", linetype="HIDDEN")
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (600, 0), (600, 900), (0, 900)], close=True)
    modelspace.add_line((18, 450), (582, 450), dxfattribs={"layer": "OCULTAS"})
    modelspace.add_line((18, 300), (300, 300), dxfattribs={"layer": "OCULTAS"})  # too short
    modelspace.add_line((18, 600), (582, 600))  # continuous
    path = tmp_path / "hidden.dxf"
    document.saveas(path)

    hidden = [item for item in extract_drawing(path).evidence if item.id.startswith("evidence-hidden-")]

    assert len(hidden) == 1
    assert "HIDDEN" in hidden[0].description and "horizontal" in hidden[0].description and "50% of its height" in hidden[0].description
    assert "not established" in hidden[0].description and "shelf" not in hidden[0].description.lower()


def test_catalog_is_packaged_and_ruff_is_a_dev_extra() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["setuptools"]["package-data"]["backend.app.validador"] == ["catalogo_taller.json"]
    assert any(item.startswith("ruff") for item in project["project"]["optional-dependencies"]["dev"])
