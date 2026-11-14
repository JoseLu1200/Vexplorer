from __future__ import annotations

import hashlib
import json

import pytest

from evaluation.semantic import (
    SemanticEvaluationError,
    compare_semantic_reports,
    evaluate_semantic_files,
    evaluate_semantic_payloads,
)
from tools.evaluate_semantic import (
    adapt_general_furniture_output,
    freeze_paired_semantic_outputs,
    main,
)


HASH_A = "a" * 64


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


def test_optional_roles_cannot_inflate_required_recovery() -> None:
    reference = _reference(
        [
            {"label": "required top", "role": "top", "quantity": 1, "required": True},
            *[
                {
                    "label": f"optional {index}",
                    "role": f"optional_{index}",
                    "quantity": 1,
                    "required": False,
                }
                for index in range(9)
            ],
        ]
    )
    predictions = _prediction(
        [{"role": f"optional_{index}", "quantity": 1} for index in range(9)]
    )

    aggregate = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]

    assert (aggregate["component_roles"]["tp"], aggregate["component_roles"]["fn"]) == (0, 1)
    assert aggregate["component_roles"]["optional_tp"] == 9
    assert aggregate["component_roles"]["recall"] == 0.0
    assert aggregate["component_roles"]["f1"] == 0.0
    assert (aggregate["physical_occurrences"]["tp"], aggregate["physical_occurrences"]["fn"]) == (0, 1)
    assert aggregate["physical_occurrences"]["optional_tp_units"] == 9


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
    assert report["physical_occurrences"]["fn"] == 2
    assert report["physical_occurrences"]["f1"] == 0.0
    assert report["physical_occurrences"]["unknown_reference_units"] == 2
    assert report["physical_occurrences"]["coverage"] == 0.0
    assert report["physical_occurrences"]["coverage_numerator"] == 0
    assert report["physical_occurrences"]["coverage_denominator"] == 2
    assert report["physical_occurrences"]["covered_only"]["f1"] is None
    assert report["assembly_relations"]["fn"] == 1
    assert report["assembly_relations"]["f1"] == 0.0
    assert report["assembly_relations"]["coverage"] == 0.0
    assert report["assembly_relations"]["covered_only"]["f1"] is None


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
    assert report["component_roles"]["fn"] == 1
    assert report["component_roles"]["f1"] == pytest.approx(2 / 3)
    assert report["component_roles"]["covered_only"]["f1"] == 1.0
    assert report["component_roles"]["unknown_reference_roles"] == 1
    assert report["component_roles"]["coverage"] == 0.5
    assert report["physical_occurrences"]["fn"] == 1
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


