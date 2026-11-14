import json
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.metrics import EvaluationInputError, evaluate_files


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    references = {
        "schema_version": "1.0",
        "dataset": {
            "id": "fixture-set",
            "evidence_kind": "developer_fixture",
            "frozen_before_evaluation": True,
            "partition_policy": "project_and_family",
            "component_matching": "reference_alignment",
            "cost_currency": "EUR",
            "cost_scope_id": "manufacturing-v1",
            "cost_effective_date": "2026-11-01",
            "hours_scope_id": "shop-hours-v1",
            "retrieval_items": {
                "hist-1": {"project_id": "p-h1", "family_id": "f-other", "duplicate_group_id": "d-h1"},
                "hist-2": {"project_id": "p-h2", "family_id": "f-other", "duplicate_group_id": "d-h2"},
                "hist-3": {"project_id": "p-h3", "family_id": "f-other", "duplicate_group_id": "d-h3"},
                "hist-4": {"project_id": "p-h4", "family_id": "f-other", "duplicate_group_id": "d-h4"},
            },
        },
        "cases": [
            {
                "id": "case-1",
                "split": "test",
                "project_id": "p-1",
                "family_id": "f-1",
                "duplicate_group_id": "d-1",
                "components": [
                    {
                        "key": "oracle-A",
                        "quantity": 2,
                        "dimensions_mm": {"length": 100, "width": 50, "thickness": 10},
                    },
                    {
                        "key": "oracle-B",
                        "quantity": 1,
                        "quantity_state": "hypothesis",
                        "quantity_review_status": "unreviewed",
                        "dimensions_mm": {"length": 80, "width": 40, "thickness": None},
                    },
                ],
                "relevant_item_ids": ["hist-1", "hist-3"],
                "cost": {"value": 200, "currency": "EUR", "scope_id": "manufacturing-v1", "effective_date": "2026-11-01"},
                "hours": {"value": 0, "scope_id": "shop-hours-v1"},
                "technician_baseline": {"duration_seconds": 600, "acceptable": True, "corrections_until_acceptable": 4},
                "component_matches": [
                    {"prediction_key": "local-A", "reference_key": "oracle-A"}
                ],
                "acceptable_scenarios": [{"key": "oracle-scenario-1"}, {"key": "oracle-scenario-2"}],
                "scenario_matches": [{"prediction_key": "local-scenario-1", "reference_key": "oracle-scenario-1"}],
            },
            {
                "id": "case-2",
                "split": "test",
                "project_id": "p-2",
                "family_id": "f-2",
                "duplicate_group_id": "d-2",
                "components": [],
                "relevant_item_ids": [],
                "cost": {"value": 100, "currency": "EUR", "scope_id": "manufacturing-v1", "effective_date": "2026-11-01"},
                "hours": {"value": 5, "scope_id": "shop-hours-v1"},
                "technician_baseline": None,
                "component_matches": [],
                "acceptable_scenarios": [],
                "scenario_matches": [],
            },
        ],
    }
    predictions = {
        "schema_version": "1.0",
        "dataset_id": "fixture-set",
        "cases": [
            {
                "id": "case-1",
                "components": [
                    {
                        "key": "local-A",
                        "quantity": 1,
                        "quantity_state": "hypothesis",
                        "dimensions_mm": {"length": 102, "width": 50, "thickness": 9},
                        "dimension_states": {"length": "hypothesis", "width": "hypothesis", "thickness": "hypothesis"},
                        "dimension_review_statuses": {"length": "unreviewed", "width": "unreviewed", "thickness": "unreviewed"},
                    },
                    {
                        "key": "C",
                        "quantity": 1,
                        "quantity_state": "hypothesis",
                        "quantity_review_status": "unreviewed",
                        "dimensions_mm": {"length": 70, "width": 30, "thickness": 8},
                        "dimension_states": {"length": "hypothesis", "width": "hypothesis", "thickness": "hypothesis"},
                        "dimension_review_statuses": {"length": "unreviewed", "width": "unreviewed", "thickness": "unreviewed"},
                    },
                ],
                "retrieved_item_ids": ["hist-3", "hist-2", "hist-4"],
                "cost": {"value": 230, "currency": "EUR", "scope_id": "manufacturing-v1", "effective_date": "2026-11-01"},
                "hours": {"value": 1, "scope_id": "shop-hours-v1"},
                "assisted": {"duration_seconds": 300, "acceptable": True, "corrections_until_acceptable": 1},
                "scenarios": [{"key": "local-scenario-1", "state": "hypothesis", "review_status": "unreviewed"}, {"key": "local-scenario-unsupported", "state": "hypothesis", "review_status": "unreviewed"}],
            },
            {
                "id": "case-2",
                "components": [],
                "retrieved_item_ids": [],
                "cost": None,
                "hours": None,
                "assisted": None,
                "scenarios": [],
            },
        ],
    }
    reference_path = tmp_path / "private-reference.json"
    prediction_path = tmp_path / "frozen-predictions.json"
    prediction_bytes = json.dumps(predictions).encode("utf-8")
    prediction_path.write_bytes(prediction_bytes)
    references["dataset"]["predictions_sha256"] = hashlib.sha256(prediction_bytes).hexdigest()
    reference_path.write_text(json.dumps(references), encoding="utf-8")
    return prediction_path, reference_path


