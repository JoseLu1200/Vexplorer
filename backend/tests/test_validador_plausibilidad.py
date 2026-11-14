"""Plausibilidad contra el catálogo del taller: pistas deterministas, nunca valores rellenados."""
from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.validador.plausibilidad import CATALOG_ENV, WorkshopCatalog, check_plausibility, load_catalog

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"


def _side_panel_with_holes(tmp_path: Path, diameter: float, pitch: float, setback: float) -> Path:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    modelspace.add_lwpolyline([(0, 0), (400, 0), (400, 700), (0, 700)], close=True)
    for index in range(6):
        modelspace.add_circle((setback, 100 + pitch * index), diameter / 2)
    path = tmp_path / "lateral.dxf"
    document.saveas(path)
    return path


def test_default_catalog_ships_only_verified_values() -> None:
    catalog = load_catalog()

    assert catalog.confirmed_by_workshop is False
    assert [(item.pitch_mm, item.hole_diameter_mm, item.setback_mm) for item in catalog.drilling_systems] == [(32.0, 5.0, 37.0)]
    assert catalog.board_thicknesses_mm == () and catalog.edge_banding_thicknesses_mm == ()


def test_system32_row_with_setback_passes_as_a_hint(tmp_path: Path) -> None:
    extraction = extract_drawing(_side_panel_with_holes(tmp_path, 5.0, 32.0, 37.0))

    findings = check_plausibility(extraction, ())

    assert len(findings) == 1
    assert findings[0].status == "pass" and findings[0].check == "hole_row_drilling_system"
    assert "Sistema 32 mm" in findings[0].message and "37.0 mm (coincide" in findings[0].message
    assert findings[0].evidence_ids == ("evidence-holes-unknown-1",)
    assert check_plausibility(extraction, ()) == findings  # deterministic


def test_other_hole_rows_are_unknown_not_failures(tmp_path: Path) -> None:
    extraction = extract_drawing(_side_panel_with_holes(tmp_path, 8.0, 50.0, 37.0))

    findings = check_plausibility(extraction, ())

    assert [item.status for item in findings] == ["unknown"]


def test_observed_thickness_is_unknown_without_catalog_and_checked_with_one(tmp_path: Path, monkeypatch) -> None:
    extraction = extract_drawing(FIXTURE)
    scenarios = derive_decomposition_scenarios(extraction)
    observed = [proposal for scenario in scenarios for proposal in scenario.components if proposal.observed_thickness_mm is not None]
    assert observed, "the demo fixture draws side thickness"

    default = check_plausibility(extraction, scenarios)
    assert {item.status for item in default if item.check == "observed_thickness_in_catalog"} == {"unknown"}

    value = observed[0].observed_thickness_mm
    catalog_path = tmp_path / "catalogo.json"
    catalog_path.write_text(json.dumps({"source": "prueba", "board_thicknesses_mm": [value]}), encoding="utf-8")
    monkeypatch.setenv(CATALOG_ENV, str(catalog_path))
    matching = check_plausibility(extraction, scenarios)
    assert {item.status for item in matching if item.check == "observed_thickness_in_catalog"} == {"pass"}

    other = WorkshopCatalog(source="prueba", board_thicknesses_mm=(value + 5,))
    assert {item.status for item in check_plausibility(extraction, scenarios, other) if item.check == "observed_thickness_in_catalog"} == {"fail"}
    assert all(proposal.thickness_mm is None for scenario in scenarios for proposal in scenario.components)
