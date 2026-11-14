from __future__ import annotations

import pytest

from evaluation.complex_cutlist import (
    evaluate_case,
    freeze_prediction_bundle,
    load_frozen_prediction_bundle,
    score_frozen_bundle,
    summarize_cases,
)


def _reference(*dimensions: tuple[float, float, float]) -> dict:
    return {
        "components": [
            {"source_index": index, "bounds_mm": [0, 0, 0, *value]}
            for index, value in enumerate(dimensions, start=1)
        ]
    }


def _panel(
    length: float | None,
    width: float | None,
    thickness: float | None,
    *,
    quantity: int | None = 1,
    kind: str = "panel",
) -> dict:
    def dimension(value: float | None) -> dict:
        return {"value_mm": value, "state": "deduced" if value is not None else "unknown"}

    component = {
        "id": f"piece-{length}-{width}-{thickness}-{quantity}",
        "kind": kind,
        "length": dimension(length),
        "width": dimension(width),
        "thickness": dimension(thickness),
        "quantity": {"value": quantity, "state": "hypothesis"},
    }
    if kind != "panel":
        component.update({
            "necessity": "estimated_required",
            "premise_ids": ["premise:auxiliary"],
        })
        component["quantity"]["dependency_refs"] = ["premise:auxiliary"]
    return component


def _accepted_prediction(*components: dict, status: str = "succeeded") -> dict:
    rows = []
    field_reviews = []
    for component in components:
        component_id = component["id"]
        rows.append({
            **component,
            "component_id": component_id,
            "machine_field_reviews": [
                {"field": field, "status": "accepted"}
                for field in ("length", "width", "thickness", "quantity")
            ],
        })
        field_reviews.extend(
            {"target_ref": f"component:{component_id}.{field}", "status": "accepted"}
            for field in ("kind", "existence", "geometry", "length", "width", "thickness", "quantity")
        )
    return {
        "job_state": status,
        "proposal_revision": 1,
        "review_revision": 1,
        "review": {
            "proposal_revision": 1,
            "review_revision": 1,
            "reviewer_kind": "machine",
            "auto_review_status": "accepted",
            "status": "reviewed_incomplete",
            "construction_validation": {"status": "valid"},
            "machine_field_reviews": field_reviews,
        },
        "derived": {
            "proposal_revision": 1,
            "review_revision": 1,
            "status": "ready",
            "bom_rows": rows,
            "construction": {"warnings": []},
        },
    }


def test_case_penalizes_missing_and_false_panel_occurrences() -> None:
    reference = _reference((100, 50, 10), (200, 60, 10), (300, 70, 10))
    prediction = _accepted_prediction(
            _panel(100, 50, 10),
            _panel(200, 60, 10),
            _panel(999, 80, 10),
    )

    report = evaluate_case("case-1", reference, prediction)

    assert report["panel_occurrences"] == {
        "reference": 3,
        "predicted": 3,
        "matched": 2,
        "false_positive": 1,
        "missed": 1,
        "recall": pytest.approx(2 / 3),
        "precision": pytest.approx(2 / 3),
        "f1": pytest.approx(2 / 3),
    }
    assert report["dimensions"]["paired_known_accuracy"] == 1.0
    assert report["dimensions"]["reference_dimension_coverage"] == pytest.approx(2 / 3)
    assert report["dimensions"]["predicted_dimension_precision"] == pytest.approx(2 / 3)
    assert report["passes_90_percent_target"] is False


def test_case_expands_quantity_and_ignores_non_panel_auxiliaries() -> None:
    reference = _reference((100, 50, 10), (100, 50, 10))
    prediction = _accepted_prediction(
        _panel(100.4, 49.6, 10.1, quantity=2),
        _panel(None, None, None, quantity=4, kind="hardware"),
    )

    report = evaluate_case("case-2", reference, prediction)

    assert report["panel_occurrences"]["matched"] == 2
    assert report["panel_occurrences"]["precision"] == 1.0
    assert report["panel_occurrences"]["recall"] == 1.0
    assert report["unsupported_auxiliary_occurrences"] == 0
    assert report["supported_hardware_occurrences"] == 4
    assert report["dimensions"]["paired_known_accuracy"] == 1.0
    assert report["passes_90_percent_target"] is True


