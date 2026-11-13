from __future__ import annotations

import builtins
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.agente.prompts import SYSTEM_PROMPT
from backend.app.agente.tools import tool_schemas
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
    """Fail immediately if an endpoint/tool tries to open evaluator data."""
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


def _client(tmp_path: Path, monkeypatch) -> TestClient:
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


def _start_geometry_only(client: TestClient, document_id: str) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/runs",
        json={"document_id": document_id, "mode": "geometry_only"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()["data"]
    return payload["run"]["id"], payload["result"]


def test_real_api_freezes_hypotheses_before_private_comparison_and_recalculates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        document_id = _upload(client, "estanteria_montada.dxf")
        run_id, initial = _start_geometry_only(client, document_id)
        config_payload = client.get("/api/v1/config").json()
        openapi_payload = client.get("/openapi.json").json()

    # Freeze the output before opening any evaluator-only artifact.
    frozen_output = json.loads(json.dumps(initial, sort_keys=True))
    frozen_sha256 = hashlib.sha256(
        json.dumps(frozen_output, sort_keys=True).encode("utf-8")
    ).hexdigest()

    assert frozen_output["result_revision"] == 1
    assert frozen_output["state"] == "needs_review"
    assert len(frozen_output["scenarios"]) == 2
    assert frozen_output["scenarios"][0]["id"] in frozen_output["scenarios"][1]["incompatible_with"]
    for scenario in frozen_output["scenarios"]:
        by_role = {component["role"]: component for component in scenario["components"]}
        assert {"side_panel", "top_panel", "base_panel", "shelf"} <= set(by_role)
        assert by_role["side_panel"]["quantity"] == 2
        assert by_role["shelf"]["quantity"] == 2
        assert sum(component["quantity"] or 0 for component in scenario["components"]) == 6
        assert all(component["thickness_mm"] is None for component in scenario["components"])
        assert all(component["evidence_ids"] for component in scenario["components"])

    # Only the evaluator reads these files, and only after the output hash is fixed.
    reference = json.loads(
        (REFERENCE_DIR / "estanteria_reference.json").read_text(encoding="utf-8")
    )
    economic_oracle = json.loads(
        (REFERENCE_DIR / "economic_oracle.json").read_text(encoding="utf-8")
    )
    reference_occurrences = sum(
        piece["quantity"] for piece in reference["reviewed_reference"]["pieces"]
    )
    assert reference_occurrences == 7
    assert reference_occurrences != 6  # the hidden back remains unproven from the input
    assert all(
        component["role"] != "back_panel"
        for scenario in frozen_output["scenarios"]
        for component in scenario["components"]
    )

    private_fragments = (
        "evaluation/reference",
        "estanteria_reference.json",
        "p-side",
        "p-back",
        "1164.0",
        "280.0",
    )
    exposed_surfaces = json.dumps(
        {
            "prompt": SYSTEM_PROMPT,
            "tools": tool_schemas(),
            "config": config_payload,
            "openapi": openapi_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).casefold()
    assert all(fragment.casefold() not in exposed_surfaces for fragment in private_fragments)

    with _deny_runtime_reference_reads():
        reviewed_response = client.post(
            f"/api/v1/runs/{run_id}/reviews",
            json={
                "base_result_revision": 1,
                "scenario_id": "scenario-between-sides",
                "confirmed_thickness_mm": 18,
                "material": "tablero sintético",
                "finish": "melamina sintética",
                "notes": "Técnico confirma montaje y espesor observables",
                "reviewer_name": "Revisor E2E",
            },
        )
        assert reviewed_response.status_code == 201, reviewed_response.text
        reviewed = reviewed_response.json()["data"]

        stale = client.post(
            f"/api/v1/runs/{run_id}/reviews",
            json={
                "base_result_revision": 1,
                "scenario_id": "scenario-between-sides",
                "confirmed_thickness_mm": 18,
                "notes": "revisión obsoleta",
                "reviewer_name": "Revisor E2E",
            },
        )
        snapshot = client.get(f"/api/v1/runs/{run_id}").json()["data"]
        comparables = client.get(f"/api/v1/runs/{run_id}/comparables").json()["data"]
        first_estimate_response = client.post(
            f"/api/v1/runs/{run_id}/estimate",
            json={"result_revision": 2},
        )
        second_estimate_response = client.post(
            f"/api/v1/runs/{run_id}/estimate",
            json={"result_revision": 2},
        )
        exported_json = client.get(
            f"/api/v1/runs/{run_id}/exports", params={"format": "json"}
        )
        exported_csv = client.get(
            f"/api/v1/runs/{run_id}/exports", params={"format": "csv"}
        )

    assert frozen_sha256 == hashlib.sha256(
        json.dumps(frozen_output, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert reviewed["result_revision"] == 2
    assert reviewed["state"] == "completed"
    assert snapshot["run"]["state"] == "needs_review"
    assert snapshot["result"]["result_revision"] == 2
    assert stale.status_code == 409

    by_role = {piece["role"]: piece for piece in reviewed["pieces"]}
    assert by_role["shelf"]["quantity"] == 2
    assert by_role["shelf"]["length_mm"] == 864.0  # 900 - 2 * 18, not copied from reference
    assert by_role["side_panel"]["length_mm"] == 1200.0
    assert by_role["side_panel"]["width_mm"] == 300.0

    assert comparables[0]["id"] == economic_oracle["expected"]["comparable_id"]
    assert comparables[0]["width_mm"] == 800.0
    assert any("900" in difference for difference in comparables[0]["differences"])
    assert all("1200×300" not in difference for difference in comparables[0]["differences"])
    assert first_estimate_response.status_code == 201
    assert second_estimate_response.status_code == 201
    first_estimate = first_estimate_response.json()["data"]
    second_estimate = second_estimate_response.json()["data"]
    assert first_estimate == second_estimate
    assert first_estimate["result_revision"] == 2
    concepts = {concept["id"]: concept for concept in first_estimate["concepts"]}
    assert len(concepts) == len(first_estimate["concepts"])
    assert concepts["setup"]["amount"] == economic_oracle["expected"]["fixed_amount_eur"]
    assert concepts["setup"]["factor"] == 1
    assert concepts["material"]["factor"] == economic_oracle["expected"]["material_factor"]
    assert concepts["material"]["amount"] == economic_oracle["expected"]["material_amount_eur"]
    assert first_estimate["total"] == economic_oracle["expected"]["total_eur"] == 127.84
    assert first_estimate["hours"] is economic_oracle["expected"]["hours"] is None

    assert exported_json.status_code == 200
    export_bundle = exported_json.json()
    assert export_bundle["schema_version"] == "0.2.0"
    assert export_bundle["result_revision"] == 2
    assert export_bundle["result"] == reviewed
    assert export_bundle["estimate"] == first_estimate
    assert [item["id"] for item in export_bundle["comparables"]] == [
        item["id"] for item in comparables
    ]
    assert export_bundle["events"]
    assert any(
        event["event_type"] == "human_review_committed"
        and event["data"]["result_revision"] == 2
        for event in export_bundle["events"]
    )
    assert exported_csv.status_code == 200
    assert "result_revision" in exported_csv.text
    assert ",2," in exported_csv.text


def test_incomplete_fixture_keeps_thickness_unknown_through_real_api(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with _deny_runtime_reference_reads():
        client = _client(tmp_path, monkeypatch)
        document_id = _upload(client, "estanteria_incompleta.dxf")
        run_id, result = _start_geometry_only(client, document_id)
        ledger = client.get(f"/api/v1/runs/{run_id}/ledger").json()["data"]

    assert result["state"] == "needs_review"
    assert len(ledger["dimensions"]) == 3
    assert sorted(dimension["value_mm"] for dimension in ledger["dimensions"]) == [300.0, 900.0, 1200.0]
    assert all(
        component["thickness_mm"] is None
        for scenario in result["scenarios"]
        for component in scenario["components"]
    )

