from __future__ import annotations

import hashlib
import math

from backend.app.contratos.modelos import FurnitureDescriptor, LibraryItem, SimilarityDifference, SimilarityGroup, SimilarityMatch


def _ratio(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0
    return min(left, right) / max(left, right)


def _role_score(left: FurnitureDescriptor, right: FurnitureDescriptor) -> float:
    a = {item.role: item.quantity for item in left.roles}
    b = {item.role: item.quantity for item in right.roles}
    roles = set(a) | set(b)
    if not roles:
        return 0.0
    values = []
    for role in roles:
        x, y = a.get(role), b.get(role)
        values.append(_ratio(float(x) if x else None, float(y) if y else None))
    return sum(values) / len(values)


def descriptor_differences(left: FurnitureDescriptor, right: FurnitureDescriptor) -> tuple[SimilarityDifference, ...]:
    values: list[SimilarityDifference] = []
    for field in ("width_mm", "depth_mm", "height_mm"):
        a, b = getattr(left.dimensions, field), getattr(right.dimensions, field)
        if a != b:
            values.append(SimilarityDifference(field=f"dimensions.{field}", query_value=str(a), candidate_value=str(b)))
    for field in ("structure", "material", "finish"):
        a, b = getattr(left, field), getattr(right, field)
        if a != b:
            values.append(SimilarityDifference(field=field, query_value=str(a), candidate_value=str(b)))
    a_roles = {item.role: item.quantity for item in left.roles}
    b_roles = {item.role: item.quantity for item in right.roles}
    for role in sorted(set(a_roles) | set(b_roles)):
        if a_roles.get(role) != b_roles.get(role):
            values.append(SimilarityDifference(field=f"roles.{role}", query_value=str(a_roles.get(role)), candidate_value=str(b_roles.get(role))))
    return tuple(values)


def geometric_match(query: FurnitureDescriptor, candidate: LibraryItem) -> SimilarityMatch:
    dimensions = tuple(_ratio(getattr(query.dimensions, field), getattr(candidate.descriptor.dimensions, field)) for field in ("width_mm", "depth_mm", "height_mm"))
    dimension_score = sum(dimensions) / len(dimensions)
    role_score = _role_score(query, candidate.descriptor)
    score = round(0.7 * dimension_score + 0.3 * role_score, 6)
    return SimilarityMatch(library_item_id=candidate.id, run_id=candidate.run_id, result_revision=candidate.result_revision, method="geometric", score=score, score_kind="geometric_similarity", score_components={"dimensions": round(dimension_score, 6), "roles": round(role_score, 6), "dimensions_weight": 0.7, "roles_weight": 0.3}, differences=descriptor_differences(query, candidate.descriptor))


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding_space_incompatible")
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if not left_norm or not right_norm:
        raise ValueError("invalid_embedding")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def semantic_match(query: LibraryItem, query_vector: tuple[float, ...], candidate: LibraryItem, candidate_vector: tuple[float, ...]) -> SimilarityMatch:
    if query.embedding is None or candidate.embedding is None:
        raise ValueError("semantic_embedding_missing")
    if (query.embedding.model, query.embedding.dimensions, query.embedding.descriptor_version) != (candidate.embedding.model, candidate.embedding.dimensions, candidate.embedding.descriptor_version):
        raise ValueError("embedding_space_incompatible")
    score = round(cosine_similarity(query_vector, candidate_vector), 6)
    return SimilarityMatch(library_item_id=candidate.id, run_id=candidate.run_id, result_revision=candidate.result_revision, method="semantic", score=score, score_kind="cosine_similarity", score_components={"cosine": score}, differences=descriptor_differences(query.descriptor, candidate.descriptor), embedding=candidate.embedding)


def geometric_groups(items: tuple[LibraryItem, ...], threshold: float) -> tuple[SimilarityGroup, ...]:
    ordered = tuple(sorted(items, key=lambda item: item.id))
    parent = {item.id: item.id for item in ordered}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if left.run_id != right.run_id and geometric_match(left.descriptor, right).score >= threshold:
                union(left.id, right.id)
    components: dict[str, list[str]] = {}
    for item in ordered:
        components.setdefault(find(item.id), []).append(item.id)
    groups = []
    for members in sorted(tuple(sorted(values)) for values in components.values() if len(values) >= 2):
        digest = hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
        groups.append(SimilarityGroup(id=f"group-geometric-{digest}", member_ids=tuple(members), method="geometric", score_kind="geometric_similarity", threshold=threshold, explanation="Componente conexo reproducible: cada enlace alcanza el umbral geométrico; no demuestra identidad ni intercambiabilidad."))
    return tuple(groups)
