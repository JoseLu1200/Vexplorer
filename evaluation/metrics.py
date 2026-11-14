"""Offline evaluation metrics with a hard boundary around private references.

This module is intentionally independent from the application runtime.  It only
consumes already-frozen JSON artifacts and returns aggregate metrics; it never
serves cases, prompts, tools, or reference rows.
"""

from __future__ import annotations

import json
import math
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any


class EvaluationInputError(ValueError):
    """Raised when an evaluation artifact is malformed or cannot be paired."""


_DIMENSIONS = ("length", "width", "thickness")
_PREDICTION_STATES = {
    "observed", "derived", "hypothesis", "confirmed", "unknown", "conflict"
}
_REVIEW_STATUSES = {"unreviewed", "auto_reviewed", "human_reviewed"}


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationInputError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvaluationInputError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationInputError(f"{label} must be a non-empty string")
    return value


def _number(
    value: Any,
    label: str,
    *,
    allow_none: bool = True,
    strictly_positive: bool = False,
) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationInputError(f"{label} must be a number or null")
    result = float(value)
    if not math.isfinite(result):
        raise EvaluationInputError(f"{label} must be finite")
    if strictly_positive and result <= 0:
        raise EvaluationInputError(f"{label} must be greater than zero")
    if not strictly_positive and result < 0:
        raise EvaluationInputError(f"{label} cannot be negative")
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"cannot read {label}: {exc}") from exc
    return _object(payload, label), raw


def _components(
    case: dict[str, Any], label: str, *, require_dimension_states: bool
) -> dict[str, dict[str, Any]]:
    rows = _list(case.get("components"), f"{label}.components")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        row = _object(raw, f"{label}.components[{index}]")
        key = _text(row.get("key"), f"{label}.components[{index}].key")
        if key in result:
            raise EvaluationInputError(f"duplicate component key {key!r} in {label}")
        quantity = row.get("quantity")
        if quantity is not None and (
            isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1
        ):
            raise EvaluationInputError(
                f"{label}.components[{index}].quantity must be a positive integer or null"
            )
        quantity_state = None
        if require_dimension_states:
            quantity_state = row.get(
                "quantity_state", "unknown" if quantity is None else "hypothesis"
            )
            if quantity_state not in _PREDICTION_STATES:
                raise EvaluationInputError(
                    f"{label}.components[{index}].quantity_state is invalid"
                )
            if quantity is not None and quantity_state in {"unknown", "conflict"}:
                raise EvaluationInputError(
                    f"{label}.components[{index}] has numeric quantity with state {quantity_state}"
                )
            quantity_review_status = row.get("quantity_review_status", "unreviewed")
            if quantity_review_status not in _REVIEW_STATUSES:
                raise EvaluationInputError(
                    f"{label}.components[{index}].quantity_review_status is invalid"
                )
        else:
            quantity_review_status = None
        dimensions = _object(
            row.get("dimensions_mm"),
            f"{label}.components[{index}].dimensions_mm",
        )
        normalized_dimensions = {
            field: _number(
                dimensions.get(field),
                f"{label}.components[{index}].dimensions_mm.{field}",
                strictly_positive=True,
            )
            for field in _DIMENSIONS
        }
        states: dict[str, str] = {}
        if require_dimension_states:
            raw_states = _object(
                row.get("dimension_states"),
                f"{label}.components[{index}].dimension_states",
            )
            for field in _DIMENSIONS:
                state = raw_states.get(field)
                if state not in _PREDICTION_STATES:
                    raise EvaluationInputError(
                        f"{label}.components[{index}].dimension_states.{field} is invalid"
                    )
                if normalized_dimensions[field] is not None and state in {"unknown", "conflict"}:
                    raise EvaluationInputError(
                        f"{label}.components[{index}] has numeric {field} with state {state}"
                    )
                states[field] = state
            raw_review_statuses = _object(
                row.get(
                    "dimension_review_statuses",
                    {field: "unreviewed" for field in _DIMENSIONS},
                ),
                f"{label}.components[{index}].dimension_review_statuses",
            )
            review_statuses = {}
            for field in _DIMENSIONS:
                review_status = raw_review_statuses.get(field)
                if review_status not in _REVIEW_STATUSES:
                    raise EvaluationInputError(
                        f"{label}.components[{index}].dimension_review_statuses.{field} is invalid"
                    )
                review_statuses[field] = review_status
        else:
            review_statuses = {}
        result[key] = {
            "quantity": quantity,
            "quantity_state": quantity_state,
            "quantity_review_status": quantity_review_status,
            "dimensions_mm": normalized_dimensions,
            "dimension_states": states,
            "dimension_review_statuses": review_statuses,
        }
    return result


