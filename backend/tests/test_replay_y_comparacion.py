"""Replay grabado (plan B de demo) y herramienta comparar_candidatas, sin llamar a la API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.agente.comparacion import compare_candidates
from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits, run_agent
from backend.app.agente.tools import tool_schemas
from backend.app.geometria import extract_drawing
from backend.app.servicios.decomposition import derive_decomposition_scenarios

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"


class ScriptedProvider:
    """Stands in for OpenAIResponsesProvider: inspects one evidence and delivers the cap-sides scenario."""

    calls = 0

    def __init__(self, settings) -> None:
        self.step = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        ScriptedProvider.calls += 1
        self.step += 1
        if self.step == 1:
            context = json.loads(input_items[0]["content"])
            return ProviderResponse(id="r1", tool_calls=(ToolCall(call_id="c1", name="inspeccionar_evidencia", arguments_json=json.dumps({"evidence_ids": context["evidence_ids"][:1]})),))
        return ProviderResponse(id="r2", tool_calls=(ToolCall(call_id="c2", name="entregar_despiece", arguments_json=json.dumps({"scenario_id": "scenario-cap-sides"})),))


def _client(tmp_path: Path, monkeypatch, live: bool) -> TestClient:
    monkeypatch.delenv("VEXPLORER_AGENT_RECORDINGS_DIR", raising=False)
    monkeypatch.delenv("VEXPLORER_AGENT_VISION", raising=False)
    if live:
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setenv("OPENAI_MODEL", "test-model")
        monkeypatch.setattr(main_module, "OpenAIResponsesProvider", ScriptedProvider)
    else:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(main_module.create_app(data_dir=tmp_path))


def _upload(client: TestClient) -> str:
    with FIXTURE.open("rb") as stream:
        return client.post("/api/v1/documents", files={"file": ("estanteria.dxf", stream, "application/dxf")}).json()["data"]["document_id"]


def test_a_real_live_run_is_recorded_and_replayed_offline_with_provenance(tmp_path: Path, monkeypatch) -> None:
    live_client = _client(tmp_path, monkeypatch, live=True)
    document_id = _upload(live_client)
    live = live_client.post("/api/v1/runs", json={"document_id": document_id, "mode": "live"})
    assert live.status_code == 201
    recordings = list((tmp_path / "recordings").glob("*.json"))
    assert len(recordings) == 1 and json.loads(recordings[0].read_text(encoding="utf-8"))["model"] == "test-model"

    # Later, without API key: the recording is the plan B.
    offline = _client(tmp_path, monkeypatch, live=False)
    config = offline.get("/api/v1/config").json()["data"]
    assert config["recorded_replay_available"] is True and "recorded_replay" in config["modes"]
    calls_before = ScriptedProvider.calls
    replay = offline.post("/api/v1/runs", json={"document_id": document_id, "mode": "recorded_replay"})

    assert replay.status_code == 201, replay.text
    assert ScriptedProvider.calls == calls_before  # no provider involved
    run = replay.json()["data"]["run"]
    assert run["mode"] == "recorded_replay"
    assert run["agent_selected_scenario_id"] == live.json()["data"]["run"]["agent_selected_scenario_id"] == "scenario-cap-sides"
    events = offline.get(f"/api/v1/runs/{run['id']}/events").text
    assert '"provenance": "recorded_replay"' in events and '"recorded_model": "test-model"' in events


def test_replay_is_refused_when_the_recording_no_longer_matches(tmp_path: Path, monkeypatch) -> None:
    live_client = _client(tmp_path, monkeypatch, live=True)
    document_id = _upload(live_client)
    assert live_client.post("/api/v1/runs", json={"document_id": document_id, "mode": "live"}).status_code == 201

    catalog = tmp_path / "catalogo.json"
    catalog.write_text(json.dumps({"source": "otro taller", "board_thicknesses_mm": [19]}), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_WORKSHOP_CATALOG", str(catalog))
    offline = _client(tmp_path, monkeypatch, live=False)
    replay = offline.post("/api/v1/runs", json={"document_id": document_id, "mode": "recorded_replay"})

    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "recorded_replay_unavailable"


def test_compare_candidates_relations_follow_harness_vocabulary() -> None:
    extraction = extract_drawing(FIXTURE)
    between, capped = derive_decomposition_scenarios(extraction)
    side_between = next(item for item in between.components if item.role == "side_panel")
    side_capped = next(item for item in capped.components if item.role == "side_panel")
    top_between = next(item for item in between.components if item.role == "top_panel")

    across = compare_candidates((between, side_between), (capped, side_capped))
    relations = {item["kind"]: item["status"] for item in across["relations"]}
    assert relations == {"same_physical_part": "unknown", "same_dimensions": "unknown", "mirrored_variant": "not_applicable", "alternative_hypothesis": "pass"}
    assert {"length_mm", "thickness_mm"} <= set(across["unresolved_fields"])  # capped sides derive length from an unconfirmed thickness

    within = {item["kind"]: item["status"] for item in compare_candidates((between, side_between), (between, top_between))["relations"]}
    assert within["alternative_hypothesis"] == "fail" and within["same_physical_part"] == "fail"


def test_compare_tool_is_strict_and_rejects_bad_references() -> None:
    tool = next(item for item in tool_schemas() if item["name"] == "comparar_candidatas")
    schema = tool["parameters"]
    assert schema["additionalProperties"] is False and schema["required"] == ["candidate_ids"]
    assert schema["properties"]["candidate_ids"]["minItems"] == schema["properties"]["candidate_ids"]["maxItems"] == 2
    assert "path" not in str(tool).lower() and "file" not in str(tool).lower()

    extraction = extract_drawing(FIXTURE)
    scenarios = derive_decomposition_scenarios(extraction)
    proposal = scenarios[0].components[0].id
    outputs = []

    class Fake:
        def __init__(self, responses):
            self.responses = responses

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            outputs.append(input_items)
            return self.responses.pop(0)

    deliver = ProviderResponse(id="z", tool_calls=(ToolCall(call_id="z", name="entregar_despiece", arguments={"scenario_id": scenarios[0].id}),))
    for ids, error in (([proposal, proposal], "duplicate_reference"), ([proposal, "nope"], "unknown_reference")):
        outputs.clear()
        run_agent(extraction, scenarios, Fake([ProviderResponse(id="a", tool_calls=(ToolCall(call_id="a", name="comparar_candidatas", arguments={"candidate_ids": ids}),)), deliver]), AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5))
        result = json.loads(outputs[1][0]["output"])
        assert result["error"] == error and proposal in result["valid_candidate_ids"]


@pytest.mark.parametrize("mode", ["live", "geometry_only"])
def test_existing_modes_keep_working(tmp_path: Path, monkeypatch, mode: str) -> None:
    client = _client(tmp_path, monkeypatch, live=mode == "live")
    created = client.post("/api/v1/runs", json={"document_id": _upload(client), "mode": mode})
    assert created.status_code == 201 and created.json()["data"]["run"]["mode"] == mode
