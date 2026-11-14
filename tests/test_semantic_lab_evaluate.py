import json
from pathlib import Path

import numpy as np
import pytest

from tools.semantic_lab.evaluate import (
    EmbeddingTable,
    classification_metrics,
    clustering_metrics,
    fit_representation,
    load_embedding_table,
    load_named_embedding_tables,
    retrieval_metrics,
    validate_manifest,
)
from tools.semantic_lab.query import query_index


def sample(
    sample_id: str,
    label: str,
    group: str,
    split: str,
    *,
    width: float = 1.0,
    text: str = "rectangular outline",
) -> dict:
    return {
        "id": sample_id,
        "source_path": f"private/{sample_id}.dxf",
        "image_path": f"private/{sample_id}.png",
        "label": label,
        "label_source": "folder_proxy",
        "group_id": group,
        "split": split,
        "features": {"width": width, "line_count": 4.0},
        "text": text,
    }


def manifest(samples: list[dict]) -> dict:
    return {"schema_version": 1, "metadata": {"fixture": True}, "samples": samples}


def test_manifest_rejects_a_group_crossing_splits() -> None:
    data = manifest(
        [
            sample("a", "chair", "same-family", "train"),
            sample("b", "chair", "same-family", "test"),
        ]
    )

    with pytest.raises(ValueError, match="group_id.*multiple splits"):
        validate_manifest(data)


