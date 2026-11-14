from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from tools.semantic_lab.probe_app import (
    build_worker_command,
    classify_response,
    configure_worker_environment,
    execution_metadata,
    select_cadblock_samples,
    summarize_geometry,
)


def test_select_cadblock_samples_is_diverse_deterministic_and_excludes_core(tmp_path: Path) -> None:
    root = tmp_path / "cadblock" / "dxf_metric"
    for category in ("beds", "buffets", "simple-tables", "sofas"):
        folder = root / category
        folder.mkdir(parents=True)
        (folder / "excluded.dxf").write_text("0\nEOF\n", encoding="ascii")
    for category in ("bathroom-set", "doors-plan", "kitchen-sinks"):
        folder = root / category
        folder.mkdir(parents=True)
        for index in range(10):
            (folder / f"{index:02d}.dxf").write_text("0\nEOF\n", encoding="ascii")

    selected = select_cadblock_samples(tmp_path / "cadblock", limit=8)

    assert [path.parent.name for path in selected] == [
        "bathroom-set", "doors-plan", "kitchen-sinks",
        "bathroom-set", "doors-plan", "kitchen-sinks",
        "bathroom-set", "doors-plan",
    ]
    assert all("excluded.dxf" not in path.name for path in selected)


def test_classify_response_does_not_equate_http_success_with_valid_proposal() -> None:
    classification = classify_response(
        upload_status=201,
        upload_data={"ingestion": {"state": "ready"}},
        run_status=201,
        run_data={
            "run": {"state": "completed"},
            "result": {
                "state": "needs_review",
                "pieces": [],
                "dispositions": [{"status": "needs_review"}],
            },
        },
        general_status=404,
        general_data={"error": {"code": "general_proposal_not_found"}},
    )

    assert classification == {
        "upload_ok": True,
        "ingestion_state": "ready",
        "geometry_run_created": True,
        "result_state": "needs_review",
        "piece_count": 0,
        "needs_review_count": 1,
        "general_proposal_present": False,
        "outcome": "needs_review_without_proposal",
    }


def test_classify_response_preserves_transport_or_ingestion_failure() -> None:
    classification = classify_response(
        upload_status=422,
        upload_data={"error": {"code": "invalid_dxf"}},
        run_status=None,
        run_data=None,
        general_status=None,
        general_data=None,
    )

    assert classification["upload_ok"] is False
    assert classification["outcome"] == "upload_error:invalid_dxf"
    assert classification["piece_count"] == 0


@pytest.mark.parametrize(
    ("python_executable", "script", "request_path", "expected"),
    [
        (
            PureWindowsPath("D:/app-venv/python.exe"),
            PureWindowsPath("C:/probe_app.py"),
            PureWindowsPath("D:/run/request.json"),
            [
                "D:\\app-venv\\python.exe",
                "C:\\probe_app.py",
                "_worker",
                "D:\\run\\request.json",
            ],
        ),
        (
            PurePosixPath("/opt/app-venv/python"),
            PurePosixPath("/workspace/probe_app.py"),
            PurePosixPath("/run/request.json"),
            [
                "/opt/app-venv/python",
                "/workspace/probe_app.py",
                "_worker",
                "/run/request.json",
            ],
        ),
    ],
)
def test_worker_command_uses_explicit_app_interpreter(
    python_executable: PureWindowsPath | PurePosixPath,
    script: PureWindowsPath | PurePosixPath,
    request_path: PureWindowsPath | PurePosixPath,
    expected: list[str],
) -> None:
    command = build_worker_command(
        python_executable,
        script,
        request_path,
    )

    assert command == expected


def test_worker_environment_routes_import_time_data_outside_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("VEXPLORER_DATA_DIR", raising=False)

    runtime_dir = configure_worker_environment(tmp_path)

    assert runtime_dir == tmp_path / "runtime-data"
    assert os.environ["VEXPLORER_DATA_DIR"] == str(tmp_path / "runtime-data" / "import-default")


def test_summarize_geometry_reports_observed_counts_without_claiming_parts() -> None:
    summary = summarize_geometry(
        200,
        {
            "status": "ready",
            "coordinate_unit": "mm",
            "entities": [{"id": "e1"}, {"id": "e2"}],
            "views": [{"id": "v1"}],
            "contours": [{"id": "c1"}],
            "dimensions": [],
            "observations": [{"id": "o1"}],
            "warnings": ["source_unit_unknown"],
        },
    )

    assert summary == {
        "status": "ready",
        "coordinate_unit": "mm",
        "entity_count": 2,
        "view_count": 1,
        "contour_count": 1,
        "dimension_count": 0,
        "observation_count": 1,
        "warnings": ["source_unit_unknown"],
    }


def test_execution_metadata_does_not_claim_unmeasured_network_or_payment_activity() -> None:
    metadata = execution_metadata(Path("D:/snapshot"), Path("D:/runtime"))

    assert metadata["provider_disabled_by_configuration"] is True
    assert metadata["network_activity_measured"] is False
    assert metadata["payment_activity_measured"] is False
    assert metadata["cost"] is None
    assert "network_provider_calls" not in metadata
