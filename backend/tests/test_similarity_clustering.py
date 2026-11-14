from __future__ import annotations

import hashlib

import pytest

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    EmbeddingMetadata,
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    LibraryItem,
    RoleQuantity,
)
from backend.app.similarity.service import geometric_groups, geometric_match, semantic_groups


def _make_item(
    item_id: str,
    run_id: str,
    width_mm: float,
    *,
    with_embedding: bool = False,
    model: str = "text-embedding-3-small",
    dims: int = 3,
) -> LibraryItem:
    descriptor = FurnitureDescriptor(
        family="rectangular_shelving",
        dimensions=DescriptorDimensions(width_mm=width_mm, depth_mm=400.0, height_mm=1800.0),
        roles=(
            RoleQuantity(role="side", quantity=2),
            RoleQuantity(role="top", quantity=1),
            RoleQuantity(role="base", quantity=1),
        ),
        structure="top_base_between_sides",
        unknown_fields=(),
    )
    fingerprint = hashlib.sha256(f"{item_id}:{width_mm}".encode()).hexdigest()
    embedding = (
        EmbeddingMetadata(
            model=model,
            dimensions=dims,
            descriptor_version="furniture-v1",
            cache_key=f"cache-{item_id}",
            status="cache",
        )
        if with_embedding
        else None
    )
    return LibraryItem(
        id=item_id,
        run_id=run_id,
        result_revision=1,
        label=f"Item {item_id}",
        descriptor=descriptor,
        descriptor_fingerprint=fingerprint,
        created_at="2026-01-01T00:00:00Z",
        embedding=embedding,
    )


def test_semantic_groups_prevent_chaining_when_endpoints_below_threshold() -> None:
    a = _make_item("item-a", "run-1", 600.0, with_embedding=True)
    b = _make_item("item-b", "run-2", 800.0, with_embedding=True)
    c = _make_item("item-c", "run-3", 1000.0, with_embedding=True)
    # cos(a, b) = 0.80, cos(b, c) = 0.80, cos(a, c) = 0.28 < 0.75
    vectors = {
        "item-a": (1.0, 0.0, 0.0),
        "item-b": (0.8, 0.6, 0.0),
        "item-c": (0.28, 0.96, 0.0),
    }

    groups = semantic_groups((a, b, c), vectors, threshold=0.75)

    assert len(groups) == 1
    assert groups[0].member_ids == ("item-a", "item-b")
    assert groups[0].id.startswith("group-semantic-")
    assert groups[0].method == "semantic"
    assert groups[0].score_kind == "cosine_similarity"
    assert "enlace completo" in groups[0].explanation
    assert "sin encadenamiento" in groups[0].explanation


def test_geometric_groups_prevent_chaining_when_endpoints_below_threshold() -> None:
    a = _make_item("item-a", "run-1", 600.0)
    b = _make_item("item-b", "run-2", 800.0)
    c = _make_item("item-c", "run-3", 1050.0)

    ab = geometric_match(a.descriptor, b).score
    bc = geometric_match(b.descriptor, c).score
    ac = geometric_match(a.descriptor, c).score
    assert ab >= 0.93
    assert bc >= 0.93
    assert ac < 0.93
    assert bc > ab

    groups = geometric_groups((a, b, c), threshold=0.93)

    assert len(groups) == 1
    assert groups[0].member_ids == ("item-b", "item-c")
    assert groups[0].id.startswith("group-geometric-")
    assert groups[0].method == "geometric"
    assert groups[0].score_kind == "geometric_similarity"
    assert "enlace completo" in groups[0].explanation
    assert "sin encadenamiento" in groups[0].explanation


def test_clique_forms_full_group_in_geometric_and_semantic_modes() -> None:
    a = _make_item("item-a", "run-1", 800.0, with_embedding=True)
    b = _make_item("item-b", "run-2", 810.0, with_embedding=True)
    c = _make_item("item-c", "run-3", 820.0, with_embedding=True)
    vectors = {
        "item-a": (1.0, 0.0, 0.0),
        "item-b": (0.99, 0.14, 0.0),
        "item-c": (0.98, 0.19, 0.0),
    }

    geo_groups = geometric_groups((a, b, c), threshold=0.95)
    sem_groups = semantic_groups((a, b, c), vectors, threshold=0.95)

    assert len(geo_groups) == 1
    assert geo_groups[0].member_ids == ("item-a", "item-b", "item-c")
    assert len(sem_groups) == 1
    assert sem_groups[0].member_ids == ("item-a", "item-b", "item-c")


