"""Strict offline scoring for furniture semantics.

The runtime never imports this module. Predictions are frozen from public-only
outputs before the evaluator opens the private reference file.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "semantic-evaluation/v1"
_HEX64 = re.compile(r"[0-9a-f]{64}")


class SemanticEvaluationError(ValueError):
    """A frozen prediction or private semantic reference is invalid."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SemanticEvaluationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SemanticEvaluationError(f"{label} must be an array")
    return value


def _strict(row: dict[str, Any], allowed: set[str], label: str) -> None:
    unexpected = sorted(set(row) - allowed)
    if unexpected:
        raise SemanticEvaluationError(
            f"{label} has unexpected fields: {', '.join(unexpected)}"
        )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticEvaluationError(f"{label} must be a non-empty string")
    return value.strip()


def _hash(value: Any, label: str) -> str:
    result = _text(value, label)
    if _HEX64.fullmatch(result) is None:
        raise SemanticEvaluationError(f"{label} must be lowercase 64-hex")
    return result


def _quantity(value: Any, label: str, *, nullable: bool) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        suffix = " or null" if nullable else ""
        raise SemanticEvaluationError(f"{label} must be a positive integer{suffix}")
    return value


def _normalized(value: Any, label: str) -> str:
    text = _text(value, label)
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    result = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not result:
        raise SemanticEvaluationError(f"{label} has no normalizable content")
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _metric(tp: int, fp: int, fn: int) -> dict[str, Any]:
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }


