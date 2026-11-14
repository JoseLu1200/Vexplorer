from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.operacion.auth import PasswordFile, hash_password
from backend.app.estimacion.table_costs import get_table_cost_catalog


def _users_file(tmp_path: Path) -> Path:
    path = tmp_path / "users.json"
    path.write_text(json.dumps({"alice": hash_password("correct horse")}), encoding="utf-8")
    return path


def _production_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))


def test_scrypt_password_file_verifies_named_users_without_plaintext(tmp_path: Path) -> None:
    path = _users_file(tmp_path)

    users = PasswordFile.load(path)

    assert users.authenticate("alice", "correct horse") == "alice"
    assert users.authenticate("alice", "wrong") is None
    assert "correct horse" not in path.read_text(encoding="utf-8")


def test_unknown_and_known_wrong_users_execute_one_equal_cost_scrypt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.app.operacion.auth as auth_module

    users = PasswordFile.load(_users_file(tmp_path))
    real_scrypt = auth_module.hashlib.scrypt
    calls: list[tuple[int, int, int, int, int]] = []

    def instrumented_scrypt(password: bytes, *, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
        calls.append((len(password), n, r, p, dklen))
        return real_scrypt(password, salt=salt, n=n, r=r, p=p, dklen=dklen)

    monkeypatch.setattr(auth_module.hashlib, "scrypt", instrumented_scrypt)

    assert users.authenticate("alice", "same wrong password") is None
    assert users.authenticate("unknown", "same wrong password") is None
    assert calls == [
        (19, 2**14, 8, 1, 32),
        (19, 2**14, 8, 1, 32),
    ]

    calls.clear()
    over_limit = "x" * 1025
    assert users.authenticate("alice", over_limit) is None
    assert users.authenticate("unknown", over_limit) is None
    assert calls == []


def test_invalid_or_empty_production_password_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="users_file_empty"):
        PasswordFile.load(path)


def test_production_requires_basic_auth_but_health_and_local_mode_remain_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = _users_file(tmp_path)
    _production_env(tmp_path, monkeypatch)
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))

    assert client.get("/api/v1/health").status_code == 200
    denied = client.get("/api/v1/config")
    assert denied.status_code == 401
    assert denied.headers["www-authenticate"] == 'Basic realm="Vexplorer", charset="UTF-8"'
    session = client.get("/api/v1/session", auth=("alice", "correct horse"))
    assert session.status_code == 200
    assert session.json()["data"] == {
        "authenticated": True, "username": "alice", "environment": "production"
    }
    config = client.get("/api/v1/config", auth=("alice", "correct horse"))
    assert config.json()["data"]["library_requires_real_reviewed"] is False
    private_save = client.post(
        "/api/v1/runs/run-abc/library",
        json={"result_revision": 1, "label": "private", "embedding_mode": "offline"},
        auth=("alice", "correct horse"),
        headers={"Origin": "https://vexplorer.example"},
    )
    assert private_save.status_code == 404

    monkeypatch.setenv("VEXPLORER_ENV", "local")
    local = TestClient(create_app(data_dir=tmp_path / "local", frontend_dir=tmp_path / "none"))
    assert local.get("/api/v1/config").status_code == 200


def test_production_rejects_cross_origin_mutations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    users = _users_file(tmp_path)
    _production_env(tmp_path, monkeypatch)
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))

    denied = client.post(
        "/api/v1/documents",
        files={"file": ("fixture.dxf", b"0\nEOF\n", "application/dxf")},
        auth=("alice", "correct horse"),
        headers={"Origin": "https://evil.example"},
    )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "origin_not_allowed"


def test_repeated_bad_basic_credentials_are_rate_limited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    users = _users_file(tmp_path)
    _production_env(tmp_path, monkeypatch)
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(users))
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))

    responses = [client.get("/api/v1/session", auth=("alice", "wrong")) for _ in range(11)]

    assert responses[-1].status_code == 429
    assert responses[-1].json()["error"]["code"] == "authentication_rate_limited"