def test_same_run_id_cannot_form_group_alone_but_joins_when_third_run_bridges() -> None:
    a1 = _make_item("item-a1", "run-1", 800.0, with_embedding=True)
    a2 = _make_item("item-a2", "run-1", 800.0, with_embedding=True)
    vectors_two = {"item-a1": (1.0, 0.0, 0.0), "item-a2": (1.0, 0.0, 0.0)}

    assert geometric_groups((a1, a2), threshold=0.9) == ()
    assert semantic_groups((a1, a2), vectors_two, threshold=0.9) == ()

    b = _make_item("item-b", "run-2", 800.0, with_embedding=True)
    vectors_three = {**vectors_two, "item-b": (1.0, 0.0, 0.0)}

    geo_groups = geometric_groups((a1, a2, b), threshold=0.9)
    sem_groups = semantic_groups((a1, a2, b), vectors_three, threshold=0.9)

    assert len(geo_groups) == 1
    assert geo_groups[0].member_ids == ("item-a1", "item-a2", "item-b")
    assert len(sem_groups) == 1
    assert sem_groups[0].member_ids == ("item-a1", "item-a2", "item-b")


def test_clustering_is_deterministic_across_input_permutations_and_ties() -> None:
    a = _make_item("item-a", "run-1", 600.0, with_embedding=True)
    b = _make_item("item-b", "run-2", 800.0, with_embedding=True)
    c = _make_item("item-c", "run-3", 1000.0, with_embedding=True)
    vectors = {
        "item-a": (1.0, 0.0, 0.0),
        "item-b": (0.8, 0.6, 0.0),
        "item-c": (0.28, 0.96, 0.0),
    }

    baseline_sem = semantic_groups((a, b, c), vectors, threshold=0.75)
    reversed_sem = semantic_groups((c, b, a), vectors, threshold=0.75)
    shuffled_sem = semantic_groups((b, c, a), vectors, threshold=0.75)

    assert baseline_sem == reversed_sem == shuffled_sem
    assert baseline_sem[0].member_ids == ("item-a", "item-b")

    baseline_geo = geometric_groups((a, b, c), threshold=0.90)
    reversed_geo = geometric_groups((c, b, a), threshold=0.90)
    assert baseline_geo == reversed_geo


def test_clustering_edge_cases_and_validation_errors() -> None:
    single = _make_item("item-only", "run-1", 800.0, with_embedding=True)
    assert geometric_groups((), threshold=0.8) == ()
    assert geometric_groups((single,), threshold=0.8) == ()
    assert semantic_groups((), {}, threshold=0.8) == ()
    assert semantic_groups((single,), {"item-only": (1.0, 0.0, 0.0)}, threshold=0.8) == ()

    no_emb = _make_item("item-no-emb", "run-2", 800.0, with_embedding=False)
    with pytest.raises(ValueError, match="semantic_embedding_missing"):
        semantic_groups((single, no_emb), {"item-only": (1.0, 0.0, 0.0)}, threshold=0.8)

    other_model = _make_item("item-other-model", "run-2", 800.0, with_embedding=True, model="other-model")
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        semantic_groups(
            (single, other_model),
            {"item-only": (1.0, 0.0, 0.0), "item-other-model": (1.0, 0.0, 0.0)},
            threshold=0.8,
        )

    v2_item = LibraryItem(
        id="item-v2",
        run_id="run-2",
        result_revision=1,
        label="V2",
        descriptor=FurnitureDescriptorV2(
            family="rectangular_shelving",
            dimensions=DescriptorDimensions(width_mm=800.0, depth_mm=400.0, height_mm=1800.0),
            roles=(RoleQuantity(role="side", quantity=2),),
            thicknesses_mm=(18.0,),
            classification_status="confirmed",
            structure="top_base_between_sides",
            unknown_fields=(),
        ),
        descriptor_fingerprint=hashlib.sha256(b"v2").hexdigest(),
        created_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(ValueError, match="descriptor_space_incompatible"):
        geometric_groups((single, v2_item), threshold=0.8)
