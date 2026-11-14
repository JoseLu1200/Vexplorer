from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.main import create_app
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs
import backend.app.agente.runner as runner_module
import backend.app.servicios.repository as repository_module
from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.operacion.auth import hash_password


ROOT = Path(__file__).resolve().parents[2]
LEGACY_FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"
PARTS_FIXTURE = ROOT / "data" / "planos_demo" / "piezas_completo.dxf"
TABLE_FIXTURE = ROOT / "data" / "planos_demo" / "mesa_demo_001.dxf"


class _LegacyProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        context = json.loads(input_items[0]["content"])
        return ProviderResponse(
            id="legacy-response-1",
            model="model-test",
            input_tokens=10,
            output_tokens=3,
            total_tokens=13,
            duration_ms=2,
            tool_calls=(ToolCall(
                call_id="legacy-call-1",
                name="entregar_despiece",
                arguments={"scenario_id": context["scenarios"][0]["id"]},
            ),),
        )


class _PartsProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        context = json.loads(input_items[0]["content"])
        return ProviderResponse(
            id="parts-response-1", model="model-test",
            tool_calls=(ToolCall(call_id="parts-call-1", name="entregar_candidato_montaje", arguments={
                "candidate_revision": context["candidate_revision"],
                "assembly_candidate_id": context["assembly_candidates"][0]["id"],
            }),),
        )


class _TableProvider:
    def __init__(self, *, vision: bool = False) -> None:
        extraction = extract_drawing(TABLE_FIXTURE, input_kind="mounted_orthographic_views")
        baseline = catalog_table_programs(analyze_mounted_table(extraction))[0]
        self.proposal = {
            "bindings": [item.model_dump(mode="json") for item in baseline.bindings],
            "components": [item.model_dump(mode="json") for item in baseline.components],
            "premises": [item.model_dump(mode="json") for item in baseline.premises],
            "assumptions": list(baseline.assumptions),
            "evidence_ids": list(baseline.evidence_ids),
        }
        self.vision = vision
        self.calls = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        if self.vision and self.calls == 1:
            context = json.loads(input_items[0]["content"])
            return ProviderResponse(
                id="table-response-vision", model="model-test",
                tool_calls=(ToolCall(call_id="table-call-vision", name="visualizar_vista", arguments={
                    "view_id": context["vision"]["available_views"][0]["view_id"],
                }),),
            )
        return ProviderResponse(
            id=f"table-response-{self.calls}", model="model-test",
            tool_calls=(ToolCall(call_id=f"table-call-{self.calls}", name="proponer_descomposicion", arguments=self.proposal),),
        )


def _upload(client: TestClient, fixture: Path = LEGACY_FIXTURE) -> str:
    with fixture.open("rb") as stream:
        response = client.post(
            "/api/v1/documents",
            files={"file": (fixture.name, stream, "application/dxf")},
        )
    assert response.status_code == 201, response.text
    return response.json()["data"]["document_id"]


def test_live_recording_is_server_authoritative_and_replays_offline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = _LegacyProvider()
    live_client = TestClient(create_app(data_dir=tmp_path, agent_provider=provider))
    document_id = _upload(live_client)
    request = {"document_id": document_id, "mode": "live"}

    live = live_client.post("/api/v1/runs", json=request)
    assert live.status_code == 201, live.text
    assert provider.calls == 1
    source_run = live.json()["data"]["run"]
    with sqlite3.connect(tmp_path / "vexplorer.sqlite3") as db:
        row = db.execute(
            "SELECT source_run_id,source_actor,response_count,transcript_bytes,transcript_json "
            "FROM agent_recordings"
        ).fetchone()
    assert row[:4] == (source_run["id"], "local-demo", 1, len(row[4].encode("utf-8")))
    assert "OPENAI_API_KEY" not in row[4] and "base64" not in row[4]

    replay_request = {"document_id": document_id, "mode": "recorded_replay"}
    availability = live_client.post("/api/v1/replay-availability", json=replay_request)
    assert availability.status_code == 200
    assert availability.json()["data"]["available"] is True

    offline_client = TestClient(create_app(data_dir=tmp_path))
    replay = offline_client.post("/api/v1/runs", json=replay_request)
    assert replay.status_code == 201, replay.text
    snapshot = replay.json()["data"]["run"]
    assert snapshot["mode"] == "recorded_replay"
    assert snapshot["replay_source"]["source_live_run_id"] == source_run["id"]
    assert snapshot["replay_source"]["source_actor"] == "local-demo"
    assert snapshot["replay_source"]["provider_response_ids"] == ["legacy-response-1"]
    assert replay.json()["data"]["result"] == live.json()["data"]["result"] | {
        "run_id": snapshot["id"],
        "created_at": replay.json()["data"]["result"]["created_at"],
    }
    events = offline_client.get(f"/api/v1/runs/{snapshot['id']}/events").text
    assert '"provenance": "recorded_replay"' in events
    assert source_run["id"] in events


def test_tampered_record_and_config_mismatch_are_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, agent_provider=_LegacyProvider()))
    document_id = _upload(client)
    assert client.post("/api/v1/runs", json={"document_id": document_id, "mode": "live"}).status_code == 201

    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "2048")
    changed = TestClient(create_app(data_dir=tmp_path))
    mismatch = changed.post("/api/v1/runs", json={"document_id": document_id, "mode": "recorded_replay"})
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "recorded_replay_unavailable"

    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "4096")
    with sqlite3.connect(tmp_path / "vexplorer.sqlite3") as db:
        db.execute("UPDATE agent_recordings SET transcript_json = transcript_json || ' '")
        db.commit()
    tampered = TestClient(create_app(data_dir=tmp_path)).post(
        "/api/v1/runs", json={"document_id": document_id, "mode": "recorded_replay"},
    )
    assert tampered.status_code == 409
    assert tampered.json()["error"]["code"] == "recorded_replay_stale"


