from __future__ import annotations

import hashlib
import json

import pytest

from evaluation.semantic import SemanticEvaluationError, evaluate_semantic_files, evaluate_semantic_payloads
from tools.evaluate_semantic import (
    adapt_general_furniture_output,
    freeze_paired_semantic_outputs,
    main,
)


HASH_A = "a" * 64


def _file_sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal_paired(paired, results) -> None:
    files = {
        path.relative_to(paired).as_posix(): _file_sha(path)
        for path in sorted(paired.rglob("*"))
        if path.is_file() and path.name != "frozen-manifest.json"
    }
    (paired / "frozen-manifest.json").write_text(
        json.dumps({"results": results, "files": files}), encoding="utf-8"
    )


def _prediction(components, relations=(), unknowns=(), *, alternative_id=None):
    prediction = {
        "components": list(components),
        "assembly_relations": list(relations),
        "unknowns": list(unknowns),
    }
    if alternative_id is not None:
        prediction["alternative_id"] = alternative_id
    return {
        "schema_version": "semantic-evaluation/v1",
        "dataset_id": "developer-semantic",
        "cases": [
            {
                "scenario_id": "opaque-01",
                "input_sha256": HASH_A,
                "prediction": prediction,
            }
        ],
    }


def _references(reference, *, predictions_sha256="0" * 64):
    return {
        "schema_version": "semantic-evaluation/v1",
        "dataset": {
            "id": "developer-semantic",
            "predictions_sha256": predictions_sha256,
            "frozen_before_evaluation": True,
            "partition_policy": "project_and_family",
            "reference_visibility": "evaluator_only",
        },
        "cases": [
            {
                "scenario_id": "opaque-01",
                "split": "development",
                "family_id": "desk",
                "project_id": "desk-project-01",
                "input_sha256": HASH_A,
                "reference": reference,
            }
        ],
    }


def _reference(components, relations=(), alternatives=(), ambiguity=()):
    return {
        "certification": "design_known_synthetic",
        "components": list(components),
        "assembly_relations": list(relations),
        "valid_alternatives": list(alternatives),
        "ambiguity": list(ambiguity),
    }


def test_equal_size_components_are_scored_by_role_not_geometry() -> None:
    reference = _reference(
        [
            {"label": "top", "role": "work_surface", "quantity": 1, "required": True},
            {"label": "modesty", "role": "modesty_panel", "quantity": 1, "required": True},
        ]
    )
    predictions = _prediction(
        [
            {"label": "same 1200x400", "role": "work_surface", "quantity": 1},
            {"label": "same 1200x400", "role": "shelf", "quantity": 1},
        ]
    )

    report = evaluate_semantic_payloads(predictions, _references(reference))

    assert report["aggregate"]["component_roles"]["tp"] == 1
    assert report["aggregate"]["component_roles"]["fp"] == 1
    assert report["aggregate"]["component_roles"]["fn"] == 1
    assert report["aggregate"]["component_roles"]["precision"] == 0.5
    assert report["aggregate"]["component_roles"]["recall"] == 0.5
    assert report["aggregate"]["component_roles"]["f1"] == 0.5


def test_omitted_and_excess_physical_occurrences_remain_in_denominator() -> None:
    reference = _reference(
        [
            {"label": "sides", "role": "side_panel", "quantity": 2, "required": True},
            {"label": "shelf", "role": "shelf", "quantity": 3, "required": True},
        ]
    )
    predictions = _prediction(
        [
            {"role": "side_panel", "quantity": 1},
            {"role": "shelf", "quantity": 4},
        ]
    )

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"][
        "physical_occurrences"
    ]

    assert (metric["tp"], metric["fp"], metric["fn"]) == (4, 1, 1)
    assert metric["precision"] == 0.8
    assert metric["recall"] == 0.8
    assert metric["coverage"] == 1.0