def _rehash(reference_path: Path, prediction_path: Path) -> None:
    references = json.loads(reference_path.read_text(encoding="utf-8"))
    references["dataset"]["predictions_sha256"] = hashlib.sha256(
        prediction_path.read_bytes()
    ).hexdigest()
    reference_path.write_text(json.dumps(references), encoding="utf-8")


def test_report_counts_bom_dimensions_retrieval_and_numeric_error_independently(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)

    report = evaluate_files(prediction_path, reference_path, tolerance_mm=1, retrieval_k=2)

    assert report["bom"]["component_types"] == {
        "true_positive": 1,
        "predicted": 2,
        "reference": 2,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert report["bom"]["quantity_weighted"] == {
        "true_positive": 1,
        "predicted": 2,
        "reference": 3,
        "precision": 0.5,
        "recall": 1 / 3,
        "f1": 0.4,
        "eligible_components": 2,
        "compared_components": 1,
        "coverage": 0.5,
        "by_prediction_state": {
            "hypothesis": {
                "compared_components": 1,
                "predicted_occurrences": 2,
                "true_positive_occurrences": 1,
                "reference_occurrence_recall": 1 / 3,
            }
        },
        "by_review_status": {
            "unreviewed": {
                "compared_components": 1,
                "predicted_occurrences": 2,
                "true_positive_occurrences": 1,
                "reference_occurrence_recall": 1 / 3,
            }
        },
    }
    assert report["dimensions"] == {
        "tolerance_mm": 1.0,
        "eligible_fields": 5,
        "compared_fields": 3,
        "coverage": 0.6,
        "mae_mm": 1.0,
        "within_tolerance": 2,
        "within_tolerance_rate": 2 / 3,
        "by_prediction_state": {
            "hypothesis": {
                "compared_fields": 3,
                "coverage": 0.6,
                "mae_mm": 1.0,
                "within_tolerance": 2,
                "within_tolerance_rate": 2 / 3,
            }
        },
        "by_review_status": {
            "unreviewed": {
                "compared_fields": 3,
                "coverage": 0.6,
                "mae_mm": 1.0,
                "within_tolerance": 2,
                "within_tolerance_rate": 2 / 3,
            }
        },
    }
    assert report["retrieval"] == {
        "k": 2,
        "eligible_cases": 1,
        "evaluated_cases": 1,
        "coverage": 1.0,
        "macro_precision_at_k": 0.5,
        "macro_recall_at_k": 0.5,
        "leakage_candidates": 0,
        "cases_with_leakage": 0,
    }
    assert report["cost_eur"] == {
        "eligible_cases": 2,
        "evaluated_cases": 1,
        "coverage": 0.5,
        "mae": 30.0,
        "relative_error_cases": 1,
        "mape": 0.15,
        "metadata_incompatible_cases": 0,
        "metadata_incompatibility_reasons": {},
        "currency": "EUR",
        "scope_id": "manufacturing-v1",
        "effective_date": "2026-11-01",
    }
    assert report["hours"] == {
        "eligible_cases": 2,
        "evaluated_cases": 1,
        "coverage": 0.5,
        "mae": 1.0,
        "relative_error_cases": 0,
        "mape": None,
        "metadata_incompatible_cases": 0,
        "metadata_incompatibility_reasons": {},
        "scope_id": "shop-hours-v1",
    }

def test_developer_fixture_timing_is_descriptive_and_never_claimed_as_measured_savings(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)

    timing = evaluate_files(prediction_path, reference_path)["timing"]

    assert timing["eligible_cases"] == 1
    assert timing["paired_acceptable_cases"] == 1
    assert timing["coverage"] == 1.0
    assert timing["mean_baseline_seconds"] == 600.0
    assert timing["mean_assisted_seconds"] == 300.0
    assert timing["mean_observed_difference_seconds"] == 300.0
    assert timing["mean_baseline_corrections"] == 4.0
    assert timing["mean_assisted_corrections"] == 1.0
    assert timing["mean_observed_correction_difference"] == 3.0
    assert timing["savings_claim_supported"] is False
    assert timing["claim_status"] == "developer_fixture_not_empirical"


def test_input_rejects_dataset_mismatch_duplicate_components_and_invalid_parameters(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))
    predictions["dataset_id"] = "other"
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    _rehash(reference_path, prediction_path)

    with pytest.raises(EvaluationInputError, match="dataset_id mismatch"):
        evaluate_files(prediction_path, reference_path)

    predictions["dataset_id"] = "fixture-set"
    predictions["cases"][0]["components"].append(predictions["cases"][0]["components"][0])
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    _rehash(reference_path, prediction_path)
    with pytest.raises(EvaluationInputError, match="duplicate component key"):
        evaluate_files(prediction_path, reference_path)

    with pytest.raises(EvaluationInputError, match="tolerance_mm"):
        evaluate_files(prediction_path, reference_path, tolerance_mm=-1)
    with pytest.raises(EvaluationInputError, match="retrieval_k"):
        evaluate_files(prediction_path, reference_path, retrieval_k=0)

    predictions["cases"][0]["components"].pop()
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    _rehash(reference_path, prediction_path)
    references = json.loads(reference_path.read_text(encoding="utf-8"))
    references["dataset"]["frozen_before_evaluation"] = False
    reference_path.write_text(json.dumps(references), encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="frozen before private references"):
        evaluate_files(prediction_path, reference_path)


