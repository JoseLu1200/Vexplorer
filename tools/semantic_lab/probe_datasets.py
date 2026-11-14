"""Preregister and score fixed cross-dataset semantic probes."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import ezdxf
import numpy as np
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score
from sklearn.neighbors import KNeighborsClassifier

from .dataset import (
    _group_records,
    _public_sample,
    _split_groups,
    _variant_signature,
    discover_candidates,
)
from .encode import encode_manifest
from .features import extract_dxf


CORE_CATEGORIES = ("sofas", "simple-tables", "beds", "buffets")
EXTRA_CATEGORIES = (
    "bathroom-set",
    "bathtubs",
    "dining-sets",
    "doors-elevation",
    "doors-plan",
    "kitchen-appliances",
    "kitchen-sinks",
    "living-room",
    "palm-trees",
    "ranges",
    "restaurant-layouts",
    "sanitary-ware",
    "table-lamps",
    "toilets",
    "trees-3d",
    "trees-elevation",
    "trees-plan",
)
MODEL_REVISION = "f9972ac22e696a105c482202646979e33e4b5a1e"
VIEW_LAYERS = {"front": "ORTHO_FRONT", "side": "ORTHO_SIDE", "top": "ORTHO_TOP"}
PROTOCOL = {
    "model": {
        "name": "google/embeddinggemma-2",
        "revision": MODEL_REVISION,
        "mode": "mixed",
        "dimensions": 768,
        "postprocessing": "float32_l2_normalize_rows",
    },
    "classifier": {
        "name": "knn",
        "neighbors": 5,
        "metric": "cosine",
        "weights": "distance",
        "pca": None,
    },
    "retrieval_k": 5,
    "seed": 20261114,
    "selection": "none; protocol frozen before metrics",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_manifest(path: Path | str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or not isinstance(value.get("samples"), list):
        raise ValueError(f"invalid manifest: {path}")
    ids = [str(sample.get("id")) for sample in value["samples"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate sample id in manifest: {path}")
    return value


def _read_public_cases(source: Path) -> list[dict[str, Any]]:
    cases = json.loads((source / "cases.json").read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("cases.json must contain a list")
    for case in cases:
        path = source / str(case["file"])
        if not path.is_file() or _sha256(path) != case.get("sha256"):
            raise ValueError(f"sha256 mismatch for public input {path.name}")
    return cases


def _sample_from_extraction(
    *, sample_id: str, source_path: Path, image_path: Path, label: str, label_source: str
) -> dict[str, Any]:
    extraction = extract_dxf(source_path, image_path=image_path, image_size=384)
    return {
        "id": sample_id,
        "source_path": str(source_path.resolve()),
        "image_path": str(image_path.resolve()),
        "label": label,
        "label_source": label_source,
        "group_id": label,
        "split": "probe",
        "features": extraction.features,
        "text": extraction.text,
    }


def prepare_cad_extra(
    source: Path | str,
    output_dir: Path | str,
    *,
    categories: Sequence[str] = EXTRA_CATEGORIES,
    seed: int = 20261114,
    image_size: int = 384,
) -> dict[str, Any]:
    """Prepare all eligible CADBlock extras while preserving per-file failures."""

    source_root = Path(source).resolve()
    destination = Path(output_dir).resolve()
    candidates = discover_candidates(source_root, categories)
    records: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for label, path in candidates:
        relative = path.resolve().relative_to(source_root).as_posix()
        sample_id = "cad_" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20]
        image_path = destination / "renders" / f"{sample_id}.png"
        try:
            extraction = extract_dxf(path, image_path=image_path, image_size=image_size)
        except Exception as exc:
            excluded.append(
                {
                    "source_path": str(path.resolve()),
                    "reason": str(exc),
                    "exception_type": type(exc).__name__,
                }
            )
            continue
        records.append(
            {
                "id": sample_id,
                "source_path": str(path.resolve()),
                "image_path": str(image_path.resolve()),
                "label": label,
                "label_source": "cadblock_library_proxy",
                "features": extraction.features,
                "text": extraction.text,
                "source_sha256": extraction.source_sha256,
                "geometry_signature": extraction.geometry_signature,
                "render_sha256": extraction.render_sha256,
                "variant_signature": _variant_signature(label, path),
            }
        )
    _group_records(records)
    _split_groups(records, seed)
    samples = [_public_sample(record) for record in records]
    manifest = {
        "schema_version": 1,
        "metadata": {
            "corpus": "CADBlock local 2D metric drawings; categories outside core four",
            "categories": list(categories),
            "candidate_count": len(candidates),
            "sample_count": len(samples),
            "excluded_count": len(excluded),
            "excluded": excluded,
            "split_seed": seed,
            "split_policy": "70/15/15 by duplicate group before model fitting",
            "label_policy": "directory names are editorial proxies, not human ground truth",
            "label_counts": dict(sorted(Counter(str(row["label"]) for row in samples).items())),
            "split_counts": dict(sorted(Counter(str(row["split"]) for row in samples).items())),
            "leakage_policy": "labels, paths, filenames and ids are excluded from model input",
        },
        "samples": samples,
    }
    _write_json(destination / "manifest.json", manifest)
    return manifest


def prepare_plank_views(source: Path | str, output_dir: Path | str) -> dict[str, Any]:
    """Build three geometry-only public views per PlankAssembly DXF."""

    source_path = Path(source).resolve()
    destination = Path(output_dir).resolve()
    samples: list[dict[str, Any]] = []
    for case in sorted(_read_public_cases(source_path), key=lambda item: str(item["id"])):
        if case.get("format") != "dxf":
            continue
        original = source_path / str(case["file"])
        for view, layer in VIEW_LAYERS.items():
            document = ezdxf.readfile(original)
            modelspace = document.modelspace()
            for entity in list(modelspace):
                if entity.dxf.layer != layer:
                    modelspace.delete_entity(entity)
            view_path = destination / "views" / f"{case['id']}-{view}.dxf"
            view_path.parent.mkdir(parents=True, exist_ok=True)
            document.saveas(view_path)
            samples.append(
                _sample_from_extraction(
                    sample_id=f"{case['id']}:{view}",
                    source_path=view_path,
                    image_path=destination / "renders" / f"{case['id']}-{view}.png",
                    label=str(case["id"]),
                    label_source="public_object_identity",
                )
            )
    manifest = {
        "schema_version": 1,
        "metadata": {
            "corpus": "PlankAssembly public adapter_test_v1 orthographic layers",
            "task": "same-object cross-view retrieval; no semantic family ground truth",
            "views": list(VIEW_LAYERS),
            "sample_count": len(samples),
            "leakage_policy": "object id is evaluation relevance only and never enters model input",
        },
        "samples": samples,
    }
    _write_json(destination / "manifest.json", manifest)
    return manifest


def prepare_engineering_manifest(source: Path | str, output_dir: Path | str) -> dict[str, Any]:
    """Extract public engineering DXFs and record unsupported public formats."""

    source_path = Path(source).resolve()
    destination = Path(output_dir).resolve()
    samples: list[dict[str, Any]] = []
    excluded = Counter()
    errors: list[dict[str, str]] = []
    for case in sorted(_read_public_cases(source_path), key=lambda item: str(item["id"])):
        if case.get("format") != "dxf":
            excluded[str(case.get("format", "unknown"))] += 1
            continue
        try:
            samples.append(
                _sample_from_extraction(
                    sample_id=str(case["id"]),
                    source_path=source_path / str(case["file"]),
                    image_path=destination / "renders" / f"{case['id']}.png",
                    label="outside_core_domain",
                    label_source="probe_scope_marker_not_ground_truth",
                )
            )
        except Exception as exc:
            errors.append({"id": str(case["id"]), "error": str(exc)})
    manifest = {
        "schema_version": 1,
        "metadata": {
            "corpus": "engineering_evaluation_pilot_v3 public agent inputs",
            "task": "closed-set behavior on out-of-domain engineering drawings",
            "sample_count": len(samples),
            "excluded_formats": dict(sorted(excluded.items())),
            "extraction_errors": errors,
            "accuracy_defined": False,
        },
        "samples": samples,
    }
    _write_json(destination / "manifest.json", manifest)
    return manifest


def freeze_preregistration(
    manifests: Mapping[str, Path | str], output_path: Path | str
) -> dict[str, Any]:
    frozen: dict[str, Any] = {}
    for name, raw_path in sorted(manifests.items()):
        path = Path(raw_path).resolve()
        manifest = _load_manifest(path)
        frozen[name] = {
            "path": str(path),
            "sha256": _sha256(path),
            "sample_count": len(manifest["samples"]),
        }
    preregistration = {
        "schema_version": 1,
        "date": "2026-11-14",
        "phase": "preregistered_before_metrics",
        "protocol": PROTOCOL,
        "manifests": frozen,
    }
    _write_json(Path(output_path), preregistration)
    return preregistration


def verify_preregistration(path: Path | str) -> dict[str, Any]:
    preregistration = json.loads(Path(path).read_text(encoding="utf-8"))
    if preregistration.get("phase") != "preregistered_before_metrics":
        raise ValueError("invalid preregistration phase")
    if preregistration.get("protocol") != PROTOCOL:
        raise ValueError("protocol changed after preregistration")
    for value in preregistration["manifests"].values():
        manifest_path = Path(value["path"])
        if _sha256(manifest_path) != value["sha256"]:
            raise ValueError(f"manifest changed after preregistration: {manifest_path}")
    return preregistration


def _load_vectors(path: Path | str) -> tuple[list[str], np.ndarray]:
    with np.load(path, allow_pickle=False) as table:
        ids = table["ids"].astype(str).tolist()
        matrix = np.asarray(table["embeddings"], dtype=np.float32)
    if matrix.ndim != 2 or len(ids) != len(matrix) or not np.isfinite(matrix).all():
        raise ValueError(f"invalid embeddings: {path}")
    norms = np.linalg.norm(matrix, axis=1)
    if not np.allclose(norms, 1.0, atol=2e-6):
        raise ValueError(f"embeddings are not L2-normalized float32: {path}")
    return ids, matrix


def _aligned_vectors(manifest: dict[str, Any], embeddings: Path | str) -> np.ndarray:
    ids, matrix = _load_vectors(embeddings)
    positions = {sample_id: index for index, sample_id in enumerate(ids)}
    requested = [str(sample["id"]) for sample in manifest["samples"]]
    missing = [sample_id for sample_id in requested if sample_id not in positions]
    if missing:
        raise ValueError(f"missing embeddings: {missing[:5]}")
    return np.asarray([matrix[positions[sample_id]] for sample_id in requested], dtype=np.float32)


def _fixed_split_score(
    train_vectors: np.ndarray,
    train_labels: list[str],
    target_vectors: np.ndarray,
    target_labels: list[str],
    *,
    neighbors: int,
    retrieval_k: int,
) -> dict[str, Any]:
    effective_neighbors = min(neighbors, len(train_vectors))
    classifier = KNeighborsClassifier(
        n_neighbors=effective_neighbors, metric="cosine", weights="distance"
    ).fit(train_vectors, train_labels)
    predicted = classifier.predict(target_vectors)
    effective_k = min(retrieval_k, len(train_vectors))
    distances = 1.0 - target_vectors @ train_vectors.T
    order = np.argsort(distances, axis=1)[:, :effective_k]
    relevant = np.asarray(train_labels)[order] == np.asarray(target_labels)[:, None]
    return {
        "classification": {
            "macro_f1": float(f1_score(target_labels, predicted, average="macro")),
            "balanced_accuracy": float(balanced_accuracy_score(target_labels, predicted)),
        },
        "retrieval": {
            "precision_at_k": float(relevant.mean()),
            "hit_at_k": float(relevant.any(axis=1).mean()),
            "effective_k": effective_k,
        },
    }


def evaluate_cad_extra(
    manifest_path: Path | str,
    embeddings_path: Path | str,
    *,
    neighbors: int = 5,
    retrieval_k: int = 5,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    matrix = _aligned_vectors(manifest, embeddings_path)
    samples = manifest["samples"]
    train_indexes = [i for i, sample in enumerate(samples) if sample["split"] == "train"]
    train_labels = [str(samples[i]["label"]) for i in train_indexes]
    result: dict[str, Any] = {"train_count": len(train_indexes)}
    for split in ("validation", "test"):
        indexes = [i for i, sample in enumerate(samples) if sample["split"] == split]
        if not indexes:
            result[split] = {"error": "empty split"}
            continue
        result[split] = _fixed_split_score(
            matrix[train_indexes],
            train_labels,
            matrix[indexes],
            [str(samples[i]["label"]) for i in indexes],
            neighbors=neighbors,
            retrieval_k=retrieval_k,
        )
        result[split]["count"] = len(indexes)
    return result


def cad_extra_diagnostics(
    manifest_path: Path | str,
    embeddings_path: Path | str,
    *,
    neighbors: int = 5,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Replay the frozen classifier to describe test errors, without selection."""

    manifest = _load_manifest(manifest_path)
    matrix = _aligned_vectors(manifest, embeddings_path)
    samples = manifest["samples"]
    train_indexes = [i for i, sample in enumerate(samples) if sample["split"] == "train"]
    test_indexes = [i for i, sample in enumerate(samples) if sample["split"] == "test"]
    train_labels = [str(samples[i]["label"]) for i in train_indexes]
    actual = [str(samples[i]["label"]) for i in test_indexes]
    classifier = KNeighborsClassifier(
        n_neighbors=min(neighbors, len(train_indexes)), metric="cosine", weights="distance"
    ).fit(matrix[train_indexes], train_labels)
    predicted = classifier.predict(matrix[test_indexes]).astype(str).tolist()
    labels = sorted(set(train_labels) | set(actual))
    confusion = confusion_matrix(actual, predicted, labels=labels)
    per_class = {
        label: {
            "support": int(confusion[index].sum()),
            "recall": float(confusion[index, index] / confusion[index].sum())
            if confusion[index].sum()
            else 0.0,
        }
        for index, label in enumerate(labels)
    }
    errors = Counter(
        f"{truth} -> {guess}" for truth, guess in zip(actual, predicted, strict=True) if truth != guess
    )
    result = {
        "schema_version": 1,
        "phase": "posthoc_fixed_protocol_replay",
        "selection_or_tuning": False,
        "split": "test",
        "labels": labels,
        "confusion_matrix": confusion.astype(int).tolist(),
        "per_class": per_class,
        "error_pairs": dict(sorted(errors.items())),
    }
    if output_path is not None:
        _write_json(Path(output_path), result)
    return result