def test_complete_legitimate_alternative_is_not_penalized() -> None:
    reference = _reference(
        [{"label": "plinth", "role": "plinth", "quantity": 1, "required": True}],
        [{"subject_role": "plinth", "relation": "supports", "object_role": "cabinet", "required": True}],
        alternatives=[
            {
                "id": "four-legs",
                "components": [
                    {"label": "legs", "role": "leg", "quantity": 4, "required": True}
                ],
                "assembly_relations": [
                    {"subject_role": "leg", "relation": "supports", "object_role": "cabinet", "required": True}
                ],
            }
        ],
    )
    predictions = _prediction(
        [{"role": "leg", "quantity": 4}],
        [{"subject_role": "leg", "relation": "supports", "object_role": "cabinet"}],
    )

    report = evaluate_semantic_payloads(predictions, _references(reference))

    assert report["cases"][0]["matched_variant"] == "four-legs"
    assert report["aggregate"]["physical_occurrences"]["f1"] == 1.0
    assert report["aggregate"]["assembly_relations"]["f1"] == 1.0


def test_declared_quantity_ambiguity_accepts_each_documented_value_only() -> None:
    reference = _reference(
        [{"label": "doors", "role": "door", "quantity": 2, "required": True}],
        ambiguity=[
            {
                "scope": "component:door.quantity",
                "reason": "one leaf is hidden in the supplied view",
                "acceptable_values": [1, 2],
            }
        ],
    )

    accepted = evaluate_semantic_payloads(
        _prediction([{"role": "door", "quantity": 1}]), _references(reference)
    )
    rejected = evaluate_semantic_payloads(
        _prediction([{"role": "door", "quantity": 3}]), _references(reference)
    )

    assert accepted["aggregate"]["physical_occurrences"]["f1"] == 1.0
    assert rejected["aggregate"]["physical_occurrences"]["fp"] == 1


def test_explicit_unknown_quantity_and_mounting_reduce_coverage_not_accuracy() -> None:
    reference = _reference(
        [{"label": "doors", "role": "door", "quantity": 2, "required": True}],
        [{"subject_role": "door", "relation": "hinged_to", "object_role": "side_panel", "required": True}],
    )
    predictions = _prediction(
        [{"role": "door", "quantity": None}],
        unknowns=[
            {"scope": "component:door.quantity", "reason": "views overlap"},
            {"scope": "assembly_relations", "reason": "runtime has no assembly graph"},
        ],
    )

    report = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]

    assert report["component_roles"]["f1"] == 1.0
    assert report["physical_occurrences"]["tp"] == 0
    assert report["physical_occurrences"]["fn"] == 0
    assert report["physical_occurrences"]["unknown_reference_units"] == 2
    assert report["physical_occurrences"]["coverage"] == 0.0
    assert report["assembly_relations"]["f1"] is None
    assert report["assembly_relations"]["coverage"] == 0.0


def test_unknown_component_function_reduces_coverage_without_false_error() -> None:
    reference = _reference(
        [
            {"label": "top", "role": "work_surface", "quantity": 1, "required": True},
            {"label": "panel", "role": "modesty_panel", "quantity": 1, "required": True},
        ]
    )
    predictions = _prediction(
        [{"role": "work_surface", "quantity": 1}],
        unknowns=[{"scope": "component_roles", "reason": "second panel function is occluded"}],
    )

    report = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]

    assert report["component_roles"]["tp"] == 1
    assert report["component_roles"]["fn"] == 0
    assert report["component_roles"]["unknown_reference_roles"] == 1
    assert report["component_roles"]["coverage"] == 0.5
    assert report["physical_occurrences"]["fn"] == 0
    assert report["physical_occurrences"]["unknown_reference_units"] == 1


def test_private_reference_requires_exact_frozen_prediction_hash(tmp_path) -> None:
    predictions = _prediction([{"role": "top", "quantity": 1}])
    prediction_path = tmp_path / "predictions.json"
    prediction_path.write_text(json.dumps(predictions, sort_keys=True), encoding="utf-8")
    reference = _reference(
        [{"label": "top", "role": "top", "quantity": 1, "required": True}]
    )
    references = _references(reference, predictions_sha256="f" * 64)
    reference_path = tmp_path / "private-reference.json"
    reference_path.write_text(json.dumps(references), encoding="utf-8")

    with pytest.raises(SemanticEvaluationError, match="predictions_sha256 mismatch"):
        evaluate_semantic_files(prediction_path, reference_path)

    references["dataset"]["predictions_sha256"] = hashlib.sha256(
        prediction_path.read_bytes()
    ).hexdigest()
    reference_path.write_text(json.dumps(references), encoding="utf-8")
    assert evaluate_semantic_files(prediction_path, reference_path)["case_count"] == 1


