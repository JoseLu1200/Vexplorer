from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.test_semantic_explorer import bundle, png

API = "/api/v1/semantic-explorer"


def client_with_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("VEXPLORER_EXPLORER_ENABLED", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app(data_dir=tmp_path)
    store = app.state.explorer_store
    release = store.publish("fixture", bundle(), {"p0": png()})
    store.activate("fixture", release)
    return TestClient(app), store


def test_disabled_feature_is_explicit_and_does_not_create_store(tmp_path, monkeypatch):
    monkeypatch.setenv("VEXPLORER_EXPLORER_ENABLED", "0")
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get(API + "/spaces").status_code == 503
    assert not (tmp_path / "semantic_explorer.sqlite3").exists()


def test_http_snapshot_search_image_and_retirement(tmp_path, monkeypatch):
    client, store = client_with_corpus(tmp_path, monkeypatch)
    spaces = client.get(API + "/spaces").json()["data"]["spaces"]
    assert len(spaces) == 1 and spaces[0]["id"] == "corpus:fixture"
    snapshot = client.get(API + "/snapshot", params={"space": spaces[0]["id"]}).json()[
        "data"
    ]
    request = {
        "space": spaces[0]["id"],
        "snapshot_id": snapshot["snapshot_id"],
        "member_id": "p0",
    }
    response = client.post(API + "/search", json=request)
    assert response.status_code == 200
    assert response.json()["data"]["neighbors"][0]["id"] == "p1"
    image = client.get(API + "/image", params=request)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.headers["x-content-type-options"] == "nosniff"
    assert client.get(
        API + "/image", params={**request, "member_id": "../secret"}
    ).status_code in (404, 422)
    store.retire("fixture", "p0")
    assert client.post(API + "/search", json=request).status_code == 409
    assert client.get(API + "/image", params=request).status_code == 409


def test_library_only_includes_latest_compatible_embeddings(tmp_path, monkeypatch):
    from backend.app.semantic.embeddings import EmbeddingResult
    from backend.tests.test_backend_library_api import _reviewed_run

    class Provider:
        model = "fixture"
        dimensions = 3

        def embed(self, text):
            return EmbeddingResult((1, 0, 0), self.model, self.dimensions)

    monkeypatch.setenv("VEXPLORER_EXPLORER_ENABLED", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app(data_dir=tmp_path, embedding_provider=Provider())
    client = TestClient(app)
    run = _reviewed_run(client, "test")
    client.post(
        f"/api/v1/runs/{run}/library",
        json={"result_revision": 1, "label": "Vieja", "embedding_mode": "embeddinggemma2"},
    )
    assert client.get(API + "/spaces").json()["data"]["spaces"] == []
    client.post(
        f"/api/v1/runs/{run}/library",
        json={"result_revision": 2, "label": "Actual", "embedding_mode": "embeddinggemma2"},
    )
    spaces = client.get(API + "/spaces").json()["data"]["spaces"]
    assert len(spaces) == 1
    snapshot = client.get(API + "/snapshot", params={"space": spaces[0]["id"]}).json()[
        "data"
    ]
    assert snapshot["points"][0]["result_revision"] == 2
    assert snapshot["points"][0]["label"] == "Actual"
    assert "vector" not in str(snapshot["points"])


def test_private_auth_also_protects_explorer(tmp_path, monkeypatch):
    from backend.tests.test_private_auth import _production_env, _users_file

    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://example.test")
    monkeypatch.setenv("VEXPLORER_USERS_FILE", str(_users_file(tmp_path)))
    _production_env(tmp_path, monkeypatch)
    client, _ = client_with_corpus(tmp_path, monkeypatch)
    assert client.get(API + "/spaces").status_code == 401
    assert (
        client.get(API + "/spaces", auth=("alice", "correct horse")).status_code == 200
    )
