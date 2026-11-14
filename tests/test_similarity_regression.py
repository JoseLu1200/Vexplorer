from __future__ import annotations

import json

from evaluation.similarity_regression import (
    build_synthetic_fixture,
    evaluate_similarity_regression,
    main,
)


def test_fixture_covers_declared_regression_classes_without_external_answers() -> None:
    fixture = build_synthetic_fixture()

    assert fixture.provenance == "inline_synthetic_furniture_v1"
    assert set(fixture.case_classes) == {
        "cross_version_abstention",
        "within_version_unknown_family_control",
        "different_table_structures",
        "same_geometry_different_material_finish",
        "thickness_18_to_36_with_864_to_828",
        "dimension_variant",
        "equivalent_reordered_roles_and_changed_ids",
        "duplicate_heavy_ranking",
        "nontransitive_group",
    }
    assert fixture.external_reference_paths == ()


def test_cross_version_comparison_abstains_instead_of_claiming_cross_family_ranking() -> None:
    comparison = evaluate_similarity_regression()["cross_version"]

    assert comparison == {
        "left_version": "furniture-v2",
        "right_version": "furniture-v3",
        "status": "excluded",
        "reason": "descriptor_space_incompatible",
        "score": None,
    }


def test_legacy_geometric_report_exposes_hard_negative_ties_and_duplicate_crowding() -> None:
    report = evaluate_similarity_regression()["geometric"]["legacy_raw"]

    assert report["formula_matches_current_raw_score"] is True
    assert report["ranking"]["top1_relevant"] is False
    assert report["ranking"]["reciprocal_rank"] == 1 / 3
    assert report["ranking"]["unique_relevant_recall_at_k"] == 1 / 3
    assert report["ranking"]["duplicate_fraction_at_k"] == 0.4
    assert report["hard_negative_ties"] == [
        {
            "candidate_id": "a-hard-material",
            "case_class": "same_geometry_different_material_finish",
            "score": 1.0,
        },
        {
            "candidate_id": "b-unknown-family",
            "case_class": "within_version_unknown_family_control",
            "score": 1.0,
        },
    ]


def test_current_geometric_ranking_improves_fixture_metrics_after_deduplication() -> None:
    ranking = evaluate_similarity_regression()["geometric"]["current_technical"]["ranking"]

    assert ranking["top1_relevant"] is True
    assert ranking["reciprocal_rank"] == 1.0
    assert ranking["unique_relevant_recall_at_k"] == 1.0
    assert ranking["duplicate_fraction_at_k"] == 0.0


def test_equivalence_and_thickness_cases_report_observed_score_inputs() -> None:
    geometric = evaluate_similarity_regression()["geometric"]

    assert geometric["equivalence"] == {
        "legacy_score": 1.0,
        "raw_fingerprints_equal": False,
        "canonical_design_keys_equal": True,
        "changed_fields": ["roles_order", "library_and_run_ids"],
    }
    assert geometric["thickness_change"] == {
        "from_mm": 18.0,
        "to_mm": 36.0,
        "inner_width_from_mm": 864.0,
        "inner_width_to_mm": 828.0,
        "legacy_score": 0.925,
        "part_feature_dimensions_used_by_legacy_score": False,
    }


def test_duplicate_aware_report_counts_records_and_designs_separately() -> None:
    dedupe = evaluate_similarity_regression()["geometric"]["deduplication"]

    assert dedupe["record_count"] == 8
    assert dedupe["design_count"] == 5
    assert dedupe["duplicate_record_count"] == 3
    assert dedupe["representative_ids"] == [
        "a-hard-material",
        "b-unknown-family",
        "f-duplicate-3",
        "g-dimension",
        "h-thickness36",
    ]


def test_nontransitive_groups_compare_legacy_connectivity_with_complete_link() -> None:
    groups = evaluate_similarity_regression()["geometric"]["nontransitive_group"]

    assert groups["threshold"] == 0.98
    assert groups["passing_edges"] == [["chain-a", "chain-b"], ["chain-b", "chain-c"]]
    assert groups["below_threshold_pairs"] == [["chain-a", "chain-c"]]
    assert groups["legacy_connected_component_members"] == ["chain-a", "chain-b", "chain-c"]
    assert groups["complete_link_groups"] == [["chain-a", "chain-b"]]
    assert groups["legacy_component_is_clique"] is False
    assert len(groups["current_service_groups"]) == 1
    assert groups["current_service_groups"][0] in groups["passing_edges"]
    assert len(groups["current_service_groups"][0]) == 2
    assert groups["current_service_linkage"] == ["complete"]
    assert groups["current_service_minimum_pair_scores"][0] >= 0.98


def test_fake_semantic_vectors_are_explicit_and_not_claimed_as_provider_quality() -> None:
    semantic = evaluate_similarity_regression()["semantic_fixture_boundary"]

    assert semantic["vector_source"] == "deterministic_fixture_vectors"
    assert semantic["provider_called"] is False
    assert semantic["actual_embedding_ranking_measured"] is False
    assert semantic["business_relevance_validated"] is False
    assert semantic["query_to_equivalent_cosine"] == 0.999
    assert semantic["query_to_hard_negative_cosine"] == 0.999546
    assert semantic["raw_cosine_order"] == ["a-hard-material", "c-equivalent"]
    assert semantic["technical_reranked_order"] == ["c-equivalent", "a-hard-material"]


def test_report_is_reproducible_and_cli_writes_json(tmp_path) -> None:
    first = evaluate_similarity_regression()
    second = evaluate_similarity_regression()
    assert first == second

    output = tmp_path / "nested" / "reports" / "similarity-report.json"
    assert main(["--output", str(output)]) == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written == first
    assert written["limitations"]["uses_hidden_benchmark_answers"] is False
    assert written["limitations"]["uses_actual_embeddings"] is False
    assert written["limitations"]["business_relevance_validated"] is False


