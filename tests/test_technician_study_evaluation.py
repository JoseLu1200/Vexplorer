from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.technician_study import StudyInputError, evaluate_study_file


def _fixture() -> dict:
    return {
        "schema_version": "1.0",
        "study": {
            "id": "developer-study",
            "protocol_id": "tech-study-v1",
            "evidence_kind": "developer_fixture",
            "source_kind": "developer_fixture",
            "actual_technicians_observed": False,
            "frozen_before_scoring": True,
        },
        "cases": [
            {
                "id": "case-a",
                "split": "development",
                "project_id": "project-a",
                "family_id": "family-a",
                "duplicate_group_id": "duplicate-a",
                "plan_sha256": "a" * 64,
            },
            {
                "id": "case-b",
                "split": "development",
                "project_id": "project-b",
                "family_id": "family-b",
                "duplicate_group_id": "duplicate-b",
                "plan_sha256": "b" * 64,
            },
        ],
        "sessions": [
            {
                "id": "session-manual",
                "case_id": "case-a",
                "participant_id": "participant-01",
                "condition": "manual",
                "reviewer_id": "reviewer-01",
                "reviewer_blinded_to_condition": True,
                "duration_seconds": 660,
                "interruption_seconds": 60,
                "acceptable": True,
                "corrections": [
                    {"kind": "missing_piece_added", "count": 2, "severity": "major"},
                    {"kind": "dimension_changed", "count": 1, "severity": "minor"},
                ],
            },
            {
                "id": "session-assisted",
                "case_id": "case-b",
                "participant_id": "participant-02",
                "condition": "assisted",
                "reviewer_id": "reviewer-02",
                "reviewer_blinded_to_condition": True,
                "duration_seconds": 330,
                "interruption_seconds": 30,
                "acceptable": True,
                "corrections": [
                    {"kind": "missing_piece_added", "count": 1, "severity": "major"}
                ],
            },
            {
                "id": "session-excluded",
                "case_id": "case-a",
                "participant_id": "participant-03",
                "condition": "assisted",
                "reviewer_id": "reviewer-03",
                "reviewer_blinded_to_condition": True,
                "duration_seconds": 100,
                "interruption_seconds": 0,
                "acceptable": False,
                "exclusion_reason": "procedure_interrupted",
                "corrections": [],
            },
        ],
        "economics": [
            {
                "case_id": "case-a",
                "reference_kind": "actual",
                "cost": {
                    "reference": {
                        "value": 100,
                        "currency": "EUR",
                        "scope_id": "manufacturing-v1",
                        "effective_date": "2026-11-01",
                    },
                    "prediction": {
                        "value": 120,
                        "currency": "EUR",
                        "scope_id": "manufacturing-v1",
                        "effective_date": "2026-11-01",
                    },
                },
                "hours": {
                    "reference": {"value": 4, "scope_id": "shop-hours-v1"},
                    "prediction": {"value": 3, "scope_id": "shop-hours-v1"},
                },
            },
            {
                "case_id": "case-b",
                "reference_kind": "budget",
                "cost": {
                    "reference": {
                        "value": 200,
                        "currency": "EUR",
                        "scope_id": "manufacturing-v1",
                        "effective_date": "2026-11-01",
                    },
                    "prediction": {
                        "value": 220,
                        "currency": "USD",
                        "scope_id": "manufacturing-v1",
                        "effective_date": "2026-11-01",
                    },
                },
                "hours": None,
            },
        ],
    }