def test_config_exposes_validated_reverse_proxy_root_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_ROOT_PATH", "/vexplorer")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))

    response = client.get("/api/v1/config")

    assert response.status_code == 200
    assert response.json()["data"]["root_path"] == "/vexplorer"


def test_invalid_dxf_is_not_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    data = tmp_path / "data"
    client = TestClient(create_app(data_dir=data, frontend_dir=tmp_path / "none"))

    response = client.post(
        "/api/v1/documents",
        files={"file": ("broken.dxf", b"not a dxf", "application/dxf")},
    )

    assert response.status_code == 422
    assert list((data / "documents").iterdir()) == []


def test_public_production_without_users_keeps_origin_guard_and_job_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(tmp_path, monkeypatch)
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.delenv("VEXPLORER_USERS_FILE", raising=False)
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Vexplorer</h1>", encoding="utf-8")
    with TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=frontend)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "www-authenticate" not in response.headers
        assert client.get("/api/v1/session").json()["data"] == {
            "authenticated": False, "username": None, "environment": "production"
        }
        config = client.get("/api/v1/config").json()["data"]
        assert config["authenticated"] is False
        assert config["run_submission"]["legacy_sync"] is False
        for origin, expected in [("https://evil.example", 403), ("https://vexplorer.example", 201)]:
            response = client.post("/api/v1/documents", headers={"Origin": origin}, files={
                "file": ("empty.dxf", b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", "application/dxf")
            })
            assert response.status_code == expected


def test_invalid_auth_configuration_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "typo")
    with pytest.raises(ValueError, match="invalid_auth_enabled"):
        create_app(data_dir=tmp_path / "data")


def test_concurrent_uploads_cannot_overbook_storage_quota(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.app.main as main_module

    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_MAX_STORAGE_BYTES", "100")
    monkeypatch.setattr(main_module, "MAX_UPLOAD_BYTES", 80)
    data = tmp_path / "data"
    client = TestClient(create_app(data_dir=data, frontend_dir=tmp_path / "none"))
    minimal_dxf = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"

    def upload(index: int) -> int:
        return client.post(
            "/api/v1/documents",
            files={"file": (f"fixture-{index}.dxf", minimal_dxf, "application/dxf")},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(upload, range(2)))

    assert statuses == [201, 507]
    assert len(list((data / "documents").glob("*.dxf"))) == 1


def test_public_cad_hides_history_but_exposes_offline_library_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(tmp_path, monkeypatch)
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    with TestClient(create_app(data_dir=tmp_path / "data")) as client:
        for method, path in [
            ("GET", "/api/v1/history"),
            ("GET", "/api/v1/history/records"),
            ("POST", "/api/v1/history/import/json"),
            ("POST", "/api/v1/semantic-explorer/review"),
        ]:
            response = client.request(method, path)
            assert response.status_code == 403, (path, response.text)
            assert response.json()["error"]["code"] == "private_feature_unavailable"
        assert client.get("/api/v1/library").status_code == 200
        grouped = client.post("/api/v1/library/groups", json={"mode": "geometric", "threshold": 0.8})
        assert grouped.status_code == 200
        save = client.post("/api/v1/runs/run-abc/library", json={"result_revision": 1, "label": "real", "embedding_mode": "offline"})
        assert save.status_code == 404
        similar = client.post("/api/v1/runs/run-abc/similarity", json={"result_revision": 1, "mode": "geometric"})
        assert similar.status_code == 404
        config = client.get("/api/v1/config").json()["data"]
        assert config["capabilities"]["history"]["available"] is False
        assert config["capabilities"]["library"]["available"] is True
        assert config["semantic"]["available"] is False
        assert config["semantic"]["generation_requires_authentication"] is True
        assert client.get("/api/v1/health").status_code == 200