def test_cli_writes_machine_readable_report_without_copying_private_reference(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    output_path = tmp_path / "report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.evaluate_cases",
            "--predictions",
            str(prediction_path),
            "--references",
            str(reference_path),
            "--output",
            str(output_path),
            "--tolerance-mm",
            "1",
            "--retrieval-k",
            "2",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["dataset"] == {
        "id": "fixture-set",
        "evidence_kind": "developer_fixture",
        "case_count": 2,
        "frozen_before_evaluation": True,
        "partition_policy": "project_and_family",
        "component_matching": "reference_alignment",
        "prediction_fingerprint_verified": True,
    }
    serialized = output_path.read_text(encoding="utf-8")
    assert "private-reference.json" not in serialized
    assert '"components"' not in serialized

    original = prediction_path.read_bytes()
    refused = subprocess.run(
        [sys.executable, "-m", "tools.evaluate_cases", "--predictions", str(prediction_path),
         "--references", str(reference_path), "--output", str(prediction_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
    )
    assert refused.returncode != 0
    assert "output must differ" in refused.stderr
    assert prediction_path.read_bytes() == original


def test_reports_false_component_hypotheses_and_preserved_ambiguous_scenarios(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)

    report = evaluate_files(prediction_path, reference_path)

    assert report["component_hypotheses"] == {
        "predicted_components": 2,
        "unmatched_predicted_components": 1,
        "unsupported_rate": 0.5,
        "human_corrected_fields": None,
    }
    assert report["ambiguity"] == {
        "eligible_acceptable_scenarios": 2,
        "matched_acceptable_scenarios": 1,
        "preservation_recall": 0.5,
        "predicted_scenarios": 2,
        "unsupported_predicted_scenarios": 1,
        "eligible_cases": 1,
        "evaluated_cases": 1,
        "coverage": 1.0,
        "by_prediction_state": {
            "hypothesis": {
                "predicted_scenarios": 2,
                "matched_acceptable_scenarios": 1,
                "unsupported_predicted_scenarios": 1,
            }
        },
        "by_review_status": {
            "unreviewed": {
                "predicted_scenarios": 2,
                "matched_acceptable_scenarios": 1,
                "unsupported_predicted_scenarios": 1,
            }
        },
    }


def test_hash_and_economic_metadata_mismatches_are_not_scored(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))
    predictions["cases"][0]["cost"]["currency"] = "USD"
    predictions["cases"][0]["hours"]["scope_id"] = "office-hours"
    prediction_bytes = json.dumps(predictions).encode("utf-8")
    prediction_path.write_bytes(prediction_bytes)
    references = json.loads(reference_path.read_text(encoding="utf-8"))
    references["dataset"]["predictions_sha256"] = hashlib.sha256(prediction_bytes).hexdigest()
    reference_path.write_text(json.dumps(references), encoding="utf-8")

    report = evaluate_files(prediction_path, reference_path)

    assert report["cost_eur"]["evaluated_cases"] == 0
    assert report["cost_eur"]["metadata_incompatibility_reasons"] == {"currency": 1}
    assert report["hours"]["evaluated_cases"] == 0
    assert report["hours"]["metadata_incompatibility_reasons"] == {"scope_id": 1}

    references["dataset"]["predictions_sha256"] = "0" * 64
    reference_path.write_text(json.dumps(references), encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="predictions_sha256 mismatch"):
        evaluate_files(prediction_path, reference_path)


def test_reference_economics_must_share_declared_dataset_units_and_scope(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    references = json.loads(reference_path.read_text(encoding="utf-8"))
    references["cases"][1]["cost"]["currency"] = "USD"
    reference_path.write_text(json.dumps(references), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="reference cost metadata differs"):
        evaluate_files(prediction_path, reference_path)


def test_partition_and_retrieval_leakage_checks_detect_family_project_and_duplicate_reuse(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    references = json.loads(reference_path.read_text(encoding="utf-8"))
    references["dataset"]["retrieval_items"]["hist-3"] = {
        "project_id": "p-1",
        "family_id": "f-other",
        "duplicate_group_id": "d-h3",
    }
    reference_path.write_text(json.dumps(references), encoding="utf-8")

    report = evaluate_files(prediction_path, reference_path, retrieval_k=2)

    assert report["retrieval"]["leakage_candidates"] == 1
    assert report["retrieval"]["cases_with_leakage"] == 1
    assert report["retrieval"]["macro_precision_at_k"] == 0.0
    assert report["retrieval"]["macro_recall_at_k"] == 0.0

    references["cases"][1]["split"] = "development"
    references["cases"][1]["family_id"] = "f-1"
    reference_path.write_text(json.dumps(references), encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="family_id.*crosses splits"):
        evaluate_files(prediction_path, reference_path)


def test_unknown_predicted_quantity_is_an_abstention_with_explicit_coverage(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))
    predictions["cases"][0]["components"][0]["quantity"] = None
    predictions["cases"][0]["components"][0]["quantity_state"] = "unknown"
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    _rehash(reference_path, prediction_path)

    report = evaluate_files(prediction_path, reference_path)

    assert report["bom"]["quantity_weighted"] == {
        "true_positive": 0,
        "predicted": 1,
        "reference": 3,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "eligible_components": 2,
        "compared_components": 0,
        "coverage": 0.0,
        "by_prediction_state": {
            "hypothesis": {
                "compared_components": 0,
                "predicted_occurrences": 1,
                "true_positive_occurrences": 0,
                "reference_occurrence_recall": 0.0,
            }
        },
        "by_review_status": {
            "unreviewed": {
                "compared_components": 0,
                "predicted_occurrences": 1,
                "true_positive_occurrences": 0,
                "reference_occurrence_recall": 0.0,
            }
        },
    }


def test_auto_reviewed_metrics_remain_separate_from_hypothesis_and_human(tmp_path: Path) -> None:
    prediction_path, reference_path = _write_inputs(tmp_path)
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))
    component = predictions["cases"][0]["components"][0]
    component["quantity"] = 2
    component["quantity_review_status"] = "auto_reviewed"
    component["dimension_review_statuses"] = {key: "auto_reviewed" for key in component["dimension_states"]}
    predictions["cases"][0]["scenarios"][0]["review_status"] = "auto_reviewed"
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    _rehash(reference_path, prediction_path)

    report = evaluate_files(prediction_path, reference_path)

    assert report["dimensions"]["by_prediction_state"]["hypothesis"]["compared_fields"] == 3
    assert report["dimensions"]["by_review_status"]["auto_reviewed"]["compared_fields"] == 3
    assert report["bom"]["quantity_weighted"]["by_review_status"]["auto_reviewed"] == {
        "compared_components": 1,
        "predicted_occurrences": 2,
        "true_positive_occurrences": 2,
        "reference_occurrence_recall": 2 / 3,
    }
    assert report["bom"]["quantity_weighted"]["by_prediction_state"]["hypothesis"]["true_positive_occurrences"] == 2
    assert report["bom"]["quantity_weighted"]["by_review_status"]["unreviewed"]["true_positive_occurrences"] == 0
    assert report["ambiguity"]["by_review_status"]["auto_reviewed"] == {
        "predicted_scenarios": 1,
        "matched_acceptable_scenarios": 1,
        "unsupported_predicted_scenarios": 0,
    }

