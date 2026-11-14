"""Build offline evaluator references from private panel bounds and frozen predictions.

This tool is evaluator-only. It does not run inference, read product storage or score
results. Component alignment is maximum-cardinality, then minimum-error, using
orientation-invariant dimensional triplets. Field-oriented error remains the
responsibility of ``tools.evaluate_cases``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import tempfile
from typing import Any


FIELDS = ("length", "width", "thickness")
CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
MAX_REFERENCE_TYPES = 24


def _shape_from_bounds(component: dict[str, Any], *, round_digits: int) -> tuple[float, ...]:
    bounds = component.get("bounds_mm")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 6
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bounds)
    ):
        raise ValueError("invalid private component bounds")
    if any(not isfinite(float(value)) for value in bounds):
        raise ValueError("private component bounds must be finite")
    extents = sorted(
        (abs(float(bounds[index + 3]) - float(bounds[index])) for index in range(3)),
        reverse=True,
    )
    if any(not isfinite(value) or value <= 0 for value in extents):
        raise ValueError("private component extent must be finite and positive")
    return tuple(round(value, round_digits) for value in extents)


def group_reference_components(
    components: list[dict[str, Any]], *, round_digits: int
) -> list[dict[str, Any]]:
    """Collapse physically repeated cuboids into dimensional types."""

    if not 0 <= round_digits <= 6:
        raise ValueError("round_digits must be between 0 and 6")
    counts = Counter(
        _shape_from_bounds(component, round_digits=round_digits) for component in components
    )
    if len(counts) > MAX_REFERENCE_TYPES:
        raise ValueError("reference type budget exceeded")
    return [
        {
            "key": f"private-shape-{index}",
            "quantity": counts[shape],
            "dimensions_mm": dict(zip(FIELDS, shape, strict=True)),
        }
        for index, shape in enumerate(sorted(counts), 1)
    ]


def _prediction_shape(component: dict[str, Any]) -> tuple[float, ...] | None:
    values = component.get("dimensions_mm")
    if not isinstance(values, dict) or any(values.get(field) is None for field in FIELDS):
        return None
    selected = [values[field] for field in FIELDS]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in selected):
        raise ValueError("invalid prediction dimension")
    if any(not isfinite(float(value)) for value in selected):
        raise ValueError("prediction dimensions must be finite")
    return tuple(sorted((float(value) for value in selected), reverse=True))


def align_components(
    predicted: list[dict[str, Any]],
    references: list[dict[str, Any]],
    *,
    tolerance_mm: float,
) -> list[dict[str, str]]:
    """Return a deterministic maximum-cardinality/minimum-error one-to-one alignment."""

    if not isfinite(tolerance_mm) or tolerance_mm < 0:
        raise ValueError("tolerance_mm must be finite and nonnegative")
    if len(references) > MAX_REFERENCE_TYPES:
        raise ValueError("reference type budget exceeded")
    prediction_keys = [component.get("key") for component in predicted]
    reference_keys = [component.get("key") for component in references]
    if (
        any(not isinstance(key, str) or not key for key in prediction_keys + reference_keys)
        or len(prediction_keys) != len(set(prediction_keys))
        or len(reference_keys) != len(set(reference_keys))
    ):
        raise ValueError("component keys must be nonempty and unique")

    candidates: list[list[tuple[int, float]]] = []
    for prediction in predicted:
        shape = _prediction_shape(prediction)
        options = []
        if shape is not None:
            for reference_index, reference in enumerate(references):
                dimensions = reference.get("dimensions_mm")
                reference_shape = tuple(float(dimensions[field]) for field in FIELDS)
                if any(not isfinite(value) for value in reference_shape):
                    raise ValueError("reference dimensions must be finite")
                errors = [abs(left - right) for left, right in zip(shape, reference_shape, strict=True)]
                if all(error <= tolerance_mm for error in errors):
                    options.append((reference_index, sum(errors)))
        candidates.append(options)

    @lru_cache(maxsize=None)
    def solve(index: int, used: int) -> tuple[int, float, tuple[tuple[int, int], ...]]:
        if index == len(predicted):
            return 0, 0.0, ()
        best = solve(index + 1, used)
        for reference_index, error in candidates[index]:
            bit = 1 << reference_index
            if used & bit:
                continue
            count, cost, pairs = solve(index + 1, used | bit)
            candidate = count + 1, cost + error, ((index, reference_index), *pairs)
            if (
                candidate[0] > best[0]
                or candidate[0] == best[0] and candidate[1] < best[1] - 1e-12
                or candidate[0] == best[0]
                and abs(candidate[1] - best[1]) <= 1e-12
                and candidate[2] < best[2]
            ):
                best = candidate
        return best

    return [
        {
            "prediction_key": prediction_keys[prediction_index],
            "reference_key": reference_keys[reference_index],
        }
        for prediction_index, reference_index in solve(0, 0)[2]
    ]


def build_evaluator_references(
    predictions: dict[str, Any],
    raw_references: list[dict[str, Any]],
    *,
    prediction_sha256: str,
    evidence_kind: str,
    effective_date: str,
    round_digits: int,
    tolerance_mm: float,
    acceptable_scenario_key: str | None,
) -> dict[str, Any]:
    if predictions.get("schema_version") != "1.0":
        raise ValueError("prediction schema_version must be 1.0")
    dataset_id = predictions.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ValueError("prediction dataset_id is required")
    prediction_cases = predictions.get("cases")
    if not isinstance(prediction_cases, list):
        raise ValueError("prediction cases must be a list")
    predicted_by_id = {case.get("id"): case for case in prediction_cases}
    raw_by_id = {case.get("id"): case for case in raw_references}
    if (
        None in predicted_by_id
        or None in raw_by_id
        or len(predicted_by_id) != len(prediction_cases)
        or len(raw_by_id) != len(raw_references)
        or set(predicted_by_id) != set(raw_by_id)
        or any(CASE_ID_RE.fullmatch(case_id) is None for case_id in predicted_by_id)
    ):
        raise ValueError("prediction/reference case ids must be unique and identical")

    cases = []
    for case_id in sorted(predicted_by_id):
        raw = raw_by_id[case_id]
        split = raw.get("split")
        family_id = raw.get("family_hash")
        components = raw.get("components")
        if split not in {"development", "holdout", "test"}:
            raise ValueError("invalid reference split")
        if not isinstance(family_id, str) or not family_id or not isinstance(components, list):
            raise ValueError("invalid private case metadata")
        grouped = group_reference_components(components, round_digits=round_digits)
        predicted_components = predicted_by_id[case_id].get("components")
        if not isinstance(predicted_components, list):
            raise ValueError("prediction components must be a list")
        cases.append(
            {
                "id": case_id,
                "split": split,
                "project_id": case_id,
                "family_id": family_id,
                "duplicate_group_id": case_id,
                "components": grouped,
                "component_matches": align_components(
                    predicted_components, grouped, tolerance_mm=tolerance_mm
                ),
                "relevant_item_ids": [],
                "cost": None,
                "hours": None,
                "technician_baseline": None,
                "acceptable_scenarios": (
                    [{"key": acceptable_scenario_key}] if acceptable_scenario_key else []
                ),
                "scenario_matches": [],
            }
        )
    return {
        "schema_version": "1.0",
        "dataset": {
            "id": dataset_id,
            "evidence_kind": evidence_kind,
            "frozen_before_evaluation": True,
            "predictions_sha256": prediction_sha256,
            "partition_policy": "project_and_family",
            "component_matching": "reference_alignment",
            "cost_currency": "EUR",
            "cost_scope_id": "not_available",
            "cost_effective_date": effective_date,
            "hours_scope_id": "not_available",
            "retrieval_items": {},
        },
        "cases": cases,
    }


def _encoded(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def _write_new_atomic(path: Path, value: object) -> bytes:
    if path.exists():
        raise ValueError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _encoded(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return encoded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--raw-references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--effective-date", required=True)
    parser.add_argument(
        "--evidence-kind",
        choices=("development_diagnostic", "independent_review"),
        default="development_diagnostic",
    )
    parser.add_argument("--round-digits", type=int, default=1)
    parser.add_argument("--tolerance-mm", type=float, default=1.0)
    parser.add_argument("--acceptable-scenario-key")
    parser.add_argument("--split", choices=("development", "holdout", "test"))
    parser.add_argument("--filtered-predictions-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = [args.predictions.resolve(), args.raw_references.resolve(), args.output.resolve()]
    if args.filtered_predictions_output is not None:
        paths.append(args.filtered_predictions_output.resolve())
    if len(paths) != len(set(paths)):
        raise SystemExit("input and output paths must be distinct")
    if bool(args.split) != bool(args.filtered_predictions_output):
        raise SystemExit("--split and --filtered-predictions-output must be used together")
    try:
        prediction_bytes = args.predictions.read_bytes()
        predictions = json.loads(prediction_bytes)
        raw_references = json.loads(args.raw_references.read_text(encoding="utf-8"))
        if not isinstance(predictions, dict) or not isinstance(raw_references, list):
            raise ValueError("invalid input roots")
        if args.split:
            raw_ids = {
                case.get("id") for case in raw_references if case.get("split") == args.split
            }
            raw_references = [case for case in raw_references if case.get("id") in raw_ids]
            predictions = {
                **predictions,
                "cases": [
                    case for case in predictions.get("cases", []) if case.get("id") in raw_ids
                ],
            }
            prediction_bytes = _write_new_atomic(
                args.filtered_predictions_output, predictions
            )
        references = build_evaluator_references(
            predictions,
            raw_references,
            prediction_sha256=sha256(prediction_bytes).hexdigest(),
            evidence_kind=args.evidence_kind,
            effective_date=args.effective_date,
            round_digits=args.round_digits,
            tolerance_mm=args.tolerance_mm,
            acceptable_scenario_key=args.acceptable_scenario_key,
        )
        _write_new_atomic(args.output, references)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"reference build failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
