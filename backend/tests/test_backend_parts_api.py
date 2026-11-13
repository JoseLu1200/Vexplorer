from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.main import create_app


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "piezas_completo.dxf"


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _upload(client: TestClient) -> str:
    with FIXTURE.open("rb") as stream:
        response = client.post(
            "/api/v1/documents",
            files={"file": (FIXTURE.name, stream, "application/dxf")},
        )
    assert response.status_code == 201
    return response.json()["data"]["document_id"]


def test_parts_only_run_persists_observations_and_candidates(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    drawing = client.get(
        f"/api/v1/documents/{document_id}/drawing",
        params={"input_kind": "separated_part_views"},
    )
    created = client.post(
        "/api/v1/runs",
        json={
            "document_id": document_id,
            "mode": "geometry_only",
            "input_kind": "separated_part_views",
        },
    )

    assert drawing.status_code == 200
    assert drawing.json()["data"]["input_kind"] == "separated_part_views"
    assert created.status_code == 201
    payload = created.json()["data"]
    assert payload["run"]["input_kind"] == "separated_part_views"
    assert payload["result"]["scenarios"] == []
    assert len(payload["result"]["part_analysis"]["observations"]) == 3
    assert payload["result"]["assembly_candidates"]

    run_id = payload["run"]["id"]
    parts = client.get(
        f"/api/v1/runs/{run_id}/parts", params={"result_revision": 1}
    )
    assert parts.status_code == 200
    assert parts.json()["data"]["part_analysis"]["candidate_revision"]
    assert parts.json()["data"]["selected_assembly_candidate_id"] is None


def test_parts_only_requires_explicit_input_kind(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)

    drawing = client.get(f"/api/v1/documents/{document_id}/drawing")

    assert drawing.status_code == 200
    assert drawing.json()["data"]["input_kind"] == "mounted_views_legacy"


def test_parts_scene_dispatches_to_reviewed_parts_reconstruction(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    created = client.post(
        "/api/v1/runs",
        json={
            "document_id": document_id,
            "mode": "geometry_only",
            "input_kind": "separated_part_views",
        },
    ).json()["data"]
    run_id = created["run"]["id"]
    candidate_id = created["result"]["assembly_candidates"][0]["id"]
    reviewed = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "reviewer_name": "Operadora local",
            "assembly_candidate_id": candidate_id,
            "notes": "Selecciona esta hipótesis de montaje y asignación de roles.",
        },
    )

    assert reviewed.status_code == 201
    assert reviewed.json()["data"]["state"] == "completed"
    scene = client.get(
        f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2}
    )
    assert scene.status_code == 200
    assert scene.json()["data"]["state"] == "ready"
    assert len(scene.json()["data"]["objects"]) == 6
    assert all(item["part_observation_id"] for item in scene.json()["data"]["objects"])


class _SelectingPartsProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        if self.calls == 1:
            context = __import__("json").loads(input_items[0]["content"])
            return ProviderResponse(id="parts-live-1", tool_calls=(ToolCall(
                call_id="inspect", name="inspeccionar_pieza",
                arguments={
                    "candidate_revision": context["candidate_revision"],
                    "part_observation_id": context["part_observations"][0]["id"],
                },
            ),))
        context = self.initial_context
        return ProviderResponse(id="parts-live-2", tool_calls=(ToolCall(
            call_id="select", name="entregar_candidato_montaje",
            arguments={
                "candidate_revision": context["candidate_revision"],
                "assembly_candidate_id": context["assembly_candidates"][0]["id"],
            },
        ),))

    @property
    def initial_context(self):
        return self._initial_context

    @initial_context.setter
    def initial_context(self, value):
        self._initial_context = value


def test_parts_live_uses_native_grounded_tools_and_persists_selection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    provider = _SelectingPartsProvider()
    original_create_response = provider.create_response

    def capture_context(**kwargs):
        if provider.calls == 0:
            provider.initial_context = __import__("json").loads(kwargs["input_items"][0]["content"])
        return original_create_response(**kwargs)

    provider.create_response = capture_context
    client = TestClient(create_app(data_dir=tmp_path, agent_provider=provider))
    document_id = _upload(client)

    response = client.post("/api/v1/runs", json={
        "document_id": document_id,
        "mode": "live",
        "input_kind": "separated_part_views",
    })

    assert response.status_code == 201
    payload = response.json()["data"]
    selected = payload["run"]["agent_selected_scenario_id"]
    assert selected == provider.initial_context["assembly_candidates"][0]["id"]
    assert payload["result"]["assembly_candidates"][0]["id"] == selected
    events = client.get(f"/api/v1/runs/{payload['run']['id']}/events").text
    assert "inspeccionar_pieza" in events
    assert "entregar_candidato_montaje" in events
    assert f'"selected_assembly_candidate_id": "{selected}"' in events
