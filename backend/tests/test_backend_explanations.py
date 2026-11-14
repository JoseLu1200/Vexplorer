from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agente.tools import tool_schemas
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


def _reviewed_run(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = TestClient(create_app(data_dir=tmp_path))
    with FIXTURE.open("rb") as stream:
        document_id = client.post("/api/v1/documents", files={"file": ("drawing.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    created = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = created["run"]["id"]
    scenario_id = created["result"]["scenarios"][0]["id"]
    reviewed = client.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": scenario_id, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "Montaje confirmado"})
    assert reviewed.status_code == 201
    return client, run_id


def test_explanations_are_revision_bound_and_show_sources_formula_and_premises(tmp_path: Path, monkeypatch) -> None:
    client, run_id = _reviewed_run(tmp_path, monkeypatch)

    response = client.get(f"/api/v1/runs/{run_id}/explanations", params={"result_revision": 2})

    assert response.status_code == 200
    bundle = response.json()["data"]
    assert bundle["result_revision"] == 2
    shelf = next(item for item in bundle["pieces"] if item["role"] == "shelf")
    assert shelf["source_entity_ids"]
    assert shelf["source_contour_ids"]
    assert shelf["evidence_ids"]
    assert shelf["formulas"][0]["expression"] == "overall_width_mm - 2 * confirmed_thickness_mm"
    assert shelf["formulas"][0]["result_mm"] == 864
    assert "human_mounting_confirmation" in shelf["premises"]
    assert shelf["unknown_fields"] == []


def test_explanation_unknown_revision_is_not_silently_replaced(tmp_path: Path, monkeypatch) -> None:
    client, run_id = _reviewed_run(tmp_path, monkeypatch)

    response = client.get(f"/api/v1/runs/{run_id}/explanations", params={"result_revision": 99})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "result_not_found"


def test_explanations_include_advisory_deflection_warning_for_long_shelf(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    client = TestClient(create_app(data_dir=tmp_path))
    with FIXTURE.open("rb") as stream:
        document_id = client.post(
            "/api/v1/documents",
            files={"file": ("drawing.dxf", stream, "application/dxf")},
        ).json()["data"]["document_id"]
    created = client.post(
        "/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}
    ).json()["data"]
    run_id = created["run"]["id"]
    shelf = next(
        component
        for component in created["result"]["scenarios"][0]["components"]
        if component["role"] == "shelf"
    )
    reviewed = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Técnica",
            "decisions": [
                {
                    "proposal_id": shelf["id"],
                    "action": "confirm",
                    "role": "shelf",
                    "quantity": 1,
                    "length_mm": 1200,
                    "width_mm": 300,
                    "thickness_mm": 16,
                    "material": "tablero",
                    "finish": "melamina",
                    "notes": "Balda larga confirmada",
                }
            ],
        },
    )
    assert reviewed.status_code == 201

    response = client.get(
        f"/api/v1/runs/{run_id}/explanations", params={"result_revision": 2}
    )

    assert response.status_code == 200
    warnings = response.json()["data"]["warnings"]
    assert any(item.startswith("pandeo_luz_excesiva:") for item in warnings)
    assert any("catálogo no confirmado" in item for item in warnings)


def test_initial_explanations_describe_hypotheses_without_human_confirmation(tmp_path: Path, monkeypatch) -> None:
    client, run_id = _reviewed_run(tmp_path, monkeypatch)

    bundle = client.get(f"/api/v1/runs/{run_id}/explanations", params={"result_revision": 1}).json()["data"]

    assert len(bundle["pieces"]) >= 8
    assert all("human_mounting_confirmation" not in item["premises"] for item in bundle["pieces"])
    assert any(item["field_states"]["thickness_mm"] == "unknown" for item in bundle["pieces"])
    assert any(item["measurements"]["width_mm"] == 300 for item in bundle["pieces"])


def test_explain_piece_tool_is_public_and_strict() -> None:
    schema = next(item for item in tool_schemas() if item["name"] == "explicar_pieza")
    assert schema["strict"] is True
    assert schema["parameters"]["additionalProperties"] is False