def test_partial_dimensions_can_identify_piece_but_missing_cell_reduces_coverage() -> None:
    reference = _reference((100, 50, 10))
    prediction = _accepted_prediction(
            _panel(100, 50, 10, quantity=None),
            _panel(100, None, 10),
    )

    report = evaluate_case("case-3", reference, prediction)

    assert report["panel_occurrences"]["predicted"] == 1
    assert report["panel_occurrences"]["matched"] == 1
    assert report["unknown_quantity_components"] == 1
    assert report["unknown_dimension_occurrences"] == 1
    assert report["dimensions"]["paired_known_accuracy"] == 1.0
    assert report["dimensions"]["reference_dimension_coverage"] == pytest.approx(2 / 3)
    assert report["dimensions"]["predicted_dimension_precision"] == 1.0
    assert report["passes_90_percent_target"] is False


def test_unsupported_auxiliary_relabel_blocks_pass() -> None:
    reference = _reference((100, 50, 10))
    relabeled = _panel(300, 70, 10, kind="hardware")
    relabeled.pop("necessity")
    relabeled.pop("premise_ids")
    relabeled["quantity"].pop("dependency_refs")
    prediction = _accepted_prediction(_panel(100, 50, 10), relabeled)
    prediction["review"]["machine_field_reviews"] = [
        item for item in prediction["review"]["machine_field_reviews"]
        if item["target_ref"] != f"component:{relabeled['id']}.kind"
    ]

    report = evaluate_case("case-escape", reference, prediction)

    assert report["panel_occurrences"]["recall"] == 1.0
    assert report["unsupported_auxiliary_occurrences"] == 1
    assert report["passes_90_percent_target"] is False


def test_complete_dimensions_are_orientation_invariant_at_inclusive_tolerance() -> None:
    reference = _reference((100, 50, 10))
    prediction = _accepted_prediction(_panel(50.0, 100.0, 10.2))

    report = evaluate_case("case-oriented", reference, prediction)

    assert report["panel_occurrences"]["matched"] == 1
    assert report["dimensions"]["joint_correct_occurrences"] == 1


