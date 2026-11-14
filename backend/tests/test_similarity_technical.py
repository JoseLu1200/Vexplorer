from __future__ import annotations

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    DescriptorPartFeature,
    EmbeddingMetadata,
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
    RoleQuantity,
    TableDescriptorComponentFeature,
)
from backend.app.similarity.service import (
    canonical_design_key,
    deduplicate_designs,
    geometric_match,
    geometric_groups,
    rank_semantic_candidates,
    semantic_groups,
    semantic_match,
    technical_similarity,
)


def _parts_descriptor(
    *,
    length_mm: float = 864,
    thickness_mm: float | None = 18,
    quantity: int | None = 2,
    material: str | None = "plywood",
    finish: str | None = "clear lacquer",
) -> FurnitureDescriptorV2:
    feature_unknowns = tuple(
        field
        for field, value in (("thickness_mm", thickness_mm), ("quantity", quantity))
        if value is None
    )
    return FurnitureDescriptorV2(
        family="rectangular_shelving",
        dimensions=DescriptorDimensions(width_mm=900, depth_mm=300, height_mm=1200),
        roles=(RoleQuantity(role="side_panel", quantity=quantity),),
        structure="top_base_between_sides",
        material=material,
        finish=finish,
        thicknesses_mm=() if thickness_mm is None else (thickness_mm,),
        classification_status="confirmed",
        part_features=(
            DescriptorPartFeature(
                length_mm=length_mm,
                width_mm=300,
                thickness_mm=thickness_mm,
                quantity=quantity,
                unknown_fields=feature_unknowns,
            ),
        ),
        unknown_fields=tuple(
            field
            for field, value in (("material", material), ("finish", finish))
            if value is None
        ),
    )


def _item(
    identifier: str, descriptor, *, vector_space: bool = False, revision: int = 1
) -> LibraryItem:
    return LibraryItem(
        id=identifier,
        run_id=f"run-{identifier.split('-')[0]}",
        result_revision=revision,
        label=identifier,
        descriptor=descriptor,
        descriptor_fingerprint=(identifier[0] * 64),
        created_at=f"2026-11-14T00:00:0{min(revision, 9)}Z",
        embedding=(
            EmbeddingMetadata(
                model="test-embedding",
                dimensions=2,
                descriptor_version=descriptor.descriptor_version,
                cache_key=f"cache-{identifier}",
                status="generated",
            )
            if vector_space
            else None
        ),
    )


def test_semantic_cosine_is_separate_from_piece_level_technical_similarity() -> None:
    query = _item("a-query", _parts_descriptor(length_mm=864), vector_space=True)
    candidate = _item(
        "b-candidate", _parts_descriptor(length_mm=828), vector_space=True
    )

    match = semantic_match(query, (1.0, 0.0), candidate, (1.0, 0.0))

    assert match.score == 1.0 and match.score_kind == "cosine_similarity"
    assert match.technical_score < 1.0
    assert any(
        difference.field == "part_features[0].length_mm"
        and difference.query_value == "864.0"
        and difference.candidate_value == "828.0"
        for difference in match.differences
    )


def test_technical_comparison_penalizes_material_finish_thickness_and_quantity() -> (
    None
):
    comparison = technical_similarity(
        _parts_descriptor(),
        _parts_descriptor(
            thickness_mm=25, quantity=1, material="mdf", finish="painted"
        ),
    )

    assert 0.0 <= comparison.score < 1.0
    assert comparison.components["part_features"] < 1.0
    assert {difference.field for difference in comparison.differences} >= {
        "material",
        "finish",
        "part_features[0].thickness_mm",
        "part_features[0].quantity",
    }


def test_unknown_piece_values_reduce_evidence_instead_of_counting_as_matches() -> None:
    known = technical_similarity(_parts_descriptor(), _parts_descriptor())
    unknown = technical_similarity(
        _parts_descriptor(),
        _parts_descriptor(thickness_mm=None, quantity=None, material=None, finish=None),
    )

    assert known.score == 1.0
    assert unknown.score < known.score
    assert unknown.components["evidence_coverage"] < 1.0
    assert "technical_fields_unknown" in unknown.warnings


def test_complete_link_semantic_groups_do_not_make_similarity_chains_homogeneous() -> (
    None
):
    descriptor = _parts_descriptor()
    items = tuple(
        _item(identifier, descriptor, vector_space=True)
        for identifier in ("a", "b", "c")
    )
    vectors = {"a": (1.0, 0.0), "b": (0.8660254038, 0.5), "c": (0.5, 0.8660254038)}

    forward = semantic_groups(items, vectors, 0.8)
    reverse = semantic_groups(tuple(reversed(items)), vectors, 0.8)

    assert forward == reverse
    assert [group.member_ids for group in forward] == [("a", "b")]
    assert forward[0].linkage == "complete"


