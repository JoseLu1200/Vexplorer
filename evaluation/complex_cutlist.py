"""Blind, offline scoring for complex panel cut-list proposals.

The runtime receives only the public drawing.  This module is invoked later by
the evaluator with a frozen prediction and a physically separate reference.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from math import inf, isfinite
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TOLERANCES_MM = (1.0, 1.0, 0.2)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _panel_dimensions(values: Iterable[object]) -> tuple[float, float, float] | None:
    numbers = tuple(float(value) for value in values)
    if len(numbers) != 3 or not all(isfinite(value) and value > 0 for value in numbers):
        return None
    return tuple(sorted(numbers, reverse=True))


def _predicted_panel_dimensions(
    component: dict[str, Any],
) -> tuple[float | None, float | None, float | None]:
    values: list[float | None] = []
    for name in ("length", "width", "thickness"):
        raw = _dimension_value(component, name)
        if raw is None:
            values.append(None)
            continue
        value = float(raw)
        values.append(value if isfinite(value) and value > 0 else None)
    if all(value is not None for value in values):
        return tuple(sorted(values, reverse=True))  # type: ignore[arg-type,return-value]
    return tuple(values)  # type: ignore[return-value]


def _reference_occurrences(reference: dict[str, Any]) -> list[tuple[float, float, float]]:
    occurrences: list[tuple[float, float, float]] = []
    for component in reference.get("components") or ():
        bounds = component.get("bounds_mm") or ()
        if len(bounds) != 6:
            raise ValueError("reference component requires six bounds_mm values")
        dimensions = _panel_dimensions(
            (bounds[3] - bounds[0], bounds[4] - bounds[1], bounds[5] - bounds[2])
        )
        if dimensions is None:
            raise ValueError("reference component has invalid dimensions")
        occurrences.append(dimensions)
    return occurrences


def _dimension_value(component: dict[str, Any], name: str) -> object:
    value = component.get(name)
    return value.get("value_mm") if isinstance(value, dict) else value


def _quantity(component: dict[str, Any]) -> int | None:
    raw = component.get("quantity")
    value = raw.get("value") if isinstance(raw, dict) else raw
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _prediction_components(prediction: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only the persisted, effective BOM; never score the proposal draft."""
    derived = prediction.get("derived") or {}
    return list(derived.get("bom_rows") or ())


def _expand_prediction(
    prediction: dict[str, Any],
) -> tuple[list[tuple[float | None, float | None, float | None]], int, int, int]:
    panels: list[tuple[float | None, float | None, float | None]] = []
    supported_hardware_occurrences = 0
    unsupported_auxiliary_occurrences = 0
    unknown_quantity_components = 0
    review = prediction.get("review") or {}
    accepted_fields = {
        item.get("target_ref")
        for item in review.get("machine_field_reviews") or ()
        if item.get("status") == "accepted"
    }
    for component in _prediction_components(prediction):
        quantity = _quantity(component)
        if quantity is None:
            unknown_quantity_components += 1
            continue
        component_id = component.get("component_id") or component.get("id")
        if component.get("kind") == "hardware":
            supported = all(
                f"component:{component_id}.{field}" in accepted_fields
                for field in ("kind", "existence", "quantity")
            )
            if supported:
                supported_hardware_occurrences += quantity
                continue
            # An unreviewed relabel must not escape cut-piece precision.
            unsupported_auxiliary_occurrences += quantity
        dimensions = _predicted_panel_dimensions(component)
        panels.extend([dimensions] * quantity)
    return (
        panels,
        supported_hardware_occurrences,
        unsupported_auxiliary_occurrences,
        unknown_quantity_components,
    )


def _compatible_mapping(
    reference: tuple[float, float, float],
    predicted: tuple[float | None, float | None, float | None],
    tolerances: tuple[float, float, float],
) -> tuple[float, tuple[float | None, float | None, float | None]] | None:
    candidates = (predicted, (predicted[1], predicted[0], predicted[2]))
    compatible: list[tuple[float, tuple[float | None, float | None, float | None]]] = []
    for candidate in candidates:
        known = [index for index, value in enumerate(candidate) if value is not None]
        if len(known) < 2 or not all(
            abs(reference[index] - candidate[index]) <= tolerances[index]  # type: ignore[operator]
            for index in known
        ):
            continue
        cost = sum(
            abs(reference[index] - candidate[index]) / tolerances[index]  # type: ignore[operator]
            for index in known
        )
        compatible.append((cost, candidate))
    return min(compatible, key=lambda item: item[0]) if compatible else None