def test_manifest_rejects_leaky_feature_names_and_non_finite_values() -> None:
    legitimate = sample("paths", "chair", "g0", "train")
    legitimate["features"]["path_count_log1p"] = 2.0
    assert validate_manifest(manifest([legitimate])) == [legitimate]

    leaky = sample("a", "chair", "g1", "train")
    leaky["features"]["source_path_hash"] = 1.0
    with pytest.raises(ValueError, match="forbidden feature name"):
        validate_manifest(manifest([leaky]))

    non_finite = sample("b", "chair", "g2", "train")
    non_finite["features"]["width"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        validate_manifest(manifest([non_finite]))


def test_geometry_and_text_vectors_ignore_ids_paths_and_labels() -> None:
    train = [
        sample("train-a", "chair", "g1", "train", width=1, text="four straight lines"),
        sample("train-b", "table", "g2", "train", width=3, text="round top support"),
    ]
    changed_metadata = sample(
        "secret-category-in-id",
        "secret-label",
        "g3",
        "validation",
        width=2,
        text="four straight lines",
    )
    changed_metadata["source_path"] = "secret-label/revealing-name.dxf"
    neutral_metadata = {**changed_metadata, "id": "neutral", "label": "other", "source_path": "x.dxf"}

    fitted = fit_representation(train, modalities=["geometry", "text"])
    first = fitted.transform([changed_metadata])
    second = fitted.transform([neutral_metadata])

    np.testing.assert_allclose(first, second)


def test_scaler_and_pca_are_fit_only_on_training_samples() -> None:
    train = [
        sample("a", "chair", "g1", "train", width=0),
        sample("b", "table", "g2", "train", width=2),
    ]
    validation_outlier = sample("v", "bed", "g3", "validation", width=10_000)

    fitted = fit_representation(train, modalities=["geometry"], pca_components=1)
    fitted.transform([validation_outlier])

    width_index = fitted.feature_names["geometry"].index("width")
    assert fitted.models["geometry"].named_steps["scale"].mean_[width_index] == pytest.approx(1.0)
    assert fitted.models["geometry"].named_steps["pca"].n_samples_ == 2


def test_embedding_table_rejects_duplicate_missing_and_wrong_shape(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete.npz"
    np.savez(incomplete, ids=np.array(["a"]), unrelated=np.ones((1, 3)))
    with pytest.raises(ValueError, match="must contain ids and embeddings"):
        load_embedding_table(incomplete)

    duplicate = tmp_path / "duplicate.npz"
    np.savez(duplicate, ids=np.array(["a", "a"]), embeddings=np.ones((2, 3)))
    with pytest.raises(ValueError, match="duplicate"):
        load_embedding_table(duplicate, required_ids={"a"})

    missing = tmp_path / "missing.npz"
    np.savez(missing, ids=np.array(["a"]), embeddings=np.ones((1, 3)))
    with pytest.raises(ValueError, match="missing required ids"):
        load_embedding_table(missing, required_ids={"a", "b"})

    wrong_rows = tmp_path / "wrong_rows.npz"
    np.savez(wrong_rows, ids=np.array(["a", "b"]), embeddings=np.ones((1, 3)))
    with pytest.raises(ValueError, match="row count"):
        load_embedding_table(wrong_rows, required_ids={"a", "b"})


def test_embedding_transform_requires_every_requested_id() -> None:
    train = [sample("a", "chair", "g1", "train"), sample("b", "table", "g2", "train")]
    table = EmbeddingTable(ids=("a", "b"), matrix=np.eye(2))
    fitted = fit_representation(train, modalities=["embeddings"], embeddings=table)

    with pytest.raises(ValueError, match="missing embedding.*c"):
        fitted.transform([sample("c", "bed", "g3", "validation")])


def test_metrics_report_proxy_retrieval_and_cluster_noise_honestly() -> None:
    retrieval = retrieval_metrics(
        query_vectors=np.array([[1.0, 0.0], [0.0, 1.0]]),
        query_labels=["a", "b"],
        query_ids=["qa", "qb"],
        reference_vectors=np.array([[0.9, 0.1], [0.0, 1.0], [0.8, 0.2]]),
        reference_labels=["a", "b", "a"],
        reference_ids=["ra1", "rb", "ra2"],
        k=2,
    )
    assert retrieval == {
        "precision_at_k": pytest.approx(0.75),
        "hit_at_k": pytest.approx(1.0),
        "coverage": pytest.approx(1.0),
        "evaluated_queries": 2,
        "total_queries": 2,
        "k": 2,
        "relevance": "same_proxy_label",
    }

    clusters = clustering_metrics(["a", "a", "b", "b"], [0, -1, 1, -1])
    assert clusters["coverage"] == pytest.approx(0.5)
    assert clusters["noise_count"] == 2
    assert clusters["singleton_clusters"] == 2
    assert clusters["purity_assigned"] == pytest.approx(1.0)
    assert "ari_all_including_noise" in clusters
    assert "nmi_all_including_noise" in clusters


def test_classification_metrics_use_macro_and_balanced_scores() -> None:
    metrics = classification_metrics(
        ["a", "a", "b", "b"],
        ["a", "b", "b", "b"],
        sample_ids=["one", "wrong", "three", "four"],
    )
    assert metrics["macro_f1"] == pytest.approx((2 / 3 + 0.8) / 2)
    assert metrics["balanced_accuracy"] == pytest.approx(0.75)
    assert metrics["class_count"] == 2
    assert metrics["labels"] == ["a", "b"]
    assert metrics["confusion_matrix"] == [[1, 1], [0, 2]]
    assert metrics["error_ids"] == ["wrong"]
    assert metrics["per_class"]["a"]["recall"] == pytest.approx(0.5)


def test_test_cli_requires_explicit_opt_in(tmp_path: Path) -> None:
    from tools.semantic_lab.evaluate import main

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest([])), encoding="utf-8")
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(SystemExit, match="--allow-test"):
        main(
            [
                "test",
                "--manifest",
                str(manifest_path),
                "--frozen-config",
                str(frozen),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )


def test_named_embeddings_are_compared_without_exposing_test_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from tools.semantic_lab.evaluate import main

    samples = [
        sample("tr-a", "a", "g1", "train", width=0),
        sample("tr-b", "b", "g2", "train", width=2),
        sample("va-a", "a", "g3", "validation", width=0.1),
        sample("va-b", "b", "g4", "validation", width=1.9),
        sample("SEALED-TEST-ID", "a", "g5", "test", width=0.2),
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest(samples)), encoding="utf-8")
    first = tmp_path / "first.npz"
    second = tmp_path / "second.npz"
    ids = np.asarray([item["id"] for item in samples])
    np.savez(first, ids=ids, embeddings=np.asarray([[1, 0], [0, 1], [1, 0], [0, 1], [1, 0]]))
    np.savez(second, ids=ids, embeddings=np.asarray([[1, 1], [1, 0], [1, 1], [1, 0], [1, 1]]))
    output = tmp_path / "output"

    assert main(
        [
            "select",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output),
            "--embedding",
            f"dino={first}",
            "--embedding",
            f"eg2={second}",
            "--representations",
            "embeddings",
            "--classifiers",
            "centroid",
            "--cluster-counts",
            "2",
        ]
    ) == 0

    report_text = (output / "validation-report.json").read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert {candidate["embedding_name"] for candidate in report["candidates"]} == {"dino", "eg2"}
    assert "SEALED-TEST-ID" not in report_text
    assert report["success_targets"] == {"macro_f1": 0.7, "balanced_accuracy": 0.75}
    frozen = json.loads((output / "frozen-config.json").read_text(encoding="utf-8"))
    assert frozen["embedding_name"] in {"dino", "eg2"}
    capsys.readouterr()


def test_named_embedding_specs_reject_duplicate_names(tmp_path: Path) -> None:
    path = tmp_path / "vectors.npz"
    np.savez(path, ids=np.asarray(["a"]), embeddings=np.ones((1, 2)))
    with pytest.raises(ValueError, match="duplicate embedding name"):
        load_named_embedding_tables([f"same={path}", f"same={path}"], {"a"})


