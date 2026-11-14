from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import ResolvedPiece, Result
from backend.app.main import create_app
from backend.app.salida.service import export_cutlist_csv

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "estanteria_montada.dxf"


def _piece(**overrides) -> ResolvedPiece:
    values = dict(
        id="piece-1", proposal_id="proposal-1", label="Lateral", role="side_panel", quantity=2, length_mm=1200.0, width_mm=300.0,
        thickness_mm=18.0, material="tablero sintético", finish="melamina sintética", source_observation_ids=(), source_contour_ids=(),
        evidence_ids=("evidence-1",), human_confirmation="confirmed", field_states={},
    )
    values.update(overrides)
    return ResolvedPiece(**values)


def _result(*pieces: ResolvedPiece, revision: int = 2) -> Result:
    return Result(run_id="run-1", result_revision=revision, state="completed", scenarios=(), pieces=pieces, created_at="2026-11-14T00:00:00+00:00")


def _rows(payload: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload)))


def test_cutlist_derives_area_only_from_known_values_and_names_unknowns() -> None:
    rows = _rows(export_cutlist_csv(_result(_piece(), _piece(id="piece-2", thickness_mm=None, material=None, length_mm=None))))

    complete, partial = rows
    assert complete["area_m2"] == "0.72"  # 1200 * 300 * 2 / 1e6
    assert complete["unknown_fields"] == "grain|edge_banding"
    assert complete["edge_banding_m"] == ""
    assert partial["area_m2"] == "" and partial["thickness_mm"] == "" and partial["length_mm"] == ""
    assert set(partial["unknown_fields"].split("|")) == {"length_mm", "thickness_mm", "material", "grain", "edge_banding"}
    assert complete["result_revision"] == "2"


def test_cutlist_uses_confirmed_grain_and_edges_and_derives_banded_length() -> None:
    banded, unbanded, partial = _rows(export_cutlist_csv(_result(
        _piece(grain="length", edge_banding=("length_1", "length_2", "width_1")),
        _piece(id="piece-2", grain="none", edge_banding=()),
        _piece(id="piece-3", grain="width", edge_banding=("width_1",), length_mm=None),
    )))

    assert banded["grain"] == "length" and banded["edge_banding"] == "length_1|length_2|width_1"
    assert banded["edge_banding_m"] == "5.4"  # (1200 + 1200 + 300) * 2 / 1000
    assert banded["unknown_fields"] == ""
    assert unbanded["edge_banding"] == "" and unbanded["edge_banding_m"] == "0.0" and unbanded["unknown_fields"] == ""
    assert partial["edge_banding_m"] == "" and partial["unknown_fields"] == "length_mm"


def test_cutlist_refuses_results_without_confirmed_pieces() -> None:
    with pytest.raises(ValueError, match="result_has_no_confirmed_pieces"):
        export_cutlist_csv(_result())


def test_cutlist_protects_spreadsheet_formulas() -> None:
    payload = export_cutlist_csv(_result(_piece(material="=CMD|' /C calc'!A0", finish="@SUM(A1)")))

    assert "'=CMD" in payload and "'@SUM" in payload


def test_cutlist_endpoint_requires_a_reviewed_result(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    upload = client.post("/api/v1/documents", files={"file": ("estanteria_montada.dxf", FIXTURE.read_bytes())})
    run = client.post("/api/v1/runs", json={"document_id": upload.json()["data"]["document_id"], "mode": "geometry_only"}).json()["data"]["run"]

    response = client.get(f"/api/v1/runs/{run['id']}/exports", params={"format": "cutlist"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "result_has_no_confirmed_pieces"


def test_cutlist_endpoint_exports_reviewed_pieces_with_known_and_unknown_fields(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    upload = client.post("/api/v1/documents", files={"file": ("estanteria_montada.dxf", FIXTURE.read_bytes())})
    run = client.post("/api/v1/runs", json={"document_id": upload.json()["data"]["document_id"], "mode": "geometry_only"}).json()["data"]["run"]
    review = client.post(f"/api/v1/runs/{run['id']}/reviews", json={
        "base_result_revision": 1, "reviewer_name": "Técnica de prueba", "scenario_id": "scenario-between-sides",
        "confirmed_thickness_mm": 18, "material": "tablero sintético", "finish": "melamina sintética", "notes": "Montaje confirmado en prueba",
    })
    assert review.status_code == 201

    response = client.get(f"/api/v1/runs/{run['id']}/exports", params={"format": "cutlist"})

    assert response.status_code == 200
    assert "cutlist.csv" in response.headers["content-disposition"]
    rows = _rows(response.text)
    assert rows and all(row["thickness_mm"] == "18.0" or row["thickness_mm"] == "18" for row in rows)
    assert all("grain" in row["unknown_fields"].split("|") for row in rows)
