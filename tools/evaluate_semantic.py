"""Freeze native semantic output or evaluate a frozen file offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from evaluation.semantic import SCHEMA_VERSION, SemanticEvaluationError, evaluate_semantic_files


_SAFE_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_SAFE_DATASET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _as_mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if hasattr(value, "proposal") and not isinstance(value, dict):
        value = {"proposal": value.proposal.model_dump(mode="json")}
    if not isinstance(value, dict):
        raise SemanticEvaluationError("native output must be an object")
    return value


def adapt_general_furniture_output(
    native_output: Any, *, scenario_id: str, input_sha256: str
) -> dict[str, Any]:
    """Adapt public native fields; never infer an assembly graph from geometry."""

    if _SAFE_CASE_ID.fullmatch(scenario_id) is None:
        raise SemanticEvaluationError("invalid paired scenario id")
    if _HEX64.fullmatch(input_sha256) is None:
        raise SemanticEvaluationError("invalid paired input hash")
    payload = _as_mapping(native_output)
    if "case_id" in payload and payload["case_id"] != scenario_id:
        raise SemanticEvaluationError("native wrapper case_id mismatch")
    if "input_sha256" in payload and payload["input_sha256"] != input_sha256:
        raise SemanticEvaluationError("native wrapper input_sha256 mismatch")
    outcome = _as_mapping(payload.get("outcome", payload))
    effective = outcome.get("effective_proposal_outcome")
    final_review_outcomes: dict[str, str] | None = None
    if effective is not None:
        review = _as_mapping(outcome.get("review", {}))
        raw_reviews = review.get("machine_field_reviews", [])
        if not isinstance(raw_reviews, (list, tuple)):
            raise SemanticEvaluationError("final review.machine_field_reviews must be an array")
        final_review_outcomes = {
            item.get("target_ref"): item.get("status")
            for raw in raw_reviews
            if isinstance((item := _as_mapping(raw)).get("target_ref"), str)
        }
        outcome = _as_mapping(effective)
    proposal = _as_mapping(outcome.get("proposal", outcome))
    components = proposal.get("components")
    if not isinstance(components, (list, tuple)) or not components:
        raise SemanticEvaluationError("native proposal.components must be a non-empty array")
    adapted = []
    unknowns = []
    roles_by_id: dict[str, str] = {}
    for index, raw in enumerate(components):
        component = _as_mapping(raw)
        label = component.get("label")
        role = component.get("role")
        quantity = _as_mapping(component.get("quantity"))
        if not isinstance(label, str) or not label.strip() or not isinstance(role, str) or not role.strip():
            raise SemanticEvaluationError(f"native component {index} lacks label or role")
        component_id = component.get("id")
        if isinstance(component_id, str) and component_id:
            roles_by_id[component_id] = role.strip()
        value = quantity.get("value")
        state = quantity.get("state")
        if state in {"unknown", "conflict"}:
            value = None
            unknowns.append(
                {
                    "scope": f"component:{role.strip()}.quantity",
                    "reason": f"native quantity state is {state}",
                }
            )
        if final_review_outcomes is not None:
            target_ref = f"component:{component_id}.quantity"
            if final_review_outcomes.get(target_ref) != "accepted":
                value = None
                unknowns.append(
                    {
                        "scope": f"component:{role.strip()}.quantity",
                        "reason": "final critic did not accept the quantity",
                    }
                )
        adapted.append({"label": label.strip(), "role": role.strip(), "quantity": value})

    def adapt_relation(raw: Any, label: str) -> dict[str, str] | None:
        item = _as_mapping(raw)
        subject_id = item.get("subject_component_id")
        object_id = item.get("object_component_id")
        if subject_id not in roles_by_id or object_id not in roles_by_id:
            raise SemanticEvaluationError(f"{label} references an unknown native component")
        subject_role = roles_by_id[subject_id]
        object_role = roles_by_id[object_id]
        state = item.get("state")
        predicate = item.get("relation")
        if state != "hypothesis" or predicate == "unknown":
            unknowns.append(
                {
                    "scope": f"assembly_relation:{subject_role}:{object_role}",
                    "reason": f"native assembly relation state is {state}",
                }
            )
            return None
        if not isinstance(predicate, str) or not predicate:
            raise SemanticEvaluationError(f"{label}.relation must be a non-empty string")
        return {
            "subject_role": subject_role,
            "relation": predicate,
            "object_role": object_role,
        }

    native_relations = proposal.get("assembly_relations", [])
    native_alternatives = proposal.get("assembly_alternatives", [])
    if not isinstance(native_relations, (list, tuple)) or not isinstance(native_alternatives, (list, tuple)):
        raise SemanticEvaluationError("native assembly fields must be arrays")
    assembly_relations = [
        mapped
        for index, raw in enumerate(native_relations)
        if (mapped := adapt_relation(raw, f"native assembly_relations[{index}]")) is not None
    ]
    assembly_alternatives = []
    for index, raw in enumerate(native_alternatives):
        item = _as_mapping(raw)
        alternative_id = item.get("alternative_id")
        relations = item.get("relations")
        if not isinstance(alternative_id, str) or not alternative_id or not isinstance(relations, (list, tuple)):
            raise SemanticEvaluationError(f"native assembly_alternatives[{index}] is invalid")
        mapped_relations = [
            mapped
            for relation_index, raw_relation in enumerate(relations)
            if (mapped := adapt_relation(raw_relation, f"native assembly_alternatives[{index}].relations[{relation_index}]")) is not None
        ]
        if mapped_relations:
            assembly_alternatives.append(
                {"alternative_id": alternative_id, "assembly_relations": mapped_relations}
            )
    if not native_relations and not native_alternatives:
        unknowns.append(
            {
                "scope": "assembly_relations",
                "reason": "native output declared no assessable assembly graph",
            }
        )
    return {
        "scenario_id": scenario_id,
        "input_sha256": input_sha256,
        "prediction": {
            "components": adapted,
            "assembly_relations": assembly_relations,
            "assembly_alternatives": assembly_alternatives,
            "unknowns": unknowns,
        },
    }


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SemanticEvaluationError(f"output already exists: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _failed_case(scenario_id: str, input_sha256: str) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "input_sha256": input_sha256,
        "prediction": {
            "components": [],
            "assembly_relations": [],
            "assembly_alternatives": [],
            "unknowns": [
                {"scope": "component_roles", "reason": "native inference did not produce an outcome"},
                {"scope": "assembly_relations", "reason": "native inference did not produce an outcome"},
            ],
        },
    }


def _read_json_bytes(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticEvaluationError(f"cannot read {label}: {exc}") from exc
    return _as_mapping(value), raw


def _verified_frozen_json(
    paired_output: Path,
    relative_path: str,
    frozen_files: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    expected = frozen_files.get(relative_path)
    if not isinstance(expected, str) or _HEX64.fullmatch(expected) is None:
        raise SemanticEvaluationError(
            f"frozen manifest lacks a valid hash for {relative_path}"
        )
    value, raw = _read_json_bytes(paired_output / Path(relative_path), relative_path)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise SemanticEvaluationError(f"frozen hash mismatch for {relative_path}")
    return value, actual


def _validate_wrapper_identity(
    wrapper: dict[str, Any], *, scenario_id: str, input_sha256: str
) -> None:
    if wrapper.get("case_id") != scenario_id:
        raise SemanticEvaluationError("native wrapper case_id mismatch")
    if wrapper.get("input_sha256") != input_sha256:
        raise SemanticEvaluationError("native wrapper input_sha256 mismatch")


def freeze_paired_semantic_outputs(
    paired_output: Path, destination: Path
) -> dict[str, Path]:
    """Adapt both phases of a frozen paired run without reading references."""

    paired_output = paired_output.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise SemanticEvaluationError(f"output already exists: {destination}")
    manifest, _ = _read_json_bytes(
        paired_output / "frozen-manifest.json", "frozen-manifest.json"
    )
    frozen_files = manifest.get("files")
    raw_results = manifest.get("results")
    if not isinstance(frozen_files, dict) or not isinstance(raw_results, list):
        raise SemanticEvaluationError("frozen manifest lacks files or results")
    configuration, _ = _verified_frozen_json(
        paired_output, "configuration.json", frozen_files
    )
    dataset_id = configuration.get("dataset_id")
    source_hashes = configuration.get("source_sha256")
    if (
        not isinstance(dataset_id, str)
        or _SAFE_DATASET_ID.fullmatch(dataset_id) is None
        or not isinstance(source_hashes, dict)
        or not source_hashes
    ):
        raise SemanticEvaluationError(
            "paired configuration lacks dataset_id or source_sha256"
        )
    for scenario_id, input_hash in source_hashes.items():
        if not isinstance(scenario_id, str) or _SAFE_CASE_ID.fullmatch(scenario_id) is None:
            raise SemanticEvaluationError("invalid paired scenario id")
        if not isinstance(input_hash, str) or _HEX64.fullmatch(input_hash) is None:
            raise SemanticEvaluationError(
                f"invalid paired input hash for {scenario_id!r}"
            )

    results: dict[str, dict[str, Any]] = {}
    for raw_result in raw_results:
        result = _as_mapping(raw_result)
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or _SAFE_CASE_ID.fullmatch(case_id) is None:
            raise SemanticEvaluationError("invalid frozen result case_id")
        if case_id in results:
            raise SemanticEvaluationError("duplicate frozen result case_id")
        results[case_id] = result
    if set(results) != set(source_hashes):
        raise SemanticEvaluationError("frozen result ids differ from configuration")

    native_by_phase: dict[str, dict[str, dict[str, Any] | None]] = {
        "baseline": {},
        "final": {},
    }
    for scenario_id, input_hash in source_hashes.items():
        result = results[scenario_id]
        status = result.get("status")
        if status not in {"succeeded", "failed_after_baseline", "failed_before_baseline"}:
            raise SemanticEvaluationError(
                f"unsupported frozen result status for {scenario_id!r}"
            )
        expects_baseline = status in {"succeeded", "failed_after_baseline"}
        expects_final = status == "succeeded"
        baseline_hash: str | None = None
        for phase, expected in (("baseline", expects_baseline), ("final", expects_final)):
            relative = f"{scenario_id}/{phase}.json"
            path = paired_output / scenario_id / f"{phase}.json"
            if expected:
                if not path.is_file():
                    if phase == "final":
                        raise SemanticEvaluationError(
                            f"succeeded case lacks final.json: {scenario_id}"
                        )
                    raise SemanticEvaluationError(
                        f"frozen case lacks baseline.json: {scenario_id}"
                    )
                wrapper, digest = _verified_frozen_json(
                    paired_output, relative, frozen_files
                )
                _validate_wrapper_identity(
                    wrapper, scenario_id=scenario_id, input_sha256=input_hash
                )
                declared = result.get(f"{phase}_sha256")
                if declared != digest:
                    raise SemanticEvaluationError(
                        f"result {phase}_sha256 mismatch for {scenario_id!r}"
                    )
                if phase == "baseline":
                    baseline_hash = digest
                elif wrapper.get("baseline_sha256") not in {None, baseline_hash}:
                    raise SemanticEvaluationError(
                        f"final baseline_sha256 mismatch for {scenario_id!r}"
                    )
                native_by_phase[phase][scenario_id] = wrapper
            else:
                if path.exists():
                    raise SemanticEvaluationError(
                        f"unexpected {phase}.json for failed case {scenario_id!r}"
                    )
                native_by_phase[phase][scenario_id] = None
        if status != "succeeded":
            relative = f"{scenario_id}/failure.json"
            failure, _ = _verified_frozen_json(
                paired_output, relative, frozen_files
            )
            _validate_wrapper_identity(
                failure, scenario_id=scenario_id, input_sha256=input_hash
            )
            if failure.get("status") not in {None, status}:
                raise SemanticEvaluationError(
                    f"failure status mismatch for {scenario_id!r}"
                )
            if status == "failed_after_baseline" and failure.get(
                "baseline_sha256"
            ) not in {None, baseline_hash}:
                raise SemanticEvaluationError(
                    f"failure baseline_sha256 mismatch for {scenario_id!r}"
                )

    destination.mkdir(parents=True, exist_ok=False)
    paths: dict[str, Path] = {}
    try:
        for phase in ("baseline", "final"):
            cases = []
            for scenario_id in sorted(source_hashes):
                input_sha256 = source_hashes[scenario_id]
                native = native_by_phase[phase][scenario_id]
                if native is not None:
                    case = adapt_general_furniture_output(
                        native,
                        scenario_id=scenario_id,
                        input_sha256=input_sha256,
                    )
                else:
                    case = _failed_case(scenario_id, input_sha256)
                cases.append(case)
            path = destination / f"{phase}-semantic-predictions.json"
            _write_atomic(
                path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "dataset_id": dataset_id,
                    "cases": cases,
                },
            )
            paths[phase] = path
    except Exception:
        for path in paths.values():
            path.unlink(missing_ok=True)
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return paths


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze or evaluate semantic furniture predictions offline.")
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--references", type=Path)
    parser.add_argument("--native-output", type=Path)
    parser.add_argument("--paired-output", type=Path)
    parser.add_argument("--scenario-id")
    parser.add_argument("--input-sha256")
    parser.add_argument("--dataset-id", default="semantic-benchmark")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.paired_output is not None:
            if (
                args.native_output is not None
                or args.predictions is not None
                or args.references is not None
                or args.scenario_id
                or args.input_sha256
            ):
                raise SemanticEvaluationError(
                    "paired freeze accepts only --paired-output and --output"
                )
            freeze_paired_semantic_outputs(args.paired_output, args.output)
            return 0
        if args.native_output is not None:
            if args.predictions is not None or args.references is not None or not args.scenario_id or not args.input_sha256:
                raise SemanticEvaluationError("native freeze requires --native-output, --scenario-id and --input-sha256 only")
            if args.output.resolve() == args.native_output.resolve():
                raise SemanticEvaluationError("output must differ from native input")
            native = json.loads(args.native_output.read_text(encoding="utf-8"))
            case = adapt_general_furniture_output(native, scenario_id=args.scenario_id, input_sha256=args.input_sha256)
            report = {"schema_version": SCHEMA_VERSION, "dataset_id": args.dataset_id, "cases": [case]}
        else:
            if args.predictions is None or args.references is None:
                raise SemanticEvaluationError("evaluation requires --predictions and --references")
            if args.output.resolve() in {args.predictions.resolve(), args.references.resolve()}:
                raise SemanticEvaluationError("output must differ from inputs")
            report = evaluate_semantic_files(args.predictions, args.references)
    except (OSError, UnicodeError, json.JSONDecodeError, SemanticEvaluationError) as exc:
        raise SystemExit(f"semantic evaluation input error: {exc}") from exc
    try:
        _write_atomic(args.output, report)
    except SemanticEvaluationError as exc:
        raise SystemExit(f"semantic evaluation input error: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
