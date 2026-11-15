from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import BoundedJsonBodyMiddleware, create_app
from backend.app.operacion.auth import hash_password
from backend.app.servicios.repository import DemoRepository
from backend.tests.test_private_repository import _extraction, _scenario


def _private_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    users = tmp_path / "users.json"
    users.write_text(
        json.dumps(
            {
                "alice": hash_password("alice password"),
                "bob": hash_password("bob password"),
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    return TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))


def test_json_body_middleware_stops_after_disconnect_without_calling_downstream() -> None:
    received = 0
    downstream_called = False

    async def receive() -> dict:
        nonlocal received
        received += 1
        if received > 1:
            raise AssertionError("disconnect must not be polled repeatedly")
        return {"type": "http.disconnect"}

    async def downstream(scope, receive, send) -> None:
        nonlocal downstream_called
        downstream_called = True

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/example",
        "headers": [(b"content-type", b"application/json")],
    }

    asyncio.run(BoundedJsonBodyMiddleware(downstream)(scope, receive, lambda _: None))

    assert received == 1
    assert downstream_called is False


def test_json_body_middleware_replays_body_then_delegates_disconnect() -> None:
    messages = iter(
        (
            {"type": "http.request", "body": b'{"ok":true}', "more_body": False},
            {"type": "http.disconnect"},
        )
    )
    observed: list[dict] = []

    async def receive() -> dict:
        return next(messages)

    async def downstream(scope, replay_receive, send) -> None:
        observed.append(await replay_receive())
        observed.append(await replay_receive())

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/example",
        "headers": [(b"content-type", b"application/json")],
    }

    asyncio.run(BoundedJsonBodyMiddleware(downstream)(scope, receive, lambda _: None))

    assert observed == [
        {"type": "http.request", "body": b'{"ok":true}', "more_body": False},
        {"type": "http.disconnect"},
    ]


def test_json_body_middleware_stops_when_disconnect_arrives_mid_body() -> None:
    messages = iter(
        (
            {"type": "http.request", "body": b'{"partial":', "more_body": True},
            {"type": "http.disconnect"},
        )
    )
    downstream_called = False

    async def receive() -> dict:
        return next(messages)

    async def downstream(scope, replay_receive, send) -> None:
        nonlocal downstream_called
        downstream_called = True

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/example",
        "headers": [(b"content-type", b"application/json")],
    }

    asyncio.run(BoundedJsonBodyMiddleware(downstream)(scope, receive, lambda _: None))

    assert downstream_called is False


def test_repository_run_owner_is_required_and_foreign_owner_looks_missing(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "repository.sqlite3")
    repository.create_run(
        "run-owned", "geometry_only", _extraction(), (_scenario(),), owner_actor="alice"
    )

    repository.assert_run_owner("run-owned", actor="alice")
    with pytest.raises(KeyError):
        repository.assert_run_owner("run-owned", actor="bob")
    with pytest.raises(KeyError):
        repository.assert_run_owner("run-missing", actor="alice")


