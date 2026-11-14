from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_unhashed_frontend_code_revalidates_without_changing_api_cache_headers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<script type='module' src='/app.js'></script>", encoding="utf-8")
    (frontend / "app.js").write_text("import './module.js';", encoding="utf-8")
    (frontend / "module.js").write_text("export const version = 1;", encoding="utf-8")
    (frontend / "styles.css").write_text("body { color: black; }", encoding="utf-8")
    (frontend / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=frontend))

    for path in ("/", "/index.html", "/app.js", "/module.js", "/styles.css"):
        assert client.get(path).headers["cache-control"] == "no-cache"
    assert client.get("/logo.svg").headers.get("cache-control") != "no-cache"
    assert client.get("/api/v1/health").headers.get("cache-control") != "no-cache"





