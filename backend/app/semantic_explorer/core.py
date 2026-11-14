from __future__ import annotations

import numpy as np

from .models import Bundle, Entry, digest

PROJECTION_VERSION = "pca-centered-svd-v1"


def unit_vectors(bundle: Bundle) -> np.ndarray:
    matrix = np.asarray([e.vector for e in bundle.entries], dtype=np.float64).reshape(
        (-1, bundle.space.dimensions)
    )
    if len(matrix):
        # Scale first to avoid overflow on finite but very large vectors.
        matrix = matrix / np.max(np.abs(matrix), axis=1, keepdims=True)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix


def snapshot_id(bundle: Bundle, source: str) -> str:
    return digest(
        {
            "source": source,
            "projection": PROJECTION_VERSION,
            "bundle": bundle.model_dump(mode="json"),
        }
    )


def public_entry(entry: Entry) -> dict:
    return entry.model_dump(
        mode="json", exclude={"vector", "text", "features", "image_hash"}
    ) | {"has_image": entry.image_hash is not None}


def make_snapshot(bundle: Bundle, source: str) -> dict:
    matrix = unit_vectors(bundle)
    points = np.zeros((len(matrix), 2))
    explained = [0.0, 0.0]
    if len(matrix) > 1:
        centered = matrix - matrix.mean(axis=0)
        if np.linalg.norm(centered) > 1e-14:
            u, singular, vt = np.linalg.svd(centered, full_matrices=False)
            count = min(2, len(singular))
            for axis in range(count):
                sign = 1 if vt[axis, np.argmax(np.abs(vt[axis]))] >= 0 else -1
                points[:, axis] = u[:, axis] * singular[axis] * sign
                explained[axis] = float(singular[axis] ** 2 / np.sum(singular**2))
    return {
        "snapshot_id": snapshot_id(bundle, source),
        "source": source,
        "space": bundle.space.model_dump(mode="json"),
        "vector_space_id": bundle.space.id,
        "projection": {
            "method": "PCA 2D",
            "version": PROJECTION_VERSION,
            "explained_variance_ratio": explained,
            "purpose": "visualization_only",
        },
        "provenance": bundle.provenance,
        "synthetic": bundle.synthetic,
        "points": [
            public_entry(e) | {"x": float(p[0]), "y": float(p[1])}
            for e, p in zip(bundle.entries, points, strict=True)
        ],
    }


def search(
    bundle: Bundle,
    member_id: str,
    limit: int,
    category: str | None = None,
    exclude_group: bool = False,
) -> list[dict]:
    query_index = next(
        (i for i, e in enumerate(bundle.entries) if e.id == member_id), None
    )
    if query_index is None:
        raise KeyError(member_id)
    vectors = unit_vectors(bundle)
    scores = np.clip(vectors @ vectors[query_index], -1, 1)
    query = bundle.entries[query_index]
    candidates = [
        i
        for i, e in enumerate(bundle.entries)
        if i != query_index
        and (category is None or e.category == category)
        and not (exclude_group and query.group_id and e.group_id == query.group_id)
    ]
    ordered = sorted(
        candidates, key=lambda i: (-float(scores[i]), bundle.entries[i].id)
    )[:limit]
    results = []
    for i in ordered:
        entry = bundle.entries[i]
        keys = sorted(set(query.attributes) | set(entry.attributes))
        comparable = [
            k
            for k in keys
            if query.attributes.get(k) is not None
            and entry.attributes.get(k) is not None
        ]
        differences = [
            {
                "field": k,
                "query": query.attributes.get(k),
                "candidate": entry.attributes.get(k),
            }
            for k in keys
            if query.attributes.get(k) != entry.attributes.get(k) or k not in comparable
        ]
        results.append(
            public_entry(entry)
            | {
                "cosine": float(scores[i]),
                "differences": differences,
                "known_field_coverage": len(comparable) / len(keys) if keys else None,
            }
        )
    return results
