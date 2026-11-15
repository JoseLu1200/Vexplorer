from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Callable

from backend.app.contratos.modelos import (
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
    SimilarityDifference,
    SimilarityGroup,
    SimilarityMatch,
)
from backend.app.similarity.math_utils import cosine_similarity as _cosine_similarity

Descriptor = FurnitureDescriptor | FurnitureDescriptorV2 | FurnitureDescriptorV3


@dataclass(frozen=True)
class TechnicalComparison:
    score: float
    components: dict[str, float]
    differences: tuple[SimilarityDifference, ...]
    warnings: tuple[str, ...]


def _ratio(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0
    return min(left, right) / max(left, right)


def _roles(descriptor: Descriptor) -> dict[str, int | None]:
    values = (
        descriptor.components
        if isinstance(descriptor, FurnitureDescriptorV3)
        else descriptor.roles
    )
    roles: dict[str, int | None] = {}
    for item in values:
        current = roles.get(item.role)
        roles[item.role] = (
            None
            if item.quantity is None or (item.role in roles and current is None)
            else (current or 0) + item.quantity
        )
    return roles


def _difference(field: str, left: object, right: object) -> SimilarityDifference:
    return SimilarityDifference(
        field=field, query_value=str(left), candidate_value=str(right)
    )


def _numeric_comparison(left, right, fields, prefix):
    scores: list[float] = []
    known = 0
    differences: list[SimilarityDifference] = []
    for field in fields:
        a, b = getattr(left, field), getattr(right, field)
        scores.append(_ratio(a, b))
        known += int(a is not None and b is not None)
        if a != b:
            differences.append(_difference(f"{prefix}.{field}", a, b))
    return sum(scores) / len(scores), known, len(fields), differences


def _role_comparison(left: Descriptor, right: Descriptor):
    a, b = _roles(left), _roles(right)
    roles = sorted(set(a) | set(b))
    if not roles:
        return 0.0, 0, 0, []
    scores, known, differences = [], 0, []
    for role in roles:
        x, y = a.get(role), b.get(role)
        scores.append(
            _ratio(
                float(x) if x is not None else None, float(y) if y is not None else None
            )
        )
        known += int(x is not None and y is not None)
        if x != y:
            differences.append(_difference(f"roles.{role}", x, y))
    return sum(scores) / len(scores), known, len(roles), differences


_FEATURE_FIELDS = ("length_mm", "width_mm", "thickness_mm", "quantity")


def _feature_values(feature) -> tuple[float | int | None, ...]:
    return tuple(getattr(feature, field) for field in _FEATURE_FIELDS)


def _feature_pair_score(left, right) -> float:
    return sum(
        _ratio(float(a) if a is not None else None, float(b) if b is not None else None)
        for a, b in zip(_feature_values(left), _feature_values(right), strict=True)
    ) / len(_FEATURE_FIELDS)


def _feature_pairs(left: tuple, right: tuple) -> tuple[tuple[int, int], ...]:
    size = max(len(left), len(right))
    if not size:
        return ()
    costs = [
        [
            -_feature_pair_score(left[row], right[column])
            if row < len(left) and column < len(right)
            else 0.0
            for column in range(size)
        ]
        for row in range(size)
    ]

    # Hungarian assignment for a square cost matrix. Padding has zero weight,
    # so unequal feature sets leave only the surplus rows/columns unmatched.
    row_potential = [0.0] * (size + 1)
    column_potential = [0.0] * (size + 1)
    column_row = [0] * (size + 1)
    previous_column = [0] * (size + 1)
    for row in range(1, size + 1):
        column_row[0] = row
        minimum = [math.inf] * (size + 1)
        used = [False] * (size + 1)
        column = 0
        while True:
            used[column] = True
            current_row = column_row[column]
            delta = math.inf
            next_column = 0
            for candidate_column in range(1, size + 1):
                if used[candidate_column]:
                    continue
                reduced_cost = (
                    costs[current_row - 1][candidate_column - 1]
                    - row_potential[current_row]
                    - column_potential[candidate_column]
                )
                if reduced_cost < minimum[candidate_column]:
                    minimum[candidate_column] = reduced_cost
                    previous_column[candidate_column] = column
                if minimum[candidate_column] < delta:
                    delta = minimum[candidate_column]
                    next_column = candidate_column
            for candidate_column in range(size + 1):
                if used[candidate_column]:
                    row_potential[column_row[candidate_column]] += delta
                    column_potential[candidate_column] -= delta
                else:
                    minimum[candidate_column] -= delta
            column = next_column
            if column_row[column] == 0:
                break
        while True:
            prior = previous_column[column]
            column_row[column] = column_row[prior]
            column = prior
            if column == 0:
                break

    pairs = (
        (column_row[column] - 1, column - 1)
        for column in range(1, size + 1)
        if column_row[column] <= len(left) and column <= len(right)
    )
    return tuple(sorted(pairs))


def _v2_features(left: FurnitureDescriptorV2, right: FurnitureDescriptorV2):
    if not left.part_features and not right.part_features:
        total = max(len(left.thicknesses_mm), len(right.thicknesses_mm))
        if not total:
            return 0.0, 0, 0, []
        a, b = sorted(left.thicknesses_mm), sorted(right.thicknesses_mm)
        scores = [
            _ratio(a[i] if i < len(a) else None, b[i] if i < len(b) else None)
            for i in range(total)
        ]
        differences = (
            [] if a == b else [_difference("thicknesses_mm", tuple(a), tuple(b))]
        )
        return sum(scores) / total, min(len(a), len(b)), total, differences
    left_features = tuple(
        sorted(
            left.part_features,
            key=lambda item: tuple(
                (value is None, value or 0) for value in _feature_values(item)
            ),
        )
    )
    right_features = tuple(
        sorted(
            right.part_features,
            key=lambda item: tuple(
                (value is None, value or 0) for value in _feature_values(item)
            ),
        )
    )
    pairs = _feature_pairs(left_features, right_features)
    count = max(len(left.part_features), len(right.part_features))
    scores, known, differences = [], 0, []
    for left_index, right_index in pairs:
        a, b = left_features[left_index], right_features[right_index]
        scores.append(_feature_pair_score(a, b))
        for field, x, y in zip(
            _FEATURE_FIELDS, _feature_values(a), _feature_values(b), strict=True
        ):
            known += int(x is not None and y is not None)
            if x != y:
                differences.append(
                    _difference(f"part_features[{left_index}].{field}", x, y)
                )
    scores.extend(0.0 for _ in range(count - len(pairs)))
    if len(left.part_features) != len(right.part_features):
        differences.append(
            _difference(
                "part_features.count", len(left.part_features), len(right.part_features)
            )
        )
    return sum(scores) / count, known, count * len(_FEATURE_FIELDS), differences


def _v3_features(left: FurnitureDescriptorV3, right: FurnitureDescriptorV3):
    a_by_role: dict[str, list] = {}
    b_by_role: dict[str, list] = {}
    for item in left.components:
        a_by_role.setdefault(item.role, []).append(item)
    for item in right.components:
        b_by_role.setdefault(item.role, []).append(item)
    roles = sorted(set(a_by_role) | set(b_by_role))
    if not roles:
        return 0.0, 0, 0, []
    scores, known, differences = [], 0, []
    total = 0
    for role in roles:
        left_values = tuple(
            sorted(
                a_by_role.get(role, ()),
                key=lambda item: (_feature_values(item), item.material_tariff_id or ""),
            )
        )
        right_values = tuple(
            sorted(
                b_by_role.get(role, ()),
                key=lambda item: (_feature_values(item), item.material_tariff_id or ""),
            )
        )
        count = max(len(left_values), len(right_values))
        total += count * 5
        pairs = _feature_pairs(left_values, right_values)
        for role_index, (left_index, right_index) in enumerate(pairs):
            a, b = left_values[left_index], right_values[right_index]
            numeric = [
                _ratio(float(getattr(a, field)), float(getattr(b, field)))
                for field in _FEATURE_FIELDS
            ]
            known += len(_FEATURE_FIELDS)
            for field in _FEATURE_FIELDS:
                if getattr(a, field) != getattr(b, field):
                    differences.append(
                        _difference(
                            f"components.{role}[{role_index}].{field}",
                            getattr(a, field),
                            getattr(b, field),
                        )
                    )
            material_score = float(
                a.material_tariff_id is not None
                and a.material_tariff_id == b.material_tariff_id
            )
            known += int(
                a.material_tariff_id is not None and b.material_tariff_id is not None
            )
            if a.material_tariff_id != b.material_tariff_id:
                differences.append(
                    _difference(
                        f"components.{role}[{role_index}].material_tariff_id",
                        a.material_tariff_id,
                        b.material_tariff_id,
                    )
                )
            scores.append((sum(numeric) + material_score) / 5)
        scores.extend(0.0 for _ in range(count - len(pairs)))
        if len(left_values) != len(right_values):
            differences.append(
                _difference(
                    f"components.{role}.count", len(left_values), len(right_values)
                )
            )
    return sum(scores) / len(scores), known, total, differences


def technical_similarity(left: Descriptor, right: Descriptor) -> TechnicalComparison:
    if left.descriptor_version != right.descriptor_version:
        raise ValueError("descriptor_space_incompatible")
    differences: list[SimilarityDifference] = []
    warnings: set[str] = set()
    weighted: list[tuple[float, float]] = []
    known_fields = total_fields = 0

    dimensions, known, total, values = _numeric_comparison(
        left.dimensions,
        right.dimensions,
        ("width_mm", "depth_mm", "height_mm"),
        "dimensions",
    )
    weighted.append((0.30, dimensions))
    known_fields += known
    total_fields += total
    differences.extend(values)
    roles, known, total, values = _role_comparison(left, right)
    if total:
        weighted.append((0.15, roles))
        known_fields += known
        total_fields += total
    differences.extend(values)

    categorical_scores = []
    for field, weight in (("family", 0.10), ("structure", 0.10)):
        a, b = getattr(left, field), getattr(right, field)
        value = float(a == b and a != "unknown")
        categorical_scores.append(value)
        weighted.append((weight, value))
        total_fields += 1
        known_fields += int(a != "unknown" and b != "unknown")
        if a != b:
            differences.append(_difference(field, a, b))

    descriptive_scores = []
    descriptive_fields = (
        (("material_tariff_id", 0.05),)
        if isinstance(left, FurnitureDescriptorV3)
        else (("material", 0.05), ("finish", 0.05))
    )
    for field, weight in descriptive_fields:
        if not hasattr(left, field):
            continue
        a, b = getattr(left, field), getattr(right, field)
        value = float(a is not None and a == b)
        descriptive_scores.append(value)
        weighted.append((weight, value))
        total_fields += 1
        known_fields += int(a is not None and b is not None)
        if a is None or b is None:
            warnings.add(f"{field}_unknown")
        if a != b:
            differences.append(_difference(field, a, b))
            if a is not None and b is not None:
                warnings.add(f"{field}_mismatch")
    if isinstance(left, FurnitureDescriptorV3):
        warnings.update(("finish_unknown", "process_unknown"))

    feature_score = None
    if isinstance(left, FurnitureDescriptorV2) and isinstance(
        right, FurnitureDescriptorV2
    ):
        feature_score, known, total, values = _v2_features(left, right)
    elif isinstance(left, FurnitureDescriptorV3) and isinstance(
        right, FurnitureDescriptorV3
    ):
        feature_score, known, total, values = _v3_features(left, right)
    else:
        known = total = 0
        values = []
    if total:
        weighted.append((0.25, feature_score or 0.0))
        known_fields += known
        total_fields += total
    differences.extend(values)

    weight_total = sum(weight for weight, _ in weighted)
    score = (
        round(sum(weight * value for weight, value in weighted) / weight_total, 6)
        if weight_total
        else 0.0
    )
    coverage = round(known_fields / total_fields, 6) if total_fields else 0.0
    if coverage < 1:
        warnings.add("technical_fields_unknown")
    components = {
        "dimensions": round(dimensions, 6),
        "roles": round(roles, 6),
        "family_structure": round(sum(categorical_scores) / len(categorical_scores), 6),
        "material_finish": round(sum(descriptive_scores) / len(descriptive_scores), 6)
        if descriptive_scores
        else 0.0,
        "evidence_coverage": coverage,
    }
    if feature_score is not None:
        components["part_features"] = round(feature_score, 6)
    return TechnicalComparison(
        score, components, tuple(differences), tuple(sorted(warnings))
    )


def descriptor_differences(
    left: Descriptor, right: Descriptor
) -> tuple[SimilarityDifference, ...]:
    return technical_similarity(left, right).differences


def geometric_match(query: Descriptor, candidate: LibraryItem) -> SimilarityMatch:
    comparison = technical_similarity(query, candidate.descriptor)
    dimension_score = (
        sum(
            _ratio(
                getattr(query.dimensions, field),
                getattr(candidate.descriptor.dimensions, field),
            )
            for field in ("width_mm", "depth_mm", "height_mm")
        )
        / 3
    )
    role_score, _, _, _ = _role_comparison(query, candidate.descriptor)
    if isinstance(query, FurnitureDescriptorV2) and isinstance(
        candidate.descriptor, FurnitureDescriptorV2
    ):
        left_thickness = (
            sum(query.thicknesses_mm) / len(query.thicknesses_mm)
            if query.thicknesses_mm
            else None
        )
        right_thickness = (
            sum(candidate.descriptor.thicknesses_mm)
            / len(candidate.descriptor.thicknesses_mm)
            if candidate.descriptor.thicknesses_mm
            else None
        )
        thickness_score = _ratio(left_thickness, right_thickness)
        score = round(
            0.6 * dimension_score + 0.25 * role_score + 0.15 * thickness_score, 6
        )
        geometric_components = {
            "dimensions": round(dimension_score, 6),
            "roles": round(role_score, 6),
            "thickness": round(thickness_score, 6),
            "dimensions_weight": 0.6,
            "roles_weight": 0.25,
            "thickness_weight": 0.15,
        }
    elif isinstance(query, FurnitureDescriptorV3) and isinstance(
        candidate.descriptor, FurnitureDescriptorV3
    ):
        left_count = sum(item.quantity for item in query.components)
        right_count = sum(item.quantity for item in candidate.descriptor.components)
        left_thickness = (
            sum(item.thickness_mm * item.quantity for item in query.components)
            / left_count
            if left_count
            else None
        )
        right_thickness = (
            sum(
                item.thickness_mm * item.quantity
                for item in candidate.descriptor.components
            )
            / right_count
            if right_count
            else None
        )
        thickness_score = _ratio(left_thickness, right_thickness)
        score = round(
            0.6 * dimension_score + 0.25 * role_score + 0.15 * thickness_score, 6
        )
        geometric_components = {
            "dimensions": round(dimension_score, 6),
            "roles": round(role_score, 6),
            "thickness": round(thickness_score, 6),
            "dimensions_weight": 0.6,
            "roles_weight": 0.25,
            "thickness_weight": 0.15,
        }
    else:
        score = round(0.7 * dimension_score + 0.3 * role_score, 6)
        geometric_components = {
            "dimensions": round(dimension_score, 6),
            "roles": round(role_score, 6),
            "dimensions_weight": 0.7,
            "roles_weight": 0.3,
        }
    return SimilarityMatch(
        library_item_id=candidate.id,
        run_id=candidate.run_id,
        result_revision=candidate.result_revision,
        method="geometric",
        score=score,
        score_kind="geometric_similarity",
        score_components=geometric_components,
        differences=comparison.differences,
        technical_score=comparison.score,
        technical_score_kind="technical_similarity",
        technical_score_components=comparison.components,
        compatibility_warnings=comparison.warnings,
    )


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return _cosine_similarity(left, right)


def semantic_match(
    query: LibraryItem,
    query_vector: tuple[float, ...],
    candidate: LibraryItem,
    candidate_vector: tuple[float, ...],
) -> SimilarityMatch:
    if query.embedding is None or candidate.embedding is None:
        raise ValueError("semantic_embedding_missing")
    if query.embedding.space_identity != candidate.embedding.space_identity:
        raise ValueError("embedding_space_incompatible")
    score = round(cosine_similarity(query_vector, candidate_vector), 6)
    comparison = technical_similarity(query.descriptor, candidate.descriptor)
    return SimilarityMatch(
        library_item_id=candidate.id,
        run_id=candidate.run_id,
        result_revision=candidate.result_revision,
        method="semantic",
        score=score,
        score_kind="cosine_similarity",
        score_components={"cosine": score},
        differences=comparison.differences,
        embedding=candidate.embedding,
        technical_score=comparison.score,
        technical_score_kind="technical_similarity",
        technical_score_components=comparison.components,
        compatibility_warnings=tuple(
            sorted(
                set(comparison.warnings)
                | {"cosine_not_probability_or_technical_equivalence"}
            )
        ),
    )


def canonical_design_key(descriptor: Descriptor) -> str:
    payload = descriptor.model_dump(mode="json")
    payload["unknown_fields"] = sorted(payload.get("unknown_fields", ()))
    if "thicknesses_mm" in payload:
        payload["thicknesses_mm"] = sorted(payload["thicknesses_mm"])
    for field in ("roles", "part_features", "components"):
        values = payload.get(field)
        if values is not None:
            for value in values:
                if "unknown_fields" in value:
                    value["unknown_fields"] = sorted(value["unknown_fields"])
            payload[field] = sorted(
                values,
                key=lambda item: json.dumps(
                    item, sort_keys=True, separators=(",", ":")
                ),
            )
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def deduplicate_designs(items: tuple[LibraryItem, ...]) -> tuple[LibraryItem, ...]:
    representatives: dict[str, LibraryItem] = {}
    for item in items:
        key = canonical_design_key(item.descriptor)
        current = representatives.get(key)
        if current is None or (item.result_revision, item.created_at, item.id) > (
            current.result_revision,
            current.created_at,
            current.id,
        ):
            representatives[key] = item
    return tuple(sorted(representatives.values(), key=lambda item: item.id))


def rank_semantic_candidates(
    query: LibraryItem,
    query_vector: tuple[float, ...],
    candidates_with_vectors: tuple[tuple[LibraryItem, tuple[float, ...]], ...],
) -> tuple[SimilarityMatch, ...]:
    if query.embedding is None:
        raise ValueError("semantic_embedding_missing")
    vectors = {item.id: vector for item, vector in candidates_with_vectors}
    compatible = tuple(
        item
        for item, _ in candidates_with_vectors
        if item.embedding is not None
        and (
            item.embedding.model,
            item.embedding.dimensions,
            item.embedding.descriptor_version,
        )
        == (
            query.embedding.model,
            query.embedding.dimensions,
            query.embedding.descriptor_version,
        )
    )
    matches = [
        semantic_match(query, query_vector, item, vectors[item.id])
        for item in deduplicate_designs(compatible)
    ]
    return tuple(
        sorted(
            matches,
            key=lambda item: (
                -(item.technical_score or 0.0),
                -item.score,
                item.library_item_id,
            ),
        )
    )


def _complete_link_clusters(
    items: tuple[LibraryItem, ...],
    threshold: float,
    pair_score: Callable[[LibraryItem, LibraryItem], float | None],
):
    by_id = {item.id: item for item in items}
    pair_cache: dict[tuple[str, str], float | None] = {}

    def cached_pair(left_id: str, right_id: str) -> float | None:
        key = tuple(sorted((left_id, right_id)))
        if key not in pair_cache:
            pair_cache[key] = pair_score(by_id[key[0]], by_id[key[1]])
        return pair_cache[key]

    clusters = [(item.id,) for item in sorted(items, key=lambda value: value.id)]
    while True:
        candidates = []
        for left_index, left in enumerate(clusters):
            for right_index in range(left_index + 1, len(clusters)):
                right = clusters[right_index]
                scores = [cached_pair(a, b) for a in left for b in right]
                if len({by_id[item].run_id for item in left + right}) > 1 and scores and all(
                    score is not None and score >= threshold for score in scores
                ):
                    candidates.append(
                        (
                            min(score for score in scores if score is not None),
                            tuple(sorted(left + right)),
                            left_index,
                            right_index,
                        )
                    )
        if not candidates:
            break
        _, merged, left_index, right_index = min(
            candidates, key=lambda value: (-value[0], value[1])
        )
        clusters = [
            cluster
            for index, cluster in enumerate(clusters)
            if index not in (left_index, right_index)
        ] + [merged]
        clusters.sort()
    results = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        scores = [
            cached_pair(a, b)
            for index, a in enumerate(cluster)
            for b in cluster[index + 1 :]
        ]
        results.append((cluster, min(score for score in scores if score is not None)))
    return tuple(sorted(results))


def geometric_groups(
    items: tuple[LibraryItem, ...], threshold: float
) -> tuple[SimilarityGroup, ...]:
    def pair(left, right):
        if (
            left.descriptor.descriptor_version != right.descriptor.descriptor_version
        ):
            return None
        return geometric_match(left.descriptor, right).score

    groups = []
    for members, minimum in _complete_link_clusters(items, threshold, pair):
        digest = hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
        groups.append(
            SimilarityGroup(
                id=f"group-geometric-{digest}",
                member_ids=members,
                method="geometric",
                score_kind="geometric_similarity",
                threshold=threshold,
                linkage="complete",
                minimum_pair_score=round(minimum, 6),
                explanation="Grupo reproducible de enlace completo, sin encadenamiento: todos los pares alcanzan el umbral técnico; no demuestra identidad, fabricación ni intercambiabilidad.",
            )
        )
    return tuple(groups)


def semantic_groups(
    items: tuple[LibraryItem, ...],
    vectors: dict[str, tuple[float, ...]],
    threshold: float,
) -> tuple[SimilarityGroup, ...]:
    ordered = tuple(sorted(items, key=lambda item: item.id))
    if any(item.embedding is None or item.id not in vectors for item in ordered):
        raise ValueError("semantic_embedding_missing")
    spaces = {
        item.embedding.space_identity
        for item in ordered
        if item.embedding is not None
    }
    if len(spaces) > 1:
        raise ValueError("embedding_space_incompatible")

    def pair(left, right):
        return cosine_similarity(vectors[left.id], vectors[right.id])

    groups = []
    for members, minimum in _complete_link_clusters(ordered, threshold, pair):
        digest = hashlib.sha256("\n".join(members).encode()).hexdigest()[:16]
        groups.append(
            SimilarityGroup(
                id=f"group-semantic-{digest}",
                member_ids=members,
                method="semantic",
                score_kind="cosine_similarity",
                threshold=threshold,
                linkage="complete",
                minimum_pair_score=round(minimum, 6),
                explanation="Grupo reproducible de enlace completo, sin encadenamiento: todos los pares alcanzan el umbral de coseno; no es probabilidad ni similitud técnica certificada.",
            )
        )
    return tuple(groups)
