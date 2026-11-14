import hashlib
import json
from pathlib import Path

import pytest

from tools.build_panel_evaluation_references import (
    align_components,
    build_evaluator_references,
    group_reference_components,
    main,
)


def _bounds(length: float, width: float, thickness: float) -> list[float]:
    return [0.0, 0.0, 0.0, length, width, thickness]


def _prediction(key: str, length, width, thickness) -> dict:
    return {
        "key": key,
        "quantity": 1,
        "quantity_state": "hypothesis",
        "quantity_review_status": "unreviewed",
        "dimensions_mm": {
            "length": length,
            "width": width,
            "thickness": thickness,
        },
        "dimension_states": {
            field: "hypothesis" if value is not None else "unknown"
            for field, value in {
                "length": length,
                "width": width,
                "thickness": thickness,
            }.items()
        },
    }


def test_groups_duplicate_physical_occurrences_after_declared_rounding() -> None:
    grouped = group_reference_components(
        [
            {"bounds_mm": _bounds(600.04, 400.02, 18.04)},
            {"bounds_mm": _bounds(600.03, 400.01, 18.03)},
            {"bounds_mm": _bounds(500.0, 300.0, 15.0)},
        ],
        round_digits=1,
    )

    assert grouped == [
        {
            "key": "private-shape-1",
            "quantity": 1,
            "dimensions_mm": {"length": 500.0, "width": 300.0, "thickness": 15.0},
        },
        {
            "key": "private-shape-2",
            "quantity": 2,
            "dimensions_mm": {"length": 600.0, "width": 400.0, "thickness": 18.0},
        },
    ]


def test_alignment_is_axis_invariant_but_abstentions_are_not_matchable() -> None:
    references = group_reference_components(
        [{"bounds_mm": _bounds(600, 400, 18)}], round_digits=1
    )
    matches = align_components(
        [
            _prediction("axes-swapped", 400, 600, 18),
            _prediction("abstained", 600, None, 18),
        ],
        references,
        tolerance_mm=1.0,
    )

    assert matches == [
        {"prediction_key": "axes-swapped", "reference_key": "private-shape-1"}
    ]


def test_alignment_maximizes_cardinality_before_minimizing_error() -> None:
    references = [
        {
            "key": "r0",
            "quantity": 1,
            "dimensions_mm": {"length": 100.0, "width": 50.0, "thickness": 10.0},
        },
        {
            "key": "r1",
            "quantity": 1,
            "dimensions_mm": {"length": 101.0, "width": 50.0, "thickness": 10.0},
        },
    ]
    predictions = [
        _prediction("flexible", 100.8, 50.0, 10.0),
        _prediction("only-r1", 101.9, 50.0, 10.0),
    ]

    assert align_components(predictions, references, tolerance_mm=1.0) == [
        {"prediction_key": "flexible", "reference_key": "r0"},
        {"prediction_key": "only-r1", "reference_key": "r1"},
    ]


def test_alignment_minimizes_error_among_maximum_cardinality_solutions() -> None:
    references = [
        {
            "key": "r0",
            "quantity": 1,
            "dimensions_mm": {"length": 100.0, "width": 50.0, "thickness": 10.0},
        },
        {
            "key": "r1",
            "quantity": 1,
            "dimensions_mm": {"length": 102.0, "width": 50.0, "thickness": 10.0},
        },
    ]
    predictions = [
        _prediction("near-r0", 100.9, 50.0, 10.0),
        _prediction("near-r1", 101.1, 50.0, 10.0),
    ]

    assert align_components(predictions, references, tolerance_mm=2.0) == [
        {"prediction_key": "near-r0", "reference_key": "r0"},
        {"prediction_key": "near-r1", "reference_key": "r1"},
    ]


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_rejects_nonfinite_bounds_predictions_and_tolerance(nonfinite: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        group_reference_components(
            [{"bounds_mm": _bounds(nonfinite, 400, 18)}], round_digits=1
        )

    references = group_reference_components(
        [{"bounds_mm": _bounds(600, 400, 18)}], round_digits=1
    )
    with pytest.raises(ValueError, match="finite"):
        align_components(
            [_prediction("bad", nonfinite, 400, 18)],
            references,
            tolerance_mm=1.0,
        )
    with pytest.raises(ValueError, match="finite"):
        align_components([], references, tolerance_mm=nonfinite)


def test_cli_binds_output_to_exact_prediction_bytes_and_can_filter_split(
    tmp_path: Path,
) -> None:
    predictions = {
        "schema_version": "1.0",
        "dataset_id": "public-panel-cohort",
        "cases": [
            {
                "id": "case-1",
                "components": [_prediction("p1", 400, 600, 18)],
                "retrieved_item_ids": None,
                "cost": None,
                "hours": None,
                "assisted": None,
                "scenarios": [],
            },
            {
                "id": "case-2",
                "components": [],
                "retrieved_item_ids": None,
                "cost": None,
                "hours": None,
                "assisted": None,
                "scenarios": [],
            },
        ],
    }
    raw = [
        {
            "id": "case-1",
            "split": "holdout",
            "family_hash": "family-1",
            "components": [{"bounds_mm": _bounds(600, 400, 18)}],
        },
        {
            "id": "case-2",
            "split": "development",
            "family_hash": "family-2",
            "components": [{"bounds_mm": _bounds(500, 300, 15)}],
        },
    ]
    prediction_path = tmp_path / "predictions.json"
    raw_path = tmp_path / "raw-private.json"
    output = tmp_path / "private-evaluator.json"
    filtered = tmp_path / "predictions-holdout.json"
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    raw_path.write_text(json.dumps(raw), encoding="utf-8")

    assert main(
        [
            "--predictions",
            str(prediction_path),
            "--raw-references",
            str(raw_path),
            "--output",
            str(output),
            "--effective-date",
            "2026-11-14",
            "--split",
            "holdout",
            "--filtered-predictions-output",
            str(filtered),
            "--acceptable-scenario-key",
            "private-reviewed-construction",
        ]
    ) == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    assert [case["id"] for case in result["cases"]] == ["case-1"]
    assert result["cases"][0]["component_matches"] == [
        {"prediction_key": "p1", "reference_key": "private-shape-1"}
    ]
    assert result["dataset"]["predictions_sha256"] == hashlib.sha256(
        filtered.read_bytes()
    ).hexdigest()
    assert build_evaluator_references(
        predictions,
        raw,
        prediction_sha256=hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
        evidence_kind="development_diagnostic",
        effective_date="2026-11-14",
        round_digits=1,
        tolerance_mm=1.0,
        acceptable_scenario_key=None,
    )["cases"][0]["scenario_matches"] == []