def test_partial_planar_dimensions_are_orientation_invariant() -> None:
    reference = _reference((100, 50, 10))
    prediction = _accepted_prediction(_panel(50.0, 100.0, None))

    report = evaluate_case("case-partial-oriented", reference, prediction)

    assert report["panel_occurrences"]["matched"] == 1
    assert report["dimensions"]["paired_known_accuracy"] == 1.0
    assert report["dimensions"]["reference_dimension_coverage"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("tolerances", [(0.0, 1.0, 0.2), (1.0, float("nan"), 0.2)])
def test_tolerances_must_be_finite_and_positive(tolerances: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        evaluate_case(
            "invalid-tolerance",
            _reference((100, 50, 10)),
            {"job_state": "failed", "derived": {"bom_rows": []}},
            tolerances_mm=tolerances,
        )


def test_failed_run_is_retained_and_cannot_pass_even_with_good_draft() -> None:
    reference = _reference((100, 50, 10))
    report = evaluate_case(
        "case-failed",
        reference,
        {**_accepted_prediction(_panel(100, 50, 10), status="failed"),
         "failure_code": "provider_request_timeout"},
    )

    assert report["run_completed"] is False
    assert report["panel_occurrences"]["recall"] == 1.0
    assert report["passes_90_percent_target"] is False


def test_summary_is_micro_averaged_and_keeps_failed_cases() -> None:
    good = evaluate_case(
        "good",
        _reference((100, 50, 10)),
        _accepted_prediction(_panel(100, 50, 10)),
    )
    failed = evaluate_case(
        "failed",
        _reference((200, 60, 10)),
        {"job_state": "failed", "failure_code": "timeout", "derived": {"bom_rows": []}},
    )

    summary = summarize_cases([good, failed])

    assert summary["case_count"] == 2
    assert summary["completed_cases"] == 1
    assert summary["completion_rate"] == 0.5
    assert summary["panel_occurrences"]["recall"] == 0.5
    assert summary["panel_occurrences"]["precision"] == 1.0
    assert summary["all_cases_pass"] is False


def test_prediction_bundle_is_hashed_before_scoring_and_tampering_is_rejected(tmp_path) -> None:
    path = tmp_path / "predictions.json"
    bundle = freeze_prediction_bundle(
        path,
        cases=[{
            "case_id": "blind-001",
            "public_dxf_sha256": "a" * 64,
            "split": "holdout",
            "prediction": {"job_state": "failed", "derived": {"bom_rows": []}},
        }],
        runtime_config={"config_evidence": {"job_timeout_s": 600, "reviewer_model": "gpt-6-astra"}, "evaluation_phase": "holdout", "job_timeout_s": 600, "proposer_model": "gpt-6.1-sol", "reviewer_model": "gpt-6-astra"},
    )

    assert bundle["bundle_sha256"] == load_frozen_prediction_bundle(path)["bundle_sha256"]
    path.write_text(path.read_text(encoding="utf-8").replace("blind-001", "blind-999"), encoding="utf-8")
    with pytest.raises(ValueError, match="prediction_bundle_sha256_mismatch"):
        load_frozen_prediction_bundle(path)


def test_scoring_requires_exact_case_set_and_preserves_failure(tmp_path) -> None:
    predictions = tmp_path / "predictions.json"
    references = tmp_path / "references.json"
    freeze_prediction_bundle(
        predictions,
        cases=[{
            "case_id": "blind-001",
            "public_dxf_sha256": "b" * 64,
            "split": "holdout",
            "prediction": {"job_state": "failed", "failure_code": "timeout", "derived": {"bom_rows": []}},
        }],
        runtime_config={"config_evidence": {"job_timeout_s": 600, "reviewer_model": "gpt-6-astra"}, "evaluation_phase": "holdout", "job_timeout_s": 600},
    )
    references.write_text(
        __import__("json").dumps([{
            "id": "blind-001", "split": "holdout", "public_dxf_sha256": "b" * 64,
            **_reference((100, 50, 10)),
        }]),
        encoding="utf-8",
    )

    report = score_frozen_bundle(predictions, references)

    assert report["summary"]["case_count"] == 1
    assert report["summary"]["failed_case_ids"] == ["blind-001"]
    assert report["cases"][0]["panel_occurrences"]["recall"] == 0.0


def test_success_without_terminal_accepted_review_cannot_pass() -> None:
    prediction = _accepted_prediction(_panel(100, 50, 10))
    prediction["review"]["auto_review_status"] = "incomplete"

    report = evaluate_case("unaccepted", _reference((100, 50, 10)), prediction)

    assert report["panel_occurrences"]["recall"] == 1.0
    assert report["delivery_eligible"] is False
    assert report["passes_90_percent_target"] is False


def test_scores_effective_derived_bom_not_unreviewed_draft() -> None:
    prediction = _accepted_prediction(_panel(100, 50, 10))
    prediction["draft"] = {"components": [_panel(999, 999, 99)]}

    report = evaluate_case("effective", _reference((100, 50, 10)), prediction)

    assert report["panel_occurrences"]["matched"] == 1


def test_linear_member_counts_as_physical_cut_piece() -> None:
    prediction = _accepted_prediction(_panel(100, 50, 10, kind="linear_member"))

    report = evaluate_case("linear", _reference((100, 50, 10)), prediction)

    assert report["panel_occurrences"]["predicted"] == 1
    assert report["panel_occurrences"]["matched"] == 1


def test_reference_source_hash_and_split_must_match_frozen_case(tmp_path) -> None:
    predictions = tmp_path / "predictions.json"
    references = tmp_path / "references.json"
    freeze_prediction_bundle(
        predictions,
        cases=[{
            "case_id": "blind-001", "split": "holdout", "public_dxf_sha256": "b" * 64,
            "prediction": {"job_state": "failed", "derived": {"bom_rows": []}},
        }],
        runtime_config={"config_evidence": {"job_timeout_s": 600, "reviewer_model": "gpt-6-astra"}, "evaluation_phase": "holdout", "job_timeout_s": 600},
    )
    references.write_text(__import__("json").dumps([{
        "id": "blind-001", "split": "holdout", "public_dxf_sha256": "c" * 64,
        **_reference((100, 50, 10)),
    }]), encoding="utf-8")

    with pytest.raises(ValueError, match="prediction_reference_source_mismatch"):
        score_frozen_bundle(predictions, references)


def test_development_bundle_rejects_incomplete_preregistered_cohort(tmp_path) -> None:
    with pytest.raises(ValueError, match="exactly plank-030 and plank-016"):
        freeze_prediction_bundle(
            tmp_path / "predictions.json",
            cases=[{
                "case_id": "plank-030", "split": "development",
                "public_dxf_sha256": "a" * 64,
                "prediction": {"job_state": "failed", "derived": {"bom_rows": []}},
            }],
            runtime_config={"evaluation_phase": "development"},
        )



def test_unknown_quantity_blocks_target_even_with_all_reference_pieces_matched() -> None:
    prediction = _accepted_prediction(_panel(100, 50, 10), _panel(200, 50, 10, quantity=None))
    report = evaluate_case("unknown-quantity", _reference((100, 50, 10)), prediction)
    assert report["panel_occurrences"]["recall"] == 1.0
    assert report["unknown_quantity_components"] == 1
    assert report["passes_90_percent_target"] is False


def test_hardware_exclusion_requires_accepted_quantity() -> None:
    hardware = _panel(None, None, None, kind="hardware")
    prediction = _accepted_prediction(_panel(100, 50, 10), hardware)
    prediction["review"]["machine_field_reviews"] = [
        item for item in prediction["review"]["machine_field_reviews"]
        if item["target_ref"] != f"component:{hardware['id']}.quantity"
    ]
    report = evaluate_case("hardware-quantity", _reference((100, 50, 10)), prediction)
    assert report["supported_hardware_occurrences"] == 0
    assert report["unsupported_auxiliary_occurrences"] == 1
    assert report["passes_90_percent_target"] is False


@pytest.mark.parametrize("phase", [None, "unit", "", "production"])
def test_freeze_rejects_unregistered_phase(tmp_path, phase) -> None:
    with pytest.raises(ValueError, match="evaluation_phase"):
        freeze_prediction_bundle(tmp_path / "invalid.json", cases=[{
            "case_id": "blind-001", "split": "holdout", "public_dxf_sha256": "a" * 64,
            "prediction": {"job_state": "failed"},
        }], runtime_config={"evaluation_phase": phase})


def test_interrupted_job_is_terminal_for_capture() -> None:
    from tools.capture_complex_cutlist_live import TERMINAL_JOB_STATES
    assert "interrupted" in TERMINAL_JOB_STATES


def test_summary_includes_completed_cases_that_fail_quality() -> None:
    report = evaluate_case("wrong", _reference((100, 50, 10)), _accepted_prediction(_panel(200, 50, 10)))
    summary = summarize_cases([report])
    assert summary["failed_case_ids"] == ["wrong"]
    assert summary["incomplete_case_ids"] == []


@pytest.mark.parametrize("evidence", [{}, {"job_timeout_s": 300, "reviewer_model": "gpt-6-astra"}, {"job_timeout_s": 600, "reviewer_model": "other"}])
def test_freeze_requires_verified_runtime_configuration(tmp_path, evidence) -> None:
    with pytest.raises(ValueError, match="config_evidence"):
        freeze_prediction_bundle(tmp_path / "invalid.json", cases=[{
            "case_id": "blind-001", "split": "holdout", "public_dxf_sha256": "a" * 64,
            "prediction": {"job_state": "failed"},
        }], runtime_config={"evaluation_phase": "holdout", "config_evidence": evidence})
