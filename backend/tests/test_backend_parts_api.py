from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.main import create_app


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "piezas_completo.dxf"
THICKNESS_UNKNOWN_FIXTURE = ROOT / "data" / "planos_demo" / "piezas_espesor_desconocido.dxf"


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
    events = client.get(f"/api/v1/runs/{run_id}/events").text
    assert f'"selected_assembly_candidate_id": "{candidate_id}"' in events


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
    assert payload["run"]["agent_selected_scenario_id"] is None
    selected = payload["run"]["agent_selected_assembly_candidate_id"]
    assert selected == provider.initial_context["assembly_candidates"][0]["id"]
    assert payload["result"]["assembly_candidates"][0]["id"] == selected
    events = client.get(f"/api/v1/runs/{payload['run']['id']}/events").text
    assert "inspeccionar_pieza" in events
    assert "entregar_candidato_montaje" in events
    assert f'"selected_assembly_candidate_id": "{selected}"' in events


def test_parts_review_rejects_change_to_observed_dimension(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    created = client.post("/api/v1/runs", json={
        "document_id": document_id,
        "mode": "geometry_only",
        "input_kind": "separated_part_views",
    }).json()["data"]
    run_id = created["run"]["id"]
    candidate = created["result"]["assembly_candidates"][0]
    side_use = next(item for item in candidate["uses"] if item["role"] == "side_panel")

    response = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 1,
        "reviewer_name": "Operadora local",
        "assembly_candidate_id": candidate["id"],
        "decisions": [{
            "proposal_id": side_use["id"],
            "action": "confirm",
            "role": "side_panel",
            "length_mm": 999,
            "notes": "Intento de sustituir una medida observada.",
        }],
        "notes": "Selecciona candidato.",
    })

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "observed_dimension_override"
    snapshot = client.get(f"/api/v1/runs/{run_id}").json()["data"]
    assert snapshot["result"]["result_revision"] == 1

    observation = next(
        item for item in created["result"]["part_analysis"]["observations"]
        if item["id"] == side_use["part_observation_id"]
    )
    observed_length = observation["dimensions"]["length"]["value_mm"]
    repeated = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 1,
        "reviewer_name": "Operadora local",
        "assembly_candidate_id": candidate["id"],
        "decisions": [{
            "proposal_id": side_use["id"],
            "action": "confirm",
            "role": "side_panel",
            "length_mm": observed_length + 0.05,
            "notes": "Repite la medida dentro de tolerancia.",
        }],
        "notes": "Selecciona candidato.",
    })
    assert repeated.status_code == 201
    side_piece = next(
        item for item in repeated.json()["data"]["pieces"]
        if item["proposal_id"] == side_use["id"]
    )
    assert side_piece["length_mm"] == observed_length
    assert side_piece["field_states"]["length_mm"] == "observed"


def test_parts_review_rejects_role_outside_selected_candidate(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    document_id = _upload(client)
    created = client.post("/api/v1/runs", json={
        "document_id": document_id,
        "mode": "geometry_only",
        "input_kind": "separated_part_views",
    }).json()["data"]
    run_id = created["run"]["id"]
    candidate = created["result"]["assembly_candidates"][0]
    side_use = next(item for item in candidate["uses"] if item["role"] == "side_panel")

    response = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 1,
        "reviewer_name": "Operadora local",
        "assembly_candidate_id": candidate["id"],
        "decisions": [{
            "proposal_id": side_use["id"],
            "action": "confirm",
            "role": "shelf",
            "notes": "Intento de cambiar el rol del candidato seleccionado.",
        }],
        "notes": "Selecciona candidato.",
    })

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "role_override_requires_candidate"


def test_parts_review_recomputes_selected_candidate_from_confirmed_thickness(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    with THICKNESS_UNKNOWN_FIXTURE.open("rb") as stream:
        uploaded = client.post(
            "/api/v1/documents",
            files={"file": (THICKNESS_UNKNOWN_FIXTURE.name, stream, "application/dxf")},
        )
    document_id = uploaded.json()["data"]["document_id"]
    created = client.post("/api/v1/runs", json={
        "document_id": document_id,
        "mode": "geometry_only",
        "input_kind": "separated_part_views",
    }).json()["data"]
    run_id = created["run"]["id"]
    candidate = created["result"]["assembly_candidates"][0]
    observations = {
        item["id"]: item for item in created["result"]["part_analysis"]["observations"]
    }
    unknown_use = next(
        item for item in candidate["uses"]
        if observations[item["part_observation_id"]]["dimensions"]["thickness"]["value_mm"] is None
    )

    reviewed = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 1,
        "reviewer_name": "Operadora local",
        "assembly_candidate_id": candidate["id"],
        "decisions": [{
            "proposal_id": unknown_use["id"],
            "action": "confirm",
            "role": unknown_use["role"],
            "thickness_mm": 18,
            "notes": "Confirma espesor ausente desde revisión humana.",
        }],
        "notes": "Selecciona candidato y confirma la premisa dimensional.",
    })

    assert reviewed.status_code == 201
    result = reviewed.json()["data"]
    assert result["state"] == "completed"
    assert result["part_analysis"]["observations"] == created["result"]["part_analysis"]["observations"]
    selected = next(
        item for item in result["assembly_candidates"]
        if item["id"] == result["selected_assembly_candidate_id"]
    )
    assert {item["axis"]: item["value_mm"] for item in selected["derived_dimensions"]} == {
        "width": 900.0, "height": 1200.0, "depth": 300.0,
    }
    assert "human_confirmed_operands_used" in selected["assumptions"]
    assert any(
        ref.startswith("review:2:piece:")
        for constraint in selected["constraints"] for ref in constraint["operand_refs"]
    )
    scene = client.get(f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2})
    assert scene.status_code == 200
    assert scene.json()["data"]["state"] == "ready"
    assert len(scene.json()["data"]["objects"]) == 6

    initial = client.get(f"/api/v1/runs/{run_id}/parts", params={"result_revision": 1}).json()["data"]
    original = next(item for item in initial["assembly_candidates"] if item["id"] == candidate["id"])
    assert any(item["state"] == "unknown" for item in original["derived_dimensions"])

    material_review = client.post(f"/api/v1/runs/{run_id}/reviews", json={
        "base_result_revision": 2,
        "reviewer_name": "Operadora local",
        "assembly_candidate_id": candidate["id"],
        "material": "tablero confirmado",
        "notes": "Añade material sin modificar la premisa dimensional anterior.",
    })
    assert material_review.status_code == 201
    latest = material_review.json()["data"]
    assert latest["state"] == "completed"
    retained = next(item for item in latest["pieces"] if item["proposal_id"] == unknown_use["id"])
    assert retained["thickness_mm"] == 18
    assert retained["field_states"]["thickness_mm"] == "confirmed"
    assert retained["material"] == "tablero confirmado"
    revision_two = client.get(f"/api/v1/runs/{run_id}/revisions").json()["data"][1]
    prior = next(item for item in revision_two["pieces"] if item["proposal_id"] == unknown_use["id"])
    assert prior["thickness_mm"] == 18 and prior["material"] is None