def test_owner_migration_backfills_only_unanimous_linked_job_actor(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    extraction_json = _extraction().model_dump_json()
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE runs (
                id TEXT PRIMARY KEY, mode TEXT NOT NULL, state TEXT NOT NULL,
                reason_code TEXT, candidate_revision TEXT NOT NULL,
                current_result_revision INTEGER, extraction_json TEXT NOT NULL,
                scenarios_json TEXT NOT NULL, created_at TEXT NOT NULL,
                agent_selected_scenario_id TEXT, document_id TEXT,
                input_kind TEXT NOT NULL DEFAULT 'mounted_views_legacy',
                agent_selected_assembly_candidate_id TEXT,
                agent_selected_table_program_id TEXT,
                replay_source_recording_id TEXT
            );
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, actor TEXT, request_json TEXT NOT NULL,
                request_hash TEXT NOT NULL, state TEXT NOT NULL, run_id TEXT,
                error_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                cancel_requested_at TEXT
            );
            """
        )
        for run_id in ("run-unanimous", "run-conflict"):
            db.execute(
                "INSERT INTO runs VALUES (?, 'live', 'needs_review', NULL, 'rev', 1, ?, '[]', '2026-11-14', NULL, NULL, 'mounted_views_legacy', NULL, NULL, NULL)",
                (run_id, extraction_json),
            )
        rows = (
            ("job-a1", "alice", "run-unanimous"),
            ("job-a2", "alice", "run-unanimous"),
            ("job-c1", "alice", "run-conflict"),
            ("job-c2", "bob", "run-conflict"),
        )
        for job_id, actor, run_id in rows:
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, '{}', 'hash', 'succeeded', ?, NULL, '2026-11-14', '2026-11-14', NULL)",
                (job_id, actor, run_id),
            )

    repository = DemoRepository(path)

    repository.assert_run_owner("run-unanimous", actor="alice")
    with pytest.raises(KeyError):
        repository.assert_run_owner("run-conflict", actor="alice")
    with sqlite3.connect(path) as db:
        owners = dict(db.execute("SELECT id,owner_actor FROM runs"))
    assert owners == {"run-conflict": None, "run-unanimous": "alice"}


@pytest.mark.parametrize("prefix", ["", "/vexplorer"])
def test_private_documents_and_runs_are_invisible_to_other_authenticated_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str
) -> None:
    monkeypatch.setenv("VEXPLORER_ROOT_PATH", prefix)
    client = _private_client(tmp_path, monkeypatch)
    repository = client.app.state.repository
    repository.create_run(
        "run-owned", "geometry_only", _extraction(), (_scenario(),), owner_actor="alice"
    )
    fixture = (
        b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n"
        b"0\nENDSEC\n0\nEOF\n"
    )
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("owned.dxf", fixture, "application/dxf")},
        auth=("alice", "alice password"),
        headers={"Origin": "https://vexplorer.example"},
    )
    assert upload.status_code == 201
    document_id = upload.json()["data"]["document_id"]

    for path in (
        f"/api/v1/documents/{document_id}",
        f"/api/v1/documents/{document_id}/original",
        f"/api/v1/documents/{document_id}/normalized.dxf",
        f"/api/v1/documents/{document_id}/drawing",
        "/api/v1/runs/run-owned",
        "/api/v1/runs/run-owned/revisions",
        "/api/v1/runs/run-owned/drawing",
        "/api/v1/runs/run-owned/events",
    ):
        response = client.get(prefix + path, auth=("bob", "bob password"))
        assert response.status_code == 404, (path, response.text)

    assert client.get(
        prefix + f"/api/v1/documents/{document_id}/original",
        auth=("alice", "alice password"),
    ).status_code == 200
    assert client.get(
        prefix + "/api/v1/runs/run-owned", auth=("alice", "alice password")
    ).status_code == 200


def test_body_run_and_document_ids_are_owner_checked_before_private_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _private_client(tmp_path, monkeypatch)
    repository = client.app.state.repository
    repository.create_run(
        "run-owned", "geometry_only", _extraction(), (_scenario(),), owner_actor="alice"
    )
    fixture = (
        b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n"
        b"0\nENDSEC\n0\nEOF\n"
    )
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("owned.dxf", fixture, "application/dxf")},
        auth=("alice", "alice password"),
        headers={"Origin": "https://vexplorer.example"},
    ).json()["data"]["document_id"]

    replay = client.post(
        "/api/v1/replay-availability",
        json={"document_id": uploaded, "mode": "recorded_replay"},
        auth=("bob", "bob password"),
        headers={"Origin": "https://vexplorer.example"},
    )
    scenario = client.post(
        "/api/v1/history/scenarios",
        json={
            "run_id": "run-owned",
            "proposal_revision": 1,
            "review_revision": 1,
        },
        auth=("bob", "bob password"),
        headers={"Origin": "https://vexplorer.example"},
    )

    assert replay.status_code == 404
    assert scenario.status_code == 404


@pytest.mark.parametrize(
    ("path", "payload"),
    (
        ("/api/v1/precedentes/sugerencias", {"run_id": "run-owned", "result_revision": 1}),
        ("/api/v1/precedentes/similares-hibrido", {"run_id": "run-owned", "result_revision": 1}),
        ("/api/v1/precedentes/imagen/indexar", {"run_id": "run-owned"}),
        (
            "/api/v1/precedentes/imagen/similares",
            {"run_id": "run-owned", "umbral_minimo": 0.1},
        ),
        (
            "/api/v1/history/scenarios",
            {"run_id": "run-owned", "proposal_revision": 1, "review_revision": 1},
        ),
    ),
)
def test_private_body_run_id_endpoints_reject_foreign_source_runs_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict,
) -> None:
    client = _private_client(tmp_path, monkeypatch)
    client.app.state.repository.create_run(
        "run-owned", "geometry_only", _extraction(), (_scenario(),), owner_actor="alice"
    )

    response = client.post(
        path,
        json=payload,
        auth=("bob", "bob password"),
        headers={"Origin": "https://vexplorer.example"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


def test_reconstruction_job_artifacts_follow_source_run_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _private_client(tmp_path, monkeypatch)
    repository = client.app.state.repository
    repository.create_run(
        "run-owned", "geometry_only", _extraction(), (_scenario(),), owner_actor="alice"
    )
    job_id = "a" * 32
    folder = tmp_path / "data" / "reconstruction" / job_id
    folder.mkdir(parents=True)
    (folder / "status.json").write_text(
        json.dumps({"job_id": job_id, "run_id": "run-owned", "status": "completed"}),
        encoding="utf-8",
    )

    foreign = client.get(
        f"/api/v1/reconstruction/{job_id}", auth=("bob", "bob password")
    )
    owner = client.get(
        f"/api/v1/reconstruction/{job_id}", auth=("alice", "alice password")
    )

    assert foreign.status_code == 404
    assert owner.status_code == 200


def test_corrupt_reconstruction_status_fails_closed_as_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _private_client(tmp_path, monkeypatch)
    job_id = "b" * 32
    folder = tmp_path / "data" / "reconstruction" / job_id
    folder.mkdir(parents=True)
    (folder / "status.json").write_text("[]", encoding="utf-8")

    response = client.get(
        f"/api/v1/reconstruction/{job_id}", auth=("alice", "alice password")
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "run_not_found"


@pytest.mark.parametrize(
    "corruption",
    (
        {"audit": []},
        {
            "audit": {
                "uploaded_by": "alice",
                "uploaded_at": "2026-11-14T00:00:00+00:00",
            },
            "source": [],
        },
    ),
)
def test_corrupt_manifest_owner_fields_fail_closed_and_are_skipped_by_projects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: dict,
) -> None:
    client = _private_client(tmp_path, monkeypatch)
    document_id = "doc-" + "c" * 32
    manifest = {
        "document_id": document_id,
        "original_filename": "corrupt.dxf",
        "source": {
            "filename": "corrupt.dxf",
            "format": "dxf",
            "media_type": "application/dxf",
        },
        "audit": {
            "uploaded_by": "alice",
            "uploaded_at": "2026-11-14T00:00:00+00:00",
        },
        **corruption,
    }
    documents = tmp_path / "data" / "documents"
    (documents / f"{document_id}.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    direct = client.get(
        f"/api/v1/documents/{document_id}", auth=("alice", "alice password")
    )
    projects = client.get("/api/v1/projects", auth=("alice", "alice password"))

    assert direct.status_code == 404
    assert projects.status_code == 200
    assert projects.json()["data"]["items"] == []
