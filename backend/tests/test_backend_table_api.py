from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs
from backend.app.main import create_app


FIXTURE = Path(__file__).resolve().parents[2] / "data" / "planos_demo" / "mesa_demo_001.dxf"


def _client(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _create_baseline(client):
    with FIXTURE.open("rb") as stream:
        document_id = client.post("/api/v1/documents", files={"file": ("mesa.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    response = client.post("/api/v1/runs", json={
        "document_id": document_id,
        "mode": "geometry_only",
        "input_kind": "mounted_orthographic_views",
        "table_profile": "rectangular_table_v1",
        "proposal_mode": "catalog_baseline",
        "table_template_id": "side_supports_v1",
    })
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _accept_all(program):
    return [
        {"target_kind": "program", "target_id": program["id"], "action": "accept", "reason": "Selecciona topología"},
        *({"target_kind": "component", "target_id": item["id"], "action": "accept", "reason": "Acepta componente"} for item in program["components"]),
        *({"target_kind": "premise", "target_id": item["id"], "action": "accept", "reason": "Acepta premisa"} for item in program["premises"]),
    ]


class _OneProgramProvider:
    def __init__(self, arguments):
        self.arguments = arguments
        self.inputs = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.inputs.append(input_items)
        return ProviderResponse(
            id="response-live-table",
            tool_calls=(ToolCall(call_id="propose-live-table", name="proponer_descomposicion", arguments=self.arguments),),
        )


def test_table_baseline_run_review_and_partial_cost_are_revision_bound(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = _create_baseline(client)
    run_id = created["run"]["id"]
    initial = created["result"]
    assert initial["input_semantics"] == "mounted_orthographic_views"
    assert len(initial["table_programs"]) == 1
    assert initial["table_programs"][0]["table_template_id"] == "side_supports_v1"
    assert initial["evaluated_table_program"]["state"] == "hypothesis"

    snapshot = client.get(f"/api/v1/runs/{run_id}/table", params={"result_revision": 1})
    assert snapshot.status_code == 200
    program = snapshot.json()["data"]["table_programs"][0]
    reviewed = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 1,
        "reviewer_name": "Técnica local",
        "table_program_id": program["id"],
        "table_decisions": _accept_all(program),
        "notes": "Acepta montaje y premisas",
    })
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()["data"]["state"] == "completed"
    assert reviewed.json()["data"]["evaluated_table_program"]["state"] == "completed"

    scene = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
    assert scene.status_code == 200
    assert scene.json()["data"]["state"] == "ready"
    assert len(scene.json()["data"]["objects"]) == 3
    explanations = client.get(f"/api/v1/runs/{run_id}/explanations", params={"result_revision": 2})
    assert explanations.status_code == 200
    assert {item["role"] for item in explanations.json()["data"]["pieces"]} == {"tabletop", "side_support"}
    assert all(item["formulas"] and item["premises"] for item in explanations.json()["data"]["pieces"])

    drawings = client.post(f"/api/v1/runs/{run_id}/table-drawings", json={"result_revision": 2})
    assert drawings.status_code == 201, drawings.text
    manifest = drawings.json()["data"]
    assert {item["kind"] for item in manifest["sheets"]} >= {"general", "component", "cut_sheet"}
    first_format = manifest["sheets"][0]["formats"][0]
    artifact = client.get(first_format["url"])
    assert artifact.status_code == 200
    assert artifact.headers["content-type"].split(";")[0] == first_format["media_type"]
    persisted_manifest = client.get(f"/api/v1/runs/{run_id}/table-drawings", params={"result_revision": 2})
    assert persisted_manifest.status_code == 200 and persisted_manifest.json()["data"] == manifest

    catalog = client.get("/api/v1/table-cost-catalog")
    assert catalog.status_code == 200 and catalog.json()["data"]["synthetic"] is True
    cost = client.post(f"/api/v1/runs/{run_id}/table-costs", json={"result_revision": 2, "scope": {"material_tariff_id": None, "edge_scope": "none", "operation_tariff_ids": []}})
    assert cost.status_code == 201, cost.text
    assert cost.json()["data"]["total_state"] == "partial"
    assert cost.json()["data"]["grand_total_eur"] is None
    stored = client.get(f"/api/v1/runs/{run_id}/table-costs", params={"result_revision": 2})
    assert stored.status_code == 200 and stored.json()["data"] == cost.json()["data"]
    exported = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"})
    assert exported.status_code == 200
    bundle = exported.json()
    assert bundle["schema_version"] == "0.5.0"
    assert bundle["result"]["evaluated_table_program"]["program_hash"] == manifest["program_hash"]
    assert bundle["table_drawings"] == manifest
    assert bundle["estimate"]["total_state"] == "partial"
    assert bundle["descriptor"]["descriptor_version"] == "furniture-v3"
    assert bundle["scene"]["state"] == "ready"
    assert bundle["explanations"]["pieces"]
    cutlist = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "table_cutlist"})
    assert cutlist.status_code == 200, cutlist.text
    assert cutlist.headers["content-type"].startswith("text/csv")
    assert cutlist.headers["content-disposition"].endswith(f'{run_id}-r2.csv"')
    rows = cutlist.text.splitlines()
    assert len(rows) == 3
    assert "generic_not_certified" in cutlist.text
    assert "material_state" in rows[0] and ",unknown," in cutlist.text