def test_family_project_and_input_hash_cannot_cross_splits() -> None:
    prediction_case = _prediction([{"role": "top", "quantity": 1}])["cases"][0]
    predictions = {
        "schema_version": "semantic-evaluation/v1",
        "dataset_id": "developer-semantic",
        "cases": [
            prediction_case,
            prediction_case
            | {"scenario_id": "opaque-02", "input_sha256": "b" * 64},
        ],
    }
    refs = _references(_reference([{"label": "top", "role": "top", "quantity": 1, "required": True}]))
    refs["cases"].append(
        refs["cases"][0]
        | {
            "scenario_id": "opaque-02",
            "split": "holdout",
            "project_id": "other-project",
            "input_sha256": "b" * 64,
        }
    )

    with pytest.raises(SemanticEvaluationError, match="family_id.*crosses splits"):
        evaluate_semantic_payloads(predictions, refs)


def test_sealed_corpus_private_extras_use_structural_signature_as_family() -> None:
    predictions = _prediction([{"role": "top", "quantity": 1}])
    predictions["cases"].append(
        predictions["cases"][0] | {"scenario_id": "opaque-02", "input_sha256": "b" * 64}
    )
    refs = _references(
        _reference([{"label": "top", "role": "top", "quantity": 1, "required": True}])
    )
    refs["dataset"]["partition_unit"] = "project_id+structural_signature"
    first = refs["cases"][0]
    first.pop("family_id")
    first.update(
        schema_version="semantic-reference/v1",
        product_family="table",
        structural_signature="four-legs",
        view_profile="front-side",
        design_geometry={"private": True},
    )
    refs["cases"].append(
        first
        | {
            "scenario_id": "opaque-02",
            "split": "holdout",
            "project_id": "desk-project-02",
            "structural_signature": "trestle",
            "input_sha256": "b" * 64,
        }
    )

    assert evaluate_semantic_payloads(predictions, refs)["case_count"] == 2


def test_strict_schema_rejects_oracle_ids_in_predictions() -> None:
    predictions = _prediction([{"role": "top", "quantity": 1, "oracle_id": "answer-7"}])
    refs = _references(
        _reference([{"label": "top", "role": "top", "quantity": 1, "required": True}])
    )

    with pytest.raises(SemanticEvaluationError, match="unexpected fields.*oracle_id"):
        evaluate_semantic_payloads(predictions, refs)


def test_native_adapter_uses_public_roles_and_preserves_unsupported_mounting_as_unknown() -> None:
    native = {
        "proposal": {
            "schema_version": "0.6.0",
            "components": [
                {
                    "id": "private-runtime-id-not-exported",
                    "label": "Costado",
                    "kind": "panel",
                    "role": "side_panel",
                    "quantity": {"value": 2, "state": "hypothesis"},
                },
                {
                    "id": "other-id",
                    "label": "Puerta",
                    "kind": "panel",
                    "role": "door",
                    "quantity": {"value": None, "state": "unknown"},
                },
            ],
        }
    }

    prediction = adapt_general_furniture_output(
        native, scenario_id="opaque-01", input_sha256=HASH_A
    )

    assert prediction["scenario_id"] == "opaque-01"
    assert prediction["prediction"]["components"] == [
        {"label": "Costado", "role": "side_panel", "quantity": 2},
        {"label": "Puerta", "role": "door", "quantity": None},
    ]
    assert prediction["prediction"]["assembly_relations"] == []
    assert {item["scope"] for item in prediction["prediction"]["unknowns"]} == {
        "component:door.quantity",
        "assembly_relations",
    }
    assert "private-runtime-id-not-exported" not in json.dumps(prediction)


