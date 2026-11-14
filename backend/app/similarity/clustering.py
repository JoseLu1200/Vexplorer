from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Literal

from backend.app.contratos.modelos import LibraryItem, SimilarityGroup


def complete_linkage_groups(
    items: Sequence[LibraryItem],
    threshold: float,
    score_fn: Callable[[LibraryItem, LibraryItem], float],
    *,
    method: Literal["geometric", "semantic"],
    score_kind: Literal["geometric_similarity", "cosine_similarity"],
    explanation: str,
) -> tuple[SimilarityGroup, ...]:
    """Form deterministic non-chaining groups via greedy complete-linkage clustering.

    Every pair of items in a resulting group has pairwise similarity >= threshold,
    and no group is formed solely from items sharing the same run_id.
    """
    ordered = tuple(sorted(items, key=lambda item: item.id))
    count = len(ordered)
    if count < 2:
        return ()

    # Each cluster is keyed by its sorted tuple of member indices in `ordered`.
    # Member IDs for any cluster are `tuple(ordered[i].id for i in cluster)`.
    clusters: dict[int, tuple[int, ...]] = {index: (index,) for index in range(count)}
    cluster_keys: dict[int, tuple[str, ...]] = {index: (ordered[index].id,) for index in range(count)}

    # Store only cluster pairs whose complete-linkage minimum score >= threshold.
    # Value is (min_pair_score, has_different_run_ids).
    active_edges: dict[tuple[int, int], tuple[float, bool]] = {}
    pair_scores: dict[tuple[str, str], float] = {}
    for i in range(count):
        left = ordered[i]
        for j in range(i + 1, count):
            right = ordered[j]
            score = float(score_fn(left, right))
            pair_scores[(left.id, right.id)] = score
            if score >= threshold:
                active_edges[(i, j)] = (score, left.run_id != right.run_id)

    next_cluster_id = count
    while active_edges:
        best_pair: tuple[int, int] | None = None
        best_priority: tuple[float, tuple[str, ...], tuple[str, ...]] | None = None

        for (c_a, c_b), (min_score, has_diff_run) in active_edges.items():
            if not has_diff_run:
                continue
            key_a = cluster_keys[c_a]
            key_b = cluster_keys[c_b]
            ordered_keys = (key_a, key_b) if key_a <= key_b else (key_b, key_a)
            priority = (-min_score, ordered_keys[0], ordered_keys[1])
            if best_priority is None or priority < best_priority:
                best_priority = priority
                best_pair = (c_a, c_b)

        if best_pair is None:
            break

        c_a, c_b = best_pair
        merged_members = tuple(sorted(clusters.pop(c_a) + clusters.pop(c_b)))
        cluster_keys.pop(c_a)
        cluster_keys.pop(c_b)

        # Collect edges from c_a and c_b to other surviving clusters.
        edges_a: dict[int, tuple[float, bool]] = {}
        edges_b: dict[int, tuple[float, bool]] = {}
        to_remove: list[tuple[int, int]] = []
        for edge in active_edges:
            u, v = edge
            if u == c_a or v == c_a:
                other = v if u == c_a else u
                if other != c_b:
                    edges_a[other] = active_edges[edge]
                to_remove.append(edge)
            elif u == c_b or v == c_b:
                other = v if u == c_b else u
                if other != c_a:
                    edges_b[other] = active_edges[edge]
                to_remove.append(edge)

        for edge in to_remove:
            active_edges.pop(edge)

        merged_id = next_cluster_id
        next_cluster_id += 1
        clusters[merged_id] = merged_members
        cluster_keys[merged_id] = tuple(ordered[idx].id for idx in merged_members)

        # Complete linkage: merged_id connects to `other` iff both c_a and c_b did.
        for other, (score_a, diff_a) in edges_a.items():
            if other in edges_b:
                score_b, diff_b = edges_b[other]
                edge_key = (other, merged_id) if other < merged_id else (merged_id, other)
                active_edges[edge_key] = (min(score_a, score_b), diff_a or diff_b)

    groups: list[SimilarityGroup] = []
    for members in sorted(cluster_keys[cid] for cid in clusters if len(clusters[cid]) >= 2):
        digest = hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
        groups.append(
            SimilarityGroup(
                id=f"group-{method}-{digest}",
                member_ids=members,
                method=method,
                score_kind=score_kind,
                threshold=threshold,
                explanation=explanation,
                minimum_pair_score=min(
                    pair_scores[(left, right)]
                    for index, left in enumerate(members)
                    for right in members[index + 1:]
                ),
            )
        )
    return tuple(groups)
