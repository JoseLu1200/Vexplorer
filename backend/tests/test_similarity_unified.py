from __future__ import annotations

import math

import numpy as np
import pytest

from backend.app.semantic_explorer.classification import NumericClassifier, classify
from backend.app.semantic_explorer.models import Space
from backend.app.similarity.math_utils import (
    cosine_matrix,
    cosine_similarity,
    normalize_matrix,
    normalize_vector,
)
from backend.app.similarity.service import cosine_similarity as service_cosine_similarity


def test_normalize_vector_unit_length_and_extreme_scales():
    unit = normalize_vector((3.0, 4.0))
    assert np.allclose(unit, [0.6, 0.8])
    assert math.isclose(float(np.linalg.norm(unit)), 1.0, rel_tol=1e-12)

    large = normalize_vector((1e200, 1e200))
    assert np.allclose(large, [math.sqrt(0.5), math.sqrt(0.5)])

    small = normalize_vector((1e-200, 1e-200))
    assert np.allclose(small, [math.sqrt(0.5), math.sqrt(0.5)])


@pytest.mark.parametrize("bad_vector", [(), [], [[1.0, 2.0]]])
def test_normalize_vector_rejects_empty_or_non_1d(bad_vector):
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        normalize_vector(bad_vector)


@pytest.mark.parametrize(
    "bad_vector",
    [
        (0.0, 0.0, 0.0),
        (1.0, float("nan")),
        (1.0, float("inf")),
        (float("-inf"), 1.0),
    ],
)
def test_normalize_vector_rejects_zero_and_nonfinite(bad_vector):
    with pytest.raises(ValueError, match="invalid_embedding"):
        normalize_vector(bad_vector)


def test_cosine_similarity_values_and_service_delegation():
    assert math.isclose(cosine_similarity((1.0, 0.0), (1.0, 0.0)), 1.0, rel_tol=1e-12)
    assert math.isclose(cosine_similarity((1.0, 0.0), (0.0, 1.0)), 0.0, abs_tol=1e-12)
    assert math.isclose(cosine_similarity((1.0, 0.0), (-2.0, 0.0)), -1.0, rel_tol=1e-12)
    assert math.isclose(
        cosine_similarity((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)),
        service_cosine_similarity((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)),
        rel_tol=1e-12,
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ((), ()),
        ((1.0,), (1.0, 2.0)),
        ((0.0, 0.0), (1.0, 2.0, 3.0)),
    ],
)
def test_cosine_similarity_incompatible_space(left, right):
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        cosine_similarity(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.0, 0.0), (0.0, 0.0)),
        ((1.0, float("nan")), (1.0, 0.0)),
        ((1.0, 0.0), (float("inf"), 1.0)),
    ],
)
def test_cosine_similarity_invalid_embedding(left, right):
    with pytest.raises(ValueError, match="invalid_embedding"):
        cosine_similarity(left, right)


def test_normalize_matrix_and_empty_handling():
    mat = normalize_matrix([(3.0, 4.0), (0.0, -5.0), (1e200, 0.0)])
    assert mat.shape == (3, 2)
    assert np.allclose(mat, [[0.6, 0.8], [0.0, -1.0], [1.0, 0.0]])

    empty_dims = normalize_matrix([], dimensions=4)
    assert empty_dims.shape == (0, 4)

    empty_no_dims = normalize_matrix([])
    assert empty_no_dims.shape == (0, 0)


@pytest.mark.parametrize(
    ("vectors", "dimensions"),
    [
        ([(1.0, 2.0), (3.0,)], None),
        ([(1.0, 2.0)], 3),
        ((1.0, 2.0), None),
        ([()], None),
        ([(1.0, 2.0)], 0),
    ],
)
def test_normalize_matrix_incompatible_space(vectors, dimensions):
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        normalize_matrix(vectors, dimensions=dimensions)


@pytest.mark.parametrize(
    "vectors",
    [
        [(1.0, 0.0), (0.0, 0.0)],
        [(1.0, float("nan")), (0.0, 1.0)],
        [(1.0, 0.0), (float("inf"), 1.0)],
    ],
)
def test_normalize_matrix_invalid_embedding(vectors):
    with pytest.raises(ValueError, match="invalid_embedding"):
        normalize_matrix(vectors)


def test_cosine_matrix_raw_and_prenormalized_match_pairwise():
    query = (1.0, 2.0, -1.0)
    rows = [(1.0, 0.0, 0.0), (2.0, 4.0, -2.0), (-1.0, -2.0, 1.0)]
    raw_scores = cosine_matrix(query, rows)
    prenorm_scores = cosine_matrix(query, normalize_matrix(rows), normalized=True)
    expected = [cosine_similarity(query, row) for row in rows]
    assert np.allclose(raw_scores, expected, atol=1e-12)
    assert np.allclose(prenorm_scores, expected, atol=1e-12)

    empty_scores = cosine_matrix(query, np.empty((0, 3), dtype=np.float64))
    assert empty_scores.shape == (0,)


def test_cosine_matrix_errors():
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        cosine_matrix((1.0, 2.0), [(1.0, 2.0, 3.0)])
    with pytest.raises(ValueError, match="invalid_embedding"):
        cosine_matrix((0.0, 0.0), [(1.0, 2.0)])
    with pytest.raises(ValueError, match="invalid_embedding"):
        cosine_matrix((1.0, 2.0), [(1.0, float("nan"))])

    with pytest.raises(ValueError, match="invalid_embedding"):
        cosine_matrix(
            (1.0, 2.0),
            np.asarray([(float("nan"), 0.0)], dtype=np.float64),
            normalized=True,
        )


def test_knn_classifier_uses_math_utils_error_semantics():
    space = Space(
        provider="p",
        model="m",
        revision="r",
        dimensions=2,
        mode="text",
        preprocessing="prep",
        descriptor_version="1",
    )
    model = NumericClassifier(
        kind="knn",
        vector_space_id=space.id,
        labels=("a", "b"),
        neighbors=1,
        train_vectors=((1.0, 0.0), (0.0, 1.0)),
        train_labels=(0, 1),
    )
    result = classify(model, space, (0.9, 0.1), {})
    assert result.label == "a"

    with pytest.raises(ValueError, match="classifier_invalid_vector"):
        classify(model, space, (0.0, 0.0), {})
