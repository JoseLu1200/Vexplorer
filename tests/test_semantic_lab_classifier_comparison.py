import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from tools.semantic_lab.classifier_comparison import (
    build_summary,
    candidate_specs,
    fit_candidate,
    load_dataset,
    save_candidate,
    select_fixed_ood,
    select_winner,
    validate_split_counts,
)


def test_candidate_grid_is_the_preregistered_small_set() -> None:
    assert [(spec.family, spec.parameters) for spec in candidate_specs()] == [
        ("knn_embedding", {"n_neighbors": 5}),
        ("logreg_combined", {"C": 0.1}),
        ("logreg_combined", {"C": 1.0}),
        ("logreg_combined", {"C": 10.0}),
        ("histgb_pca_geometry", {"pca_components": 32}),
        ("histgb_pca_geometry", {"pca_components": 64}),
    ]


def test_geometry_scaler_and_pca_fit_training_only() -> None:
    rng = np.random.default_rng(7)
    train_geometry = rng.normal(size=(40, 2))
    train_geometry[:, 0] += 1.0
    train_embeddings = rng.normal(size=(40, 64))
    labels = np.asarray(["a", "b"] * 20)
    validation_geometry = np.asarray([[10_000.0, 20_000.0]])
    validation_embeddings = np.full((1, 64), 10_000.0)

    fitted = fit_candidate(candidate_specs()[4], train_geometry, train_embeddings, labels)
    fitted.predict(validation_geometry, validation_embeddings)

    np.testing.assert_allclose(fitted.geometry_scaler.mean_, train_geometry.mean(axis=0))
    assert fitted.embedding_pca.n_samples_ == 40
    assert fitted.embedding_pca.n_components_ == 32


def test_knn_control_uses_embeddings_and_ignores_geometry() -> None:
    train_embeddings = np.asarray([[1.0, 0.0], [0.0, 1.0], [0.9, 0.1], [0.1, 0.9], [0.8, 0.2]])
    train_geometry = np.arange(10, dtype=float).reshape(5, 2)
    labels = np.asarray(["a", "b", "a", "b", "a"])
    fitted = fit_candidate(candidate_specs()[0], train_geometry, train_embeddings, labels)

    first = fitted.predict(np.asarray([[0.0, 0.0]]), np.asarray([[1.0, 0.0]]))
    second = fitted.predict(np.asarray([[9999.0, -9999.0]]), np.asarray([[1.0, 0.0]]))

    assert first.tolist() == second.tolist() == ["a"]


def test_saved_candidate_loads_in_a_fresh_process(tmp_path: Path) -> None:
    train_embeddings = np.asarray(
        [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1], [0.1, 0.9], [0.8, 0.2]]
    )
    train_geometry = np.arange(10, dtype=float).reshape(5, 2)
    fitted = fit_candidate(
        candidate_specs()[0], train_geometry, train_embeddings, np.asarray(["a", "b", "a", "b", "a"])
    )
    artifact = tmp_path / "winner.joblib"
    save_candidate(fitted, artifact)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from tools.semantic_lab.classifier_comparison import load_candidate; "
                f"print(load_candidate(r'{artifact}').spec.name)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "knn_eg2_k5"


def test_fixed_ood_selection_is_sorted_and_ignores_labels() -> None:
    samples = [
        {"id": f"id-{index:02d}", "label": "revealing-a" if index % 2 else "revealing-b"}
        for index in range(13, -1, -1)
    ]
    changed = [{**sample, "label": "changed"} for sample in samples]

    assert [sample["id"] for sample in select_fixed_ood(samples)] == [
        sample["id"] for sample in select_fixed_ood(changed)
    ] == [f"id-{index:02d}" for index in range(14)]
    with pytest.raises(ValueError, match="exactly 14"):
        select_fixed_ood(samples[:-1])


def test_winner_uses_macro_f1_then_balanced_accuracy_then_fixed_order() -> None:
    candidates = [
        {"name": "first", "metrics": {"macro_f1": 0.8, "balanced_accuracy": 0.7}},
        {"name": "second", "metrics": {"macro_f1": 0.8, "balanced_accuracy": 0.75}},
        {"name": "third", "metrics": {"macro_f1": 0.8, "balanced_accuracy": 0.75}},
    ]
    assert select_winner(candidates)["name"] == "second"


def test_split_counts_must_match_the_preregistered_corpus() -> None:
    samples = [{"split": "train"}, {"split": "validation"}, {"split": "test"}]
    assert validate_split_counts(samples, {"train": 1, "validation": 1, "test": 1}) is None
    with pytest.raises(ValueError, match="split counts changed"):
        validate_split_counts(samples, {"train": 2, "validation": 1, "test": 1})


def test_small_summary_keeps_balanced_accuracy_and_test_confusion() -> None:
    corpus = {
        "counts": {"train": 2, "validation": 1, "test": 1},
        "winner_validation": {
            "name": "winner",
            "metrics": {"macro_f1": 0.8, "balanced_accuracy": 0.75},
        },
        "winner_test_posthoc": {
            "macro_f1": 0.7,
            "balanced_accuracy": 0.65,
            "labels": ["a", "b"],
            "confusion_matrix": [[1, 0], [1, 0]],
        },
    }
    report = {
        "protocol": "fixture",
        "hashes": {},
        "core": corpus,
        "cad_extra": corpus,
        "forced_engineering_to_core": {"predictions": [{}], "distribution": {"a": 1}},
        "limitations": ["fixture"],
    }

    summary = build_summary(report)

    assert summary["core"]["validation_balanced_accuracy"] == 0.75
    assert summary["core"]["test_balanced_accuracy_posthoc"] == 0.65
    assert summary["core"]["test_confusion_labels"] == ["a", "b"]
    assert summary["core"]["test_confusion_matrix"] == [[1, 0], [1, 0]]


def test_dataset_loader_rejects_wrong_embedding_dimension_and_feature_schema(tmp_path: Path) -> None:
    samples = [
        {
            "id": "a",
            "split": "train",
            "label": "x",
            "source_path": "a.dxf",
            "image_path": "a.png",
            "label_source": "fixture",
            "group_id": "g-a",
            "text": "fixture a",
            "features": {f"f{index}": float(index) for index in range(27)},
        },
        {
            "id": "b",
            "split": "validation",
            "label": "x",
            "source_path": "b.dxf",
            "image_path": "b.png",
            "label_source": "fixture",
            "group_id": "g-b",
            "text": "fixture b",
            "features": {f"f{index}": float(index) for index in range(26)},
        },
    ]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "metadata": {}, "samples": samples}), encoding="utf-8")
    embeddings = tmp_path / "vectors.npz"
    np.savez(embeddings, ids=np.asarray(["a", "b"]), embeddings=np.ones((2, 32)))

    with pytest.raises(ValueError, match="768 columns"):
        load_dataset(manifest, embeddings)

    np.savez(embeddings, ids=np.asarray(["a", "b"]), embeddings=np.ones((2, 768)))
    with pytest.raises(ValueError, match="same 27 geometry features"):
        load_dataset(manifest, embeddings)
