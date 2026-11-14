"""Retrospective local classifier comparison on frozen semantic-lab corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler, normalize

from tools.semantic_lab.evaluate import SPLITS, classification_metrics, validate_manifest


EXPECTED_EMBEDDING_DIMENSION = 768
EXPECTED_GEOMETRY_DIMENSION = 27


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    family: str
    parameters: dict[str, int | float]


@dataclass
class Dataset:
    manifest_path: Path
    embedding_path: Path
    manifest_sha256: str
    embedding_sha256: str
    samples: list[dict[str, Any]]
    geometry: np.ndarray
    embeddings: np.ndarray
    feature_names: tuple[str, ...]

    def positions(self, split: str) -> np.ndarray:
        return np.asarray(
            [index for index, sample in enumerate(self.samples) if sample["split"] == split], dtype=int
        )


@dataclass
class FittedCandidate:
    spec: CandidateSpec
    estimator: Any
    geometry_scaler: StandardScaler | None = None
    embedding_pca: PCA | None = None
    combined_scaler: StandardScaler | None = None

    def _transform(self, geometry: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
        unit_embeddings = normalize(np.asarray(embeddings, dtype=float), axis=1)
        if self.spec.family == "knn_embedding":
            return unit_embeddings
        if self.spec.family == "logreg_combined":
            assert self.combined_scaler is not None
            return self.combined_scaler.transform(
                np.concatenate([unit_embeddings, np.asarray(geometry, dtype=float)], axis=1)
            )
        assert self.embedding_pca is not None and self.geometry_scaler is not None
        reduced = self.embedding_pca.transform(unit_embeddings)
        scaled_geometry = self.geometry_scaler.transform(np.asarray(geometry, dtype=float))
        return np.concatenate([reduced, scaled_geometry], axis=1)

    def predict(self, geometry: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
        return self.estimator.predict(self._transform(geometry, embeddings))

    def closed_set_score(self, geometry: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
        matrix = self._transform(geometry, embeddings)
        if hasattr(self.estimator, "predict_proba"):
            return np.max(self.estimator.predict_proba(matrix), axis=1)
        return np.full(matrix.shape[0], np.nan)


def candidate_specs() -> list[CandidateSpec]:
    return [
        CandidateSpec("knn_eg2_k5", "knn_embedding", {"n_neighbors": 5}),
        CandidateSpec("logreg_combined_c0.1", "logreg_combined", {"C": 0.1}),
        CandidateSpec("logreg_combined_c1", "logreg_combined", {"C": 1.0}),
        CandidateSpec("logreg_combined_c10", "logreg_combined", {"C": 10.0}),
        CandidateSpec("histgb_pca32_geometry", "histgb_pca_geometry", {"pca_components": 32}),
        CandidateSpec("histgb_pca64_geometry", "histgb_pca_geometry", {"pca_components": 64}),
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset(manifest_path: Path, embedding_path: Path) -> Dataset:
    manifest_bytes = manifest_path.read_bytes()
    data = json.loads(manifest_bytes)
    samples = data.get("samples")
    if data.get("schema_version") != 1 or not isinstance(samples, list) or not samples:
        raise ValueError("manifest must use schema_version 1 and contain samples")
    if {sample.get("split") for sample in samples} <= SPLITS:
        validate_manifest(data)
    ids = [str(sample.get("id", "")) for sample in samples]
    if any(not sample_id for sample_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("manifest ids must be non-empty and unique")
    with np.load(embedding_path, allow_pickle=False) as archive:
        if not {"ids", "embeddings"}.issubset(archive.files):
            raise ValueError("embedding NPZ must contain ids and embeddings")
        embedding_ids = [str(value) for value in archive["ids"].tolist()]
        matrix = np.asarray(archive["embeddings"], dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != EXPECTED_EMBEDDING_DIMENSION:
        raise ValueError("embeddings must have exactly 768 columns")
    if len(embedding_ids) != matrix.shape[0] or len(set(embedding_ids)) != len(embedding_ids):
        raise ValueError("embedding ids must be unique and match row count")
    if set(embedding_ids) != set(ids) or not np.isfinite(matrix).all():
        raise ValueError("embeddings must be finite and cover exactly the manifest ids")
    feature_names = tuple(sorted(samples[0].get("features", {})))
    if len(feature_names) != EXPECTED_GEOMETRY_DIMENSION or any(
        tuple(sorted(sample.get("features", {}))) != feature_names for sample in samples
    ):
        raise ValueError("all samples must share the same 27 geometry features")
    geometry = np.asarray(
        [[float(sample["features"][name]) for name in feature_names] for sample in samples], dtype=float
    )
    if not np.isfinite(geometry).all():
        raise ValueError("geometry features must be finite")
    embedding_positions = {sample_id: index for index, sample_id in enumerate(embedding_ids)}
    aligned = np.asarray([matrix[embedding_positions[sample_id]] for sample_id in ids], dtype=float)
    return Dataset(
        manifest_path=manifest_path,
        embedding_path=embedding_path,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        embedding_sha256=_sha256(embedding_path),
        samples=samples,
        geometry=geometry,
        embeddings=aligned,
        feature_names=feature_names,
    )


def fit_candidate(
    spec: CandidateSpec,
    train_geometry: np.ndarray,
    train_embeddings: np.ndarray,
    labels: np.ndarray,
) -> FittedCandidate:
    geometry = np.asarray(train_geometry, dtype=float)
    embeddings = normalize(np.asarray(train_embeddings, dtype=float), axis=1)
    if len(geometry) != len(embeddings) or len(labels) != len(geometry):
        raise ValueError("training arrays must have matching rows")
    if spec.family == "knn_embedding":
        neighbors = int(spec.parameters["n_neighbors"])
        if len(labels) < neighbors:
            raise ValueError("kNN requires at least five training rows")
        estimator = KNeighborsClassifier(n_neighbors=neighbors, metric="cosine", weights="distance")
        estimator.fit(embeddings, labels)
        return FittedCandidate(spec, estimator)
    if spec.family == "logreg_combined":
        combined = np.concatenate([embeddings, geometry], axis=1)
        scaler = StandardScaler().fit(combined)
        estimator = LogisticRegression(
            C=float(spec.parameters["C"]),
            class_weight="balanced",
            max_iter=2000,
            random_state=0,
        ).fit(scaler.transform(combined), labels)
        return FittedCandidate(spec, estimator, combined_scaler=scaler)
    if spec.family == "histgb_pca_geometry":
        components = int(spec.parameters["pca_components"])
        if components > min(embeddings.shape):
            raise ValueError(f"PCA {components} is invalid for training shape {embeddings.shape}")
        pca = PCA(n_components=components, svd_solver="full").fit(embeddings)
        geometry_scaler = StandardScaler().fit(geometry)
        combined = np.concatenate([pca.transform(embeddings), geometry_scaler.transform(geometry)], axis=1)
        estimator = HistGradientBoostingClassifier(
            max_iter=100,
            max_depth=3,
            l2_regularization=1.0,
            class_weight="balanced",
            random_state=0,
        ).fit(combined, labels)
        return FittedCandidate(spec, estimator, geometry_scaler, pca)
    raise ValueError(f"unknown candidate family: {spec.family}")


def save_candidate(candidate: FittedCandidate, path: Path) -> None:
    joblib.dump(
        {
            "schema_version": 1,
            "artifact_type": "semantic_lab_local_classifier",
            "spec": {
                "name": candidate.spec.name,
                "family": candidate.spec.family,
                "parameters": candidate.spec.parameters,
            },
            "estimator": candidate.estimator,
            "geometry_scaler": candidate.geometry_scaler,
            "embedding_pca": candidate.embedding_pca,
            "combined_scaler": candidate.combined_scaler,
        },
        path,
    )


def load_candidate(path: Path) -> FittedCandidate:
    payload = joblib.load(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported local classifier artifact")
    if payload.get("artifact_type") != "semantic_lab_local_classifier":
        raise ValueError("artifact was not produced by semantic-lab classifier comparison")
    spec_data = payload.get("spec")
    if not isinstance(spec_data, dict):
        raise ValueError("classifier artifact has no model specification")
    return FittedCandidate(
        spec=CandidateSpec(
            name=str(spec_data["name"]),
            family=str(spec_data["family"]),
            parameters=dict(spec_data["parameters"]),
        ),
        estimator=payload["estimator"],
        geometry_scaler=payload.get("geometry_scaler"),
        embedding_pca=payload.get("embedding_pca"),
        combined_scaler=payload.get("combined_scaler"),
    )


def select_fixed_ood(samples: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(samples) != 14:
        raise ValueError("engineering OOD set must contain exactly 14 samples")
    return sorted(samples, key=lambda sample: str(sample["id"]))


def validate_split_counts(samples: Sequence[dict[str, Any]], expected: dict[str, int]) -> None:
    observed = {
        split: sum(sample.get("split") == split for sample in samples) for split in expected
    }
    if observed != expected:
        raise ValueError(f"split counts changed: expected {expected}, observed {observed}")


def select_winner(candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise ValueError("at least one candidate is required")
    _, winner = max(
        enumerate(candidates),
        key=lambda item: (
            item[1]["metrics"]["macro_f1"],
            item[1]["metrics"]["balanced_accuracy"],
            -item[0],
        ),
    )
    return winner


def _split_arrays(dataset: Dataset, split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    positions = dataset.positions(split)
    if positions.size == 0:
        raise ValueError(f"dataset has no {split} samples")
    return (
        dataset.geometry[positions],
        dataset.embeddings[positions],
        np.asarray([str(dataset.samples[index]["label"]) for index in positions]),
        [str(dataset.samples[index]["id"]) for index in positions],
    )


def compare_corpus(dataset: Dataset) -> tuple[dict[str, Any], FittedCandidate]:
    train_geometry, train_embeddings, train_labels, train_ids = _split_arrays(dataset, "train")
    validation_geometry, validation_embeddings, validation_labels, validation_ids = _split_arrays(
        dataset, "validation"
    )
    test_geometry, test_embeddings, test_labels, test_ids = _split_arrays(dataset, "test")
    candidate_reports: list[dict[str, Any]] = []
    fitted_by_name: dict[str, FittedCandidate] = {}
    for spec in candidate_specs():
        fitted = fit_candidate(spec, train_geometry, train_embeddings, train_labels)
        predictions = fitted.predict(validation_geometry, validation_embeddings)
        candidate_reports.append(
            {
                "name": spec.name,
                "family": spec.family,
                "parameters": spec.parameters,
                "metrics": classification_metrics(
                    validation_labels.tolist(), predictions.tolist(), sample_ids=validation_ids
                ),
            }
        )
        fitted_by_name[spec.name] = fitted
    winner = select_winner(candidate_reports)
    fitted_winner = fitted_by_name[winner["name"]]
    test_predictions = fitted_winner.predict(test_geometry, test_embeddings)
    return (
        {
            "counts": {"train": len(train_ids), "validation": len(validation_ids), "test": len(test_ids)},
            "candidates_validation": candidate_reports,
            "winner_validation": winner,
            "winner_test_posthoc": classification_metrics(
                test_labels.tolist(), test_predictions.tolist(), sample_ids=test_ids
            ),
        },
        fitted_winner,
    )


def _distribution(values: Sequence[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def build_summary(report: dict[str, Any]) -> dict[str, Any]:
    def corpus_summary(corpus: dict[str, Any]) -> dict[str, Any]:
        validation = corpus["winner_validation"]
        test = corpus["winner_test_posthoc"]
        return {
            "counts": corpus["counts"],
            "winner": validation["name"],
            "validation_macro_f1": validation["metrics"]["macro_f1"],
            "validation_balanced_accuracy": validation["metrics"]["balanced_accuracy"],
            "test_macro_f1_posthoc": test["macro_f1"],
            "test_balanced_accuracy_posthoc": test["balanced_accuracy"],
            "test_confusion_labels": test["labels"],
            "test_confusion_matrix": test["confusion_matrix"],
        }

    forced = report["forced_engineering_to_core"]
    return {
        "schema_version": 1,
        "protocol": report["protocol"],
        "retrospective_posthoc": True,
        "hashes": report["hashes"],
        "model_arguments": [
            {"name": spec.name, "family": spec.family, "parameters": spec.parameters}
            for spec in candidate_specs()
        ],
        "core": corpus_summary(report["core"]),
        "cad_extra": corpus_summary(report["cad_extra"]),
        "engineering_forced_count": len(forced["predictions"]),
        "engineering_forced_distribution": forced["distribution"],
        "limitations": report["limitations"],
    }


def run_comparison(args: argparse.Namespace) -> dict[str, Any]:
    core = load_dataset(args.core_manifest, args.core_embeddings)
    cad = load_dataset(args.cad_manifest, args.cad_embeddings)
    engineering = load_dataset(args.engineering_manifest, args.engineering_embeddings)
    validate_split_counts(core.samples, {"train": 82, "validation": 17, "test": 18})
    validate_split_counts(cad.samples, {"train": 262, "validation": 56, "test": 55})
    if core.feature_names != cad.feature_names or core.feature_names != engineering.feature_names:
        raise ValueError("all three corpora must use the same geometry feature names")
    core_report, core_winner = compare_corpus(core)
    cad_report, cad_winner = compare_corpus(cad)
    ood_samples = select_fixed_ood(engineering.samples)
    ood_positions = np.asarray(
        [{sample["id"]: index for index, sample in enumerate(engineering.samples)}[sample["id"]] for sample in ood_samples]
    )
    ood_predictions = core_winner.predict(
        engineering.geometry[ood_positions], engineering.embeddings[ood_positions]
    )
    ood_scores = core_winner.closed_set_score(
        engineering.geometry[ood_positions], engineering.embeddings[ood_positions]
    )
    forced = [
        {
            "id": str(sample["id"]),
            "forced_core_label": str(prediction),
            "closed_set_score": float(score),
        }
        for sample, prediction, score in zip(ood_samples, ood_predictions, ood_scores, strict=True)
    ]
    report = {
        "schema_version": 1,
        "protocol": "classifier-comparison-2026-11-14-v2",
        "retrospective_posthoc": True,
        "hashes": {
            "core_manifest": core.manifest_sha256,
            "core_embeddings": core.embedding_sha256,
            "cad_manifest": cad.manifest_sha256,
            "cad_embeddings": cad.embedding_sha256,
            "engineering_manifest": engineering.manifest_sha256,
            "engineering_embeddings": engineering.embedding_sha256,
        },
        "feature_names": list(core.feature_names),
        "embedding_dimension": EXPECTED_EMBEDDING_DIMENSION,
        "core": core_report,
        "cad_extra": cad_report,
        "forced_engineering_to_core": {
            "count": len(forced),
            "predictions": forced,
            "distribution": _distribution([item["forced_core_label"] for item in forced]),
            "route_to_review": "not_calibrated_or_evaluated",
        },
        "baselines_test_macro_f1": {"core": 0.8261278, "cad_extra": 0.778},
        "limitations": [
            "Core and CAD-extra test metrics are retrospective post-hoc comparisons.",
            "Engineering assignments are forced closed-set outputs, not OOD accuracy.",
            "Closed-set scores are not calibrated review thresholds.",
            "Jev 1.14 is an external API reference, not a local checkpoint.",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "full-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    save_candidate(core_winner, args.output_dir / "core-winner.joblib")
    save_candidate(cad_winner, args.output_dir / "cad-extra-winner.joblib")
    summary = build_summary(report)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-manifest", type=Path, required=True)
    parser.add_argument("--core-embeddings", type=Path, required=True)
    parser.add_argument("--cad-manifest", type=Path, required=True)
    parser.add_argument("--cad-embeddings", type=Path, required=True)
    parser.add_argument("--engineering-manifest", type=Path, required=True)
    parser.add_argument("--engineering-embeddings", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_comparison(args)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