def _write(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "study.json"
    path.write_text(json.dumps(payload or _fixture()), encoding="utf-8")
    return path


def test_scores_sessions_corrections_and_economic_error_with_explicit_exclusions(
    tmp_path: Path,
) -> None:
    report = evaluate_study_file(_write(tmp_path))

    assert report["dataset"] == {
        "id": "developer-study",
        "protocol_id": "tech-study-v1",
        "evidence_kind": "developer_fixture",
        "source_kind": "developer_fixture",
        "case_count": 2,
        "session_count": 3,
        "actual_technicians_observed": False,
        "technician_evidence_available": False,
        "frozen_before_scoring": True,
    }
    assert report["sessions"]["eligible_sessions"] == 2
    assert report["sessions"]["excluded_sessions"] == 1
    assert report["sessions"]["exclusion_reasons"] == {"procedure_interrupted": 1}
    assert report["sessions"]["by_condition"]["manual"] == {
        "sessions": 1,
        "acceptable_sessions": 1,
        "acceptance_rate": 1.0,
        "acceptable_time_sessions": 1,
        "mean_active_seconds_to_acceptable": 600.0,
        "median_active_seconds_to_acceptable": 600.0,
        "correction_count": 3,
        "mean_corrections_per_session": 3.0,
        "missing_piece_occurrences": 2,
        "extra_piece_occurrences": 0,
        "corrections_by_kind": {"dimension_changed": 1, "missing_piece_added": 2},
        "corrections_by_severity": {"major": 2, "minor": 1},
    }
    assert report["sessions"]["by_condition"]["assisted"]["mean_active_seconds_to_acceptable"] == 300.0
    assert report["sessions"]["by_condition"]["assisted"]["missing_piece_occurrences"] == 1
    assert report["sessions"]["descriptive_difference"] == {
        "assisted_minus_manual_mean_active_seconds": -300.0,
        "assisted_minus_manual_mean_corrections": -2.0,
        "savings_claim_supported": False,
        "claim_status": "developer_fixture_not_empirical",
    }
    assert report["economics"]["cost"] == {
        "eligible_references": 2,
        "evaluated": 1,
        "coverage": 0.5,
        "mae": 20.0,
        "median_absolute_error": 20.0,
        "mean_signed_error": 20.0,
        "relative_error_cases": 1,
        "mape": 0.2,
        "wape": 0.2,
        "reference_kind_counts": {"actual": 1, "budget": 1},
        "evaluated_reference_kind_counts": {"actual": 1},
        "metadata_incompatible_cases": 1,
        "metadata_incompatibility_reasons": {"currency": 1},
    }
    assert report["economics"]["hours"]["mae"] == 1.0
    assert report["economics"]["hours"]["coverage"] == 1.0


def test_rejects_forged_or_unsafe_study_provenance(tmp_path: Path) -> None:
    payload = _fixture()
    payload["study"]["evidence_kind"] = "observed_technician_study"
    with pytest.raises(StudyInputError, match="actual_technicians_observed"):
        evaluate_study_file(_write(tmp_path, payload))

    payload = _fixture()
    payload["study"]["frozen_before_scoring"] = False
    with pytest.raises(StudyInputError, match="frozen_before_scoring"):
        evaluate_study_file(_write(tmp_path, payload))

    payload = _fixture()
    payload["cases"][0]["plan_sha256"] = "not-a-hash"
    with pytest.raises(StudyInputError, match="plan_sha256"):
        evaluate_study_file(_write(tmp_path, payload))

    payload = _fixture()
    payload["sessions"][1]["case_id"] = "case-a"
    payload["sessions"][1]["participant_id"] = "participant-01"
    with pytest.raises(StudyInputError, match="participant.*case"):
        evaluate_study_file(_write(tmp_path, payload))


def test_rejects_invalid_correction_counts_and_session_timing(tmp_path: Path) -> None:
    payload = _fixture()
    payload["sessions"][0]["corrections"][0]["count"] = 0
    with pytest.raises(StudyInputError, match="correction count"):
        evaluate_study_file(_write(tmp_path, payload))

    payload = _fixture()
    payload["sessions"][0]["interruption_seconds"] = 700
    with pytest.raises(StudyInputError, match="interruption_seconds"):
        evaluate_study_file(_write(tmp_path, payload))

    payload = _fixture()
    payload["sessions"][0]["participant_id"] = payload["sessions"][0]["reviewer_id"]
    with pytest.raises(StudyInputError, match="reviewer_id"):
        evaluate_study_file(_write(tmp_path, payload))


def test_economic_incompatibility_counts_cases_not_mismatched_fields(tmp_path: Path) -> None:
    payload = _fixture()
    prediction = payload["economics"][0]["cost"]["prediction"]
    prediction["currency"] = "USD"
    prediction["scope_id"] = "retail-v1"

    report = evaluate_study_file(_write(tmp_path, payload))

    assert report["economics"]["cost"]["metadata_incompatible_cases"] == 2
    assert report["economics"]["cost"]["metadata_incompatibility_reasons"] == {
        "currency": 2,
        "scope_id": 1,
    }


def test_cli_writes_only_aggregate_report_and_never_overwrites_input(tmp_path: Path) -> None:
    input_path = _write(tmp_path)
    output_path = tmp_path / "report.json"
    command = [
        sys.executable,
        "-m",
        "tools.evaluate_technician_study",
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    serialized = output_path.read_text(encoding="utf-8")
    assert "participant-01" not in serialized
    assert "reviewer-01" not in serialized
    assert "case-a" not in serialized
    assert json.loads(serialized)["sessions"]["eligible_sessions"] == 2

    original = input_path.read_bytes()
    refused = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.evaluate_technician_study",
            "--input",
            str(input_path),
            "--output",
            str(input_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "output must differ" in refused.stderr
    assert input_path.read_bytes() == original
