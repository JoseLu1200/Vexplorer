from __future__ import annotations

import builtins
import json
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
        revisions_response = client.get(f"/api/v1/runs/{run_id}/revisions")
        explanations_response = client.get(
            f"/api/v1/runs/{run_id}/explanations",
            params={"result_revision": 2},
        )

    assert initial["result_revision"] == 1
    assert unavailable_response.status_code == 200, unavailable_response.text
    unavailable = unavailable_response.json()["data"]
    assert unavailable["state"] == "unavailable"
    assert unavailable["objects"] == []

    assert reviewed["result_revision"] == 2
    assert revisions_response.status_code == 200, revisions_response.text
    assert [item["result_revision"] for item in revisions_response.json()["data"]] == [1, 2]
    assert explanations_response.status_code == 200, explanations_response.text
    explanations = explanations_response.json()["data"]
    assert explanations["schema_version"] == "0.3.0"
    shelf_explanation = next(item for item in explanations["pieces"] if item["role"] == "shelf")
    assert shelf_explanation["source_entity_ids"]
    assert shelf_explanation["source_contour_ids"]
    assert shelf_explanation["evidence_ids"]
    assert "human_mounting_confirmation" in shelf_explanation["premises"]
    assert shelf_explanation["formulas"] == [
        {
            "field": "length_mm",
            "expression": "overall_width_mm - 2 * confirmed_thickness_mm",
            "operands_mm": {
                "overall_width_mm": 900.0,
                "confirmed_thickness_mm": 18.0,
            },
            "result_mm": 864.0,
        }
    ]
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


def test_offline_library_is_invariant_explainable_and_reproducibly_grouped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = {
        "case-A": "estanteria_montada.dxf",
        "case-B": "mueble_demo_004.dxf",
        "case-C": "mueble_demo_002.dxf",
        "case-D": "mueble_demo_003.dxf",
    }
    runs: dict[str, str] = {}
    saved: dict[str, dict] = {}

    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        for label, filename in cases.items():
            document_id = _upload(client, filename)
            run_id, _ = _start(client, document_id)
            _review_between_sides(client, run_id)
            response = client.post(
                f"/api/v1/runs/{run_id}/library",
                json={
                    "result_revision": 2,
                    "label": label,
                    "embedding_mode": "offline",
                },
            )
            assert response.status_code == 201, response.text
            runs[label] = run_id
            saved[label] = response.json()["data"]

        listed_response = client.get("/api/v1/library")
        similarity_response = client.post(
            f"/api/v1/runs/{runs['case-A']}/similarity",
            json={"result_revision": 2, "mode": "geometric", "limit": 10},
        )
        semantic_response = client.post(
            f"/api/v1/runs/{runs['case-A']}/similarity",
            json={"result_revision": 2, "mode": "semantic", "limit": 10},
        )
        groups_first_response = client.post(
            "/api/v1/library/groups",
            json={"mode": "geometric", "threshold": 0.999999},
        )
        groups_second_response = client.post(
            "/api/v1/library/groups",
            json={"mode": "geometric", "threshold": 0.999999},
        )
        export_response = client.get(
            f"/api/v1/runs/{runs['case-A']}/exports",
            params={"format": "json"},
        )

    assert listed_response.status_code == 200, listed_response.text
    listed = listed_response.json()["data"]
    assert len(listed) == 4
    assert all(item["embedding"] is None for item in listed)

    original = saved["case-A"]
    translated = saved["case-B"]
    dimensional_variant = saved["case-C"]
    structural_variant = saved["case-D"]
    assert original["descriptor"]["descriptor_version"] == "furniture-v1"
    assert original["descriptor"] == translated["descriptor"]
    assert original["descriptor_fingerprint"] == translated["descriptor_fingerprint"]
    assert original["descriptor_fingerprint"] != dimensional_variant["descriptor_fingerprint"]
    assert dimensional_variant["descriptor"]["structure"] == original["descriptor"]["structure"]
    assert structural_variant["descriptor"]["roles"] != original["descriptor"]["roles"]

    descriptor_surfaces = json.dumps(
        [item["descriptor"] for item in listed],
        ensure_ascii=False,
        sort_keys=True,
    ).casefold()
    for forbidden in (
        "run-",
        "doc-",
        "mueble_demo",
        "estanteria_montada",
        "case-a",
        "case-b",
        "evaluation/reference",
        "private_id",
    ):
        assert forbidden not in descriptor_surfaces

    assert similarity_response.status_code == 200, similarity_response.text
    matches = similarity_response.json()["data"]
    assert [item["method"] for item in matches] == ["geometric"] * 3
    assert [item["score_kind"] for item in matches] == ["geometric_similarity"] * 3
    assert matches[0]["run_id"] == runs["case-B"]
    assert matches[0]["score"] == pytest.approx(1.0)
    scores_by_run = {item["run_id"]: item["score"] for item in matches}
    assert scores_by_run[runs["case-C"]] > scores_by_run[runs["case-D"]]
    assert matches[1]["differences"]
    assert "probability" not in json.dumps(matches).casefold()

    assert semantic_response.status_code == 409
    assert semantic_response.json()["error"]["code"] == "semantic_embedding_missing"

    assert groups_first_response.status_code == 200, groups_first_response.text
    assert groups_second_response.status_code == 200, groups_second_response.text
    groups_first = groups_first_response.json()["data"]
    groups_second = groups_second_response.json()["data"]
    assert groups_first == groups_second
    assert len(groups_first) == 1
    assert set(groups_first[0]["member_ids"]) == {original["id"], translated["id"]}
    assert groups_first[0]["method"] == "geometric"
    assert groups_first[0]["score_kind"] == "geometric_similarity"
    assert groups_first[0]["threshold"] == pytest.approx(0.999999)

    # La referencia se abre solo después de congelar las salidas del runtime.
    frozen_groups = json.loads(json.dumps(groups_first, sort_keys=True))
    private_reference = json.loads(
        (REFERENCE_DIR / "library_reference.json").read_text(encoding="utf-8")
    )
    assert private_reference["expected_groups"]["same_structure"][:1] == [
        "estanteria_montada.dxf"
    ]
    assert frozen_groups == groups_first

    assert export_response.status_code == 200, export_response.text
    bundle = export_response.json()
    assert bundle["result_revision"] == 2
    assert bundle["scene"]["state"] == "ready"
    assert bundle["explanations"]["result_revision"] == 2
    assert bundle["descriptor"] == original["descriptor"]
    assert bundle["library_item"]["id"] == original["id"]

