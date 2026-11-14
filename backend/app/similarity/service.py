from __future__ import annotations

from backend.app.contratos.modelos import FurnitureDescriptor, FurnitureDescriptorV2, FurnitureDescriptorV3, LibraryItem, SimilarityDifference, SimilarityGroup, SimilarityMatch
from backend.app.similarity.clustering import complete_linkage_groups
from backend.app.similarity.math_utils import cosine_similarity as _cosine_similarity

Descriptor = FurnitureDescriptor | FurnitureDescriptorV2 | FurnitureDescriptorV3


def _ratio(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0
    return min(left, right) / max(left, right)


def _roles(descriptor: Descriptor) -> dict[str, int | None]:
    if isinstance(descriptor, FurnitureDescriptorV3):
        return {item.role: item.quantity for item in descriptor.components}
    return {item.role: item.quantity for item in descriptor.roles}


def _role_score(left: Descriptor, right: Descriptor) -> float:
    a = _roles(left)
    b = _roles(right)
    roles = set(a) | set(b)
    if not roles:
        return 0.0
    values = []
    for role in roles:
        x, y = a.get(role), b.get(role)
        values.append(_ratio(float(x) if x else None, float(y) if y else None))
    return sum(values) / len(values)


def descriptor_differences(left: Descriptor, right: Descriptor) -> tuple[SimilarityDifference, ...]:
    values: list[SimilarityDifference] = []
    for field in ("width_mm", "depth_mm", "height_mm"):
        a, b = getattr(left.dimensions, field), getattr(right.dimensions, field)
        if a != b:
            values.append(SimilarityDifference(field=f"dimensions.{field}", query_value=str(a), candidate_value=str(b)))
    for field in ("structure", "material", "finish"):
        a, b = getattr(left, field, None), getattr(right, field, None)
        if a != b:
            values.append(SimilarityDifference(field=field, query_value=str(a), candidate_value=str(b)))
    if isinstance(left, FurnitureDescriptorV2) and isinstance(right, FurnitureDescriptorV2) and left.thicknesses_mm != right.thicknesses_mm:
        values.append(SimilarityDifference(field="thicknesses_mm", query_value=str(left.thicknesses_mm), candidate_value=str(right.thicknesses_mm)))
    if isinstance(left, FurnitureDescriptorV3) and isinstance(right, FurnitureDescriptorV3) and left.components != right.components:
        values.append(SimilarityDifference(field="components", query_value=str(left.components), candidate_value=str(right.components)))
    a_roles = _roles(left)
    b_roles = _roles(right)
    for role in sorted(set(a_roles) | set(b_roles)):
        if a_roles.get(role) != b_roles.get(role):
            values.append(SimilarityDifference(field=f"roles.{role}", query_value=str(a_roles.get(role)), candidate_value=str(b_roles.get(role))))
    return tuple(values)


def geometric_match(query: Descriptor, candidate: LibraryItem) -> SimilarityMatch:
    if query.descriptor_version != candidate.descriptor.descriptor_version:
        raise ValueError("descriptor_space_incompatible")
    dimensions = tuple(_ratio(getattr(query.dimensions, field), getattr(candidate.descriptor.dimensions, field)) for field in ("width_mm", "depth_mm", "height_mm"))
    dimension_score = sum(dimensions) / len(dimensions)
    role_score = _role_score(query, candidate.descriptor)
    if isinstance(query, FurnitureDescriptorV2) and isinstance(candidate.descriptor, FurnitureDescriptorV2):
        left_thickness = sum(query.thicknesses_mm) / len(query.thicknesses_mm) if query.thicknesses_mm else None
        right_thickness = sum(candidate.descriptor.thicknesses_mm) / len(candidate.descriptor.thicknesses_mm) if candidate.descriptor.thicknesses_mm else None
        thickness_score = _ratio(left_thickness, right_thickness)
        score = round(0.6 * dimension_score + 0.25 * role_score + 0.15 * thickness_score, 6)
        components = {"dimensions": round(dimension_score, 6), "roles": round(role_score, 6), "thickness": round(thickness_score, 6), "dimensions_weight": 0.6, "roles_weight": 0.25, "thickness_weight": 0.15}
    elif isinstance(query, FurnitureDescriptorV3) and isinstance(candidate.descriptor, FurnitureDescriptorV3):
        query_thickness = sum(item.thickness_mm * item.quantity for item in query.components) / sum(item.quantity for item in query.components)
        candidate_thickness = sum(item.thickness_mm * item.quantity for item in candidate.descriptor.components) / sum(item.quantity for item in candidate.descriptor.components)
        thickness_score = _ratio(query_thickness, candidate_thickness)
        score = round(0.6 * dimension_score + 0.25 * role_score + 0.15 * thickness_score, 6)
        components = {"dimensions": round(dimension_score, 6), "roles": round(role_score, 6), "thickness": round(thickness_score, 6), "dimensions_weight": 0.6, "roles_weight": 0.25, "thickness_weight": 0.15}
    else:
        score = round(0.7 * dimension_score + 0.3 * role_score, 6)
        components = {"dimensions": round(dimension_score, 6), "roles": round(role_score, 6), "dimensions_weight": 0.7, "roles_weight": 0.3}
    return SimilarityMatch(library_item_id=candidate.id, run_id=candidate.run_id, result_revision=candidate.result_revision, method="geometric", score=score, score_kind="geometric_similarity", score_components=components, differences=descriptor_differences(query, candidate.descriptor))


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return _cosine_similarity(left, right)


def semantic_match(query: LibraryItem, query_vector: tuple[float, ...], candidate: LibraryItem, candidate_vector: tuple[float, ...]) -> SimilarityMatch:
    if query.embedding is None or candidate.embedding is None:
        raise ValueError("semantic_embedding_missing")
    if (query.embedding.model, query.embedding.dimensions, query.embedding.descriptor_version) != (candidate.embedding.model, candidate.embedding.dimensions, candidate.embedding.descriptor_version):
        raise ValueError("embedding_space_incompatible")
    score = round(cosine_similarity(query_vector, candidate_vector), 6)
    return SimilarityMatch(library_item_id=candidate.id, run_id=candidate.run_id, result_revision=candidate.result_revision, method="semantic", score=score, score_kind="cosine_similarity", score_components={"cosine": score}, differences=descriptor_differences(query.descriptor, candidate.descriptor), embedding=candidate.embedding)


def geometric_groups(items: tuple[LibraryItem, ...], threshold: float) -> tuple[SimilarityGroup, ...]:
    return complete_linkage_groups(
        items=items,
        threshold=threshold,
        score_fn=lambda left, right: geometric_match(left.descriptor, right).score,
        method="geometric",
        score_kind="geometric_similarity",
        explanation="Grupo compacto reproducible (enlace completo, sin encadenamiento): todos los pares alcanzan el umbral geométrico; no demuestra identidad ni intercambiabilidad.",
    )


def semantic_groups(items: tuple[LibraryItem, ...], vectors: dict[str, tuple[float, ...]], threshold: float) -> tuple[SimilarityGroup, ...]:
    ordered = tuple(sorted(items, key=lambda item: item.id))
    if any(item.embedding is None or item.id not in vectors for item in ordered):
        raise ValueError("semantic_embedding_missing")
    spaces = {(item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version) for item in ordered if item.embedding is not None}
    if len(spaces) > 1:
        raise ValueError("embedding_space_incompatible")
    return complete_linkage_groups(
        items=ordered,
        threshold=threshold,
        score_fn=lambda left, right: cosine_similarity(vectors[left.id], vectors[right.id]),
        method="semantic",
        score_kind="cosine_similarity",
        explanation="Grupo compacto reproducible (enlace completo, sin encadenamiento): todos los pares alcanzan el umbral por coseno en un mismo espacio de embedding; el score no es probabilidad ni demuestra identidad.",
    )
