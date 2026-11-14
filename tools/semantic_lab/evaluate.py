"""Leakage-conscious evaluation CLI for the isolated semantic laboratory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    adjusted_rand_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    normalized_mutual_info_score,
    precision_recall_fscore_support,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, normalize


FORBIDDEN_FEATURE_FIELDS = {
    "id",
    "label",
    "label_source",
    "sample_id",
    "group_id",
    "source_path",
    "image_path",
    "source",
    "split",
    "group",
    "category",
    "class",
    "filename",
}
SPLITS = {"train", "validation", "test"}
MODALITIES = {"geometry", "text", "embeddings"}


@dataclass(frozen=True)
class EmbeddingTable:
    ids: tuple[str, ...]
    matrix: np.ndarray
    sha256: str | None = None

    def lookup(self, requested_ids: Sequence[str]) -> np.ndarray:
        positions = {sample_id: index for index, sample_id in enumerate(self.ids)}
        missing = [sample_id for sample_id in requested_ids if sample_id not in positions]
        if missing:
            raise ValueError(f"missing embedding for ids: {', '.join(missing[:5])}")
        return np.asarray([self.matrix[positions[sample_id]] for sample_id in requested_ids], dtype=float)


@dataclass
class TextModel:
    vectorizer: TfidfVectorizer
    pca: PCA | None = None

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        matrix = self.vectorizer.transform(texts).toarray()
        return self.pca.transform(matrix) if self.pca is not None else matrix


@dataclass
class EmbeddingModel:
    table: EmbeddingTable
    pca: PCA | None = None

    def transform(self, ids: Sequence[str]) -> np.ndarray:
        matrix = self.table.lookup(ids)
        return self.pca.transform(matrix) if self.pca is not None else matrix


@dataclass
class FittedRepresentation:
    modalities: tuple[str, ...]
    models: dict[str, Any]
    feature_names: dict[str, list[str]]
    weights: dict[str, float]
    dimensions: dict[str, int]

    def transform_modalities(self, samples: Sequence[dict[str, Any]]) -> dict[str, np.ndarray]:
        outputs: dict[str, np.ndarray] = {}
        if "geometry" in self.modalities:
            names = self.feature_names["geometry"]
            raw = np.asarray(
                [[float(sample["features"].get(name, 0.0)) for name in names] for sample in samples],
                dtype=float,
            )
            outputs["geometry"] = _unit_rows(self.models["geometry"].transform(raw))
        if "text" in self.modalities:
            outputs["text"] = _unit_rows(
                self.models["text"].transform([str(sample["text"]) for sample in samples])
            )
        if "embeddings" in self.modalities:
            outputs["embeddings"] = _unit_rows(
                self.models["embeddings"].transform([str(sample["id"]) for sample in samples])
            )
        return outputs

    def transform(self, samples: Sequence[dict[str, Any]]) -> np.ndarray:
        if not samples:
            return np.empty((0, sum(self.dimensions.values())), dtype=float)
        by_modality = self.transform_modalities(samples)
        fused = np.concatenate(
            [by_modality[name] * self.weights[name] for name in self.modalities], axis=1
        )
        return _unit_rows(fused)


class NearestCentroidClassifier(BaseEstimator, ClassifierMixin):
    def fit(self, matrix: np.ndarray, labels: Sequence[str]) -> "NearestCentroidClassifier":
        self.classes_ = np.asarray(sorted(set(labels)))
        self.centroids_ = np.vstack(
            [np.asarray(matrix)[np.asarray(labels) == label].mean(axis=0) for label in self.classes_]
        )
        self.centroids_ = _unit_rows(self.centroids_)
        return self

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return self.classes_[np.argmax(_unit_rows(np.asarray(matrix)) @ self.centroids_.T, axis=1)]


def _unit_rows(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape[0] == 0:
        return matrix
    return normalize(matrix, norm="l2", axis=1)


def validate_manifest(data: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if not isinstance(data.get("metadata"), dict) or not isinstance(data.get("samples"), list):
        raise ValueError("manifest requires metadata object and samples array")
    required = {
        "id",
        "source_path",
        "image_path",
        "label",
        "label_source",
        "group_id",
        "split",
        "features",
        "text",
    }
    ids: set[str] = set()
    groups: dict[str, str] = {}
    for index, sample in enumerate(data["samples"]):
        if not isinstance(sample, dict) or not required.issubset(sample):
            raise ValueError(f"sample {index} is missing required fields")
        sample_id = sample["id"]
        if not isinstance(sample_id, str) or not sample_id or sample_id in ids:
            raise ValueError(f"sample id must be unique and non-empty: {sample_id!r}")
        ids.add(sample_id)
        split = sample["split"]
        if split not in SPLITS:
            raise ValueError(f"sample {sample_id} has invalid split {split!r}")
        group = sample["group_id"]
        if not isinstance(group, str) or not group:
            raise ValueError(f"sample {sample_id} has invalid group_id")
        previous_split = groups.setdefault(group, split)
        if previous_split != split:
            raise ValueError(f"group_id {group!r} occurs in multiple splits")
        if not isinstance(sample["features"], dict):
            raise ValueError(f"sample {sample_id} features must be an object")
        for name, value in sample["features"].items():
            normalized_name = str(name).lower().replace("-", "_")
            if any(
                normalized_name == field or normalized_name.startswith(f"{field}_")
                for field in FORBIDDEN_FEATURE_FIELDS
            ):
                raise ValueError(f"forbidden feature name {name!r} in sample {sample_id}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"feature {name!r} in sample {sample_id} must be finite numeric")
        if not isinstance(sample["text"], str):
            raise ValueError(f"sample {sample_id} text must be a string")
    return data["samples"]


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    data = json.loads(raw)
    validate_manifest(data)
    return data, hashlib.sha256(raw).hexdigest()


def load_embedding_table(path: Path, required_ids: set[str] | None = None) -> EmbeddingTable:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path, allow_pickle=False) as archive:
        if not {"ids", "embeddings"}.issubset(archive.files):
            raise ValueError("embedding NPZ must contain ids and embeddings")
        ids_array = np.asarray(archive["ids"])
        matrix = np.asarray(archive["embeddings"], dtype=float)
    if ids_array.ndim != 1 or matrix.ndim != 2:
        raise ValueError("embedding ids must be 1D and embeddings must be 2D")
    ids = tuple(str(value) for value in ids_array.tolist())
    if matrix.shape[0] != len(ids):
        raise ValueError("embedding row count does not match ids")
    if len(set(ids)) != len(ids):
        raise ValueError("embedding ids contain duplicates")
    if matrix.shape[1] == 0 or not np.isfinite(matrix).all():
        raise ValueError("embeddings must be non-empty finite vectors")
    if required_ids:
        missing = sorted(required_ids - set(ids))
        if missing:
            raise ValueError(f"embedding table missing required ids: {', '.join(missing[:5])}")
    return EmbeddingTable(ids=ids, matrix=matrix, sha256=digest)


def load_named_embedding_tables(
    specifications: Sequence[str], required_ids: set[str] | None = None
) -> dict[str, EmbeddingTable]:
    tables: dict[str, EmbeddingTable] = {}
    for specification in specifications:
        if "=" not in specification:
            raise ValueError("--embedding must use NAME=PATH")
        name, raw_path = specification.split("=", 1)
        if not name or not raw_path:
            raise ValueError("--embedding must use non-empty NAME=PATH")
        if name in tables:
            raise ValueError(f"duplicate embedding name: {name}")
        tables[name] = load_embedding_table(Path(raw_path), required_ids)
    return tables


def _fit_pca(matrix: np.ndarray, requested: int | None) -> PCA | None:
    if requested is None:
        return None
    maximum = min(matrix.shape)
    if requested < 1 or requested > maximum:
        raise ValueError(f"PCA components {requested} invalid; valid range is 1..{maximum}")
    return PCA(n_components=requested, svd_solver="full").fit(matrix)


def fit_representation(
    train_samples: Sequence[dict[str, Any]],
    *,
    modalities: Sequence[str],
    embeddings: EmbeddingTable | None = None,
    pca_components: int | None = None,
    weights: dict[str, float] | None = None,
) -> FittedRepresentation:
    if not train_samples:
        raise ValueError("at least one training sample is required")
    selected = tuple(modalities)
    if not selected or len(set(selected)) != len(selected) or set(selected) - MODALITIES:
        raise ValueError(f"invalid modalities: {selected}")
    configured_weights = {name: 1.0 for name in selected}
    if weights:
        configured_weights.update(weights)
    if any(not math.isfinite(configured_weights[name]) or configured_weights[name] <= 0 for name in selected):
        raise ValueError("fusion weights must be positive finite numbers")

    models: dict[str, Any] = {}
    feature_names: dict[str, list[str]] = {}
    dimensions: dict[str, int] = {}
    if "geometry" in selected:
        names = sorted({name for sample in train_samples for name in sample["features"]})
        if not names:
            raise ValueError("geometry representation requires at least one feature")
        raw = np.asarray(
            [[float(sample["features"].get(name, 0.0)) for name in names] for sample in train_samples]
        )
        steps: list[tuple[str, Any]] = [("scale", StandardScaler())]
        scaled = steps[0][1].fit_transform(raw)
        if pca_components is not None:
            pca = _fit_pca(scaled, pca_components)
            assert pca is not None
            steps.append(("pca", pca))
        pipeline = Pipeline(steps)
        pipeline.steps[0] = ("scale", steps[0][1])
        models["geometry"] = pipeline
        feature_names["geometry"] = names
        dimensions["geometry"] = pca_components or raw.shape[1]
    if "text" in selected:
        vectorizer = TfidfVectorizer(lowercase=True, norm="l2", dtype=np.float64)
        raw_text = vectorizer.fit_transform([str(sample["text"]) for sample in train_samples]).toarray()
        pca = _fit_pca(raw_text, pca_components) if pca_components is not None else None
        models["text"] = TextModel(vectorizer, pca)
        feature_names["text"] = vectorizer.get_feature_names_out().tolist()
        dimensions["text"] = pca_components or raw_text.shape[1]
    if "embeddings" in selected:
        if embeddings is None:
            raise ValueError("embeddings modality requires an embedding table")
        raw_embeddings = embeddings.lookup([str(sample["id"]) for sample in train_samples])
        pca = _fit_pca(raw_embeddings, pca_components) if pca_components is not None else None
        models["embeddings"] = EmbeddingModel(embeddings, pca)
        feature_names["embeddings"] = []
        dimensions["embeddings"] = pca_components or raw_embeddings.shape[1]
    return FittedRepresentation(selected, models, feature_names, configured_weights, dimensions)


def classification_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    sample_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    if len(y_true) != len(y_pred) or (sample_ids is not None and len(sample_ids) != len(y_true)):
        raise ValueError("classification inputs must have matching lengths")
    labels = sorted(set(y_true) | set(y_pred))
    precision, recall, class_f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    result = {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "class_count": len(set(y_true)),
        "sample_count": len(y_true),
        "labels": labels,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(class_f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(labels)
        },
    }
    if sample_ids is not None:
        result["error_ids"] = [
            str(sample_id)
            for sample_id, expected, predicted in zip(sample_ids, y_true, y_pred, strict=True)
            if expected != predicted
        ]
    return result


def retrieval_metrics(
    *,
    query_vectors: np.ndarray,
    query_labels: Sequence[str],
    query_ids: Sequence[str],
    reference_vectors: np.ndarray,
    reference_labels: Sequence[str],
    reference_ids: Sequence[str],
    k: int,
) -> dict[str, Any]:
    if k < 1:
        raise ValueError("retrieval k must be positive")
    precisions: list[float] = []
    hits: list[float] = []
    similarities = _unit_rows(query_vectors) @ _unit_rows(reference_vectors).T
    for row, (query_id, query_label) in enumerate(zip(query_ids, query_labels, strict=True)):
        candidates = [index for index, ref_id in enumerate(reference_ids) if ref_id != query_id]
        relevant = [index for index in candidates if reference_labels[index] == query_label]
        if not relevant:
            continue
        ranked = sorted(candidates, key=lambda index: (-similarities[row, index], reference_ids[index]))
        selected = ranked[: min(k, len(ranked))]
        relevant_count = sum(reference_labels[index] == query_label for index in selected)
        precisions.append(relevant_count / len(selected) if selected else 0.0)
        hits.append(float(relevant_count > 0))
    total = len(query_ids)
    return {
        "precision_at_k": float(np.mean(precisions)) if precisions else 0.0,
        "hit_at_k": float(np.mean(hits)) if hits else 0.0,
        "coverage": len(precisions) / total if total else 0.0,
        "evaluated_queries": len(precisions),
        "total_queries": total,
        "k": k,
        "relevance": "same_proxy_label",
    }


def clustering_metrics(labels: Sequence[str], clusters: Sequence[int]) -> dict[str, Any]:
    labels_array = np.asarray(labels)
    cluster_array = np.asarray(clusters)
    assigned = cluster_array != -1
    assigned_ids = sorted(set(cluster_array[assigned].tolist()))
    correct = 0
    sizes: dict[str, int] = {}
    for cluster_id in assigned_ids:
        cluster_labels = labels_array[cluster_array == cluster_id]
        counts = np.unique(cluster_labels, return_counts=True)[1]
        correct += int(counts.max())
        sizes[str(cluster_id)] = int(len(cluster_labels))
    assigned_count = int(assigned.sum())
    return {
        "ari_all_including_noise": float(adjusted_rand_score(labels_array, cluster_array)),
        "nmi_all_including_noise": float(normalized_mutual_info_score(labels_array, cluster_array)),
        "purity_assigned": correct / assigned_count if assigned_count else 0.0,
        "coverage": assigned_count / len(labels_array) if len(labels_array) else 0.0,
        "noise_count": int((~assigned).sum()),
        "singleton_clusters": sum(size == 1 for size in sizes.values()),
        "cluster_count_excluding_noise": len(assigned_ids),
        "cluster_sizes": sizes,
    }


def _classifier(name: str, *, neighbors: int, seed: int) -> Any:
    if name == "knn":
        return KNeighborsClassifier(n_neighbors=neighbors, metric="cosine", weights="distance")
    if name == "centroid":
        return NearestCentroidClassifier()
    if name == "logreg":
        return LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
    raise ValueError(f"unknown classifier {name!r}")


def _distribution(samples: Sequence[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for sample in samples:
        result[str(sample["label"])] = result.get(str(sample["label"]), 0) + 1
    return dict(sorted(result.items()))


def _fit_clusterer(name: str, matrix: np.ndarray, *, count: int, seed: int) -> np.ndarray:
    if name == "kmeans":
        return KMeans(n_clusters=count, random_state=seed, n_init=20).fit_predict(matrix)
    if name == "hdbscan":
        try:
            from sklearn.cluster import HDBSCAN
        except ImportError as exc:
            raise RuntimeError("HDBSCAN is unavailable in this scikit-learn build") from exc
        return HDBSCAN(min_cluster_size=max(2, count)).fit_predict(matrix)
    raise ValueError(f"unknown clusterer {name!r}")


def _evaluate_configuration(
    train: Sequence[dict[str, Any]],
    target: Sequence[dict[str, Any]],
    *,
    modalities: Sequence[str],
    classifier_name: str,
    neighbors: int,
    retrieval_k: int,
    pca_components: int | None,
    embeddings: EmbeddingTable | None,
    seed: int,
) -> tuple[dict[str, Any], FittedRepresentation]:
    representation = fit_representation(
        train,
        modalities=modalities,
        embeddings=embeddings,
        pca_components=pca_components,
    )
    train_vectors = representation.transform(train)
    target_vectors = representation.transform(target)
    classifier = _classifier(classifier_name, neighbors=min(neighbors, len(train)), seed=seed)
    classifier.fit(train_vectors, [str(sample["label"]) for sample in train])
    predicted = classifier.predict(target_vectors)
    result = {
        "representation": "+".join(modalities),
        "modalities": list(modalities),
        "pca_components": pca_components,
        "classifier": classifier_name,
        "classification": classification_metrics(
            [str(sample["label"]) for sample in target],
            predicted.tolist(),
            sample_ids=[str(sample["id"]) for sample in target],
        ),
        "retrieval": retrieval_metrics(
            query_vectors=target_vectors,
            query_labels=[str(sample["label"]) for sample in target],
            query_ids=[str(sample["id"]) for sample in target],
            reference_vectors=train_vectors,
            reference_labels=[str(sample["label"]) for sample in train],
            reference_ids=[str(sample["id"]) for sample in train],
            k=retrieval_k,
        ),
    }
    return result, representation


def _parse_representations(values: Sequence[str], embeddings_available: bool) -> list[list[str]]:
    representations: list[list[str]] = []
    for value in values:
        modalities = value.split("+")
        if "embeddings" in modalities and not embeddings_available:
            continue
        if not modalities or set(modalities) - MODALITIES:
            raise ValueError(f"invalid representation {value!r}")
        representations.append(modalities)
    if not representations:
        raise ValueError("no usable representations requested")
    return representations


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical_sha256(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_frozen_selection(
    frozen: dict[str, Any], frozen_path: Path, manifest_hash: str
) -> dict[str, Any]:
    report_path = frozen_path.parent / "validation-report.json"
    if not report_path.is_file():
        raise ValueError("adjacent validation-report.json is required")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        report.get("schema_version") != 1
        or report.get("phase") != "validation_selection"
        or report.get("test_evaluated") is not False
        or frozen.get("selection_phase") != "validation_only"
    ):
        raise ValueError("invalid validation selection provenance")
    if report.get("manifest_sha256") != manifest_hash or frozen.get("manifest_sha256") != manifest_hash:
        raise ValueError("manifest changed after validation selection")
    if report.get("selected_config_sha256") != _canonical_sha256(frozen):
        raise ValueError("frozen configuration hash does not match validation report")
    winner = report.get("winner")
    if not isinstance(winner, dict) or any(
        winner.get(key) != frozen.get(key)
        for key in ("modalities", "pca_components", "classifier", "embedding_name")
    ):
        raise ValueError("validation winner is inconsistent with frozen configuration")
    best_cluster = report.get("best_cluster")
    expected_cluster = (
        {"name": best_cluster.get("clusterer"), "parameter": best_cluster.get("parameter")}
        if isinstance(best_cluster, dict)
        else None
    )
    if frozen.get("cluster") != expected_cluster:
        raise ValueError("validation cluster is inconsistent with frozen configuration")
    return report


def _persist_index(
    output_dir: Path,
    representation: FittedRepresentation,
    samples: Sequence[dict[str, Any]],
    *,
    reference_split: str = "train",
) -> None:
    combined = representation.transform(samples)
    modalities = representation.transform_modalities(samples)
    arrays: dict[str, Any] = {
        "ids": np.asarray([str(sample["id"]) for sample in samples]),
        "vectors": combined,
    }
    arrays.update({f"modality_{name}": matrix for name, matrix in modalities.items()})
    np.savez_compressed(output_dir / "query-index.npz", **arrays)
    _write_json(
        output_dir / "query-index.json",
        {
            "schema_version": 1,
            "distance": "cosine",
            "modalities": list(representation.modalities),
            "reference_split": reference_split,
            "samples": [
                {"id": sample["id"], "proxy_label": sample["label"], "split": sample["split"]}
                for sample in samples
            ],
        },
    )


def run_select(args: argparse.Namespace) -> dict[str, Any]:
    data, manifest_hash = load_manifest(args.manifest)
    samples = data["samples"]
    train = [sample for sample in samples if sample["split"] == "train"]
    validation = [sample for sample in samples if sample["split"] == "validation"]
    if not train or not validation:
        raise ValueError("selection requires non-empty train and validation splits")
    embedding_tables = load_named_embedding_tables(
        args.embedding, {str(sample["id"]) for sample in train + validation}
    )
    representations = _parse_representations(args.representations, bool(embedding_tables))
    pca_values: list[int | None] = [None]
    pca_values.extend(args.pca_components)
    candidates: list[dict[str, Any]] = []
    for modalities in representations:
        named_tables: Iterable[tuple[str | None, EmbeddingTable | None]] = (
            embedding_tables.items() if "embeddings" in modalities else [(None, None)]
        )
        for embedding_name, embeddings in named_tables:
            for pca in pca_values:
                for classifier_name in args.classifiers:
                    try:
                        result, _ = _evaluate_configuration(
                            train,
                            validation,
                            modalities=modalities,
                            classifier_name=classifier_name,
                            neighbors=args.neighbors,
                            retrieval_k=args.retrieval_k,
                            pca_components=pca,
                            embeddings=embeddings,
                            seed=args.seed,
                        )
                        result["embedding_name"] = embedding_name
                        candidates.append(result)
                    except (ValueError, RuntimeError) as exc:
                        candidates.append(
                            {
                                "representation": "+".join(modalities),
                                "modalities": modalities,
                                "embedding_name": embedding_name,
                                "pca_components": pca,
                                "classifier": classifier_name,
                                "error": str(exc),
                            }
                        )
    valid = [candidate for candidate in candidates if "error" not in candidate]
    if not valid:
        raise RuntimeError("all validation candidates failed")
    winner = max(
        valid,
        key=lambda item: (
            item["classification"]["macro_f1"],
            item["classification"]["balanced_accuracy"],
            item["retrieval"]["precision_at_k"],
            -len(item["modalities"]),
            item["representation"],
            item["classifier"],
        ),
    )
    cluster_candidates: list[dict[str, Any]] = []
    _, winner_representation = _evaluate_configuration(
        train,
        validation,
        modalities=winner["modalities"],
        classifier_name=winner["classifier"],
        neighbors=args.neighbors,
        retrieval_k=args.retrieval_k,
        pca_components=winner["pca_components"],
        embeddings=(embedding_tables[winner["embedding_name"]] if winner["embedding_name"] else None),
        seed=args.seed,
    )
    validation_vectors = winner_representation.transform(validation)
    for clusterer in args.clusterers:
        for count in args.cluster_counts:
            if count > len(validation):
                continue
            try:
                assignments = _fit_clusterer(clusterer, validation_vectors, count=count, seed=args.seed)
                cluster_candidates.append(
                    {
                        "clusterer": clusterer,
                        "parameter": count,
                        "metrics": clustering_metrics(
                            [str(sample["label"]) for sample in validation], assignments
                        ),
                    }
                )
            except (ValueError, RuntimeError) as exc:
                cluster_candidates.append({"clusterer": clusterer, "parameter": count, "error": str(exc)})
    valid_clusters = [item for item in cluster_candidates if "error" not in item]
    best_cluster = (
        max(
            valid_clusters,
            key=lambda item: (
                item["metrics"]["nmi_all_including_noise"],
                item["metrics"]["coverage"],
                -item["metrics"]["singleton_clusters"],
            ),
        )
        if valid_clusters
        else None
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "phase": "validation_selection",
        "manifest_sha256": manifest_hash,
        "test_evaluated": False,
        "split_summary": {
            "train": {"count": len(train), "distribution": _distribution(train)},
            "validation": {"count": len(validation), "distribution": _distribution(validation)},
        },
        "candidates": candidates,
        "cluster_candidates": cluster_candidates,
        "winner": winner,
        "best_cluster": best_cluster,
        "success_targets": {"macro_f1": 0.70, "balanced_accuracy": 0.75},
        "success_targets_met": bool(
            winner["classification"]["macro_f1"] >= 0.70
            and winner["classification"]["balanced_accuracy"] >= 0.75
        ),
    }
    frozen = {
        "schema_version": 1,
        "manifest_sha256": manifest_hash,
        "selection_phase": "validation_only",
        "modalities": winner["modalities"],
        "embedding_name": winner["embedding_name"],
        "embedding_sha256": (
            embedding_tables[winner["embedding_name"]].sha256 if winner["embedding_name"] else None
        ),
        "pca_components": winner["pca_components"],
        "classifier": winner["classifier"],
        "neighbors": args.neighbors,
        "retrieval_k": args.retrieval_k,
        "seed": args.seed,
        "cluster": (
            {"name": best_cluster["clusterer"], "parameter": best_cluster["parameter"]}
            if best_cluster
            else None
        ),
    }
    report["selected_config_sha256"] = _canonical_sha256(frozen)
    _write_json(args.output_dir / "validation-report.json", report)
    _write_json(args.output_dir / "frozen-config.json", frozen)
    _persist_index(args.output_dir, winner_representation, train + validation)
    return report


def run_test(args: argparse.Namespace) -> dict[str, Any]:
    if not args.allow_test:
        raise SystemExit("test split is sealed; pass --allow-test after freezing configuration")
    if (args.output_dir / "test-report.json").exists():
        raise FileExistsError("test-report.json already exists; refusing to open test twice")
    data, manifest_hash = load_manifest(args.manifest)
    frozen = json.loads(args.frozen_config.read_text(encoding="utf-8"))
    if frozen.get("schema_version") != 1 or frozen.get("selection_phase") != "validation_only":
        raise ValueError("invalid frozen configuration")
    _verify_frozen_selection(frozen, args.frozen_config, manifest_hash)
    samples = data["samples"]
    train = [sample for sample in samples if sample["split"] == "train"]
    test = [sample for sample in samples if sample["split"] == "test"]
    if not train or not test:
        raise ValueError("final evaluation requires non-empty train and test splits")
    embedding_tables = load_named_embedding_tables(
        args.embedding, {str(sample["id"]) for sample in train + test}
    )
    embedding_name = frozen.get("embedding_name")
    embeddings = embedding_tables.get(embedding_name) if embedding_name else None
    if "embeddings" in frozen["modalities"] and embeddings is None:
        raise ValueError(f"frozen configuration requires --embedding {embedding_name}=PATH")
    if embeddings is not None and embeddings.sha256 != frozen.get("embedding_sha256"):
        raise ValueError("embedding file changed after validation selection")
    result, representation = _evaluate_configuration(
        train,
        test,
        modalities=frozen["modalities"],
        classifier_name=frozen["classifier"],
        neighbors=int(frozen["neighbors"]),
        retrieval_k=int(frozen["retrieval_k"]),
        pca_components=frozen["pca_components"],
        embeddings=embeddings,
        seed=int(frozen["seed"]),
    )
    cluster_result = None
    if frozen.get("cluster"):
        test_vectors = representation.transform(test)
        assignments = _fit_clusterer(
            frozen["cluster"]["name"],
            test_vectors,
            count=int(frozen["cluster"]["parameter"]),
            seed=int(frozen["seed"]),
        )
        cluster_result = {
            **frozen["cluster"],
            "metrics": clustering_metrics([str(sample["label"]) for sample in test], assignments),
        }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "phase": "final_test",
        "manifest_sha256": manifest_hash,
        "frozen_config": frozen,
        "split_summary": {
            "train": {"count": len(train), "distribution": _distribution(train)},
            "test": {"count": len(test), "distribution": _distribution(test)},
        },
        "result": result,
        "cluster": cluster_result,
        "limitations": [
            "Labels are directory/category proxies, not technical relevance judgments.",
            "Precision@k and hit@k define relevance as the same proxy label.",
            "Noise, singleton clusters, and retrieval coverage are reported explicitly.",
        ],
    }
    _write_json(args.output_dir / "test-report.json", report)
    _persist_index(args.output_dir, representation, train + test)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    select = subparsers.add_parser("select", help="select and freeze using validation only")
    select.add_argument("--manifest", type=Path, required=True)
    select.add_argument("--output-dir", type=Path, required=True)
    select.add_argument(
        "--embedding",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="named learned vectors; repeat to compare models",
    )
    select.add_argument(
        "--representations",
        nargs="+",
        default=["geometry", "text", "geometry+text", "embeddings", "geometry+embeddings"],
    )
    select.add_argument("--classifiers", nargs="+", choices=["knn", "centroid", "logreg"], default=["knn", "centroid", "logreg"])
    select.add_argument("--clusterers", nargs="+", choices=["kmeans", "hdbscan"], default=["kmeans"])
    select.add_argument("--cluster-counts", nargs="+", type=int, default=[2, 3, 4, 5])
    select.add_argument("--pca-components", nargs="*", type=int, default=[])
    select.add_argument("--neighbors", type=int, default=5)
    select.add_argument("--retrieval-k", type=int, default=5)
    select.add_argument("--seed", type=int, default=0)

    test = subparsers.add_parser("test", help="evaluate the sealed test with frozen config")
    test.add_argument("--manifest", type=Path, required=True)
    test.add_argument("--frozen-config", type=Path, required=True)
    test.add_argument("--output-dir", type=Path, required=True)
    test.add_argument("--embedding", action="append", default=[], metavar="NAME=PATH")
    test.add_argument("--allow-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "test" and not args.allow_test:
        raise SystemExit("test split is sealed; pass --allow-test after freezing configuration")
    report = run_select(args) if args.command == "select" else run_test(args)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