def test_native_adapter_maps_hypothesis_relations_and_preserves_alternatives() -> None:
    native = {
        "proposal": {
            "components": [
                {"id": "s", "label": "Shelf", "role": "shelf", "quantity": {"value": 1, "state": "hypothesis"}},
                {"id": "p", "label": "Side", "role": "side_panel", "quantity": {"value": 2, "state": "hypothesis"}},
            ],
            "assembly_relations": [
                {"subject_component_id": "s", "relation": "supported_by", "object_component_id": "p", "state": "hypothesis"}
            ],
            "assembly_alternatives": [
                {"alternative_id": "fixed", "relations": [
                    {"subject_component_id": "s", "relation": "fixed_to", "object_component_id": "p", "state": "hypothesis"}
                ]}
            ],
        }
    }

    case = adapt_general_furniture_output(native, scenario_id="opaque-01", input_sha256=HASH_A)

    assert case["prediction"]["assembly_relations"] == [
        {"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel"}
    ]
    assert case["prediction"]["assembly_alternatives"] == [
        {"alternative_id": "fixed", "assembly_relations": [
            {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel"}
        ]}
    ]


def test_relation_specific_unknown_does_not_erase_known_relation_score() -> None:
    reference = _reference(
        [{"label": "shelf", "role": "shelf", "quantity": 1, "required": True}],
        [
            {"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel", "required": True},
            {"subject_role": "door", "relation": "hinged_to", "object_role": "side_panel", "required": True},
        ],
    )
    predictions = _prediction(
        [{"role": "shelf", "quantity": 1}],
        [{"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel"}],
        unknowns=[{"scope": "assembly_relation:door:side_panel", "reason": "hinge is hidden"}],
    )

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["assembly_relations"]

    assert metric["tp"] == 1
    assert metric["fn"] == 0
    assert metric["unknown_reference_relations"] == 1
    assert metric["coverage"] == 0.5


def test_predicted_construction_alternatives_measure_supported_set() -> None:
    reference = _reference(
        [{"label": "shelf", "role": "shelf", "quantity": 1, "required": True}],
        [{"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel", "required": True}],
        alternatives=[
            {
                "id": "fixed",
                "assembly_relations": [
                    {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel", "required": True}
                ],
            }
        ],
    )
    predictions = _prediction(
        [{"role": "shelf", "quantity": 1}],
        [{"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel"}],
    )
    predictions["cases"][0]["prediction"]["assembly_alternatives"] = [
        {"alternative_id": "candidate-base", "assembly_relations": [
            {"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel"}
        ]},
        {"alternative_id": "candidate-a", "assembly_relations": [
            {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel"}
        ]},
        {"alternative_id": "candidate-b", "assembly_relations": [
            {"subject_role": "shelf", "relation": "adjacent_to", "object_role": "side_panel"}
        ]},
    ]

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["construction_alternatives"]

    assert (metric["tp"], metric["fp"], metric["fn"]) == (2, 1, 0)
    assert metric["precision"] == pytest.approx(2 / 3)
    assert metric["recall"] == 1.0


def test_native_shaped_two_construction_alternatives_score_perfectly() -> None:
    reference = _reference(
        [{"label": "shelf", "role": "shelf", "quantity": 1, "required": True}],
        [{"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel", "required": True}],
        alternatives=[
            {"id": "fixed", "assembly_relations": [
                {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel", "required": True}
            ]}
        ],
    )
    predictions = _prediction([{"role": "shelf", "quantity": 1}])
    predictions["cases"][0]["prediction"]["assembly_alternatives"] = [
        {"alternative_id": "supported", "assembly_relations": [
            {"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel"}
        ]},
        {"alternative_id": "fixed", "assembly_relations": [
            {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel"}
        ]},
    ]

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["construction_alternatives"]

    assert (metric["tp"], metric["fp"], metric["fn"]) == (2, 0, 0)
    assert metric["f1"] == 1.0
    assert metric["coverage"] == 1.0
    assert metric["unknown_reference_alternatives"] == 0


def test_unknown_construction_alternatives_reduce_coverage_without_false_negative() -> None:
    reference = _reference(
        [{"label": "shelf", "role": "shelf", "quantity": 1, "required": True}],
        [{"subject_role": "shelf", "relation": "supported_by", "object_role": "side_panel", "required": True}],
        alternatives=[
            {"id": "fixed", "assembly_relations": [
                {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel", "required": True}
            ]}
        ],
    )
    predictions = _prediction(
        [{"role": "shelf", "quantity": 1}],
        unknowns=[{"scope": "assembly_relations", "reason": "joint is hidden"}],
    )

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["construction_alternatives"]

    assert (metric["tp"], metric["fp"], metric["fn"]) == (0, 0, 0)
    assert metric["f1"] is None
    assert metric["coverage"] == 0.0
    assert metric["unknown_reference_alternatives"] == 2


def test_batch_adapter_reads_paired_wrappers_and_keeps_failed_case(tmp_path) -> None:
    paired = tmp_path / "paired"
    paired.mkdir()
    (paired / "configuration.json").write_text(
        json.dumps({"dataset_id": "public-run", "source_sha256": {"ok": HASH_A, "failed": "b" * 64}}),
        encoding="utf-8",
    )
    ok = paired / "ok"
    ok.mkdir()
    proposal = {
        "components": [{"id": "c", "label": "Top", "role": "work_surface", "quantity": {"value": 1, "state": "hypothesis"}}],
        "assembly_relations": [],
        "assembly_alternatives": [],
    }
    baseline_path = ok / "baseline.json"
    baseline_path.write_text(
        json.dumps({"case_id": "ok", "input_sha256": HASH_A, "outcome": {"proposal": proposal}}),
        encoding="utf-8",
    )
    final_path = ok / "final.json"
    final_path.write_text(
        json.dumps({"case_id": "ok", "input_sha256": HASH_A, "outcome": {"effective_proposal_outcome": {"proposal": proposal}}}),
        encoding="utf-8",
    )
    failed = paired / "failed"
    failed.mkdir()
    failure_path = failed / "failure.json"
    failure_path.write_text(
        json.dumps({"case_id": "failed", "input_sha256": "b" * 64, "status": "failed_before_baseline"}),
        encoding="utf-8",
    )
    _seal_paired(
        paired,
        [
            {"case_id": "ok", "status": "succeeded", "baseline_sha256": _file_sha(baseline_path), "final_sha256": _file_sha(final_path)},
            {"case_id": "failed", "status": "failed_before_baseline"},
        ],
    )
    destination = tmp_path / "semantic"

    paths = freeze_paired_semantic_outputs(paired, destination)

    assert set(paths) == {"baseline", "final"}
    final = json.loads(paths["final"].read_text(encoding="utf-8"))
    assert [case["scenario_id"] for case in final["cases"]] == ["failed", "ok"]
    assert final["cases"][0]["prediction"]["components"] == []
    assert {item["scope"] for item in final["cases"][0]["prediction"]["unknowns"]} >= {
        "component_roles", "assembly_relations"
    }
    assert final["cases"][1]["prediction"]["components"][0]["role"] == "work_surface"
    assert final["cases"][1]["prediction"]["components"][0]["quantity"] is None


def test_batch_adapter_rejects_unsafe_scenario_id_before_path_resolution(tmp_path) -> None:
    paired = tmp_path / "paired"
    paired.mkdir()
    config = paired / "configuration.json"
    config.write_text(
        json.dumps({"dataset_id": "public-run", "source_sha256": {"../escape": HASH_A}}),
        encoding="utf-8",
    )
    _seal_paired(paired, [{"case_id": "../escape", "status": "failed_before_baseline"}])

    with pytest.raises(SemanticEvaluationError, match="invalid paired scenario id"):
        freeze_paired_semantic_outputs(paired, tmp_path / "out")


def test_batch_adapter_rejects_tampered_configuration_hash(tmp_path) -> None:
    paired = tmp_path / "paired"
    paired.mkdir()
    config = paired / "configuration.json"
    config.write_text(
        json.dumps({"dataset_id": "public-run", "source_sha256": {"case-1": HASH_A}}),
        encoding="utf-8",
    )
    _seal_paired(paired, [{"case_id": "case-1", "status": "failed_before_baseline"}])
    config.write_text(config.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(SemanticEvaluationError, match="frozen hash mismatch.*configuration.json"):
        freeze_paired_semantic_outputs(paired, tmp_path / "out")


@pytest.mark.parametrize("mismatch", ["case_id", "input_sha256"])
def test_batch_adapter_rejects_native_wrapper_identity_mismatch(tmp_path, mismatch) -> None:
    paired = tmp_path / "paired"
    paired.mkdir()
    config = paired / "configuration.json"
    config.write_text(
        json.dumps({"dataset_id": "public-run", "source_sha256": {"case-1": HASH_A}}),
        encoding="utf-8",
    )
    case_dir = paired / "case-1"
    case_dir.mkdir()
    proposal = {
        "components": [{"id": "c", "label": "Top", "role": "top", "quantity": {"value": 1, "state": "hypothesis"}}]
    }
    wrapper = {"case_id": "case-1", "input_sha256": HASH_A, "outcome": {"proposal": proposal}}
    wrapper[mismatch] = "wrong" if mismatch == "case_id" else "b" * 64
    baseline = case_dir / "baseline.json"
    baseline.write_text(json.dumps(wrapper), encoding="utf-8")
    failure = case_dir / "failure.json"
    failure.write_text(
        json.dumps({"case_id": "case-1", "input_sha256": HASH_A, "status": "failed_after_baseline"}),
        encoding="utf-8",
    )
    _seal_paired(
        paired,
        [{"case_id": "case-1", "status": "failed_after_baseline", "baseline_sha256": _file_sha(baseline)}],
    )

    with pytest.raises(SemanticEvaluationError, match=f"native wrapper {mismatch} mismatch"):
        freeze_paired_semantic_outputs(paired, tmp_path / "out")


def test_batch_adapter_rejects_missing_final_for_succeeded_case(tmp_path) -> None:
    paired = tmp_path / "paired"
    paired.mkdir()
    (paired / "configuration.json").write_text(
        json.dumps({"dataset_id": "public-run", "source_sha256": {"case-1": HASH_A}}),
        encoding="utf-8",
    )
    case_dir = paired / "case-1"
    case_dir.mkdir()
    proposal = {
        "components": [{"id": "c", "label": "Top", "role": "top", "quantity": {"value": 1, "state": "hypothesis"}}]
    }
    baseline = case_dir / "baseline.json"
    baseline.write_text(
        json.dumps({"case_id": "case-1", "input_sha256": HASH_A, "outcome": {"proposal": proposal}}),
        encoding="utf-8",
    )
    _seal_paired(
        paired,
        [{"case_id": "case-1", "status": "succeeded", "baseline_sha256": _file_sha(baseline), "final_sha256": "b" * 64}],
    )

    with pytest.raises(SemanticEvaluationError, match="succeeded case lacks final.json"):
        freeze_paired_semantic_outputs(paired, tmp_path / "out")


def test_final_adapter_exports_only_review_accepted_quantity() -> None:
    component = {
        "id": "c",
        "label": "Top",
        "role": "work_surface",
        "quantity": {"value": 1, "state": "hypothesis"},
    }
    final = {
        "outcome": {
            "effective_proposal_outcome": {"proposal": {"components": [component]}},
            "review": {
                "machine_field_reviews": [
                    {"target_ref": "component:c.quantity", "status": "rejected"}
                ]
            },
        }
    }

    case = adapt_general_furniture_output(final, scenario_id="opaque-01", input_sha256=HASH_A)

    assert case["prediction"]["components"][0]["quantity"] is None
    assert "component:work_surface.quantity" in {
        item["scope"] for item in case["prediction"]["unknowns"]
    }


def test_freeze_refuses_to_overwrite_an_existing_output(tmp_path) -> None:
    native = tmp_path / "native.json"
    native.write_text(
        json.dumps({"proposal": {"components": [{"label": "Top", "role": "top", "quantity": {"value": 1, "state": "hypothesis"}}]}}),
        encoding="utf-8",
    )
    output = tmp_path / "frozen.json"
    output.write_text("do-not-replace", encoding="utf-8")

    with pytest.raises(SystemExit, match="output already exists"):
        main([
            "--native-output", str(native), "--scenario-id", "opaque-01",
            "--input-sha256", HASH_A, "--output", str(output),
        ])
    assert output.read_text(encoding="utf-8") == "do-not-replace"


def test_cli_writes_aggregate_report_for_frozen_files(tmp_path) -> None:
    predictions = _prediction([{"role": "top", "quantity": 1}])
    prediction_path = tmp_path / "predictions.json"
    prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
    refs = _references(
        _reference([{"label": "top", "role": "top", "quantity": 1, "required": True}]),
        predictions_sha256=hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
    )
    reference_path = tmp_path / "private.json"
    reference_path.write_text(json.dumps(refs), encoding="utf-8")
    output = tmp_path / "report.json"

    assert main(["--predictions", str(prediction_path), "--references", str(reference_path), "--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["aggregate"]["component_roles"]["f1"] == 1.0
    assert "reference" not in report
