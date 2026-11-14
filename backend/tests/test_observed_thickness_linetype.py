from __future__ import annotations

from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

from backend.app.geometria import extract_drawing
from backend.app.main import create_app
from backend.app.servicios.decomposition import derive_decomposition_scenarios

DEMO = Path(__file__).resolve().parents[2] / "data" / "planos_demo"


def _side_thickness(path: Path):
    scenarios = derive_decomposition_scenarios(extract_drawing(path))
    sides = [item for scenario in scenarios for item in scenario.components if item.role == "side_panel"]
    return [(item.observed_thickness_mm, item.thickness_mm) for item in sides]


def _edited(tmp_path: Path, delete_handles: set[str]) -> Path:
    document = ezdxf.readfile(DEMO / "estanteria_montada.dxf")
    modelspace = document.modelspace()
    for entity in list(modelspace):
        if entity.dxf.handle in delete_handles:
            modelspace.delete_entity(entity)
    path = tmp_path / "edited.dxf"
    document.saveas(path)
    return path


def test_drawn_side_thickness_is_observed_but_never_confirmed() -> None:
    values = _side_thickness(DEMO / "estanteria_montada.dxf")

    assert values and all(observed == 18.0 and confirmed is None for observed, confirmed in values)


def test_observed_thickness_applies_only_to_side_panels_and_cites_its_lines() -> None:
    extraction = extract_drawing(DEMO / "estanteria_montada.dxf")
    components = [item for scenario in derive_decomposition_scenarios(extraction) for item in scenario.components]

    assert all((item.observed_thickness_mm is not None) == (item.role == "side_panel") for item in components)
    side = next(item for item in components if item.role == "side_panel")
    assert set(side.thickness_source_entity_ids) <= {entity.id for entity in extraction.entities}
    assert len(side.thickness_source_entity_ids) == 4
    assert any("Espesor observado de 18 mm" in text for text in side.assumptions)


def test_variant_without_thickness_evidence_stays_unknown() -> None:
    assert all(observed is None for observed, _ in _side_thickness(DEMO / "estanteria_incompleta.dxf"))


def test_asymmetric_or_unconfirmed_thickness_abstains(tmp_path: Path) -> None:
    # entity-91 / entity-95 are the right-hand inner verticals in FRONT / TOP; handles come from the fixture.
    assert all(observed is None for observed, _ in _side_thickness(_edited(tmp_path, {"91"})))  # only one side drawn in FRONT
    assert all(observed is None for observed, _ in _side_thickness(_edited(tmp_path, {"94", "95"})))  # TOP does not repeat it


def test_linetype_is_read_directly_and_through_the_layer(tmp_path: Path) -> None:
    document = ezdxf.new("R2010", setup=True)
    document.header["$INSUNITS"] = 4
    document.layers.add("OCULTAS", linetype="DASHED")
    modelspace = document.modelspace()
    modelspace.add_line((0, 0), (100, 0), dxfattribs={"linetype": "HIDDEN"})
    modelspace.add_line((0, 10), (100, 10), dxfattribs={"layer": "OCULTAS"})
    modelspace.add_line((0, 20), (100, 20))
    path = tmp_path / "linetypes.dxf"
    document.saveas(path)

    lines = [entity for entity in extract_drawing(path).entities if entity.kind == "LINE"]

    assert [item.linetype for item in lines] == ["HIDDEN", "DASHED", "CONTINUOUS"]


def test_grain_and_edge_banding_survive_review_and_reach_the_cutlist(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    upload = client.post("/api/v1/documents", files={"file": ("estanteria_montada.dxf", (DEMO / "estanteria_montada.dxf").read_bytes())})
    created = client.post("/api/v1/runs", json={"document_id": upload.json()["data"]["document_id"], "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    proposal = next(item for scenario in created["result"]["scenarios"] if scenario["id"] == "scenario-between-sides" for item in scenario["components"] if item["role"] == "side_panel")
    assert proposal["observed_thickness_mm"] == 18.0

    review = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 1, "reviewer_name": "Técnica de prueba",
        "decisions": [{"proposal_id": proposal["id"], "action": "confirm", "role": "side_panel", "quantity": 2, "length_mm": 1200, "width_mm": 300, "thickness_mm": 18, "material": "tablero sintético", "finish": "melamina sintética", "grain": "length", "edge_banding": ["length_1"], "notes": "Confirmado en prueba"}],
    })
    assert review.status_code == 201
    piece = review.json()["data"]["pieces"][0]
    assert piece["grain"] == "length" and piece["edge_banding"] == ["length_1"]

    row = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "cutlist"}).text.splitlines()[1].split(",")
    assert "length" in row and "length_1" in row and "2.4" in row  # 1200 mm * 2 pieces of banded length
