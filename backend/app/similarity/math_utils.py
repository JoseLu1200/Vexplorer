from __future__ import annotations

from typing import Sequence

import numpy as np


def normalize_vector(vector: Sequence[float] | np.ndarray) -> np.ndarray:
    """Return an L2-normalized 1D float64 vector, rejecting empty, zero, or non-finite inputs."""
    arr = np.asarray(vector, dtype=np.float64)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("embedding_space_incompatible")
    if not np.isfinite(arr).all():
        raise ValueError("invalid_embedding")
    max_abs = float(np.max(np.abs(arr)))
    if max_abs == 0.0 or not np.isfinite(max_abs):
        raise ValueError("invalid_embedding")
    scaled = arr / max_abs
    norm = float(np.linalg.norm(scaled))
    if norm == 0.0 or not np.isfinite(norm):
        raise ValueError("invalid_embedding")
    return scaled / norm


def normalize_matrix(
    vectors: Sequence[Sequence[float]] | np.ndarray,
    *,
    dimensions: int | None = None,
) -> np.ndarray:
    """Return a row-wise L2-normalized 2D float64 matrix."""
    if dimensions is not None and dimensions <= 0:
        raise ValueError("embedding_space_incompatible")
    if isinstance(vectors, np.ndarray):
        matrix = np.asarray(vectors, dtype=np.float64)
    else:
        if len(vectors) == 0:
            cols = 0 if dimensions is None else dimensions
            return np.empty((0, cols), dtype=np.float64)
        try:
            matrix = np.asarray(vectors, dtype=np.float64)
        except ValueError as exc:
            raise ValueError("embedding_space_incompatible") from exc
    if matrix.ndim != 2:
        raise ValueError("embedding_space_incompatible")
    if matrix.shape[0] == 0:
        if dimensions is not None and matrix.shape[1] != dimensions:
            return np.empty((0, dimensions), dtype=np.float64)
        return np.empty((0, matrix.shape[1]), dtype=np.float64)
    if matrix.shape[1] == 0 or (dimensions is not None and matrix.shape[1] != dimensions):
        raise ValueError("embedding_space_incompatible")
    if not np.isfinite(matrix).all():
        raise ValueError("invalid_embedding")
    max_abs = np.max(np.abs(matrix), axis=1, keepdims=True)
    if np.any(max_abs == 0.0):
        raise ValueError("invalid_embedding")
    scaled = matrix / max_abs
    norms = np.linalg.norm(scaled, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms == 0.0):
        raise ValueError("invalid_embedding")
    return scaled / norms


def cosine_similarity(
    left: Sequence[float] | np.ndarray,
    right: Sequence[float] | np.ndarray,
) -> float:
    """Compute cosine similarity between two 1D vectors in [-1.0, 1.0]."""
    left_arr = np.asarray(left, dtype=np.float64)
    right_arr = np.asarray(right, dtype=np.float64)
    if (
        left_arr.ndim != 1
        or right_arr.ndim != 1
        or left_arr.size == 0
        or left_arr.size != right_arr.size
    ):
        raise ValueError("embedding_space_incompatible")
    left_unit = normalize_vector(left_arr)
    right_unit = normalize_vector(right_arr)
    return float(np.clip(np.dot(left_unit, right_unit), -1.0, 1.0))


def cosine_matrix(
    query: Sequence[float] | np.ndarray,
    matrix: Sequence[Sequence[float]] | np.ndarray,
    *,
    normalized: bool = False,
) -> np.ndarray:
    """Compute cosine similarity between a query vector and each row of a matrix."""
    query_unit = normalize_vector(query)
    dims = query_unit.shape[0]
    if normalized:
        mat = np.asarray(matrix, dtype=np.float64)
        if mat.ndim != 2 or (mat.shape[0] > 0 and mat.shape[1] != dims):
            raise ValueError("embedding_space_incompatible")
        if mat.shape[0] == 0:
            return np.empty((0,), dtype=np.float64)
    else:
        mat = normalize_matrix(matrix, dimensions=dims)
        if mat.shape[0] == 0:
            return np.empty((0,), dtype=np.float64)
    return np.clip(mat @ query_unit, -1.0, 1.0)