def test_query_uses_train_references_and_explains_each_modality(tmp_path: Path) -> None:
    npz_path = tmp_path / "query-index.npz"
    np.savez(
        npz_path,
        ids=np.asarray(["train-a", "train-b", "heldout"]),
        vectors=np.asarray([[1.0, 0], [0, 1.0], [0.8, 0.2]]),
        modality_geometry=np.asarray([[1.0, 0], [0, 1.0], [1.0, 0]]),
        modality_text=np.asarray([[1.0, 0], [0, 1.0], [0.6, 0.8]]),
    )
    metadata_path = tmp_path / "query-index.json"
    metadata_path.write_text(
        json.dumps(
            {
                "reference_split": "train",
                "samples": [
                    {"id": "train-a", "proxy_label": "a", "split": "train"},
                    {"id": "train-b", "proxy_label": "b", "split": "train"},
                    {"id": "heldout", "proxy_label": "a", "split": "test"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = query_index(
        npz_path,
        metadata_path,
        "heldout",
        k=2,
        frozen_config={"classifier": "centroid", "neighbors": 1, "seed": 0},
    )

    assert [neighbor["id"] for neighbor in result["neighbors"]] == ["train-a", "train-b"]
    assert result["neighbors"][0]["cosine_similarity"] == pytest.approx(0.9701425)
    assert result["neighbors"][0]["modality_cosine"] == {
        "geometry": pytest.approx(1.0),
        "text": pytest.approx(0.6),
    }
    assert result["predicted_label"] == "a"


def test_final_test_rejects_changed_embedding_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from tools.semantic_lab.evaluate import main

    samples = [
        sample("tr-a", "a", "g1", "train"),
        sample("tr-b", "b", "g2", "train"),
        sample("va-a", "a", "g3", "validation"),
        sample("va-b", "b", "g4", "validation"),
        sample("te-a", "a", "g5", "test"),
        sample("te-b", "b", "g6", "test"),
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest(samples)), encoding="utf-8")
    vectors_path = tmp_path / "learned.npz"
    ids = np.asarray([item["id"] for item in samples])
    np.savez(vectors_path, ids=ids, embeddings=np.asarray([[1, 0], [0, 1]] * 3))
    output = tmp_path / "output"
    main(
        [
            "select",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output),
            "--embedding",
            f"learned={vectors_path}",
            "--representations",
            "embeddings",
            "--classifiers",
            "centroid",
            "--cluster-counts",
            "2",
        ]
    )
    capsys.readouterr()
    np.savez(vectors_path, ids=ids, embeddings=np.asarray([[0, 1], [1, 0]] * 3))

    with pytest.raises(ValueError, match="embedding file changed after validation selection"):
        main(
            [
                "test",
                "--manifest",
                str(manifest_path),
                "--frozen-config",
                str(output / "frozen-config.json"),
                "--output-dir",
                str(output),
                "--embedding",
                f"learned={vectors_path}",
                "--allow-test",
            ]
        )


def _prepare_geometry_selection(tmp_path: Path) -> tuple[Path, Path, Path]:
    from tools.semantic_lab.evaluate import main

    samples = [
        sample("tr-a", "a", "g1", "train", width=0),
        sample("tr-b", "b", "g2", "train", width=2),
        sample("va-a", "a", "g3", "validation", width=0.1),
        sample("va-b", "b", "g4", "validation", width=1.9),
        sample("te-a", "a", "g5", "test", width=0.2),
        sample("te-b", "b", "g6", "test", width=1.8),
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest(samples)), encoding="utf-8")
    output = tmp_path / "output"
    main(
        [
            "select",
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output),
            "--representations",
            "geometry",
            "--classifiers",
            "centroid",
            "--cluster-counts",
            "2",
        ]
    )
    return manifest_path, output / "frozen-config.json", output


def test_final_test_rejects_frozen_config_edited_after_selection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.semantic_lab.evaluate import main

    manifest_path, frozen_path, output = _prepare_geometry_selection(tmp_path)
    capsys.readouterr()
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen["neighbors"] = 99
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")

    with pytest.raises(ValueError, match="frozen configuration hash does not match validation report"):
        main(
            [
                "test",
                "--manifest",
                str(manifest_path),
                "--frozen-config",
                str(frozen_path),
                "--output-dir",
                str(output),
                "--allow-test",
            ]
        )


def test_final_test_requires_adjacent_validation_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.semantic_lab.evaluate import main

    manifest_path, frozen_path, output = _prepare_geometry_selection(tmp_path)
    capsys.readouterr()
    (output / "validation-report.json").unlink()

    with pytest.raises(ValueError, match="adjacent validation-report.json is required"):
        main(
            [
                "test",
                "--manifest",
                str(manifest_path),
                "--frozen-config",
                str(frozen_path),
                "--output-dir",
                str(output),
                "--allow-test",
            ]
        )


def test_final_test_rejects_validation_winner_inconsistent_with_frozen_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.semantic_lab.evaluate import main

    manifest_path, frozen_path, output = _prepare_geometry_selection(tmp_path)
    capsys.readouterr()
    report_path = output / "validation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["winner"]["classifier"] = "knn"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="validation winner is inconsistent with frozen configuration"):
        main(
            [
                "test",
                "--manifest",
                str(manifest_path),
                "--frozen-config",
                str(frozen_path),
                "--output-dir",
                str(output),
                "--allow-test",
            ]
        )