def identity_retrieval(
    manifest_path: Path | str, embeddings_path: Path | str, *, k: int = 2
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    matrix = _aligned_vectors(manifest, embeddings_path)
    labels = np.asarray([str(sample["label"]) for sample in manifest["samples"]])
    similarity = matrix @ matrix.T
    np.fill_diagonal(similarity, -np.inf)
    effective_k = min(k, max(0, len(matrix) - 1))
    order = np.argsort(-similarity, axis=1)[:, :effective_k]
    relevant = labels[order] == labels[:, None]
    return {
        "hit_at_1": float(relevant[:, :1].any(axis=1).mean()),
        "hit_at_2": float(relevant.any(axis=1).mean()),
        "queries": len(matrix),
        "k": effective_k,
    }


def closed_set_probe(
    core_manifest_path: Path | str,
    core_embeddings_path: Path | str,
    probe_manifest_path: Path | str,
    probe_embeddings_path: Path | str,
    *,
    neighbors: int = 5,
) -> dict[str, Any]:
    core = _load_manifest(core_manifest_path)
    probe = _load_manifest(probe_manifest_path)
    core_matrix = _aligned_vectors(core, core_embeddings_path)
    probe_matrix = _aligned_vectors(probe, probe_embeddings_path)
    train_indexes = [i for i, sample in enumerate(core["samples"]) if sample["split"] == "train"]
    labels = [str(core["samples"][i]["label"]) for i in train_indexes]
    classifier = KNeighborsClassifier(
        n_neighbors=min(neighbors, len(train_indexes)), metric="cosine", weights="distance"
    ).fit(core_matrix[train_indexes], labels)
    predicted = classifier.predict(probe_matrix).astype(str)
    distances, _ = classifier.kneighbors(probe_matrix)
    rows = [
        {
            "id": str(sample["id"]),
            "forced_proxy_label": str(label),
            "nearest_cosine_distance": float(distance[0]),
        }
        for sample, label, distance in zip(probe["samples"], predicted, distances, strict=True)
    ]
    return {
        "interpretation": "closed-set forced assignment; no accuracy or rejection threshold",
        "prediction_counts": dict(sorted(Counter(predicted.tolist()).items())),
        "samples": rows,
    }


def prepare_all(args: argparse.Namespace) -> dict[str, Any]:
    root = args.output_root.resolve()
    cad_dir = root / "cad-extra"
    prepare_cad_extra(
        args.cadblock_source,
        cad_dir,
        categories=EXTRA_CATEGORIES,
        seed=PROTOCOL["seed"],
        image_size=384,
    )
    prepare_plank_views(args.plank_source, root / "plank-views")
    prepare_engineering_manifest(args.engineering_source, root / "engineering")
    return freeze_preregistration(
        {
            "cad_extra": cad_dir / "manifest.json",
            "plank_views": root / "plank-views" / "manifest.json",
            "engineering": root / "engineering" / "manifest.json",
        },
        root / "preregistration.json",
    )


def score_all(args: argparse.Namespace) -> dict[str, Any]:
    preregistration = verify_preregistration(args.preregistration)
    root = args.output_root.resolve()
    embedding_paths: dict[str, Path] = {}
    embedding_metadata: dict[str, Any] = {}
    for name, frozen in preregistration["manifests"].items():
        output_path = root / "embeddings" / f"{name}-embeddinggemma2-mixed-768.npz"
        metadata = encode_manifest(
            manifest_path=frozen["path"],
            model="embeddinggemma2",
            mode="mixed",
            output_path=output_path,
            cache_dir=args.cache_dir,
            precision="bfloat16",
            device="cuda",
        )
        if metadata["model"]["revision"] != MODEL_REVISION or metadata["dimensions"] != 768:
            raise ValueError("encoder revision or dimensions differ from preregistration")
        embedding_paths[name] = output_path
        embedding_metadata[name] = metadata
    manifests = {name: Path(value["path"]) for name, value in preregistration["manifests"].items()}
    report = {
        "schema_version": 1,
        "date": "2026-11-14",
        "preregistration_sha256": _sha256(Path(args.preregistration)),
        "cad_extra": evaluate_cad_extra(manifests["cad_extra"], embedding_paths["cad_extra"]),
        "plank_views": identity_retrieval(
            manifests["plank_views"], embedding_paths["plank_views"], k=2
        ),
        "engineering_closed_set": closed_set_probe(
            args.core_manifest,
            args.core_embeddings,
            manifests["engineering"],
            embedding_paths["engineering"],
        ),
        "embeddings": embedding_metadata,
        "limitations": [
            "CAD-extra uses CADBlock directory labels as editorial proxies.",
            "Plank view retrieval measures public object identity, not semantic family relevance.",
            "Engineering labels are forced closed-set outputs; accuracy and rejection are undefined.",
        ],
    }
    _write_json(root / "report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--cadblock-source", type=Path, required=True)
    prepare.add_argument("--plank-source", type=Path, required=True)
    prepare.add_argument("--engineering-source", type=Path, required=True)
    prepare.add_argument("--output-root", type=Path, required=True)
    score = commands.add_parser("score")
    score.add_argument("--preregistration", type=Path, required=True)
    score.add_argument("--output-root", type=Path, required=True)
    score.add_argument("--cache-dir", type=Path, required=True)
    score.add_argument("--core-manifest", type=Path, required=True)
    score.add_argument("--core-embeddings", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_all(args) if args.command == "prepare" else score_all(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
