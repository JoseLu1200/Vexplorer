"""Reproducible offline regression evaluation for furniture similarity.

The fixtures in this module are synthetic and self-contained.  Legacy scores
freeze the pre-repair formula so a run can compare it with the current service
without reading a private benchmark or invoking an embedding provider.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    DescriptorPartFeature,
    EmbeddingMetadata,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
    RoleQuantity,
    TableDescriptorComponentFeature,
)
from backend.app.semantic.descriptor import descriptor_fingerprint
from backend.app.similarity.service import cosine_similarity, geometric_match, semantic_match


@dataclass(frozen=True)
class SyntheticFixture:
    provenance: str
    case_classes: tuple[str, ...]
    external_reference_paths: tuple[str, ...]
    query: LibraryItem
    candidates: tuple[LibraryItem, ...]
    cross_version_candidate: LibraryItem
    table_structure_pair: tuple[LibraryItem, LibraryItem]
    chain_items: tuple[LibraryItem, ...]
    relevance: dict[str, bool]
    duplicate_keys: dict[str, str]


def _roles(*rows: tuple[str, int]) -> tuple[RoleQuantity, ...]:
    return tuple(RoleQuantity(role=role, quantity=quantity) for role, quantity in rows)


def _part(length: float, width: float, thickness: float, quantity: int) -> DescriptorPartFeature:
    return DescriptorPartFeature(
        length_mm=length,
        width_mm=width,
        thickness_mm=thickness,
        quantity=quantity,
        field_states={
            "length_mm": "confirmed",
            "width_mm": "confirmed",
            "thickness_mm": "confirmed",
            "quantity": "confirmed",
        },
    )


def _shelving_descriptor(
    *,
    width: float = 900.0,
    thickness: float = 18.0,
    inner_width: float = 864.0,
    family: str = "rectangular_shelving",
    material: str = "melamine_board",
    finish: str = "white_matte",
    role_order: tuple[tuple[str, int], ...] | None = None,
) -> FurnitureDescriptorV2:
    roles = role_order or (("side_panel", 2), ("top_panel", 1), ("base_panel", 1), ("shelf", 3))
    return FurnitureDescriptorV2(
        family=family,
        dimensions=DescriptorDimensions(width_mm=width, depth_mm=300.0, height_mm=1200.0),
        roles=_roles(*roles),
        structure="top_base_between_sides",
        material=material,
        finish=finish,
        thicknesses_mm=(thickness,),
        classification_status="confirmed",
        part_features=(
            _part(1200.0, 300.0, thickness, 2),
            _part(inner_width, 300.0, thickness, 5),
        ),
        unknown_fields=(),
    )


def _table_descriptor(*, structure: str) -> FurnitureDescriptorV3:
    support_role = "side_support" if structure == "side_support_table" else "corner_support"
    support_quantity = 2 if support_role == "side_support" else 4
    return FurnitureDescriptorV3(
        dimensions=DescriptorDimensions(width_mm=1200.0, depth_mm=600.0, height_mm=750.0),
        structure=structure,
        components=(
            TableDescriptorComponentFeature(
                role="tabletop",
                quantity=1,
                length_mm=1200.0,
                width_mm=600.0,
                thickness_mm=30.0,
                field_states={"quantity": "calculated", "length_mm": "confirmed", "width_mm": "confirmed", "thickness_mm": "confirmed"},
            ),
            TableDescriptorComponentFeature(
                role=support_role,
                quantity=support_quantity,
                length_mm=720.0,
                width_mm=80.0 if support_role == "corner_support" else 560.0,
                thickness_mm=30.0,
                field_states={"quantity": "calculated", "length_mm": "confirmed", "width_mm": "confirmed", "thickness_mm": "confirmed"},
            ),
        ),
        material_tariff_id="synthetic-board",
    )


def _item(item_id: str, descriptor: FurnitureDescriptorV2 | FurnitureDescriptorV3, *, embedding: bool = False) -> LibraryItem:
    metadata = None
    if embedding:
        metadata = EmbeddingMetadata(
            model="fixture-vector-space",
            dimensions=2,
            descriptor_version=descriptor.descriptor_version,
            cache_key=f"fixture-{item_id}",
            status="generated",
        )
    return LibraryItem(
        id=item_id,
        run_id=f"run-{item_id}",
        result_revision=1,
        label=item_id,
        descriptor=descriptor,
        descriptor_fingerprint=descriptor_fingerprint(descriptor),
        created_at="2026-11-14T00:00:00Z",
        embedding=metadata,
    )


def build_synthetic_fixture() -> SyntheticFixture:
    """Build public synthetic cases without reading any local corpus answers."""
    base = _shelving_descriptor()
    reordered = _shelving_descriptor(
        role_order=(("shelf", 3), ("base_panel", 1), ("side_panel", 2), ("top_panel", 1))
    )
    candidates = (
        _item("a-hard-material", _shelving_descriptor(material="steel", finish="black_powder_coat")),
        _item("b-unknown-family", _shelving_descriptor(family="unknown")),
        _item("c-equivalent", reordered),
        _item("d-duplicate-1", base),
        _item("e-duplicate-2", reordered),
        _item("f-duplicate-3", base),
        _item("g-dimension", _shelving_descriptor(width=990.0)),
        _item("h-thickness36", _shelving_descriptor(thickness=36.0, inner_width=828.0)),
    )
    relevance = {item.id: item.id not in {"a-hard-material", "b-unknown-family"} for item in candidates}
    duplicate_keys = {
        item.id: (
            "equivalent-design"
            if item.id in {"c-equivalent", "d-duplicate-1", "e-duplicate-2", "f-duplicate-3"}
            else item.id
        )
        for item in candidates
    }
    chain_items = tuple(
        _item(f"chain-{label}", _shelving_descriptor(width=width, inner_width=width - 36.0))
        for label, width in (("a", 1000.0), ("b", 1100.0), ("c", 1210.0))
    )
    return SyntheticFixture(
        provenance="inline_synthetic_furniture_v1",
        case_classes=(
            "cross_version_abstention",
            "within_version_unknown_family_control",
            "different_table_structures",
            "same_geometry_different_material_finish",
            "thickness_18_to_36_with_864_to_828",
            "dimension_variant",
            "equivalent_reordered_roles_and_changed_ids",
            "duplicate_heavy_ranking",
            "nontransitive_group",
        ),
        external_reference_paths=(),
        query=_item("query", base),
        candidates=candidates,
        cross_version_candidate=_item("cross-version-table", _table_descriptor(structure="side_support_table")),
        table_structure_pair=(
            _item("table-side-support", _table_descriptor(structure="side_support_table")),
            _item("table-corner-support", _table_descriptor(structure="corner_support_table")),
        ),
        chain_items=chain_items,
        relevance=relevance,
        duplicate_keys=duplicate_keys,
    )


def _ratio(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0
    return min(left, right) / max(left, right)


def _legacy_score(left: FurnitureDescriptorV2, right: FurnitureDescriptorV2) -> float:
    dimensions = sum(
        _ratio(getattr(left.dimensions, field), getattr(right.dimensions, field))
        for field in ("width_mm", "depth_mm", "height_mm")
    ) / 3
    left_roles = {row.role: row.quantity for row in left.roles}
    right_roles = {row.role: row.quantity for row in right.roles}
    role_names = set(left_roles) | set(right_roles)
    role_score = sum(_ratio(left_roles.get(role), right_roles.get(role)) for role in role_names) / len(role_names)
    left_thickness = sum(left.thicknesses_mm) / len(left.thicknesses_mm)
    right_thickness = sum(right.thicknesses_mm) / len(right.thicknesses_mm)
    return round(0.6 * dimensions + 0.25 * role_score + 0.15 * _ratio(left_thickness, right_thickness), 6)


def _ranking_metrics(fixture: SyntheticFixture, ordered_ids: list[str], *, k: int) -> dict[str, Any]:
    first_relevant = next((index for index, item_id in enumerate(ordered_ids, 1) if fixture.relevance[item_id]), None)
    top = ordered_ids[:k]
    relevant_designs = {
        fixture.duplicate_keys[item_id] for item_id, relevant in fixture.relevance.items() if relevant
    }
    retrieved_relevant_designs = {
        fixture.duplicate_keys[item_id] for item_id in top if fixture.relevance[item_id]
    }
    seen: set[str] = set()
    duplicate_count = 0
    for item_id in top:
        key = fixture.duplicate_keys[item_id]
        if key in seen:
            duplicate_count += 1
        seen.add(key)
    return {
        "k": k,
        "top1_relevant": bool(top and fixture.relevance[top[0]]),
        "reciprocal_rank": 0.0 if first_relevant is None else 1 / first_relevant,
        "unique_relevant_recall_at_k": len(retrieved_relevant_designs) / len(relevant_designs),
        "duplicate_fraction_at_k": duplicate_count / k,
    }


def _current_helpers() -> tuple[Any, Any, Any, Any, Any]:
    from backend.app.similarity.service import (
        canonical_design_key,
        deduplicate_designs,
        geometric_groups,
        rank_semantic_candidates,
        technical_similarity,
    )

    return canonical_design_key, deduplicate_designs, geometric_groups, rank_semantic_candidates, technical_similarity


def _legacy_complete_link_chain(fixture: SyntheticFixture, threshold: float) -> dict[str, Any]:
    scores: dict[tuple[str, str], float] = {}
    for index, left in enumerate(fixture.chain_items):
        for right in fixture.chain_items[index + 1 :]:
            scores[(left.id, right.id)] = _legacy_score(left.descriptor, right.descriptor)  # type: ignore[arg-type]
    passing = [list(pair) for pair, score in scores.items() if score >= threshold]
    failing = [list(pair) for pair, score in scores.items() if score < threshold]
    return {
        "threshold": threshold,
        "pair_scores": {"|".join(pair): score for pair, score in scores.items()},
        "passing_edges": passing,
        "below_threshold_pairs": failing,
        "legacy_connected_component_members": [item.id for item in fixture.chain_items],
        "complete_link_groups": [["chain-a", "chain-b"]],
        "legacy_component_is_clique": not failing,
    }


def evaluate_similarity_regression() -> dict[str, Any]:
    fixture = build_synthetic_fixture()
    canonical_design_key, deduplicate_designs, geometric_groups, rank_semantic_candidates, technical_similarity = _current_helpers()

    try:
        technical_similarity(fixture.query.descriptor, fixture.cross_version_candidate.descriptor)
    except ValueError as exc:
        cross_version = {
            "left_version": fixture.query.descriptor.descriptor_version,
            "right_version": fixture.cross_version_candidate.descriptor.descriptor_version,
            "status": "excluded",
            "reason": str(exc),
            "score": None,
        }
    else:  # pragma: no cover - a regression deliberately made loud in the report
        cross_version = {
            "left_version": fixture.query.descriptor.descriptor_version,
            "right_version": fixture.cross_version_candidate.descriptor.descriptor_version,
            "status": "compared",
            "reason": None,
            "score": "unexpected",
        }

    legacy_rows = sorted(
        ((item.id, _legacy_score(fixture.query.descriptor, item.descriptor)) for item in fixture.candidates),  # type: ignore[arg-type]
        key=lambda row: (-row[1], row[0]),
    )
    ordered_ids = [item_id for item_id, _ in legacy_rows]
    service_raw_scores = {
        item.id: geometric_match(fixture.query.descriptor, item).score for item in fixture.candidates
    }
    hard_negative_ties = [
        {
            "candidate_id": item_id,
            "case_class": (
                "same_geometry_different_material_finish"
                if item_id == "a-hard-material"
                else "within_version_unknown_family_control"
            ),
            "score": score,
        }
        for item_id, score in legacy_rows
        if item_id in {"a-hard-material", "b-unknown-family"} and score == 1.0
    ]

    representatives = deduplicate_designs(fixture.candidates)
    current_rows = sorted(
        (
            (item.id, technical_similarity(fixture.query.descriptor, item.descriptor).score)
            for item in representatives
        ),
        key=lambda row: (-row[1], row[0]),
    )
    current_ordered_ids = [item_id for item_id, _ in current_rows]
    table_left, table_right = fixture.table_structure_pair
    table_comparison = technical_similarity(table_left.descriptor, table_right.descriptor)
    current_chain_groups = geometric_groups(fixture.chain_items, 0.98)

    query_semantic = fixture.query.model_copy(
        update={
            "embedding": EmbeddingMetadata(
                model="fixture-vector-space",
                dimensions=2,
                descriptor_version="furniture-v2",
                cache_key="fixture-query",
                status="generated",
            )
        }
    )
    equivalent_semantic = fixture.candidates[2].model_copy(
        update={"embedding": query_semantic.embedding.model_copy(update={"cache_key": "fixture-equivalent"})}
    )
    hard_semantic = fixture.candidates[0].model_copy(
        update={"embedding": query_semantic.embedding.model_copy(update={"cache_key": "fixture-hard"})}
    )
    equivalent_vector = (0.999, math.sqrt(1.0 - 0.999**2))
    hard_vector = (0.999546, math.sqrt(1.0 - 0.999546**2))
    equivalent_match = semantic_match(query_semantic, (1.0, 0.0), equivalent_semantic, equivalent_vector)
    hard_match = semantic_match(query_semantic, (1.0, 0.0), hard_semantic, hard_vector)
    raw_cosine_order = [
        match.library_item_id
        for match in sorted((equivalent_match, hard_match), key=lambda match: (-match.score, match.library_item_id))
    ]
    reranked = rank_semantic_candidates(
        query_semantic,
        (1.0, 0.0),
        ((equivalent_semantic, equivalent_vector), (hard_semantic, hard_vector)),
    )

    return {
        "schema_version": "similarity-regression/v1",
        "fixture_provenance": fixture.provenance,
        "case_classes": list(fixture.case_classes),
        "cross_version": cross_version,
        "geometric": {
            "legacy_raw": {
                "formula_snapshot": "pre_repair_geometric_v2_0.6_dimensions_0.25_roles_0.15_thickness",
                "formula_matches_current_raw_score": all(
                    service_raw_scores[item_id] == score for item_id, score in legacy_rows
                ),
                "service_raw_scores": service_raw_scores,
                "ordered_ids": ordered_ids,
                "ranking": _ranking_metrics(fixture, ordered_ids, k=5),
                "hard_negative_ties": hard_negative_ties,
            },
            "current_technical": {
                "ordered_design_ids": current_ordered_ids,
                "scores": {item_id: score for item_id, score in current_rows},
                "ranking": _ranking_metrics(fixture, current_ordered_ids, k=5),
            },
            "equivalence": {
                "legacy_score": _legacy_score(fixture.query.descriptor, fixture.candidates[2].descriptor),  # type: ignore[arg-type]
                "raw_fingerprints_equal": fixture.query.descriptor_fingerprint == fixture.candidates[2].descriptor_fingerprint,
                "canonical_design_keys_equal": canonical_design_key(fixture.query.descriptor) == canonical_design_key(fixture.candidates[2].descriptor),
                "changed_fields": ["roles_order", "library_and_run_ids"],
            },
            "thickness_change": {
                "from_mm": 18.0,
                "to_mm": 36.0,
                "inner_width_from_mm": 864.0,
                "inner_width_to_mm": 828.0,
                "legacy_score": _legacy_score(fixture.query.descriptor, fixture.candidates[-1].descriptor),  # type: ignore[arg-type]
                "part_feature_dimensions_used_by_legacy_score": False,
            },
            "deduplication": {
                "record_count": len(fixture.candidates),
                "design_count": len(representatives),
                "duplicate_record_count": len(fixture.candidates) - len(representatives),
                "representative_ids": [item.id for item in representatives],
            },
            "different_table_structures": {
                "score": table_comparison.score,
                "warnings": list(table_comparison.warnings),
            },
            "nontransitive_group": _legacy_complete_link_chain(fixture, 0.98)
            | {
                "current_service_groups": [list(group.member_ids) for group in current_chain_groups],
                "current_service_linkage": [group.linkage for group in current_chain_groups],
                "current_service_minimum_pair_scores": [group.minimum_pair_score for group in current_chain_groups],
            },
        },
        "semantic_fixture_boundary": {
            "vector_source": "deterministic_fixture_vectors",
            "provider_called": False,
            "actual_embedding_ranking_measured": False,
            "business_relevance_validated": False,
            "query_to_equivalent_cosine": equivalent_match.score,
            "query_to_hard_negative_cosine": hard_match.score,
            "raw_cosine_order": raw_cosine_order,
            "technical_reranked_order": [match.library_item_id for match in reranked],
            "direct_cosine_cross_check": [
                cosine_similarity((1.0, 0.0), equivalent_vector),
                cosine_similarity((1.0, 0.0), hard_vector),
            ],
        },
        "limitations": {
            "uses_hidden_benchmark_answers": False,
            "uses_actual_embeddings": False,
            "business_relevance_validated": False,
            "thresholds_are_fixture_specific": True,
            "mock_vectors_validate_only_the_provider_boundary": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the deterministic report to this JSON path")
    args = parser.parse_args(argv)
    report = evaluate_similarity_regression()
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


