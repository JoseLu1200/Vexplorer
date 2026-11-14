"""Build already-processed synthetic furniture for the existing web app.

Only a new temporary runtime is used. No external provider or live service is called.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tools.backup import create_backup, verify_backup

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("estanteria_900", "Estantería de 900 mm", "estanteria_montada.dxf", True),
    ("estanteria_variante", "Estantería de otras dimensiones", "mueble_demo_002.dxf", True),
    ("mueble_bajo", "Mueble bajo", "mueble_demo_003.dxf", True),
    ("espesor_desconocido", "Control con espesor desconocido", "estanteria_incompleta.dxf", False),
)
DEMO_ENV = {
    "VEXPLORER_ENV": "local", "VEXPLORER_AUTH_ENABLED": "false",
    "OPENAI_API_KEY": "", "VEXPLORER_ROOT_PATH": "",
}


def _data(response, status: int = 200):
    if response.status_code != status:
        raise RuntimeError(f"demo_request_failed:{response.status_code}:{response.text}")
    return response.json()["data"]


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_bundle(output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": "1.0", "synthetic": True,
                "mode": "geometry_only", "requires_model_api": False,
                "public_library_eligible": False, "cases": []}
    isolated_env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("VEXPLORER_", "OPENAI_"))}
    isolated_env.update(DEMO_ENV)
    with tempfile.TemporaryDirectory(prefix="vexplorer-demo-") as temporary, patch.dict(os.environ, isolated_env, clear=True):
        runtime = Path(temporary) / "data"
        os.environ["VEXPLORER_DATA_DIR"] = str(runtime)
        from backend.app.main import create_app

        app = create_app(data_dir=runtime, frontend_dir=ROOT / "frontend")
        with TestClient(app) as client:
            manifest["published_history"] = []
            for dataset in ("furniture_costs", "furniture_hours"):
                payload = json.loads((ROOT / "data" / "datasets" / dataset / "historical_import.json").read_text(encoding="utf-8"))
                imported = _data(client.post("/api/v1/history/import/json", json=payload))
                if imported["rejected"]:
                    raise RuntimeError(f"demo_history_rejected:{dataset}")
                manifest["published_history"].append({"dataset": dataset, "records": imported["accepted"]})
            for case_id, label, filename, reviewed in CASES:
                case_dir = output / case_id
                case_dir.mkdir()
                source = ROOT / "data" / "planos_demo" / filename
                content = source.read_bytes()
                (case_dir / "fuente.dxf").write_bytes(content)
                uploaded = _data(client.post("/api/v1/documents", files={
                    "file": (filename, content, "application/dxf")}), 201)
                snapshot = _data(client.post("/api/v1/runs", json={
                    "document_id": uploaded["document_id"], "mode": "geometry_only",
                    "input_kind": "mounted_views_legacy"}), 201)
                run_id = snapshot["run"]["id"]
                _write_json(case_dir / "revision_inicial.json", snapshot)
                if reviewed:
                    request = {"base_result_revision": 1, "reviewer_name": "Ensayo sintético Vexplorer",
                               "scenario_id": "scenario-between-sides", "confirmed_thickness_mm": 18,
                               "material": "tablero sintético", "finish": "melamina sintética",
                               "notes": "Fixture propio sintético: decisión de ensayo, no certificación de un mueble real."}
                    _data(client.post(f"/api/v1/runs/{run_id}/reviews", json=request), 201)
                    _write_json(case_dir / "revision_ensayo.json", request)
                    _data(client.post(f"/api/v1/runs/{run_id}/estimate", json={"result_revision": 2}), 201)
                    _data(client.post(f"/api/v1/runs/{run_id}/library", json={
                        "result_revision": 2, "label": f"DEMO SINTÉTICA · {label}",
                        "embedding_mode": "offline"}), 201)
                bundle_response = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "json"})
                bundle_response.raise_for_status()
                bundle = bundle_response.json()
                _write_json(case_dir / "resultado.json", bundle)
                for resource in ("drawing", "ledger"):
                    _write_json(case_dir / f"{resource}.json", _data(client.get(f"/api/v1/runs/{run_id}/{resource}")))
                csv = client.get(f"/api/v1/runs/{run_id}/exports", params={"format": "csv"})
                csv.raise_for_status()
                (case_dir / "despiece.csv").write_bytes(csv.content)
                manifest["cases"].append({
                    "id": case_id, "label": label, "source": f"data/planos_demo/{filename}",
                    "source_sha256_lf": hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest(),
                    "run_id": run_id, "url_query": f"?run={run_id}",
                    "result_revision": bundle["result_revision"], "state": bundle["result"]["state"],
                    "piece_rows": len(bundle["result"]["pieces"]),
                })
            for case in manifest["cases"]:
                if case["state"] == "completed":
                    comparisons = _data(client.post(f"/api/v1/runs/{case['run_id']}/similarity", json={
                        "result_revision": case["result_revision"], "mode": "geometric",
                        "include_summary": True, "limit": 10}))
                    _write_json(output / case["id"] / "similitud_geometrica.json", comparisons)
        # sqlite connections retained by cycles must release Windows file handles
        # before the temporary runtime can be removed.
        del client, app
        gc.collect()
        backup = create_backup(runtime, output / "demo-runtime.zip")
        verify_backup(backup)
        manifest["backup"] = {"path": backup.name, "format": "vexplorer-backup-v2",
                              "sha256": hashlib.sha256(backup.read_bytes()).hexdigest()}
    _write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New destination directory")
    args = parser.parse_args()
    manifest = build_bundle(args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
