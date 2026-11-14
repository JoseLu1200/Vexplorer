"""Inference from numeric artifacts only. No executable model deserialization."""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field

from backend.app.similarity.math_utils import cosine_matrix, normalize_vector

from .models import Classification, Space, StrictModel, digest


class NumericClassifier(StrictModel):
    kind: Literal["logreg", "knn"]
    vector_space_id: str
    labels: tuple[str, ...] = Field(min_length=2, max_length=100)
    feature_names: tuple[str, ...] = ()
    coefficients: tuple[tuple[float, ...], ...] = ()
    intercept: tuple[float, ...] = ()
    mean: tuple[float, ...] = ()
    scale: tuple[float, ...] = ()
    train_vectors: tuple[tuple[float, ...], ...] = Field(default=(), max_length=2000)
    train_labels: tuple[int, ...] = Field(default=(), max_length=2000)
    neighbors: int = Field(default=5, ge=1, le=50)


class TrainingRecord(StrictModel):
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    npz_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    split: Literal["train"] = "train"
    members: tuple[str, ...] = Field(default=(), max_length=2000)
    recipe: str | None = None


class ClassifierArtifact(StrictModel):
    schema_version: Literal[2] = 2
    space: Space
    feature_names: tuple[str, ...]
    training: TrainingRecord
    classifier: NumericClassifier


def classify(
    model: NumericClassifier,
    space: Space,
    vector: tuple[float, ...],
    features: dict[str, float],
) -> Classification:
    if model.vector_space_id != space.id or len(vector) != space.dimensions:
        raise ValueError("classifier_space_incompatible")
    try:
        x = normalize_vector(vector)
    except ValueError as exc:
        raise ValueError("classifier_invalid_vector") from exc
    if model.kind == "logreg":
        if any(name not in features for name in model.feature_names):
            raise ValueError("classifier_features_missing")
        x = np.concatenate((x, [features[n] for n in model.feature_names]))
        coefs, intercept, mean, scale = map(
            np.asarray, (model.coefficients, model.intercept, model.mean, model.scale)
        )
        rows = 1 if len(model.labels) == 2 else len(model.labels)
        if (
            coefs.shape != (rows, len(x))
            or intercept.shape != (rows,)
            or mean.shape != x.shape
            or scale.shape != x.shape
            or np.any(scale <= 0)
        ):
            raise ValueError("classifier_shape_invalid")
        scores = coefs @ ((x - mean) / scale) + intercept
        if not np.isfinite(scores).all():
            raise ValueError("classifier_nonfinite")
        if rows == 1:
            p = float(1 / (1 + np.exp(-np.clip(scores[0], -700, 700))))
            probabilities = np.array([1 - p, p])
        else:
            exp = np.exp(scores - scores.max())
            probabilities = exp / exp.sum()
    else:
        train = np.asarray(model.train_vectors, dtype=float)
        labels = np.asarray(model.train_labels, dtype=int)
        if (
            train.ndim != 2
            or train.shape[1] != len(x)
            or len(train) < model.neighbors
            or labels.shape != (len(train),)
            or np.any(labels < 0)
            or np.any(labels >= len(model.labels))
        ):
            raise ValueError("classifier_shape_invalid")
        try:
            scores = cosine_matrix(x, train)
        except ValueError as exc:
            if str(exc) == "invalid_embedding":
                raise ValueError("classifier_nonfinite") from exc
            raise ValueError("classifier_shape_invalid") from exc
        distances = np.maximum(0, 1 - scores)
        positions = np.argsort(distances, kind="stable")[: model.neighbors]
        selected = distances[positions]
        exact = selected <= 1e-15
        weights = exact.astype(float) if exact.any() else 1 / selected
        probabilities = np.bincount(
            labels[positions], weights=weights, minlength=len(model.labels)
        )
        probabilities /= probabilities.sum()
    winner = int(np.argmax(probabilities))
    return Classification(
        label=model.labels[winner],
        score=float(probabilities[winner]),
        method=model.kind,
        artifact_id=digest(model.model_dump(mode="json")),
    )
