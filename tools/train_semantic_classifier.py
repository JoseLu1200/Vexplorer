"""Reproduce a selected local recipe on train only, with a bound numeric artifact.

No model selection, evaluation, encoder download or pickle deserialization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from backend.app.semantic_explorer.classification import (
    ClassifierArtifact,
    NumericClassifier,
)
from backend.app.semantic_explorer.models import Bundle
from tools.publish_semantic_explorer import build_bundle, sha


def train_numeric(bundle: Bundle, kind: str):
    from tools.semantic_lab.classifier_comparison import CandidateSpec, fit_candidate

    entries = [entry for entry in bundle.entries if entry.split == "train"]
    if not entries or any(entry.category is None for entry in entries):
        raise ValueError("labeled_train_required")
    names = tuple(sorted(entries[0].features))
    if any(tuple(sorted(entry.features)) != names for entry in bundle.entries):
        raise ValueError("classifier_features_incompatible")
    if len({entry.category for entry in entries}) < 2:
        raise ValueError("at_least_two_training_classes_required")
    recipes = {
        "knn": CandidateSpec("knn_eg2_k5", "knn_embedding", {"n_neighbors": 5}),
        "logreg": CandidateSpec("logreg_combined_c0.1", "logreg_combined", {"C": 0.1}),
    }
    candidate = fit_candidate(
        recipes[kind],
        np.array([[entry.features[n] for n in names] for entry in entries]),
        np.array([entry.vector for entry in entries]),
        np.array([entry.category for entry in entries]),
    )
    estimator = candidate.estimator
    common = {
        "vector_space_id": bundle.space.id,
        "labels": tuple(str(x) for x in estimator.classes_),
    }
    if kind == "knn":
        model = NumericClassifier(
            kind="knn",
            **common,
            train_vectors=estimator._fit_X.tolist(),
            train_labels=estimator._y.tolist(),
            neighbors=estimator.n_neighbors,
        )
    else:
        scaler = candidate.combined_scaler
        model = NumericClassifier(
            kind="logreg",
            **common,
            feature_names=names,
            coefficients=estimator.coef_.tolist(),
            intercept=estimator.intercept_.tolist(),
            mean=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),
        )
    return model, candidate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--kind", choices=("knn", "logreg"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("output_exists_use_new_artifact")
    bundle, _ = build_bundle(args.manifest, args.embeddings)
    model, fitted = train_numeric(bundle, args.kind)
    artifact = ClassifierArtifact.model_validate(
        {
            "schema_version": 2,
            "space": bundle.space.model_dump(mode="json"),
            "feature_names": sorted(bundle.entries[0].features),
            "training": {
                "manifest_sha256": sha(args.manifest),
                "npz_sha256": sha(args.embeddings),
                "split": "train",
                "members": [e.id for e in bundle.entries if e.split == "train"],
                "recipe": fitted.spec.name,
            },
            "classifier": model.model_dump(mode="json"),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(artifact.model_dump_json())
    print(
        json.dumps(
            {
                "artifact": str(args.output),
                "sha256": sha(args.output),
                "training_members": len(artifact.training.members),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
