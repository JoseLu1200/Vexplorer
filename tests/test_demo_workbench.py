from __future__ import annotations

import builtins
import os
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "planos_demo"
REFERENCE_DIR = (ROOT / "evaluation" / "reference").resolve()


def _is_private_path(value: object) -> bool:
    try:
        candidate = Path(os.fspath(value)).resolve()
    except (TypeError, ValueError, OSError):
        return False
    return candidate == REFERENCE_DIR or REFERENCE_DIR in candidate.parents


@contextmanager
def _deny_runtime_reference_reads():
    original_builtin_open = builtins.open
    original_path_open = Path.open

    def guarded_open(file, *args, **kwargs):
        assert not _is_private_path(file), f"runtime attempted private read: {file}"
        return original_builtin_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args, **kwargs):
        assert not _is_private_path(path), f"runtime attempted private read: {path}"
        return original_path_open(path, *args, **kwargs)

    with patch("builtins.open", guarded_open), patch.object(Path, "open", guarded_path_open):
        yield


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    return TestClient(create_app(data_dir=tmp_path))


def _upload(client: TestClient, filename: str) -> str:
    with (PUBLIC_DIR / filename).open("rb") as stream:
        response = client.post(
            "/api/v1/documents",
            files={"file": (filename, stream, "application/dxf")},
        )
    assert response.status_code == 201, response.text
    return response.json()["data"]["document_id"]


def _start(client: TestClient, document_id: str) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["run"]["id"], data["result"]


def _review_between_sides(client: TestClient, run_id: str) -> dict:
    response = client.post(
        f"/api/v1/runs/{run_id}/reviews",
        json={
            "base_result_revision": 1,
            "scenario_id": "scenario-between-sides",
            "confirmed_thickness_mm": 18,
            "material": "tablero sintético",
            "finish": "melamina sintética",
            "notes": "Confirmación de ensayo para reconstrucción",
            "reviewer_name": "Revisor E2E",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_document_preview_survives_unknown_units_and_unsupported_decomposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        unknown_id = _upload(client, "mueble_demo_unidades_desconocidas.dxf")
        unknown_response = client.get(f"/api/v1/documents/{unknown_id}/drawing")

        trapezoid_id = _upload(client, "mueble_demo_trapecio.dxf")
        trapezoid_response = client.get(f"/api/v1/documents/{trapezoid_id}/drawing")
        rejected_run = client.post(
            "/api/v1/runs",
            json={"document_id": trapezoid_id, "mode": "geometry_only"},
        )

    assert unknown_response.status_code == 200, unknown_response.text
    unknown = unknown_response.json()["data"]
    assert unknown["source_unit"] == "unknown"
    assert unknown["coordinate_unit"] == "source"
    assert len(unknown["views"]) == 3
    assert all(entity["points_mm"] is None for entity in unknown["entities"])
    assert all(dimension["value_mm"] is None for dimension in unknown["dimensions"])
    assert all(
        value is None
        for graphic in unknown["dimension_graphics"]
        for key, value in graphic.items()
        if key.endswith("_mm")
    )

    assert trapezoid_response.status_code == 200, trapezoid_response.text
    trapezoid = trapezoid_response.json()["data"]
    assert trapezoid["coordinate_unit"] == "mm"
    assert len(trapezoid["views"]) == 3
    assert trapezoid["contours"]
    assert rejected_run.status_code == 422
    assert rejected_run.json()["error"]["code"] == "unsupported_geometry"


def test_reconstruction_scene_counts_occurrences_and_matches_independent_volume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        document_id = _upload(client, "estanteria_montada.dxf")
        run_id, initial = _start(client, document_id)
        unavailable_response = client.get(
            f"/api/v1/runs/{run_id}/scene", params={"result_revision": 1}
        )
        reviewed = _review_between_sides(client, run_id)
        scene_response = client.get(
            f"/api/v1/runs/{run_id}/scene", params={"result_revision": 2}
        )

    assert initial["result_revision"] == 1
    assert unavailable_response.status_code == 200, unavailable_response.text
    unavailable = unavailable_response.json()["data"]
    assert unavailable["state"] == "unavailable"
    assert unavailable["objects"] == []

    assert reviewed["result_revision"] == 2
    assert scene_response.status_code == 200, scene_response.text
    scene = scene_response.json()["data"]
    assert scene["schema_version"] == "0.3.0"
    assert scene["result_revision"] == 2
    assert scene["state"] == "ready"
    assert scene["selected_scenario_id"] == "scenario-between-sides"
    assert scene["collision_status"] == "not_evaluated"
    assert scene["coordinate_system"] == "x=width,y=height,z=depth; origin=front-left-bottom"

    objects = scene["objects"]
    assert len(objects) == 6
    assert Counter(item["role"] for item in objects) == {
        "side_panel": 2,
        "top_panel": 1,
        "base_panel": 1,
        "shelf": 2,
    }
    assert len(objects) != 3  # tres vistas no son tres ocurrencias físicas
    assert sorted(item["occurrence_index"] for item in objects if item["role"] == "side_panel") == [1, 2]
    assert sorted(item["occurrence_index"] for item in objects if item["role"] == "shelf") == [1, 2]

    volume = 0.0
    for item in objects:
        size = item["dimensions_mm"]
        bbox = item["bbox_mm"]
        assert bbox["max"]["x"] - bbox["min"]["x"] == pytest.approx(size["x"])
        assert bbox["max"]["y"] - bbox["min"]["y"] == pytest.approx(size["y"])
        assert bbox["max"]["z"] - bbox["min"]["z"] == pytest.approx(size["z"])
        assert item["source_contour_ids"]
        assert item["evidence_ids"]
        assert item["placement_basis"]
        volume += size["x"] * size["y"] * size["z"]
    assert volume == pytest.approx(31_622_400.0)


def test_unknown_thickness_blocks_scene_solids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        document_id = _upload(client, "estanteria_incompleta.dxf")
        run_id, result = _start(client, document_id)
        scene_response = client.get(
            f"/api/v1/runs/{run_id}/scene", params={"result_revision": 1}
        )

    assert result["state"] == "needs_review"
    assert scene_response.status_code == 200, scene_response.text
    scene = scene_response.json()["data"]
    assert scene["state"] == "unavailable"
    assert scene["objects"] == []
    assert scene["warnings"]