def _timing(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    item = _object(value, label)
    acceptable = item.get("acceptable")
    if not isinstance(acceptable, bool):
        raise EvaluationInputError(f"{label}.acceptable must be boolean")
    return {
        "duration_seconds": _number(
            item.get("duration_seconds"),
            f"{label}.duration_seconds",
            allow_none=False,
            strictly_positive=True,
        ),
        "acceptable": acceptable,
        "corrections_until_acceptable": _nonnegative_integer(
            item.get("corrections_until_acceptable"),
            f"{label}.corrections_until_acceptable",
        ),
    }

def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationInputError(f"{label} must be a non-negative integer")
    return value


def _economic(value: Any, label: str, *, cost: bool) -> dict[str, Any] | None:
    if value is None:
        return None
    item = _object(value, label)
    result = {
        "value": _number(item.get("value"), f"{label}.value", allow_none=False),
        "scope_id": _text(item.get("scope_id"), f"{label}.scope_id"),
    }
    if cost:
        currency = _text(item.get("currency"), f"{label}.currency")
        if re.fullmatch(r"[A-Z]{3}", currency) is None:
            raise EvaluationInputError(f"{label}.currency must be three uppercase letters")
        effective_date = _text(item.get("effective_date"), f"{label}.effective_date")
        try:
            date.fromisoformat(effective_date)
        except ValueError as exc:
            raise EvaluationInputError(f"{label}.effective_date must be an ISO date") from exc
        result.update(currency=currency, effective_date=effective_date)
    return result


def _scenario_keys(value: Any, label: str) -> list[str]:
    keys = [
        _text(_object(item, f"{label}[{index}]").get("key"), f"{label}[{index}].key")
        for index, item in enumerate(_list(value, label))
    ]
    if len(keys) != len(set(keys)):
        raise EvaluationInputError(f"{label} contains duplicate keys")
    return keys


def _prediction_scenarios(value: Any, label: str) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for index, item in enumerate(_list(value, label)):
        scenario = _object(item, f"{label}[{index}]")
        key = _text(scenario.get("key"), f"{label}[{index}].key")
        state = scenario.get("state", "hypothesis")
        if state not in _PREDICTION_STATES:
            raise EvaluationInputError(f"{label}[{index}].state is invalid")
        review_status = scenario.get("review_status", "unreviewed")
        if review_status not in _REVIEW_STATUSES:
            raise EvaluationInputError(f"{label}[{index}].review_status is invalid")
        if key in result:
            raise EvaluationInputError(f"{label} contains duplicate keys")
        result[key] = (state, review_status)
    return result


def _case_map(payload: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(payload.get("cases"), f"{label}.cases")):
        case = _object(raw, f"{label}.cases[{index}]")
        case_id = _text(case.get("id"), f"{label}.cases[{index}].id")
        if case_id in result:
            raise EvaluationInputError(f"duplicate case id {case_id!r} in {label}")
        result[case_id] = case
    return result


def _validate_string_ids(value: Any, label: str) -> list[str]:
    values = [_text(item, f"{label}[]") for item in _list(value, label)]
    if len(values) != len(set(values)):
        raise EvaluationInputError(f"{label} contains duplicate ids")
    return values


def evaluate_files(
    predictions_path: str | Path,
    references_path: str | Path,
    *,
    tolerance_mm: float = 1.0,
    retrieval_k: int = 5,
) -> dict[str, Any]:
    """Evaluate frozen predictions against evaluator-only references.

    The returned object contains aggregate values only.  Neither input paths nor
    component rows are copied into it.
    """

    if isinstance(tolerance_mm, bool) or not isinstance(tolerance_mm, (int, float)):
        raise EvaluationInputError("tolerance_mm must be a non-negative number")
    tolerance_mm = float(tolerance_mm)
    if not math.isfinite(tolerance_mm) or tolerance_mm < 0:
        raise EvaluationInputError("tolerance_mm must be a non-negative finite number")
    if isinstance(retrieval_k, bool) or not isinstance(retrieval_k, int) or retrieval_k < 1:
        raise EvaluationInputError("retrieval_k must be a positive integer")

    predictions, prediction_bytes = _read_json(Path(predictions_path), "predictions")
    references, _ = _read_json(Path(references_path), "references")
    if predictions.get("schema_version") != "1.0" or references.get("schema_version") != "1.0":
        raise EvaluationInputError("schema_version must be '1.0'")

    dataset = _object(references.get("dataset"), "references.dataset")
    dataset_id = _text(dataset.get("id"), "references.dataset.id")
    expected_prediction_hash = _text(
        dataset.get("predictions_sha256"), "references.dataset.predictions_sha256"
    )
    if re.fullmatch(r"[0-9a-f]{64}", expected_prediction_hash) is None:
        raise EvaluationInputError(
            "references.dataset.predictions_sha256 must be lowercase 64-hex"
        )
    if hashlib.sha256(prediction_bytes).hexdigest() != expected_prediction_hash:
        raise EvaluationInputError("predictions_sha256 mismatch")
    if predictions.get("dataset_id") != dataset_id:
        raise EvaluationInputError("dataset_id mismatch between predictions and references")
    evidence_kind = dataset.get("evidence_kind")
    if evidence_kind not in {
        "developer_fixture",
        "development_diagnostic",
        "independent_review",
        "observed_technician_study",
    }:
        raise EvaluationInputError("unsupported references.dataset.evidence_kind")
    frozen = dataset.get("frozen_before_evaluation")
    if not isinstance(frozen, bool):
        raise EvaluationInputError(
            "references.dataset.frozen_before_evaluation must be boolean"
        )
    if not frozen:
        raise EvaluationInputError(
            "predictions must be frozen before private references are opened"
        )
    partition_policy = dataset.get("partition_policy")
    if partition_policy != "project_and_family":
        raise EvaluationInputError(
            "references.dataset.partition_policy must be 'project_and_family'"
        )
    component_matching = dataset.get("component_matching")
    if component_matching != "reference_alignment":
        raise EvaluationInputError(
            "references.dataset.component_matching must be 'reference_alignment'"
        )
    cost_currency = _text(dataset.get("cost_currency"), "references.dataset.cost_currency")
    if re.fullmatch(r"[A-Z]{3}", cost_currency) is None:
        raise EvaluationInputError("references.dataset.cost_currency must be three uppercase letters")
    cost_scope_id = _text(dataset.get("cost_scope_id"), "references.dataset.cost_scope_id")
    cost_effective_date = _text(
        dataset.get("cost_effective_date"), "references.dataset.cost_effective_date"
    )
    try:
        date.fromisoformat(cost_effective_date)
    except ValueError as exc:
        raise EvaluationInputError("references.dataset.cost_effective_date must be an ISO date") from exc
    hours_scope_id = _text(dataset.get("hours_scope_id"), "references.dataset.hours_scope_id")
    retrieval_items_raw = _object(
        dataset.get("retrieval_items"), "references.dataset.retrieval_items"
    )
    retrieval_items: dict[str, dict[str, str]] = {}
    for item_id, raw in retrieval_items_raw.items():
        item_id = _text(item_id, "references.dataset.retrieval_items key")
        item = _object(raw, f"references.dataset.retrieval_items.{item_id}")
        retrieval_items[item_id] = {
            field: _text(
                item.get(field), f"references.dataset.retrieval_items.{item_id}.{field}"
            )
            for field in ("project_id", "family_id", "duplicate_group_id")
        }

    reference_cases = _case_map(references, "references")
    prediction_cases = _case_map(predictions, "predictions")
    if set(reference_cases) != set(prediction_cases):
        missing = sorted(set(reference_cases) - set(prediction_cases))
        extra = sorted(set(prediction_cases) - set(reference_cases))
        raise EvaluationInputError(f"case ids mismatch; missing={missing}, extra={extra}")

    case_partitions: dict[str, dict[str, str]] = {}
    project_splits: dict[str, set[str]] = {}
    family_splits: dict[str, set[str]] = {}
    for case_id, case in reference_cases.items():
        metadata = {
            field: _text(case.get(field), f"references.{case_id}.{field}")
            for field in ("split", "project_id", "family_id", "duplicate_group_id")
        }
        case_partitions[case_id] = metadata
        project_splits.setdefault(metadata["project_id"], set()).add(metadata["split"])
        family_splits.setdefault(metadata["family_id"], set()).add(metadata["split"])
    for project_id, splits in project_splits.items():
        if len(splits) > 1:
            raise EvaluationInputError(
                f"project_id {project_id!r} crosses splits: {sorted(splits)}"
            )
    for family_id, splits in family_splits.items():
        if len(splits) > 1:
            raise EvaluationInputError(
                f"family_id {family_id!r} crosses splits: {sorted(splits)}"
            )

    type_reference = type_predicted = type_true_positive = 0
    quantity_reference = quantity_predicted = quantity_true_positive = 0
    quantity_eligible_components = quantity_compared_components = 0
    quantity_by_state: dict[str, dict[str, int]] = {}
    quantity_by_review: dict[str, dict[str, int]] = {}
    unmatched_predicted_components = 0
    dimension_eligible = dimension_compared = dimension_within = 0
    dimension_errors: list[float] = []
    dimension_by_state: dict[str, dict[str, Any]] = {}
    dimension_by_review: dict[str, dict[str, Any]] = {}
    retrieval_eligible = retrieval_evaluated = 0
    retrieval_precisions: list[float] = []
    retrieval_recalls: list[float] = []
    retrieval_leakage_candidates = 0
    retrieval_leakage_cases = 0
    numeric: dict[str, dict[str, Any]] = {
        "cost_eur": {"eligible": 0, "evaluated": 0, "errors": [], "relative": []},
        "hours": {"eligible": 0, "evaluated": 0, "errors": [], "relative": []},
    }
    timing_eligible = 0
    paired_timings: list[tuple[float, float]] = []
    paired_corrections: list[tuple[int, int]] = []
    scenario_eligible = scenario_matched = scenario_predicted = scenario_unsupported = 0
    scenario_eligible_cases = scenario_evaluated_cases = 0
    scenario_by_state: dict[str, dict[str, int]] = {}
    scenario_by_review: dict[str, dict[str, int]] = {}

    for case_id in sorted(reference_cases):
        reference = reference_cases[case_id]
        prediction = prediction_cases[case_id]
        reference_components = _components(
            reference, f"references.{case_id}", require_dimension_states=False
        )
        prediction_components = _components(
            prediction, f"predictions.{case_id}", require_dimension_states=True
        )

        reference_keys = set(reference_components)
        prediction_keys = set(prediction_components)
        matches_raw = _list(
            reference.get("component_matches"),
            f"references.{case_id}.component_matches",
        )
        matched_pairs: list[tuple[str, str]] = []
        used_prediction_keys: set[str] = set()
        used_reference_keys: set[str] = set()
        for index, raw in enumerate(matches_raw):
            match = _object(raw, f"references.{case_id}.component_matches[{index}]")
            prediction_key = _text(
                match.get("prediction_key"),
                f"references.{case_id}.component_matches[{index}].prediction_key",
            )
            reference_key = _text(
                match.get("reference_key"),
                f"references.{case_id}.component_matches[{index}].reference_key",
            )
            if prediction_key not in prediction_components:
                raise EvaluationInputError(
                    f"component match references unknown prediction key {prediction_key!r} in {case_id}"
                )
            if reference_key not in reference_components:
                raise EvaluationInputError(
                    f"component match references unknown reference key {reference_key!r} in {case_id}"
                )
            if prediction_key in used_prediction_keys or reference_key in used_reference_keys:
                raise EvaluationInputError(
                    f"component_matches must be one-to-one in {case_id}"
                )
            used_prediction_keys.add(prediction_key)
            used_reference_keys.add(reference_key)
            matched_pairs.append((prediction_key, reference_key))
        type_reference += len(reference_keys)
        type_predicted += len(prediction_keys)
        type_true_positive += len(matched_pairs)
        unmatched_predicted_components += len(prediction_keys - used_prediction_keys)
        quantity_reference += sum(
            item["quantity"]
            for item in reference_components.values()
            if item["quantity"] is not None
        )
        quantity_predicted += sum(
            item["quantity"]
            for item in prediction_components.values()
            if item["quantity"] is not None
        )
        for item in prediction_components.values():
            if item["quantity"] is None:
                continue
            state_metrics = quantity_by_state.setdefault(
                item["quantity_state"], {"compared": 0, "predicted": 0, "true_positive": 0}
            )
            state_metrics["predicted"] += item["quantity"]
            review_metrics = quantity_by_review.setdefault(
                item["quantity_review_status"],
                {"compared": 0, "predicted": 0, "true_positive": 0},
            )
            review_metrics["predicted"] += item["quantity"]
        quantity_eligible_components += sum(
            item["quantity"] is not None for item in reference_components.values()
        )
        for prediction_key, reference_key in matched_pairs:
            reference_quantity = reference_components[reference_key]["quantity"]
            predicted_quantity = prediction_components[prediction_key]["quantity"]
            if reference_quantity is None or predicted_quantity is None:
                continue
            quantity_compared_components += 1
            true_positive_quantity = min(reference_quantity, predicted_quantity)
            quantity_true_positive += true_positive_quantity
            state_metrics = quantity_by_state[prediction_components[prediction_key]["quantity_state"]]
            state_metrics["compared"] += 1
            state_metrics["true_positive"] += true_positive_quantity
            review_metrics = quantity_by_review[
                prediction_components[prediction_key]["quantity_review_status"]
            ]
            review_metrics["compared"] += 1
            review_metrics["true_positive"] += true_positive_quantity

        prediction_by_reference = {
            reference_key: prediction_components[prediction_key]
            for prediction_key, reference_key in matched_pairs
        }
        for key, component in reference_components.items():
            for field in _DIMENSIONS:
                reference_value = component["dimensions_mm"][field]
                if reference_value is None:
                    continue
                dimension_eligible += 1
                predicted = prediction_by_reference.get(key)
                if predicted is None:
                    continue
                predicted_value = predicted["dimensions_mm"][field]
                if predicted_value is None:
                    continue
                dimension_compared += 1
                error = abs(predicted_value - reference_value)
                dimension_errors.append(error)
                state = predicted["dimension_states"][field]
                state_metrics = dimension_by_state.setdefault(
                    state, {"count": 0, "errors": [], "within": 0}
                )
                state_metrics["count"] += 1
                state_metrics["errors"].append(error)
                review_status = predicted["dimension_review_statuses"][field]
                review_metrics = dimension_by_review.setdefault(
                    review_status, {"count": 0, "errors": [], "within": 0}
                )
                review_metrics["count"] += 1
                review_metrics["errors"].append(error)
                if error <= tolerance_mm:
                    dimension_within += 1
                    state_metrics["within"] += 1
                    review_metrics["within"] += 1

        relevant = _validate_string_ids(
            reference.get("relevant_item_ids"), f"references.{case_id}.relevant_item_ids"
        )
        unknown_relevant = sorted(set(relevant) - set(retrieval_items))
        if unknown_relevant:
            raise EvaluationInputError(
                f"relevant ids missing private metadata in {case_id}: {unknown_relevant}"
            )
        retrieved_raw = prediction.get("retrieved_item_ids")
        retrieved: list[str] | None = None
        if retrieved_raw is not None:
            retrieved = _validate_string_ids(
                retrieved_raw, f"predictions.{case_id}.retrieved_item_ids"
            )
            unknown_items = sorted(
                (set(relevant) | set(retrieved)) - set(retrieval_items)
            )
            if unknown_items:
                raise EvaluationInputError(
                    f"retrieval ids missing private metadata in {case_id}: {unknown_items}"
                )
            case_metadata = case_partitions[case_id]
            clean_retrieved: list[str] = []
            leaked = 0
            for item_id in retrieved:
                item_metadata = retrieval_items[item_id]
                if any(
                    item_metadata[field] == case_metadata[field]
                    for field in ("project_id", "family_id", "duplicate_group_id")
                ):
                    leaked += 1
                else:
                    clean_retrieved.append(item_id)
            retrieval_leakage_candidates += leaked
            if leaked:
                retrieval_leakage_cases += 1
            retrieved = clean_retrieved
        if relevant:
            retrieval_eligible += 1
            if retrieved is not None:
                retrieval_evaluated += 1
                top = retrieved[:retrieval_k]
                hits = len(set(top) & set(relevant))
                retrieval_precisions.append(hits / retrieval_k)
                retrieval_recalls.append(hits / len(relevant))

        for field in ("cost_eur", "hours"):
            source_field = "cost" if field == "cost_eur" else "hours"
            reference_item = _economic(
                reference.get(source_field),
                f"references.{case_id}.{source_field}",
                cost=field == "cost_eur",
            )
            predicted_item = _economic(
                prediction.get(source_field),
                f"predictions.{case_id}.{source_field}",
                cost=field == "cost_eur",
            )
            if reference_item is None:
                continue
            expected_metadata = (
                {
                    "currency": cost_currency,
                    "scope_id": cost_scope_id,
                    "effective_date": cost_effective_date,
                }
                if field == "cost_eur"
                else {"scope_id": hours_scope_id}
            )
            if any(reference_item[name] != value for name, value in expected_metadata.items()):
                raise EvaluationInputError(
                    f"reference {'cost' if field == 'cost_eur' else 'hours'} metadata differs from dataset declaration in {case_id}"
                )
            metric = numeric[field]
            metric["eligible"] += 1
            if predicted_item is None:
                continue
            metadata_fields = ("currency", "scope_id", "effective_date") if field == "cost_eur" else ("scope_id",)
            mismatch = next(
                (name for name in metadata_fields if predicted_item[name] != reference_item[name]),
                None,
            )
            if mismatch is not None:
                metric.setdefault("incompatible", []).append(mismatch)
                continue
            metric["evaluated"] += 1
            reference_value = reference_item["value"]
            predicted_value = predicted_item["value"]
            error = abs(predicted_value - reference_value)
            metric["errors"].append(error)
            if reference_value != 0:
                metric["relative"].append(error / abs(reference_value))

        baseline = _timing(
            reference.get("technician_baseline"),
            f"references.{case_id}.technician_baseline",
        )
        assisted = _timing(prediction.get("assisted"), f"predictions.{case_id}.assisted")
        if baseline is not None:
            timing_eligible += 1
            if assisted is not None and baseline["acceptable"] and assisted["acceptable"]:
                paired_timings.append(
                    (baseline["duration_seconds"], assisted["duration_seconds"])
                )
                paired_corrections.append(
                    (
                        baseline["corrections_until_acceptable"],
                        assisted["corrections_until_acceptable"],
                    )
                )

        acceptable_scenarios = _scenario_keys(
            reference.get("acceptable_scenarios"),
            f"references.{case_id}.acceptable_scenarios",
        )
        predicted_scenarios = _prediction_scenarios(
            prediction.get("scenarios"), f"predictions.{case_id}.scenarios"
        )
        scenario_matches = _list(
            reference.get("scenario_matches"), f"references.{case_id}.scenario_matches"
        )
        matched_prediction_scenarios: set[str] = set()
        matched_reference_scenarios: set[str] = set()
        for index, raw in enumerate(scenario_matches):
            match = _object(raw, f"references.{case_id}.scenario_matches[{index}]")
            prediction_key = _text(match.get("prediction_key"), "scenario prediction_key")
            reference_key = _text(match.get("reference_key"), "scenario reference_key")
            if prediction_key not in predicted_scenarios or reference_key not in acceptable_scenarios:
                raise EvaluationInputError(f"scenario match outside case in {case_id}")
            if prediction_key in matched_prediction_scenarios or reference_key in matched_reference_scenarios:
                raise EvaluationInputError(f"scenario_matches must be one-to-one in {case_id}")
            matched_prediction_scenarios.add(prediction_key)
            matched_reference_scenarios.add(reference_key)
        scenario_eligible += len(acceptable_scenarios)
        scenario_matched += len(matched_reference_scenarios)
        scenario_predicted += len(predicted_scenarios)
        scenario_unsupported += len(set(predicted_scenarios) - matched_prediction_scenarios)
        for prediction_key, (state, review_status) in predicted_scenarios.items():
            state_metrics = scenario_by_state.setdefault(
                state, {"predicted": 0, "matched": 0, "unsupported": 0}
            )
            state_metrics["predicted"] += 1
            if prediction_key in matched_prediction_scenarios:
                state_metrics["matched"] += 1
            else:
                state_metrics["unsupported"] += 1
            review_metrics = scenario_by_review.setdefault(
                review_status, {"predicted": 0, "matched": 0, "unsupported": 0}
            )
            review_metrics["predicted"] += 1
            if prediction_key in matched_prediction_scenarios:
                review_metrics["matched"] += 1
            else:
                review_metrics["unsupported"] += 1
        if acceptable_scenarios:
            scenario_eligible_cases += 1
            scenario_evaluated_cases += 1

    type_precision = _ratio(type_true_positive, type_predicted)
    type_recall = _ratio(type_true_positive, type_reference)
    quantity_precision = _ratio(quantity_true_positive, quantity_predicted)
    quantity_recall = _ratio(quantity_true_positive, quantity_reference)

    def numeric_report(field: str) -> dict[str, Any]:
        metric = numeric[field]
        errors = metric["errors"]
        relative = metric["relative"]
        incompatible = metric.get("incompatible", [])
        incompatibility_reasons = {
            reason: incompatible.count(reason) for reason in sorted(set(incompatible))
        }
        report = {
            "eligible_cases": metric["eligible"],
            "evaluated_cases": metric["evaluated"],
            "coverage": _ratio(metric["evaluated"], metric["eligible"]),
            "mae": sum(errors) / len(errors) if errors else None,
            "relative_error_cases": len(relative),
            "mape": sum(relative) / len(relative) if relative else None,
            "metadata_incompatible_cases": len(incompatible),
            "metadata_incompatibility_reasons": incompatibility_reasons,
        }
        if field == "cost_eur":
            report.update(
                currency=cost_currency,
                scope_id=cost_scope_id,
                effective_date=cost_effective_date,
            )
        else:
            report.update(scope_id=hours_scope_id)
        return report

    baseline_values = [baseline for baseline, _ in paired_timings]
    assisted_values = [assisted for _, assisted in paired_timings]
    differences = [baseline - assisted for baseline, assisted in paired_timings]
    baseline_corrections = [baseline for baseline, _ in paired_corrections]
    assisted_corrections = [assisted for _, assisted in paired_corrections]
    correction_differences = [baseline - assisted for baseline, assisted in paired_corrections]
    if evidence_kind == "developer_fixture":
        claim_status = "developer_fixture_not_empirical"
    elif not paired_timings:
        claim_status = "no_paired_acceptable_observations"
    else:
        claim_status = "descriptive_observation_not_causal"

    return {
        "schema_version": "1.0",
        "dataset": {
            "id": dataset_id,
            "evidence_kind": evidence_kind,
            "case_count": len(reference_cases),
            "frozen_before_evaluation": frozen,
            "partition_policy": partition_policy,
            "component_matching": component_matching,
            "prediction_fingerprint_verified": True,
        },
        "bom": {
            "component_types": {
                "true_positive": type_true_positive,
                "predicted": type_predicted,
                "reference": type_reference,
                "precision": type_precision,
                "recall": type_recall,
                "f1": _f1(type_precision, type_recall),
            },
            "quantity_weighted": {
                "true_positive": quantity_true_positive,
                "predicted": quantity_predicted,
                "reference": quantity_reference,
                "precision": quantity_precision,
                "recall": quantity_recall,
                "f1": _f1(quantity_precision, quantity_recall),
                "eligible_components": quantity_eligible_components,
                "compared_components": quantity_compared_components,
                "coverage": _ratio(
                    quantity_compared_components, quantity_eligible_components
                ),
                "by_prediction_state": {
                    state: {
                        "compared_components": values["compared"],
                        "predicted_occurrences": values["predicted"],
                        "true_positive_occurrences": values["true_positive"],
                        "reference_occurrence_recall": _ratio(
                            values["true_positive"], quantity_reference
                        ),
                    }
                    for state, values in sorted(quantity_by_state.items())
                },
                "by_review_status": {
                    status: {
                        "compared_components": values["compared"],
                        "predicted_occurrences": values["predicted"],
                        "true_positive_occurrences": values["true_positive"],
                        "reference_occurrence_recall": _ratio(
                            values["true_positive"], quantity_reference
                        ),
                    }
                    for status, values in sorted(quantity_by_review.items())
                },
            },
        },
        "dimensions": {
            "tolerance_mm": tolerance_mm,
            "eligible_fields": dimension_eligible,
            "compared_fields": dimension_compared,
            "coverage": _ratio(dimension_compared, dimension_eligible),
            "mae_mm": (
                sum(dimension_errors) / len(dimension_errors)
                if dimension_errors
                else None
            ),
            "within_tolerance": dimension_within,
            "within_tolerance_rate": _ratio(dimension_within, dimension_compared),
            "by_prediction_state": {
                state: {
                    "compared_fields": values["count"],
                    "coverage": _ratio(values["count"], dimension_eligible),
                    "mae_mm": sum(values["errors"]) / len(values["errors"]),
                    "within_tolerance": values["within"],
                    "within_tolerance_rate": _ratio(values["within"], values["count"]),
                }
                for state, values in sorted(dimension_by_state.items())
            },
            "by_review_status": {
                status: {
                    "compared_fields": values["count"],
                    "coverage": _ratio(values["count"], dimension_eligible),
                    "mae_mm": sum(values["errors"]) / len(values["errors"]),
                    "within_tolerance": values["within"],
                    "within_tolerance_rate": _ratio(values["within"], values["count"]),
                }
                for status, values in sorted(dimension_by_review.items())
            },
        },
        "component_hypotheses": {
            "predicted_components": type_predicted,
            "unmatched_predicted_components": unmatched_predicted_components,
            "unsupported_rate": _ratio(unmatched_predicted_components, type_predicted),
            "human_corrected_fields": None,
        },
        "ambiguity": {
            "eligible_acceptable_scenarios": scenario_eligible,
            "matched_acceptable_scenarios": scenario_matched,
            "preservation_recall": _ratio(scenario_matched, scenario_eligible),
            "predicted_scenarios": scenario_predicted,
            "unsupported_predicted_scenarios": scenario_unsupported,
            "eligible_cases": scenario_eligible_cases,
            "evaluated_cases": scenario_evaluated_cases,
            "coverage": _ratio(scenario_evaluated_cases, scenario_eligible_cases),
            "by_prediction_state": {
                state: {
                    "predicted_scenarios": values["predicted"],
                    "matched_acceptable_scenarios": values["matched"],
                    "unsupported_predicted_scenarios": values["unsupported"],
                }
                for state, values in sorted(scenario_by_state.items())
            },
            "by_review_status": {
                status: {
                    "predicted_scenarios": values["predicted"],
                    "matched_acceptable_scenarios": values["matched"],
                    "unsupported_predicted_scenarios": values["unsupported"],
                }
                for status, values in sorted(scenario_by_review.items())
            },
        },
        "retrieval": {
            "k": retrieval_k,
            "eligible_cases": retrieval_eligible,
            "evaluated_cases": retrieval_evaluated,
            "coverage": _ratio(retrieval_evaluated, retrieval_eligible),
            "macro_precision_at_k": (
                sum(retrieval_precisions) / len(retrieval_precisions)
                if retrieval_precisions
                else None
            ),
            "macro_recall_at_k": (
                sum(retrieval_recalls) / len(retrieval_recalls)
                if retrieval_recalls
                else None
            ),
            "leakage_candidates": retrieval_leakage_candidates,
            "cases_with_leakage": retrieval_leakage_cases,
        },
        "cost_eur": numeric_report("cost_eur"),
        "hours": numeric_report("hours"),
        "timing": {
            "eligible_cases": timing_eligible,
            "paired_acceptable_cases": len(paired_timings),
            "coverage": _ratio(len(paired_timings), timing_eligible),
            "mean_baseline_seconds": (
                sum(baseline_values) / len(baseline_values) if baseline_values else None
            ),
            "mean_assisted_seconds": (
                sum(assisted_values) / len(assisted_values) if assisted_values else None
            ),
            "mean_observed_difference_seconds": (
                sum(differences) / len(differences) if differences else None
            ),
            "mean_baseline_corrections": (
                sum(baseline_corrections) / len(baseline_corrections)
                if baseline_corrections
                else None
            ),
            "mean_assisted_corrections": (
                sum(assisted_corrections) / len(assisted_corrections)
                if assisted_corrections
                else None
            ),
            "mean_observed_correction_difference": (
                sum(correction_differences) / len(correction_differences)
                if correction_differences
                else None
            ),
            "savings_claim_supported": False,
            "claim_status": claim_status,
        },
        "limitations": [
            "Aggregate metrics do not make a developer fixture an independent benchmark.",
            "Observed paired time differences are descriptive and are not a causal savings claim.",
            "Missing predictions reduce coverage and are not imputed as zero error.",
        ],
    }

