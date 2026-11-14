import json
from pathlib import Path

import pytest

from tools.build_processed_demo import build_bundle


def test_processed_demo_preserves_review_and_unknowns(tmp_path: Path, monkeypatch):
    external = tmp_path / "do-not-touch.sqlite3"
    external.write_bytes(b"external data")
    monkeypatch.setenv("VEXPLORER_HISTORY_DB", str(external))
    output = tmp_path / "demo"
    manifest = build_bundle(output)
    assert external.read_bytes() == b"external data"
    assert len(manifest["cases"]) == 4
    assert manifest["synthetic"] is True
    complete = json.loads((output / "estanteria_900" / "resultado.json").read_text(encoding="utf-8"))
    assert complete["result"]["state"] == "completed"
    shelf = next(p for p in complete["result"]["pieces"] if p["role"] == "shelf")
    assert (shelf["quantity"], shelf["length_mm"]) == (2, 864)
    assert complete["library_item"]["label"].startswith("DEMO SINTÉTICA")
    assert complete["estimate"]["total"] > 0
    assert complete["scene"]["objects"]
    incomplete = json.loads((output / "espesor_desconocido" / "resultado.json").read_text(encoding="utf-8"))
    assert incomplete["result"]["state"] == "needs_review"
    assert incomplete["result"]["result_revision"] == 1
    assert incomplete["result"]["pieces"] == []
    for case in manifest["cases"]:
        assert (output / case["id"] / "despiece.csv").is_file()
        assert case["source_sha256_lf"]


def test_builder_refuses_existing_destination(tmp_path: Path):
    marker = tmp_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_bundle(tmp_path)
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("published_snapshot", [False, True])
def test_bundle_restores_into_existing_app_without_model(tmp_path: Path, monkeypatch, published_snapshot):
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from tools.backup import restore_backup

    output = Path(__file__).resolve().parents[1] / "data/muebles_procesados_demo" if published_snapshot else tmp_path / "bundle"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8")) if published_snapshot else build_bundle(output)
    restored = restore_backup(output / "demo-runtime.zip", tmp_path / "restored")
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with TestClient(create_app(data_dir=restored)) as client:
        assert client.get("/api/v1/config").json()["data"]["live_available"] is False
        assert len(client.get("/api/v1/library").json()["data"]) == 3
        assert client.get("/api/v1/history/records").json()["data"]["total"] == 19
        for case in manifest["cases"]:
            run_id = case["run_id"]
            result = client.get(f"/api/v1/runs/{run_id}").json()["data"]["result"]
            assert result["state"] == case["state"]
            for route in ("drawing", "ledger", "scene", "explanations"):
                assert client.get(f"/api/v1/runs/{run_id}/{route}", params={
                    "result_revision": case["result_revision"]}).status_code == 200
            exported = client.get(f"/api/v1/runs/{run_id}/exports?format=json").json()
            expected = json.loads((output / case["id"] / "resultado.json").read_text(encoding="utf-8"))
            assert exported["result"] == expected["result"]
            assert exported["scene"] == expected["scene"]