def _component_rows(value: Any, label: str, *, reference: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allowed = {"label", "role", "quantity", "required", "aliases"} if reference else {
        "label", "role", "quantity", "confidence"
    }
    for index, raw in enumerate(_array(value, label)):
        item_label = f"{label}[{index}]"
        row = _object(raw, item_label)
        _strict(row, allowed, item_label)
        role = _normalized(row.get("role"), f"{item_label}.role")
        quantity = _quantity(row.get("quantity"), f"{item_label}.quantity", nullable=not reference)
        normalized: dict[str, Any] = {
            "role": role,
            "label": _text(row.get("label", role), f"{item_label}.label"),
            "quantity": quantity,
        }
        if reference:
            required = row.get("required", True)
            if not isinstance(required, bool):
                raise SemanticEvaluationError(f"{item_label}.required must be boolean")
            normalized["required"] = required
            aliases = row.get("aliases", [])
            normalized["aliases"] = [
                _normalized(alias, f"{item_label}.aliases[]")
                for alias in _array(aliases, f"{item_label}.aliases")
            ]
        elif "confidence" in row:
            confidence = row["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
                raise SemanticEvaluationError(f"{item_label}.confidence must be between 0 and 1")
        rows.append(normalized)
    return rows


def _relation_rows(value: Any, label: str, *, reference: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allowed = {"subject_role", "relation", "object_role", "required"} if reference else {
        "subject_role", "relation", "object_role"
    }
    for index, raw in enumerate(_array(value, label)):
        item_label = f"{label}[{index}]"
        row = _object(raw, item_label)
        _strict(row, allowed, item_label)
        normalized = {
            "subject_role": _normalized(row.get("subject_role"), f"{item_label}.subject_role"),
            "relation": _normalized(row.get("relation"), f"{item_label}.relation"),
            "object_role": _normalized(row.get("object_role"), f"{item_label}.object_role"),
        }
        if reference:
            required = row.get("required", True)
            if not isinstance(required, bool):
                raise SemanticEvaluationError(f"{item_label}.required must be boolean")
            normalized["required"] = required
        rows.append(normalized)
    if len({(r["subject_role"], r["relation"], r["object_role"]) for r in rows}) != len(rows):
        raise SemanticEvaluationError(f"{label} contains duplicate relations")
    return rows


def _ambiguity_rows(value: Any, label: str) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(_array(value, label)):
        item_label = f"{label}[{index}]"
        row = _object(raw, item_label)
        _strict(row, {"scope", "reason", "acceptable_values"}, item_label)
        scope = _text(row.get("scope"), f"{item_label}.scope")
        reason = _text(row.get("reason"), f"{item_label}.reason")
        values = _array(row.get("acceptable_values"), f"{item_label}.acceptable_values")
        if not values:
            raise SemanticEvaluationError(f"{item_label}.acceptable_values cannot be empty")
        rows.append({"scope": scope, "reason": reason, "acceptable_values": values})
    return rows


def _prediction(value: Any, label: str) -> dict[str, Any]:
    row = _object(value, label)
    _strict(row, {"components", "assembly_relations", "assembly_alternatives", "alternative_id", "unknowns"}, label)
    unknowns = []
    for index, raw in enumerate(_array(row.get("unknowns"), f"{label}.unknowns")):
        item_label = f"{label}.unknowns[{index}]"
        item = _object(raw, item_label)
        _strict(item, {"scope", "reason"}, item_label)
        unknowns.append(
            {
                "scope": _text(item.get("scope"), f"{item_label}.scope"),
                "reason": _text(item.get("reason"), f"{item_label}.reason"),
            }
        )
    alternative_id = row.get("alternative_id")
    alternatives = []
    alternative_ids: set[str] = set()
    for index, raw in enumerate(_array(row.get("assembly_alternatives", []), f"{label}.assembly_alternatives")):
        item_label = f"{label}.assembly_alternatives[{index}]"
        item = _object(raw, item_label)
        _strict(item, {"alternative_id", "assembly_relations"}, item_label)
        item_id = _text(item.get("alternative_id"), f"{item_label}.alternative_id")
        if item_id in alternative_ids:
            raise SemanticEvaluationError(f"{label}.assembly_alternatives contains duplicate ids")
        alternative_ids.add(item_id)
        alternatives.append(
            {
                "alternative_id": item_id,
                "assembly_relations": _relation_rows(
                    item.get("assembly_relations"),
                    f"{item_label}.assembly_relations",
                    reference=False,
                ),
            }
        )
    return {
        "components": _component_rows(row.get("components"), f"{label}.components", reference=False),
        "assembly_relations": _relation_rows(row.get("assembly_relations"), f"{label}.assembly_relations", reference=False),
        "alternative_id": None if alternative_id is None else _text(alternative_id, f"{label}.alternative_id"),
        "assembly_alternatives": alternatives,
        "unknowns": unknowns,
    }


def _reference(value: Any, label: str) -> dict[str, Any]:
    row = _object(value, label)
    _strict(row, {"certification", "components", "assembly_relations", "valid_alternatives", "ambiguity"}, label)
    certification = _text(row.get("certification"), f"{label}.certification")
    if certification not in {"design_known_synthetic", "technician_reviewed", "observed_technician_study"}:
        raise SemanticEvaluationError(f"{label}.certification is unsupported")
    components = _component_rows(row.get("components"), f"{label}.components", reference=True)
    if len({item["role"] for item in components}) != len(components):
        raise SemanticEvaluationError(f"{label}.components contains duplicate roles; aggregate physical occurrences with quantity")
    alternatives = []
    alternative_ids: set[str] = set()
    for index, raw in enumerate(_array(row.get("valid_alternatives"), f"{label}.valid_alternatives")):
        item_label = f"{label}.valid_alternatives[{index}]"
        item = _object(raw, item_label)
        _strict(item, {"id", "components", "assembly_relations"}, item_label)
        alternative_id = _text(item.get("id"), f"{item_label}.id")
        if alternative_id in alternative_ids:
            raise SemanticEvaluationError(f"{label}.valid_alternatives contains duplicate ids")
        alternative_ids.add(alternative_id)
        alt_components = _component_rows(item.get("components", row.get("components")), f"{item_label}.components", reference=True)
        if len({component["role"] for component in alt_components}) != len(alt_components):
            raise SemanticEvaluationError(f"{item_label}.components contains duplicate roles")
        alternatives.append(
            {
                "id": alternative_id,
                "components": alt_components,
                "assembly_relations": _relation_rows(item.get("assembly_relations", row.get("assembly_relations")), f"{item_label}.assembly_relations", reference=True),
            }
        )
    return {
        "certification": certification,
        "components": components,
        "assembly_relations": _relation_rows(row.get("assembly_relations"), f"{label}.assembly_relations", reference=True),
        "valid_alternatives": alternatives,
        "ambiguity": _ambiguity_rows(row.get("ambiguity"), f"{label}.ambiguity"),
    }


def _aliases(components: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for component in components:
        for alias in [component["role"], *component.get("aliases", [])]:
            if alias in aliases and aliases[alias] != component["role"]:
                raise SemanticEvaluationError(f"component alias {alias!r} is ambiguous")
            aliases[alias] = component["role"]
    return aliases


def _aggregate_predictions(rows: list[dict[str, Any]], aliases: dict[str, str]) -> dict[str, int | None]:
    grouped: dict[str, int | None] = {}
    for row in rows:
        role = aliases.get(row["role"], row["role"])
        quantity = row["quantity"]
        if role not in grouped:
            grouped[role] = quantity
        elif grouped[role] is None or quantity is None:
            grouped[role] = None
        else:
            grouped[role] = int(grouped[role]) + quantity
    return grouped


def _relation_key(row: dict[str, Any], aliases: dict[str, str]) -> tuple[str, str, str]:
    return (
        aliases.get(row["subject_role"], row["subject_role"]),
        row["relation"],
        aliases.get(row["object_role"], row["object_role"]),
    )


def _quantity_options(reference: dict[str, Any], role: str, default: int) -> list[int]:
    scope = f"component:{role}.quantity"
    for ambiguity in reference["ambiguity"]:
        if ambiguity["scope"] == scope:
            return [
                _quantity(value, f"ambiguity {scope}", nullable=False)
                for value in ambiguity["acceptable_values"]
            ]
    return [default]


def _score_variant(prediction: dict[str, Any], reference: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    components = variant["components"]
    aliases = _aliases(components)
    predicted = _aggregate_predictions(prediction["components"], aliases)
    expected = {item["role"]: item for item in components}
    required_roles = {role for role, item in expected.items() if item["required"]}
    allowed_roles = set(expected)
    predicted_roles = set(predicted)
    unknown_scopes = {item["scope"] for item in prediction["unknowns"]}
    roles_declared_unknown = "component_roles" in unknown_scopes
    unknown_roles = len(required_roles - predicted_roles) if roles_declared_unknown else 0
    role_metric = _metric(
        len(predicted_roles & allowed_roles),
        len(predicted_roles - allowed_roles),
        0 if roles_declared_unknown else len(required_roles - predicted_roles),
    )
    role_metric.update(
        unknown_reference_roles=unknown_roles,
        coverage=_ratio(
            len(required_roles & predicted_roles) if roles_declared_unknown else len(required_roles),
            len(required_roles),
        ),
        _coverage_numerator=(
            len(required_roles & predicted_roles) if roles_declared_unknown else len(required_roles)
        ),
        _coverage_denominator=len(required_roles),
    )

    occurrence_tp = occurrence_fp = occurrence_fn = unknown_units = 0
    coverage_numerator = coverage_denominator = 0
    for role in required_roles | (predicted_roles & allowed_roles):
        item = expected[role]
        options = _quantity_options(reference, role, item["quantity"])
        predicted_quantity = predicted.get(role)
        if role not in predicted:
            reference_quantity = options[0]
            if roles_declared_unknown:
                unknown_units += reference_quantity
            else:
                occurrence_fn += reference_quantity
                coverage_numerator += reference_quantity
            coverage_denominator += reference_quantity
        elif predicted_quantity is None:
            reference_quantity = min(options)
            unknown_units += reference_quantity
            coverage_denominator += reference_quantity
        else:
            reference_quantity = min(options, key=lambda value: (abs(value - predicted_quantity), value))
            occurrence_tp += min(predicted_quantity, reference_quantity)
            occurrence_fp += max(0, predicted_quantity - reference_quantity)
            occurrence_fn += max(0, reference_quantity - predicted_quantity)
            coverage_numerator += reference_quantity
            coverage_denominator += reference_quantity
    for role in predicted_roles - allowed_roles:
        if predicted[role] is not None:
            occurrence_fp += int(predicted[role])
    occurrence_metric = _metric(occurrence_tp, occurrence_fp, occurrence_fn)
    occurrence_metric.update(
        unknown_reference_units=unknown_units,
        coverage=_ratio(coverage_numerator, coverage_denominator),
        _coverage_numerator=coverage_numerator,
        _coverage_denominator=coverage_denominator,
    )

    relation_rows = variant["assembly_relations"]
    required_relations = {
        _relation_key(row, aliases) for row in relation_rows if row["required"]
    }
    allowed_relations = {_relation_key(row, aliases) for row in relation_rows}
    predicted_relations = {
        _relation_key(row, aliases) for row in prediction["assembly_relations"]
    }
    if "assembly_relations" in unknown_scopes:
        relation_metric = _metric(0, 0, 0)
        relation_metric.update(
            precision=None,
            recall=None,
            f1=None,
            unknown_reference_relations=len(required_relations),
            coverage=0.0 if required_relations else 1.0,
            _coverage_numerator=0,
            _coverage_denominator=len(required_relations),
        )
    else:
        unknown_pairs = set()
        for scope in unknown_scopes:
            match = re.fullmatch(r"assembly_relation:([^:]+):([^:]+)", scope)
            if match:
                unknown_pairs.add(
                    (
                        aliases.get(_normalized(match.group(1), "unknown relation subject"), _normalized(match.group(1), "unknown relation subject")),
                        aliases.get(_normalized(match.group(2), "unknown relation object"), _normalized(match.group(2), "unknown relation object")),
                    )
                )
        unknown_relations = {
            relation
            for relation in required_relations
            if (relation[0], relation[2]) in unknown_pairs
        }
        evaluable_required = required_relations - unknown_relations
        relation_metric = _metric(
            len(predicted_relations & allowed_relations),
            len(predicted_relations - allowed_relations),
            len(evaluable_required - predicted_relations),
        )
        relation_metric.update(
            unknown_reference_relations=len(unknown_relations),
            coverage=_ratio(len(evaluable_required), len(required_relations)) if required_relations else 1.0,
            _coverage_numerator=len(evaluable_required),
            _coverage_denominator=len(required_relations),
        )
    return {
        "variant": variant["id"],
        "component_roles": role_metric,
        "physical_occurrences": occurrence_metric,
        "assembly_relations": relation_metric,
    }


def _candidate_rank(score: dict[str, Any]) -> tuple[float, float, float, int]:
    def value(metric: dict[str, Any]) -> float:
        return -1.0 if metric["f1"] is None else float(metric["f1"])

    return (
        value(score["component_roles"]),
        value(score["physical_occurrences"]),
        value(score["assembly_relations"]),
        -sum(score[name]["fp"] + score[name]["fn"] for name in ("component_roles", "physical_occurrences", "assembly_relations")),
    )


def _score_construction_alternatives(
    prediction: dict[str, Any], reference: dict[str, Any]
) -> dict[str, Any]:
    aliases = _aliases(reference["components"])

    def signature(rows: list[dict[str, Any]]) -> frozenset[tuple[str, str, str]]:
        return frozenset(_relation_key(row, aliases) for row in rows)

    expected = {
        signature(variant["assembly_relations"])
        for variant in reference["valid_alternatives"]
    }
    if reference["valid_alternatives"]:
        expected.add(signature(reference["assembly_relations"]))
    predicted = [
        signature(variant["assembly_relations"])
        for variant in prediction["assembly_alternatives"]
    ]
    unknown = (
        "assembly_relations" in {item["scope"] for item in prediction["unknowns"]}
        and not predicted
    )
    if unknown:
        metric = _metric(0, 0, 0)
        metric.update(
            precision=None,
            recall=None,
            f1=None,
            unknown_reference_alternatives=len(expected),
            coverage=0.0 if expected else 1.0,
            _coverage_numerator=0,
            _coverage_denominator=len(expected),
        )
    else:
        matched = {item for item in predicted if item in expected}
        metric = _metric(
            sum(item in expected for item in predicted),
            sum(item not in expected for item in predicted),
            len(expected - matched),
        )
        metric.update(
            unknown_reference_alternatives=0,
            coverage=1.0,
            _coverage_numerator=len(expected),
            _coverage_denominator=len(expected),
        )
    return metric


def _parse_payloads(predictions: Any, references: Any) -> tuple[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    predictions = _object(predictions, "predictions")
    references = _object(references, "references")
    _strict(predictions, {"schema_version", "dataset_id", "cases"}, "predictions")
    _strict(references, {"schema_version", "dataset", "cases"}, "references")
    if predictions.get("schema_version") != SCHEMA_VERSION or references.get("schema_version") != SCHEMA_VERSION:
        raise SemanticEvaluationError(f"schema_version must be {SCHEMA_VERSION!r}")
    dataset_id = _text(predictions.get("dataset_id"), "predictions.dataset_id")
    dataset = _object(references.get("dataset"), "references.dataset")
    _strict(dataset, {"id", "predictions_sha256", "frozen_before_evaluation", "partition_policy", "reference_visibility", "partition_unit"}, "references.dataset")
    if _text(dataset.get("id"), "references.dataset.id") != dataset_id:
        raise SemanticEvaluationError("dataset id mismatch")
    _hash(dataset.get("predictions_sha256"), "references.dataset.predictions_sha256")
    if dataset.get("frozen_before_evaluation") is not True:
        raise SemanticEvaluationError("predictions must be frozen before evaluation")
    if dataset.get("partition_policy") != "project_and_family":
        raise SemanticEvaluationError("partition_policy must be 'project_and_family'")
    if dataset.get("reference_visibility") != "evaluator_only":
        raise SemanticEvaluationError("reference_visibility must be 'evaluator_only'")
    partition_unit = dataset.get("partition_unit")
    if partition_unit is not None and partition_unit != "project_id+structural_signature":
        raise SemanticEvaluationError(
            "partition_unit must be 'project_id+structural_signature'"
        )

    prediction_cases: dict[str, tuple[str, dict[str, Any]]] = {}
    for index, raw in enumerate(_array(predictions.get("cases"), "predictions.cases")):
        label = f"predictions.cases[{index}]"
        row = _object(raw, label)
        _strict(row, {"scenario_id", "input_sha256", "prediction"}, label)
        scenario_id = _text(row.get("scenario_id"), f"{label}.scenario_id")
        if scenario_id in prediction_cases:
            raise SemanticEvaluationError("predictions contains duplicate scenario_id")
        prediction_cases[scenario_id] = (
            _hash(row.get("input_sha256"), f"{label}.input_sha256"),
            _prediction(row.get("prediction"), f"{label}.prediction"),
        )

    reference_cases: dict[str, tuple[str, str, str, str, dict[str, Any]]] = {}
    family_splits: dict[str, str] = {}
    project_splits: dict[str, str] = {}
    input_splits: dict[str, str] = {}
    for index, raw in enumerate(_array(references.get("cases"), "references.cases")):
        label = f"references.cases[{index}]"
        row = _object(raw, label)
        _strict(
            row,
            {
                "scenario_id", "schema_version", "split", "family_id", "project_id",
                "product_family", "structural_signature", "view_profile", "input_sha256",
                "reference", "design_geometry",
            },
            label,
        )
        scenario_id = _text(row.get("scenario_id"), f"{label}.scenario_id")
        if scenario_id in reference_cases:
            raise SemanticEvaluationError("references contains duplicate scenario_id")
        split = _text(row.get("split"), f"{label}.split")
        family_value = row.get("family_id", row.get("structural_signature"))
        family = _text(family_value, f"{label}.family_id_or_structural_signature")
        project = _text(row.get("project_id"), f"{label}.project_id")
        input_hash = _hash(row.get("input_sha256"), f"{label}.input_sha256")
        if "schema_version" in row:
            _text(row["schema_version"], f"{label}.schema_version")
        if "product_family" in row:
            _text(row["product_family"], f"{label}.product_family")
        if "structural_signature" in row:
            _text(row["structural_signature"], f"{label}.structural_signature")
        if "view_profile" in row:
            _text(row["view_profile"], f"{label}.view_profile")
        if "design_geometry" in row:
            _object(row["design_geometry"], f"{label}.design_geometry")
        for kind, key, mapping in (("family_id", family, family_splits), ("project_id", project, project_splits), ("input_sha256", input_hash, input_splits)):
            previous = mapping.setdefault(key, split)
            if previous != split:
                raise SemanticEvaluationError(f"{kind} {key!r} crosses splits")
        reference_cases[scenario_id] = (
            input_hash,
            split,
            family,
            project,
            _reference(row.get("reference"), f"{label}.reference"),
        )
    if set(prediction_cases) != set(reference_cases):
        raise SemanticEvaluationError("prediction and reference scenario_id sets differ")
    paired = []
    for scenario_id, (input_hash, prediction) in prediction_cases.items():
        reference_hash, _, _, _, reference = reference_cases[scenario_id]
        if input_hash != reference_hash:
            raise SemanticEvaluationError(f"input_sha256 mismatch for scenario {scenario_id!r}")
        paired.append((scenario_id, prediction, reference))
    return dataset_id, paired


def evaluate_semantic_payloads(predictions: Any, references: Any) -> dict[str, Any]:
    """Score public-only predictions against an already-private reference payload."""

    dataset_id, paired = _parse_payloads(predictions, references)
    cases = []
    totals = {
        name: {"tp": 0, "fp": 0, "fn": 0, "unknown": 0, "coverage_numerator": 0, "coverage_denominator": 0}
        for name in (
            "component_roles",
            "physical_occurrences",
            "assembly_relations",
            "construction_alternatives",
        )
    }
    for scenario_id, prediction, reference in paired:
        variants = [
            {
                "id": "base",
                "components": reference["components"],
                "assembly_relations": reference["assembly_relations"],
            },
            *reference["valid_alternatives"],
        ]
        scores = [_score_variant(prediction, reference, variant) for variant in variants]
        selected = max(scores, key=_candidate_rank)
        selected["construction_alternatives"] = _score_construction_alternatives(
            prediction, reference
        )
        case_metrics = {}
        for name in totals:
            metric = selected[name]
            totals[name]["tp"] += metric["tp"]
            totals[name]["fp"] += metric["fp"]
            totals[name]["fn"] += metric["fn"]
            totals[name]["unknown"] += metric.get(
                "unknown_reference_roles",
                metric.get(
                    "unknown_reference_units",
                    metric.get(
                        "unknown_reference_relations",
                        metric.get("unknown_reference_alternatives", 0),
                    ),
                ),
            )
            totals[name]["coverage_numerator"] += metric.get("_coverage_numerator", 0)
            totals[name]["coverage_denominator"] += metric.get("_coverage_denominator", 0)
            case_metrics[name] = {key: value for key, value in metric.items() if not key.startswith("_")}
        cases.append(
            {
                "scenario_id": scenario_id,
                "matched_variant": selected["variant"],
                "declared_alternative_id": prediction["alternative_id"],
                "semantic_claim_status": "hypothesis_unreviewed",
                "metrics": case_metrics,
            }
        )
    aggregate = {}
    for name, counts in totals.items():
        metric = _metric(counts["tp"], counts["fp"], counts["fn"])
        if name == "component_roles":
            metric["unknown_reference_roles"] = counts["unknown"]
            metric["coverage"] = _ratio(counts["coverage_numerator"], counts["coverage_denominator"])
            if counts["coverage_denominator"] and counts["coverage_numerator"] == 0:
                metric.update(precision=None, recall=None, f1=None)
        elif name == "physical_occurrences":
            metric["unknown_reference_units"] = counts["unknown"]
            metric["coverage"] = _ratio(counts["coverage_numerator"], counts["coverage_denominator"])
        elif name == "assembly_relations":
            metric["unknown_reference_relations"] = counts["unknown"]
            metric["coverage"] = _ratio(counts["coverage_numerator"], counts["coverage_denominator"])
            if counts["coverage_denominator"] and counts["coverage_numerator"] == 0:
                metric.update(precision=None, recall=None, f1=None)
        elif name == "construction_alternatives":
            metric["unknown_reference_alternatives"] = counts["unknown"]
            metric["coverage"] = _ratio(
                counts["coverage_numerator"], counts["coverage_denominator"]
            )
            if counts["coverage_denominator"] and counts["coverage_numerator"] == 0:
                metric.update(precision=None, recall=None, f1=None)
        aggregate[name] = metric
    return {
        "schema_version": "semantic-evaluation-report/v1",
        "dataset_id": dataset_id,
        "case_count": len(cases),
        "aggregate": aggregate,
        "cases": cases,
    }


def evaluate_semantic_files(predictions_path: str | Path, references_path: str | Path) -> dict[str, Any]:
    """Verify the exact frozen bytes, then evaluate without exposing references."""

    try:
        prediction_bytes = Path(predictions_path).read_bytes()
        predictions = json.loads(prediction_bytes.decode("utf-8"))
        references = json.loads(Path(references_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticEvaluationError(f"cannot read evaluation input: {exc}") from exc
    dataset = _object(_object(references, "references").get("dataset"), "references.dataset")
    expected = _hash(dataset.get("predictions_sha256"), "references.dataset.predictions_sha256")
    if hashlib.sha256(prediction_bytes).hexdigest() != expected:
        raise SemanticEvaluationError("predictions_sha256 mismatch")
    return evaluate_semantic_payloads(predictions, references)