def _optimal_tolerance_matching(
    references: list[tuple[float, float, float]],
    predictions: list[tuple[float | None, float | None, float | None]],
    tolerances: tuple[float, float, float],
) -> list[tuple[int, int, tuple[float | None, float | None, float | None]]]:
    if not references or not predictions:
        return []
    incompatible = 1_000_000.0
    unmatched = 1_000.0
    costs: list[list[float]] = []
    for reference in references:
        row = []
        for prediction in predictions:
            mapping = _compatible_mapping(reference, prediction, tolerances)
            row.append(mapping[0] if mapping is not None else incompatible)
        row.extend([unmatched] * len(references))
        costs.append(row)
    pairs = _hungarian(costs)
    matched = []
    for reference_index, prediction_index in pairs:
        if (
            prediction_index >= len(predictions)
            or costs[reference_index][prediction_index] >= unmatched
        ):
            continue
        mapping = _compatible_mapping(
            references[reference_index], predictions[prediction_index], tolerances
        )
        if mapping is not None:
            matched.append((reference_index, prediction_index, mapping[1]))
    return matched


def _delivery_eligibility(prediction: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    review = prediction.get("review") or {}
    derived = prediction.get("derived") or {}
    if prediction.get("job_state") != "succeeded":
        reasons.append("job_not_succeeded")
    if review.get("reviewer_kind") != "machine" or review.get("auto_review_status") != "accepted":
        reasons.append("terminal_machine_review_not_accepted")
    if (review.get("construction_validation") or {}).get("status") != "valid":
        reasons.append("construction_validation_not_valid")
    revisions = (
        prediction.get("proposal_revision"), prediction.get("review_revision")
    )
    if any(value in (None, 0) for value in revisions) or any(
        (container or {}).get(name) != value
        for container in (review, derived)
        for name, value in zip(("proposal_revision", "review_revision"), revisions)
    ):
        reasons.append("revision_mismatch")
    if derived.get("construction") is None:
        reasons.append("construction_output_missing")
    accepted = {
        item.get("target_ref")
        for item in review.get("machine_field_reviews") or ()
        if item.get("status") == "accepted"
    }
    for row in _prediction_components(prediction):
        component_id = row.get("component_id") or row.get("id")
        relevant = ("kind", "existence") if row.get("kind") == "hardware" else (
            "kind", "existence", "geometry", "length", "width", "thickness", "quantity"
        )
        for field in relevant:
            if f"component:{component_id}.{field}" not in accepted:
                reasons.append(f"unaccepted:{component_id}.{field}")
    return not reasons, reasons


def _hungarian(costs: list[list[float]]) -> list[tuple[int, int]]:
    """Minimum-cost assignment for a rectangular matrix without dependencies."""
    if not costs or not costs[0]:
        return []
    transposed = len(costs) > len(costs[0])
    matrix = [list(row) for row in zip(*costs)] if transposed else costs
    row_count, column_count = len(matrix), len(matrix[0])
    u = [0.0] * (row_count + 1)
    v = [0.0] * (column_count + 1)
    p = [0] * (column_count + 1)
    way = [0] * (column_count + 1)
    for row in range(1, row_count + 1):
        p[0] = row
        column0 = 0
        minimum = [inf] * (column_count + 1)
        used = [False] * (column_count + 1)
        while True:
            used[column0] = True
            row0 = p[column0]
            delta = inf
            column1 = 0
            for column in range(1, column_count + 1):
                if used[column]:
                    continue
                current = matrix[row0 - 1][column - 1] - u[row0] - v[column]
                if current < minimum[column]:
                    minimum[column] = current
                    way[column] = column0
                if minimum[column] < delta:
                    delta = minimum[column]
                    column1 = column
            for column in range(column_count + 1):
                if used[column]:
                    u[p[column]] += delta
                    v[column] -= delta
                else:
                    minimum[column] -= delta
            column0 = column1
            if p[column0] == 0:
                break
        while True:
            column1 = way[column0]
            p[column0] = p[column1]
            column0 = column1
            if column0 == 0:
                break
    pairs = [(p[column] - 1, column - 1) for column in range(1, column_count + 1) if p[column]]
    return [(column, row) for row, column in pairs] if transposed else pairs


def _dimension_metrics(
    references: list[tuple[float, float, float]],
    predictions: list[tuple[float | None, float | None, float | None]],
    pairs: list[tuple[int, int, tuple[float | None, float | None, float | None]]],
    tolerances: tuple[float, float, float],
) -> dict[str, Any]:
    correct_cells = 0
    paired_known_cells = 0
    joint_correct = 0
    absolute_errors: list[list[float]] = [[], [], []]
    for reference_index, prediction_index, prediction in pairs:
        flags: list[bool] = []
        for axis in range(3):
            if prediction[axis] is None:
                continue
            error = abs(references[reference_index][axis] - prediction[axis])
            flags.append(error <= tolerances[axis])
            absolute_errors[axis].append(error)
        paired_known_cells += len(flags)
        correct_cells += sum(flags)
        joint_correct += int(len(flags) == 3 and all(flags))
    paired = len(pairs)
    predicted_numeric_cells = sum(
        value is not None for prediction in predictions for value in prediction
    )
    return {
        "predicted_occurrences": len(predictions),
        "paired_occurrences": paired,
        "joint_correct_occurrences": joint_correct,
        "paired_known_accuracy": _ratio(correct_cells, paired_known_cells),
        "joint_accuracy_on_paired": _ratio(joint_correct, paired),
        "reference_dimension_coverage": _ratio(correct_cells, 3 * len(references)),
        "joint_reference_coverage": _ratio(joint_correct, len(references)),
        "predicted_dimension_precision": _ratio(correct_cells, predicted_numeric_cells),
        "joint_prediction_precision": _ratio(joint_correct, len(predictions)),
        "mae_mm": {
            name: (sum(errors) / len(errors) if errors else None)
            for name, errors in zip(("length", "width", "thickness"), absolute_errors)
        },
        "tolerances_mm": {
            "length": tolerances[0], "width": tolerances[1], "thickness": tolerances[2]
        },
    }


def evaluate_case(
    case_id: str,
    reference: dict[str, Any],
    prediction: dict[str, Any],
    *,
    tolerances_mm: tuple[float, float, float] = DEFAULT_TOLERANCES_MM,
) -> dict[str, Any]:
    if len(tolerances_mm) != 3 or not all(
        isfinite(value) and value > 0 for value in tolerances_mm
    ):
        raise ValueError("tolerances_mm must contain three finite positive values")
    references = _reference_occurrences(reference)
    panel_predictions, supported_hardware, unsupported_auxiliary, unknown_quantity = _expand_prediction(prediction)
    matches = _optimal_tolerance_matching(references, panel_predictions, tolerances_mm)
    matched = len(matches)
    recall = _ratio(matched, len(references))
    precision = _ratio(matched, len(panel_predictions))
    dimensions = _dimension_metrics(references, panel_predictions, matches, tolerances_mm)
    run_completed = prediction.get("job_state") == "succeeded"
    delivery_eligible, delivery_blockers = _delivery_eligibility(prediction)
    passes = (
        delivery_eligible
        and recall >= 0.9
        and precision >= 0.9
        and dimensions["reference_dimension_coverage"] >= 0.9
        and dimensions["predicted_dimension_precision"] >= 0.9
        and unsupported_auxiliary == 0
        and unknown_quantity == 0
    )
    return {
        "case_id": case_id,
        "run_completed": run_completed,
        "job_state": prediction.get("job_state", "unknown"),
        "failure_code": prediction.get("failure_code"),
        "failure_reason_code": prediction.get("failure_reason_code"),
        "failure_phase": prediction.get("failure_phase"),
        "model_calls": prediction.get("model_calls"),
        "tool_calls": prediction.get("tool_calls"),
        "delivery_eligible": delivery_eligible,
        "delivery_blockers": delivery_blockers,
        "panel_occurrences": {
            "reference": len(references),
            "predicted": len(panel_predictions),
            "matched": matched,
            "false_positive": len(panel_predictions) - matched,
            "missed": len(references) - matched,
            "recall": recall,
            "precision": precision,
            "f1": _f1(precision, recall),
        },
        "supported_hardware_occurrences": supported_hardware,
        "unsupported_auxiliary_occurrences": unsupported_auxiliary,
        "unknown_quantity_components": unknown_quantity,
        "unknown_dimension_occurrences": sum(any(value is None for value in item) for item in panel_predictions),
        "dimensions": dimensions,
        "passes_90_percent_target": passes,
    }


def summarize_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = list(cases)
    reference = sum(case["panel_occurrences"]["reference"] for case in values)
    predicted = sum(case["panel_occurrences"]["predicted"] for case in values)
    matched = sum(case["panel_occurrences"]["matched"] for case in values)
    precision = _ratio(matched, predicted)
    recall = _ratio(matched, reference)
    completed = sum(case["run_completed"] for case in values)
    return {
        "case_count": len(values),
        "completed_cases": completed,
        "completion_rate": _ratio(completed, len(values)),
        "panel_occurrences": {
            "reference": reference,
            "predicted": predicted,
            "matched": matched,
            "recall": recall,
            "precision": precision,
            "f1": _f1(precision, recall),
        },
        "per_case_target_required": True,
        "all_cases_pass": bool(values) and all(case["passes_90_percent_target"] for case in values),
        "failed_case_ids": [case["case_id"] for case in values if not case["passes_90_percent_target"]],
        "incomplete_case_ids": [case["case_id"] for case in values if not case["run_completed"]],
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _validate_bundle_inputs(cases: list[dict[str, Any]], runtime_config: dict[str, Any]) -> None:
    case_ids = [str(item.get("case_id") or "") for item in cases]
    if not case_ids or any(not value for value in case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError("prediction bundle requires unique non-empty case ids")
    for item in cases:
        source_hash = item.get("public_dxf_sha256")
        if (
            item.get("split") not in {"development", "holdout"}
            or not isinstance(source_hash, str)
            or len(source_hash) != 64
            or any(character not in "0123456789abcdef" for character in source_hash.lower())
        ):
            raise ValueError("prediction bundle requires split and sha256 source custody")
    phase = runtime_config.get("evaluation_phase")
    if phase not in {"development", "holdout"}:
        raise ValueError("evaluation_phase must be development or holdout")
    if phase == "development" and (
        set(case_ids) != {"plank-030", "plank-016"}
        or any(item["split"] != "development" for item in cases)
    ):
        raise ValueError("development cohort must be exactly plank-030 and plank-016")
    if phase == "holdout" and (
        not cases or any(item["split"] != "holdout" for item in cases)
    ):
        raise ValueError("holdout cohort requires at least one sealed holdout case")
    evidence = runtime_config.get("config_evidence") or {}
    codex_interactive = (
        runtime_config.get("execution_transport") == "codex_agent_relay"
        and runtime_config.get("test_profile") == "interactive_codex_1800_v1"
        and runtime_config.get("api_key_loaded") is False
    )
    required_timeout = 1800 if codex_interactive else 600
    if evidence.get("job_timeout_s") != required_timeout or evidence.get("reviewer_model") != "gpt-6-astra":
        raise ValueError("evaluation requires config_evidence for the preregistered time budget and reviewer_model=gpt-6-astra")


def freeze_prediction_bundle(
    path: Path,
    *,
    cases: list[dict[str, Any]],
    runtime_config: dict[str, Any],
) -> dict[str, Any]:
    _validate_bundle_inputs(cases, runtime_config)
    payload = {
        "protocol_version": "complex-cutlist-blind-v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "runtime_config": runtime_config,
        "cases": cases,
    }
    payload["bundle_sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_frozen_prediction_bundle(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("bundle_sha256", None)
    observed = hashlib.sha256(_canonical_json(payload)).hexdigest()
    payload["bundle_sha256"] = expected
    if not isinstance(expected, str) or expected != observed:
        raise ValueError("prediction_bundle_sha256_mismatch")
    if payload.get("protocol_version") != "complex-cutlist-blind-v1":
        raise ValueError("prediction_bundle_protocol_mismatch")
    _validate_bundle_inputs(payload["cases"], payload["runtime_config"])
    return payload


def score_frozen_bundle(predictions_path: Path, references_path: Path) -> dict[str, Any]:
    """Score only after the prediction bundle has passed its custody hash.

    Keeping this operation separate from capture ensures the runtime command
    never accepts or opens a reference path.
    """
    bundle = load_frozen_prediction_bundle(predictions_path)
    references_bytes = references_path.read_bytes()
    raw_references = json.loads(references_bytes)
    references = raw_references.get("cases") if isinstance(raw_references, dict) else raw_references
    if not isinstance(references, list):
        raise ValueError("references must be a list or contain a cases list")
    by_id = {str(item.get("id") or item.get("case_id") or ""): item for item in references}
    prediction_ids = [item["case_id"] for item in bundle["cases"]]
    if set(prediction_ids) != set(by_id) or len(by_id) != len(references):
        raise ValueError("prediction_reference_case_set_mismatch")
    for item in bundle["cases"]:
        reference = by_id[item["case_id"]]
        if (
            item.get("public_dxf_sha256") != reference.get("public_dxf_sha256")
            or item.get("split") != reference.get("split")
        ):
            raise ValueError("prediction_reference_source_mismatch")
    reports = [
        evaluate_case(item["case_id"], by_id[item["case_id"]], item["prediction"])
        for item in bundle["cases"]
    ]
    return {
        "protocol_version": bundle["protocol_version"],
        "prediction_bundle_sha256": bundle["bundle_sha256"],
        "references_sha256": hashlib.sha256(references_bytes).hexdigest(),
        "runtime_config": bundle["runtime_config"],
        "cases": reports,
        "summary": summarize_cases(reports),
    }