def test_parts_and_table_record_then_replay_without_provider_calls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cases = [
        (PARTS_FIXTURE, _PartsProvider(), {"input_kind": "separated_part_views"}),
        (TABLE_FIXTURE, _TableProvider(), {
            "input_kind": "mounted_orthographic_views", "table_profile": "rectangular_table_v1",
            "proposal_mode": "model_generated",
        }),
    ]
    for index, (fixture, provider, options) in enumerate(cases):
        case_dir = tmp_path / str(index)
        live_client = TestClient(create_app(data_dir=case_dir, agent_provider=provider))
        document_id = _upload(live_client, fixture)
        live_request = {"document_id": document_id, "mode": "live", **options}
        live = live_client.post("/api/v1/runs", json=live_request)
        assert live.status_code == 201, live.text
        calls = provider.calls
        replay = TestClient(create_app(data_dir=case_dir)).post(
            "/api/v1/runs", json={**live_request, "mode": "recorded_replay"},
        )
        assert replay.status_code == 201, replay.text
        assert provider.calls == calls
        assert replay.json()["data"]["run"]["mode"] == "recorded_replay"


def test_recorded_replay_uses_durable_job_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path, agent_provider=_LegacyProvider()))
    document_id = _upload(client)
    assert client.post("/api/v1/runs", json={"document_id": document_id, "mode": "live"}).status_code == 201
    submitted = client.post(
        "/api/v1/jobs", json={"document_id": document_id, "mode": "recorded_replay"},
        headers={"Idempotency-Key": "replay-job-1"},
    )
    assert submitted.status_code == 202
    job_id = submitted.json()["data"]["id"]
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        if job["state"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert job["state"] == "succeeded" and job["run_id"]
    assert client.get(f"/api/v1/runs/{job['run_id']}").json()["data"]["run"]["mode"] == "recorded_replay"


def test_table_vision_replay_rejects_changed_rendered_png_hash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.setenv("OPENAI_VISION_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = _TableProvider(vision=True)
    client = TestClient(create_app(data_dir=tmp_path, agent_provider=provider))
    document_id = _upload(client, TABLE_FIXTURE)
    request = {
        "document_id": document_id, "mode": "live", "input_kind": "mounted_orthographic_views",
        "table_profile": "rectangular_table_v1", "proposal_mode": "model_generated",
    }
    live = client.post("/api/v1/runs", json=request)
    assert live.status_code == 201, live.text
    original = runner_module.render_view

    def changed_render(*args, **kwargs):
        artifact = original(*args, **kwargs)
        return replace(artifact, png=artifact.png + b"changed")

    monkeypatch.setattr(runner_module, "render_view", changed_render)
    replay = TestClient(create_app(data_dir=tmp_path)).post(
        "/api/v1/runs", json={**request, "mode": "recorded_replay"},
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "recorded_replay_stale"


def test_total_recording_count_quota_rolls_back_live_run_atomically(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(repository_module, "MAX_STORED_RECORDINGS", 1)
    client = TestClient(create_app(data_dir=tmp_path, agent_provider=_LegacyProvider()))
    document_id = _upload(client)
    request = {"document_id": document_id, "mode": "live"}
    assert client.post("/api/v1/runs", json=request).status_code == 201
    rejected = client.post("/api/v1/runs", json=request)
    assert rejected.status_code == 507
    assert rejected.json()["error"]["code"] == "recording_storage_exhausted"
    with sqlite3.connect(tmp_path / "vexplorer.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM agent_recordings").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_production_authenticated_jobs_record_and_replay_for_shared_team(tmp_path: Path, monkeypatch) -> None:
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"alice": hash_password("correct horse")}), encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("OPENAI_MODEL", "model-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = _LegacyProvider()
    client = TestClient(create_app(data_dir=tmp_path / "data", agent_provider=provider))
    auth = ("alice", "correct horse")
    mutation_headers = {"Origin": "https://vexplorer.example"}
    with LEGACY_FIXTURE.open("rb") as stream:
        uploaded = client.post(
            "/api/v1/documents", files={"file": (LEGACY_FIXTURE.name, stream, "application/dxf")},
            auth=auth, headers=mutation_headers,
        )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["data"]["document_id"]

    def submit(mode: str, key: str) -> dict:
        response = client.post(
            "/api/v1/jobs", json={"document_id": document_id, "mode": mode}, auth=auth,
            headers={**mutation_headers, "Idempotency-Key": key},
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["data"]["id"]
        for _ in range(100):
            job = client.get(f"/api/v1/jobs/{job_id}", auth=auth).json()["data"]
            if job["state"] not in {"queued", "running"}:
                return job
            time.sleep(0.01)
        return job

    live_job = submit("live", "live-1")
    assert live_job["state"] == "succeeded"
    calls = provider.calls
    replay_job = submit("recorded_replay", "replay-1")
    assert replay_job["state"] == "succeeded"
    assert provider.calls == calls
    snapshot = client.get(f"/api/v1/runs/{replay_job['run_id']}", auth=auth).json()["data"]["run"]
    assert snapshot["replay_source"]["source_actor"] == "alice"