def test_complete_link_geometric_groups_skip_incompatible_descriptor_spaces() -> None:
    def legacy(identifier: str, width: float) -> LibraryItem:
        return _item(
            identifier,
            FurnitureDescriptor(
                family="rectangular_shelving",
                dimensions=DescriptorDimensions(
                    width_mm=width, depth_mm=100, height_mm=100
                ),
                roles=(RoleQuantity(role="panel", quantity=1),),
                structure="unknown",
                unknown_fields=("structure", "material", "finish"),
            ),
        )

    items = (
        legacy("a", 100),
        legacy("b", 120),
        legacy("c", 144),
        _item("v2", _parts_descriptor()),
    )
    groups = geometric_groups(items, 0.95)

    assert [group.member_ids for group in groups] == [("a", "b")]
    assert groups[0].minimum_pair_score >= 0.95


def test_geometric_score_keeps_legacy_formula_while_technical_score_is_separate() -> (
    None
):
    query = FurnitureDescriptor(
        family="rectangular_shelving",
        dimensions=DescriptorDimensions(width_mm=100, depth_mm=100, height_mm=100),
        roles=(),
        structure="unknown",
        unknown_fields=("structure", "material", "finish"),
    )
    candidate = _item(
        "candidate",
        query.model_copy(
            update={
                "dimensions": DescriptorDimensions(
                    width_mm=120, depth_mm=100, height_mm=100
                ),
            }
        ),
    )

    match = geometric_match(query, candidate)

    assert match.score == 0.661111
    assert match.technical_score != match.score


def test_v3_repeated_roles_aggregate_quantities_without_losing_components() -> None:
    def component(quantity: int, length: float) -> TableDescriptorComponentFeature:
        return TableDescriptorComponentFeature(
            role="side_support",
            quantity=quantity,
            length_mm=length,
            width_mm=700,
            thickness_mm=30,
            material_tariff_id="oak",
            field_states={
                field: "confirmed"
                for field in ("quantity", "length_mm", "width_mm", "thickness_mm")
            },
        )

    left = FurnitureDescriptorV3(
        dimensions=DescriptorDimensions(width_mm=1200, depth_mm=700, height_mm=750),
        structure="side_support_table",
        components=(component(1, 720), component(1, 680)),
    )
    right = left.model_copy(update={"components": (component(2, 720),)})

    comparison = technical_similarity(left, right)

    assert comparison.components["roles"] == 1.0
    assert comparison.components["part_features"] < 1.0
    assert any(
        item.field == "components.side_support.count" for item in comparison.differences
    )


def test_piece_assignment_finds_global_optimum_and_is_permutation_invariant() -> None:
    def descriptor(
        rows: tuple[tuple[float, float, float, int], ...],
    ) -> FurnitureDescriptorV2:
        return FurnitureDescriptorV2(
            family="rectangular_shelving",
            dimensions=DescriptorDimensions(width_mm=100, depth_mm=100, height_mm=100),
            roles=(),
            structure="top_base_between_sides",
            material="board",
            finish="raw",
            thicknesses_mm=(30, 50, 100),
            classification_status="confirmed",
            part_features=tuple(
                DescriptorPartFeature(
                    length_mm=length,
                    width_mm=width,
                    thickness_mm=thickness,
                    quantity=quantity,
                )
                for length, width, thickness, quantity in rows
            ),
            unknown_fields=(),
        )

    left_rows = ((50, 10, 50, 20), (20, 100, 100, 100), (100, 10, 100, 30))
    right_rows = ((20, 30, 100, 20), (10, 10, 30, 30), (20, 100, 30, 20))

    forward = technical_similarity(descriptor(left_rows), descriptor(right_rows))
    permuted = technical_similarity(
        descriptor(tuple(reversed(left_rows))),
        descriptor((right_rows[1], right_rows[2], right_rows[0])),
    )

    # Exhaustive assignment gives sum 1.791666..., average 0.597222.
    # The former greedy matcher selected sum 1.558333..., average 0.519444.
    assert forward.components["part_features"] == 0.597222
    assert permuted.components["part_features"] == 0.597222
    assert forward.score == permuted.score


def test_design_key_is_order_invariant_but_conservative_about_finish_and_unknowns() -> (
    None
):
    descriptor = _parts_descriptor()
    reordered = descriptor.model_copy(
        update={
            "roles": tuple(reversed(descriptor.roles)),
            "part_features": tuple(reversed(descriptor.part_features)),
            "unknown_fields": tuple(reversed(descriptor.unknown_fields)),
        }
    )

    assert canonical_design_key(descriptor) == canonical_design_key(reordered)
    assert canonical_design_key(descriptor) != canonical_design_key(
        descriptor.model_copy(update={"finish": "painted"})
    )
    assert canonical_design_key(descriptor) != canonical_design_key(
        descriptor.model_copy(update={"finish": None, "unknown_fields": ("finish",)})
    )


def test_deduplication_selects_latest_revision_before_semantic_ranking() -> None:
    descriptor = _parts_descriptor()
    old = _item("same-old", descriptor, vector_space=True, revision=1)
    latest = _item("same-latest", descriptor, vector_space=True, revision=2)
    other = _item("other", _parts_descriptor(length_mm=828), vector_space=True)

    unique = deduplicate_designs((old, other, latest))
    ranked = rank_semantic_candidates(
        latest,
        (1.0, 0.0),
        tuple((item, (1.0, 0.0)) for item in unique if item.id != latest.id),
    )

    assert [item.id for item in unique] == ["other", "same-latest"]
    assert [match.library_item_id for match in ranked] == ["other"]