def test_table_run_rejects_implicit_catalog_choice(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    with FIXTURE.open("rb") as stream:
        document_id = client.post("/api/v1/documents", files={"file": ("mesa.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    response = client.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only", "input_kind": "mounted_orthographic_views", "table_profile": "rectangular_table_v1", "proposal_mode": "catalog_baseline"})
    assert response.status_code == 422


def test_live_model_generated_table_program_can_be_reviewed_to_completion(tmp_path, monkeypatch):
    extraction = extract_drawing(FIXTURE, input_kind="mounted_orthographic_views")
    analysis = analyze_mounted_table(extraction)
    baseline = catalog_table_programs(analysis)[0]
    arguments = {
        "bindings": [item.model_dump(mode="json") for item in baseline.bindings],
        "components": [item.model_dump(mode="json") for item in baseline.components],
        "premises": [item.model_dump(mode="json") for item in baseline.premises],
        "assumptions": list(baseline.assumptions),
        "evidence_ids": list(baseline.evidence_ids),
    }
    monkeypatch.setenv("OPENAI_VISION_ENABLED", "true")
    provider = _OneProgramProvider(arguments)
    client = TestClient(create_app(data_dir=tmp_path, agent_provider=provider))
    with FIXTURE.open("rb") as stream:
        document_id = client.post("/api/v1/documents", files={"file": ("mesa.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    created = client.post("/api/v1/runs", json={
        "document_id": document_id,
        "mode": "live",
        "input_kind": "mounted_orthographic_views",
        "table_profile": "rectangular_table_v1",
        "proposal_mode": "model_generated",
    })
    assert created.status_code == 201, created.text
    payload = created.json()["data"]
    program = payload["result"]["table_programs"][0]
    assert program["proposal_origin"] == "model_generated"
    assert program["table_template_id"] is None
    initial_content = provider.inputs[0][0]["content"]
    assert sum(item["type"] == "input_image" for item in initial_content) == 3
    events = client.get(f'/api/v1/runs/{payload["run"]["id"]}/events')
    assert "renderizar_contexto_visual" in events.text
    assert "artifact_sha256" in events.text and "mark_count" in events.text
    reviewed = client.post(f'/api/v1/runs/{payload["run"]["id"]}/reviews', json={
        "base_result_revision": 1,
        "reviewer_name": "Técnica local",
        "table_program_id": program["id"],
        "table_decisions": _accept_all(program),
        "notes": "Valida expresamente el programa generado.",
    })
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()["data"]["state"] == "completed"
    assert reviewed.json()["data"]["evaluated_table_program"]["state"] == "completed"
