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
    f1 = _f1(precision, recall)
    if f1 is None and tp == 0 and fp + fn > 0:
        f1 = 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
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
    role_tp = len(predicted_roles & required_roles)
    optional_role_tp = len(predicted_roles & (allowed_roles - required_roles))
    role_fp = len(predicted_roles - allowed_roles)
    missing_required_roles = required_roles - predicted_roles
    role_metric = _metric(role_tp, role_fp, len(missing_required_roles))
    role_metric.update(
        unknown_reference_roles=unknown_roles,
        optional_tp=optional_role_tp,
        covered_only=_metric(
            role_tp,
            role_fp,
            0 if roles_declared_unknown else len(missing_required_roles),
        ),
        coverage=_ratio(
            len(required_roles & predicted_roles) if roles_declared_unknown else len(required_roles),
            len(required_roles),
        ),
        _coverage_numerator=(
            len(required_roles & predicted_roles) if roles_declared_unknown else len(required_roles)
        ),
        _coverage_denominator=len(required_roles),
        coverage_numerator=(
            len(required_roles & predicted_roles) if roles_declared_unknown else len(required_roles)
        ),
        coverage_denominator=len(required_roles),
    )

    occurrence_tp = occurrence_fp = occurrence_fn = unknown_units = 0
    coverage_numerator = coverage_denominator = 0
    optional_tp_units = 0
    for role in required_roles:
        item = expected[role]
        options = _quantity_options(reference, role, item["quantity"])
        predicted_quantity = predicted.get(role)
        if role not in predicted:
            reference_quantity = min(options)
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
    for role in predicted_roles & (allowed_roles - required_roles):
        predicted_quantity = predicted[role]
        if predicted_quantity is not None:
            options = _quantity_options(reference, role, expected[role]["quantity"])
            reference_quantity = min(
                options, key=lambda value: (abs(value - predicted_quantity), value)
            )
            optional_tp_units += min(predicted_quantity, reference_quantity)
    for role in predicted_roles - allowed_roles:
        if predicted[role] is not None:
            occurrence_fp += int(predicted[role])
    occurrence_metric = _metric(
        occurrence_tp, occurrence_fp, occurrence_fn + unknown_units
    )
    occurrence_metric.update(
        unknown_reference_units=unknown_units,
        optional_tp_units=optional_tp_units,
        covered_only=_metric(occurrence_tp, occurrence_fp, occurrence_fn),
        coverage=_ratio(coverage_numerator, coverage_denominator),
        _coverage_numerator=coverage_numerator,
        _coverage_denominator=coverage_denominator,
        coverage_numerator=coverage_numerator,
        coverage_denominator=coverage_denominator,
    )

    relation_rows = variant["assembly_relations"]
    required_relations = {
        _relation_key(row, aliases) for row in relation_rows if row["required"]
    }
    allowed_relations = {_relation_key(row, aliases) for row in relation_rows}
    predicted_relations = {
        _relation_key(row, aliases) for row in prediction["assembly_relations"]
    }
    unknown_pairs = set()
    for scope in unknown_scopes:
        match = re.fullmatch(r"assembly_relation:([^:]+):([^:]+)", scope)
        if match:
            subject = _normalized(match.group(1), "unknown relation subject")
            object_role = _normalized(match.group(2), "unknown relation object")
            unknown_pairs.add(
                (
                    aliases.get(subject, subject),
                    aliases.get(object_role, object_role),
                )
            )
    if "assembly_relations" in unknown_scopes:
        unknown_relations = required_relations - predicted_relations
    else:
        unknown_relations = {
            relation
            for relation in required_relations - predicted_relations
            if (relation[0], relation[2]) in unknown_pairs
        }
    evaluable_required = required_relations - unknown_relations
    relation_tp = len(predicted_relations & required_relations)
    optional_relation_tp = len(
        predicted_relations & (allowed_relations - required_relations)
    )
    relation_fp = len(predicted_relations - allowed_relations)
    relation_metric = _metric(
        relation_tp,
        relation_fp,
        len(required_relations - predicted_relations),
    )
    relation_metric.update(
        unknown_reference_relations=len(unknown_relations),
        optional_tp=optional_relation_tp,
        covered_only=_metric(
            relation_tp,
            relation_fp,
            len(evaluable_required - predicted_relations),
        ),
        coverage=_ratio(len(evaluable_required), len(required_relations)) if required_relations else 1.0,
        _coverage_numerator=len(evaluable_required),
        _coverage_denominator=len(required_relations),
        coverage_numerator=len(evaluable_required),
        coverage_denominator=len(required_relations),
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
    predicted = [
        signature(variant["assembly_relations"])
        for variant in prediction["assembly_alternatives"]
    ]
    matched = {item for item in predicted if item in expected}
    metric = _metric(
        sum(item in expected for item in predicted),
        sum(item not in expected for item in predicted),
        len(expected - matched),
    )
    if "assembly_relations" in {item["scope"] for item in prediction["unknowns"]} and not predicted:
        metric.update(
            unknown_reference_alternatives=len(expected),
            coverage=0.0,
            _coverage_numerator=0,
            _coverage_denominator=len(expected),
        )
    else:
        metric.update(
            unknown_reference_alternatives=0,
            coverage=1.0,
            _coverage_numerator=len(expected),
            _coverage_denominator=len(expected),
        )
    metric["coverage_numerator"] = metric["_coverage_numerator"]
    metric["coverage_denominator"] = metric["_coverage_denominator"]
    metric["covered_only"] = _metric(metric["tp"], metric["fp"], metric["fn"])
    return metric


def _parse_payloads(predictions: Any, references: Any) -> tuple[str, str, list[tuple[str, str, str, dict[str, Any], dict[str, Any]]]]:
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
        reference_hash, split, _, project, reference = reference_cases[scenario_id]
        if input_hash != reference_hash:
            raise SemanticEvaluationError(f"input_sha256 mismatch for scenario {scenario_id!r}")
        paired.append((scenario_id, split, project, prediction, reference))
    batch_identity = [
        {
            "scenario_id": scenario_id,
            "input_sha256": prediction_cases[scenario_id][0],
            "split": reference_cases[scenario_id][1],
        }
        for scenario_id in sorted(prediction_cases)
    ]
    batch_sha256 = hashlib.sha256(
        json.dumps(
            batch_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return dataset_id, batch_sha256, paired


def evaluate_semantic_payloads(predictions: Any, references: Any) -> dict[str, Any]:
    """Score public-only predictions against an already-private reference payload."""

    dataset_id, evaluation_batch_sha256, paired = _parse_payloads(predictions, references)
    cases = []
    metric_names = (
        "component_roles",
        "physical_occurrences",
        "assembly_relations",
        "construction_alternatives",
    )

    def new_totals() -> dict[str, dict[str, int]]:
        return {
            name: {
                "tp": 0, "fp": 0, "fn": 0, "covered_tp": 0,
                "covered_fp": 0, "covered_fn": 0, "unknown": 0,
                "optional_tp": 0, "optional_tp_units": 0,
                "coverage_numerator": 0, "coverage_denominator": 0,
            }
            for name in metric_names
        }

    def add_metric(target: dict[str, dict[str, int]], name: str, metric: dict[str, Any]) -> None:
        target[name]["tp"] += metric["tp"]
        target[name]["fp"] += metric["fp"]
        target[name]["fn"] += metric["fn"]
        covered = metric.get("covered_only", metric)
        target[name]["covered_tp"] += covered["tp"]
        target[name]["covered_fp"] += covered["fp"]
        target[name]["covered_fn"] += covered["fn"]
        target[name]["unknown"] += metric.get(
            "unknown_reference_roles",
            metric.get(
                "unknown_reference_units",
                metric.get(
                    "unknown_reference_relations",
                    metric.get("unknown_reference_alternatives", 0),
                ),
            ),
        )
        target[name]["optional_tp"] += metric.get("optional_tp", 0)
        target[name]["optional_tp_units"] += metric.get("optional_tp_units", 0)
        target[name]["coverage_numerator"] += metric.get("_coverage_numerator", 0)
        target[name]["coverage_denominator"] += metric.get("_coverage_denominator", 0)

    def finish_totals(source: dict[str, dict[str, int]]) -> dict[str, Any]:
        result = {}
        for name, counts in source.items():
            metric = _metric(counts["tp"], counts["fp"], counts["fn"])
            metric["covered_only"] = _metric(
                counts["covered_tp"], counts["covered_fp"], counts["covered_fn"]
            )
            metric["coverage_numerator"] = counts["coverage_numerator"]
            metric["coverage_denominator"] = counts["coverage_denominator"]
            metric["coverage"] = _ratio(
                counts["coverage_numerator"], counts["coverage_denominator"]
            )
            if name == "component_roles":
                metric["unknown_reference_roles"] = counts["unknown"]
                metric["optional_tp"] = counts["optional_tp"]
            elif name == "physical_occurrences":
                metric["unknown_reference_units"] = counts["unknown"]
                metric["optional_tp_units"] = counts["optional_tp_units"]
            elif name == "assembly_relations":
                metric["unknown_reference_relations"] = counts["unknown"]
                metric["optional_tp"] = counts["optional_tp"]
            elif name == "construction_alternatives":
                metric["unknown_reference_alternatives"] = counts["unknown"]
            result[name] = metric
        return result

    totals = new_totals()
    split_totals: dict[str, dict[str, dict[str, int]]] = {}
    split_case_counts: dict[str, int] = {}
    complete_case_count = 0
    split_complete_case_counts: dict[str, int] = {}
    projects: set[str] = set()
    split_projects: dict[str, set[str]] = {}
    for scenario_id, split, project, prediction, reference in paired:
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
        current_split_totals = split_totals.setdefault(split, new_totals())
        split_case_counts[split] = split_case_counts.get(split, 0) + 1
        projects.add(project)
        split_projects.setdefault(split, set()).add(project)
        for name in metric_names:
            metric = selected[name]
            add_metric(totals, name, metric)
            add_metric(current_split_totals, name, metric)
            case_metrics[name] = {key: value for key, value in metric.items() if not key.startswith("_")}
        core_metrics = [
            selected[name]
            for name in ("component_roles", "physical_occurrences", "assembly_relations")
        ]
        complete_recovery = all(
            metric["fp"] == 0
            and metric["fn"] == 0
            and metric.get(
                "unknown_reference_roles",
                metric.get(
                    "unknown_reference_units",
                    metric.get("unknown_reference_relations", 0),
                ),
            )
            == 0
            for metric in core_metrics
        )
        if complete_recovery:
            complete_case_count += 1
            split_complete_case_counts[split] = split_complete_case_counts.get(split, 0) + 1
        cases.append(
            {
                "scenario_id": scenario_id,
                "split": split,
                "matched_variant": selected["variant"],
                "declared_alternative_id": prediction["alternative_id"],
                "semantic_claim_status": "hypothesis_unreviewed",
                "complete_recovery": complete_recovery,
                "metrics": case_metrics,
            }
        )
    aggregate = finish_totals(totals)
    return {
        "schema_version": "semantic-evaluation-report/v2",
        "metric_definition": "complete_recovery_with_explicit_coverage/v2",
        "dataset_id": dataset_id,
        "evaluation_batch_sha256": evaluation_batch_sha256,
        "case_count": len(cases),
        "project_count": len(projects),
        "complete_case_count": complete_case_count,
        "complete_case_rate": _ratio(complete_case_count, len(cases)),
        "aggregate": aggregate,
        "splits": {
            split: {
                "case_count": split_case_counts[split],
                "project_count": len(split_projects[split]),
                "complete_case_count": split_complete_case_counts.get(split, 0),
                "complete_case_rate": _ratio(
                    split_complete_case_counts.get(split, 0), split_case_counts[split]
                ),
                "aggregate": finish_totals(split_totals[split]),
            }
            for split in sorted(split_totals)
        },
        "cases": cases,
    }


def compare_semantic_reports(baseline: Any, final: Any) -> dict[str, Any]:
    """Compare two v2 reports without copying case or reference payloads."""

    baseline = _object(baseline, "baseline report")
    final = _object(final, "final report")
    for label, report in (("baseline", baseline), ("final", final)):
        if report.get("schema_version") != "semantic-evaluation-report/v2":
            raise SemanticEvaluationError(f"{label} report must use semantic-evaluation-report/v2")
        if report.get("metric_definition") != "complete_recovery_with_explicit_coverage/v2":
            raise SemanticEvaluationError(f"{label} report uses an incompatible metric definition")
    for field in (
        "dataset_id", "evaluation_batch_sha256", "case_count", "project_count"
    ):
        if baseline.get(field) != final.get(field):
            raise SemanticEvaluationError(f"baseline and final {field} differ")

    def numeric_fields(metric: dict[str, Any]) -> dict[str, int | float | None]:
        return {
            key: value
            for key, value in metric.items()
            if key != "covered_only"
            and (value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)))
        }

    def compare_metric(left: Any, right: Any, label: str) -> dict[str, Any]:
        left = _object(left, f"baseline {label}")
        right = _object(right, f"final {label}")
        left_values = numeric_fields(left)
        right_values = numeric_fields(right)
        if set(left_values) != set(right_values):
            raise SemanticEvaluationError(f"baseline and final {label} metric fields differ")
        delta = {
            key: (
                float(right_values[key]) - float(left_values[key])
                if right_values[key] is not None and left_values[key] is not None
                else None
            )
            for key in left_values
        }
        result: dict[str, Any] = {
            "baseline": left_values,
            "final": right_values,
            "delta": delta,
        }
        if "covered_only" in left or "covered_only" in right:
            result["covered_only"] = compare_metric(
                left.get("covered_only"), right.get("covered_only"), f"{label}.covered_only"
            )
        return result

    def compare_aggregate(left: Any, right: Any, label: str) -> dict[str, Any]:
        left = _object(left, f"baseline {label}")
        right = _object(right, f"final {label}")
        if set(left) != set(right):
            raise SemanticEvaluationError(f"baseline and final {label} metric sets differ")
        return {
            name: compare_metric(left[name], right[name], f"{label}.{name}")
            for name in sorted(left)
        }

    baseline_splits = _object(baseline.get("splits"), "baseline splits")
    final_splits = _object(final.get("splits"), "final splits")
    if set(baseline_splits) != set(final_splits):
        raise SemanticEvaluationError("baseline and final split sets differ")
    splits = {}
    for split in sorted(baseline_splits):
        left = _object(baseline_splits[split], f"baseline split {split}")
        right = _object(final_splits[split], f"final split {split}")
        for field in ("case_count", "project_count"):
            if left.get(field) != right.get(field):
                raise SemanticEvaluationError(f"baseline and final split {split} {field} differ")
        splits[split] = {
            "case_count": left["case_count"],
            "project_count": left["project_count"],
            "complete_cases": {
                "baseline": {
                    "count": left.get("complete_case_count"),
                    "rate": left.get("complete_case_rate"),
                },
                "final": {
                    "count": right.get("complete_case_count"),
                    "rate": right.get("complete_case_rate"),
                },
                "delta": {
                    "count": right.get("complete_case_count", 0)
                    - left.get("complete_case_count", 0),
                    "rate": right.get("complete_case_rate", 0.0)
                    - left.get("complete_case_rate", 0.0),
                },
            },
            "aggregate": compare_aggregate(
                left.get("aggregate"), right.get("aggregate"), f"split {split}"
            ),
        }
    return {
        "schema_version": "semantic-evaluation-comparison/v2",
        "metric_definition": "complete_recovery_with_explicit_coverage/v2",
        "dataset_id": baseline["dataset_id"],
        "evaluation_batch_sha256": baseline["evaluation_batch_sha256"],
        "case_count": baseline["case_count"],
        "project_count": baseline["project_count"],
        "complete_cases": {
            "baseline": {
                "count": baseline.get("complete_case_count"),
                "rate": baseline.get("complete_case_rate"),
            },
            "final": {
                "count": final.get("complete_case_count"),
                "rate": final.get("complete_case_rate"),
            },
            "delta": {
                "count": final.get("complete_case_count", 0)
                - baseline.get("complete_case_count", 0),
                "rate": final.get("complete_case_rate", 0.0)
                - baseline.get("complete_case_rate", 0.0),
            },
        },
        "aggregate": compare_aggregate(
            baseline.get("aggregate"), final.get("aggregate"), "aggregate"
        ),
        "splits": splits,
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
