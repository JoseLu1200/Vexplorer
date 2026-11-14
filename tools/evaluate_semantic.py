"""Freeze native semantic output or evaluate a frozen file offline."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from evaluation.semantic import (
    SCHEMA_VERSION,
    SemanticEvaluationError,
    compare_semantic_reports,
    evaluate_semantic_files,
)


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

    payload = _as_mapping(native_output)
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

    def unique_relations(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[tuple[str, str, str]] = set()
        result = []
        for row in rows:
            key = (row["subject_role"], row["relation"], row["object_role"])
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

    native_relations = proposal.get("assembly_relations", [])
    native_alternatives = proposal.get("assembly_alternatives", [])
    if not isinstance(native_relations, (list, tuple)) or not isinstance(native_alternatives, (list, tuple)):
        raise SemanticEvaluationError("native assembly fields must be arrays")
    assembly_relations = unique_relations([
        mapped
        for index, raw in enumerate(native_relations)
        if (mapped := adapt_relation(raw, f"native assembly_relations[{index}]")) is not None
    ])
    assembly_alternatives = []
    for index, raw in enumerate(native_alternatives):
        item = _as_mapping(raw)
        alternative_id = item.get("alternative_id")
        relations = item.get("relations")
        if not isinstance(alternative_id, str) or not alternative_id or not isinstance(relations, (list, tuple)):
            raise SemanticEvaluationError(f"native assembly_alternatives[{index}] is invalid")
        mapped_relations = unique_relations([
            mapped
            for relation_index, raw_relation in enumerate(relations)
            if (mapped := adapt_relation(raw_relation, f"native assembly_alternatives[{index}].relations[{relation_index}]")) is not None
        ])
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


def freeze_paired_semantic_outputs(
    paired_output: Path, destination: Path
) -> dict[str, Path]:
    """Adapt both phases of a frozen paired run without reading references."""

    paired_output = paired_output.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise SemanticEvaluationError(f"output already exists: {destination}")
    try:
        configuration = json.loads(
            (paired_output / "configuration.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticEvaluationError(f"cannot read paired configuration: {exc}") from exc
    dataset_id = configuration.get("dataset_id")
    source_hashes = configuration.get("source_sha256")
    if (
        not isinstance(dataset_id, str)
        or not dataset_id
        or not isinstance(source_hashes, dict)
        or not source_hashes
    ):
        raise SemanticEvaluationError(
            "paired configuration lacks dataset_id or source_sha256"
        )
    destination.mkdir(parents=True, exist_ok=False)
    paths: dict[str, Path] = {}
    try:
        for phase, filename in (("baseline", "baseline.json"), ("final", "final.json")):
            cases = []
            for scenario_id in sorted(source_hashes):
                input_sha256 = source_hashes[scenario_id]
                if not isinstance(scenario_id, str) or not isinstance(input_sha256, str):
                    raise SemanticEvaluationError("paired source ids and hashes must be strings")
                native_path = paired_output / scenario_id / filename
                if native_path.is_file():
                    native = json.loads(native_path.read_text(encoding="utf-8"))
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
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--final-report", type=Path)
    parser.add_argument("--scenario-id")
    parser.add_argument("--input-sha256")
    parser.add_argument("--dataset-id", default="semantic-benchmark")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.baseline_report is not None or args.final_report is not None:
            if (
                args.baseline_report is None
                or args.final_report is None
                or args.paired_output is not None
                or args.native_output is not None
                or args.predictions is not None
                or args.references is not None
                or args.scenario_id
                or args.input_sha256
            ):
                raise SemanticEvaluationError(
                    "comparison requires only --baseline-report, --final-report and --output"
                )
            if args.output.resolve() in {
                args.baseline_report.resolve(), args.final_report.resolve()
            }:
                raise SemanticEvaluationError("output must differ from comparison inputs")
            baseline = json.loads(args.baseline_report.read_text(encoding="utf-8"))
            final = json.loads(args.final_report.read_text(encoding="utf-8"))
            report = compare_semantic_reports(baseline, final)
        elif args.paired_output is not None:
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
        elif args.native_output is not None:
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
