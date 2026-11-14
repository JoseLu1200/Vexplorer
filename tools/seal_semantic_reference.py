"""Seal an evaluator-only reference subset to one frozen prediction batch."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "semantic-evaluation/v1"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_object(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value, raw


def seal_semantic_reference(private_destination: Path, predictions_path: Path) -> Path:
    """Write an immutable per-batch envelope for a non-empty selected subset."""

    private_destination = private_destination.resolve()
    predictions_path = predictions_path.resolve()
    references, _ = _read_object(private_destination / "references.json")
    manifest, _ = _read_object(private_destination / "manifest.json")
    predictions, prediction_bytes = _read_object(predictions_path)
    if set(predictions) != {"schema_version", "dataset_id", "cases"}:
        raise ValueError("unexpected frozen prediction batch fields")
    if predictions.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected frozen prediction schema_version")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or predictions.get("dataset_id") != dataset_id:
        raise ValueError("prediction dataset id does not match private reference")
    scenarios = references.get("scenarios")
    prediction_cases = predictions.get("cases")
    if not isinstance(scenarios, list) or not isinstance(prediction_cases, list) or not prediction_cases:
        raise ValueError("non-empty reference and prediction case lists required")
    scenario_by_id = {
        scenario.get("scenario_id"): scenario
        for scenario in scenarios
        if isinstance(scenario, dict) and isinstance(scenario.get("scenario_id"), str)
    }
    if len(scenario_by_id) != len(scenarios):
        raise ValueError("private reference case ids must be unique strings")
    selected_ids: list[str] = []
    for case in prediction_cases:
        if not isinstance(case, dict):
            raise ValueError("frozen prediction cases must be objects")
        scenario_id = case.get("scenario_id")
        input_sha256 = case.get("input_sha256")
        if not isinstance(scenario_id, str) or scenario_id not in scenario_by_id:
            raise ValueError("prediction case ids are not a private reference subset")
        if scenario_id in selected_ids:
            raise ValueError("prediction case ids must not contain duplicates")
        expected_input_hash = scenario_by_id[scenario_id].get("input_sha256")
        if input_sha256 != expected_input_hash:
            raise ValueError(f"input_sha256 mismatch for {scenario_id}")
        if "prediction" not in case:
            raise ValueError(f"prediction payload missing for {scenario_id}")
        selected_ids.append(scenario_id)
    prediction_hash = _digest(prediction_bytes)
    target = private_destination / f"evaluation-reference-{prediction_hash[:16]}.json"
    if target.resolve() == predictions_path or target.exists():
        raise ValueError("private reference already sealed for this prediction batch")
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "dataset": {
            "id": dataset_id,
            "predictions_sha256": prediction_hash,
            "frozen_before_evaluation": True,
            "partition_policy": "project_and_family",
            "partition_unit": "project_id+structural_signature",
            "reference_visibility": "evaluator_only",
        },
        "cases": [scenario_by_id[scenario_id] for scenario_id in selected_ids],
    }
    encoded = (json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with target.open("xb") as stream:
        stream.write(encoded)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-reference", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        target = seal_semantic_reference(args.private_reference, args.predictions)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Seal failed: {exc}\n")
    print(json.dumps({"sealed_reference": str(target), "sha256": _digest(target.read_bytes())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