def test_native_adapter_deduplicates_occurrence_edges_after_role_projection() -> None:
    native = {
        "proposal": {
            "components": [
                {"id": "top", "label": "Top", "role": "tabletop", "quantity": {"value": 1, "state": "hypothesis"}},
                {"id": "leg-a", "label": "Leg A", "role": "table_leg", "quantity": {"value": 1, "state": "hypothesis"}},
                {"id": "leg-b", "label": "Leg B", "role": "table_leg", "quantity": {"value": 1, "state": "hypothesis"}},
            ],
            "assembly_relations": [
                {"subject_component_id": "top", "relation": "supported_by", "object_component_id": "leg-a", "state": "hypothesis"},
                {"subject_component_id": "top", "relation": "supported_by", "object_component_id": "leg-b", "state": "hypothesis"},
            ],
            "assembly_alternatives": [
                {
                    "alternative_id": "fixed",
                    "relations": [
                        {"subject_component_id": "top", "relation": "fixed_to", "object_component_id": "leg-a", "state": "hypothesis"},
                        {"subject_component_id": "top", "relation": "fixed_to", "object_component_id": "leg-b", "state": "hypothesis"},
                    ],
                }
            ],
        }
    }

    case = adapt_general_furniture_output(
        native, scenario_id="opaque-01", input_sha256=HASH_A
    )

    assert case["prediction"]["assembly_relations"] == [
        {
            "subject_role": "tabletop",
            "relation": "supported_by",
            "object_role": "table_leg",
        }
    ]
    assert case["prediction"]["assembly_alternatives"] == [
        {
            "alternative_id": "fixed",
            "assembly_relations": [
                {
                    "subject_role": "tabletop",
                    "relation": "fixed_to",
                    "object_role": "table_leg",
                }
            ],
        }
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
    assert metric["fn"] == 1
    assert metric["f1"] == pytest.approx(2 / 3)
    assert metric["covered_only"]["f1"] == 1.0
    assert metric["unknown_reference_relations"] == 1
    assert metric["coverage"] == 0.5


def test_global_relation_unknown_does_not_hide_claimed_false_positive() -> None:
    reference = _reference(
        [{"label": "door", "role": "door", "quantity": 1, "required": True}],
        [{"subject_role": "door", "relation": "hinged_to", "object_role": "side_panel", "required": True}],
    )
    predictions = _prediction(
        [{"role": "door", "quantity": 1}],
        [{"subject_role": "door", "relation": "glued_to", "object_role": "side_panel"}],
        unknowns=[{"scope": "assembly_relations", "reason": "mounting remains unresolved"}],
    )

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["assembly_relations"]

    assert (metric["tp"], metric["fp"], metric["fn"]) == (0, 1, 1)
    assert metric["f1"] == 0.0
    assert metric["unknown_reference_relations"] == 1
    assert metric["coverage"] == 0.0


def test_report_separates_development_and_holdout_metrics() -> None:
    predictions = _prediction([{"role": "top", "quantity": 1}])
    predictions["cases"].append(
        {
            "scenario_id": "opaque-02",
            "input_sha256": "b" * 64,
            "prediction": {
                "components": [],
                "assembly_relations": [],
                "unknowns": [
                    {"scope": "component_roles", "reason": "inference failed"},
                    {"scope": "assembly_relations", "reason": "inference failed"},
                ],
            },
        }
    )
    reference = _reference(
        [{"label": "top", "role": "top", "quantity": 1, "required": True}]
    )
    references = _references(reference)
    references["cases"].append(
        {
            "scenario_id": "opaque-02",
            "split": "holdout",
            "family_id": "cabinet",
            "project_id": "cabinet-project-02",
            "input_sha256": "b" * 64,
            "reference": reference,
        }
    )

    report = evaluate_semantic_payloads(predictions, references)

    assert report["splits"]["development"]["case_count"] == 1
    assert report["splits"]["development"]["project_count"] == 1
    assert report["splits"]["development"]["aggregate"]["component_roles"]["f1"] == 1.0
    assert report["splits"]["holdout"]["case_count"] == 1
    assert report["splits"]["holdout"]["project_count"] == 1
    assert report["splits"]["holdout"]["aggregate"]["component_roles"]["fn"] == 1
    assert report["splits"]["holdout"]["aggregate"]["component_roles"]["coverage"] == 0.0
    assert report["project_count"] == 2
    assert report["complete_case_count"] == 1
    assert report["complete_case_rate"] == 0.5
    assert report["splits"]["development"]["complete_case_count"] == 1
    assert report["splits"]["holdout"]["complete_case_count"] == 0


def test_unknown_construction_alternatives_keep_coverage_denominator() -> None:
    reference = _reference(
        [{"label": "shelf", "role": "shelf", "quantity": 1, "required": True}],
        alternatives=[
            {
                "id": "fixed",
                "assembly_relations": [
                    {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side", "required": True}
                ],
            }
        ],
    )
    predictions = _prediction(
        [{"role": "shelf", "quantity": 1}],
        unknowns=[{"scope": "assembly_relations", "reason": "joint is hidden"}],
    )

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["construction_alternatives"]

    assert metric["fn"] == 1
    assert metric["unknown_reference_alternatives"] == 1
    assert metric["coverage_numerator"] == 0
    assert metric["coverage_denominator"] == 1
    assert metric["coverage"] == 0.0


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
        {"alternative_id": "candidate-a", "assembly_relations": [
            {"subject_role": "shelf", "relation": "fixed_to", "object_role": "side_panel"}
        ]},
        {"alternative_id": "candidate-b", "assembly_relations": [
            {"subject_role": "shelf", "relation": "adjacent_to", "object_role": "side_panel"}
        ]},
    ]

    metric = evaluate_semantic_payloads(predictions, _references(reference))["aggregate"]["construction_alternatives"]

    assert (metric["tp"], metric["fp"], metric["fn"]) == (1, 1, 0)
    assert metric["precision"] == 0.5
    assert metric["recall"] == 1.0


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
    (ok / "baseline.json").write_text(json.dumps({"outcome": {"proposal": proposal}}), encoding="utf-8")
    (ok / "final.json").write_text(
        json.dumps({"outcome": {"effective_proposal_outcome": {"proposal": proposal}}}), encoding="utf-8"
    )
    (paired / "failed").mkdir()
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
    assert report["schema_version"] == "semantic-evaluation-report/v2"
    assert report["metric_definition"] == "complete_recovery_with_explicit_coverage/v2"
    assert report["aggregate"]["component_roles"]["f1"] == 1.0
    assert "reference" not in report


def test_comparison_report_exposes_baseline_final_and_delta_without_cases() -> None:
    reference = _references(
        _reference([{"label": "top", "role": "top", "quantity": 1, "required": True}])
    )
    baseline = evaluate_semantic_payloads(
        _prediction([{"role": "top", "quantity": 1}]), reference
    )
    final = evaluate_semantic_payloads(
        _prediction(
            [],
            unknowns=[
                {"scope": "component_roles", "reason": "unresolved"},
                {"scope": "assembly_relations", "reason": "unresolved"},
            ],
        ),
        reference,
    )

    comparison = compare_semantic_reports(baseline, final)

    role = comparison["aggregate"]["component_roles"]
    assert role["baseline"]["f1"] == 1.0
    assert role["final"]["f1"] == 0.0
    assert role["delta"]["f1"] == -1.0
    assert role["delta"]["coverage"] == -1.0
    assert "cases" not in comparison


def test_comparison_rejects_different_inputs_with_same_dataset_and_counts() -> None:
    reference = _reference(
        [{"label": "top", "role": "top", "quantity": 1, "required": True}]
    )
    baseline = evaluate_semantic_payloads(
        _prediction([{"role": "top", "quantity": 1}]), _references(reference)
    )
    other_predictions = _prediction([{"role": "top", "quantity": 1}])
    other_predictions["cases"][0].update(
        scenario_id="opaque-02", input_sha256="b" * 64
    )
    other_references = _references(reference)
    other_references["cases"][0].update(
        scenario_id="opaque-02", input_sha256="b" * 64
    )
    final = evaluate_semantic_payloads(other_predictions, other_references)

    with pytest.raises(SemanticEvaluationError, match="evaluation_batch_sha256"):
        compare_semantic_reports(baseline, final)


def test_cli_writes_public_comparison_from_two_v2_reports(tmp_path) -> None:
    reference = _references(
        _reference([{"label": "top", "role": "top", "quantity": 1, "required": True}])
    )
    baseline = evaluate_semantic_payloads(
        _prediction([{"role": "top", "quantity": 1}]), reference
    )
    final = evaluate_semantic_payloads(
        _prediction([], unknowns=[{"scope": "component_roles", "reason": "unknown"}]),
        reference,
    )
    baseline_path = tmp_path / "baseline-report.json"
    final_path = tmp_path / "final-report.json"
    output = tmp_path / "comparison.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    final_path.write_text(json.dumps(final), encoding="utf-8")

    assert main([
        "--baseline-report", str(baseline_path),
        "--final-report", str(final_path),
        "--output", str(output),
    ]) == 0
    comparison = json.loads(output.read_text(encoding="utf-8"))
    assert comparison["schema_version"] == "semantic-evaluation-comparison/v2"
    assert comparison["aggregate"]["component_roles"]["delta"]["recall"] == -1.0
