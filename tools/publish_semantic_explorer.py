"""Publish checked semantic-lab artifacts into an instance's private explorer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import zipfile

import numpy as np

from backend.app.semantic_explorer.classification import (
    ClassifierArtifact,
    NumericClassifier,
    classify,
)
from backend.app.semantic_explorer.models import (
    Bundle,
    Entry,
    MAX_IMAGE_BYTES,
    MAX_MEMBERS,
    Space,
    digest,
)
from backend.app.semantic_explorer.store import ExplorerStore


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(
    manifest_path: Path, npz_path: Path, classifier: NumericClassifier | None = None
) -> tuple[Bundle, dict[str, bytes]]:
    if (
        manifest_path.stat().st_size > 32 * 1024 * 1024
        or npz_path.stat().st_size > 64 * 1024 * 1024
    ):
        raise ValueError("artifact_too_large")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = json.loads(
        npz_path.with_suffix(npz_path.suffix + ".json").read_text(encoding="utf-8")
    )
    if meta.get("manifest_sha256") != sha(manifest_path) or meta.get(
        "npz_sha256"
    ) != sha(npz_path):
        raise ValueError("artifact_hash_mismatch")
    samples = manifest.get("samples", [])
    if not 1 <= len(samples) <= MAX_MEMBERS:
        raise ValueError("member_limit")
    with zipfile.ZipFile(npz_path) as z:
        if sum(x.file_size for x in z.infolist()) > 128 * 1024 * 1024:
            raise ValueError("artifact_too_large")
    with np.load(npz_path, allow_pickle=False) as archive:
        ids = archive["ids"].tolist()
        vectors = archive["embeddings"]
    if (
        ids != [s["id"] for s in samples]
        or len(set(ids)) != len(ids)
        or vectors.shape != (len(ids), meta["dimensions"])
    ):
        raise ValueError("artifact_ids_or_dimensions_mismatch")
    model = meta["model"]
    preprocessing = {
        key: manifest.get("metadata", {}).get(key, "unknown")
        for key in ("render", "feature_version")
    }
    space = Space(
        provider="local",
        model=model["model"],
        revision=model["revision"],
        mode=meta["mode"],
        dimensions=meta["dimensions"],
        precision=model["precision"],
        preprocessing=digest(
            {
                "runner": meta["config_identity"]["runner_version"],
                "config": model["config"],
                "postprocessing": meta["config_identity"]["postprocessing"],
                "inputs": preprocessing,
            }
        ),
    )
    images = {}
    entries = []
    hashes = meta.get("ordered_input_hashes", [])
    if len(hashes) != len(samples):
        raise ValueError("input_hashes_missing")
    for index, (sample, vector) in enumerate(zip(samples, vectors, strict=True)):
        text = sample.get("text", "")
        if meta["mode"] in {"text", "mixed"} and hashlib.sha256(
            text.encode()
        ).hexdigest() != hashes[index].get("text_sha256"):
            raise ValueError("input_text_hash_mismatch")
        image_path = sample.get("image_path")
        if image_path:
            path = Path(image_path)
            base = manifest_path.parent.resolve()
            if (
                path.is_absolute()
                or PureWindowsPath(image_path).drive
                or PureWindowsPath(image_path).root
            ):
                raise ValueError("image_path_must_be_relative")
            path = (base / path).resolve()
            if not path.is_relative_to(base):
                raise ValueError("image_path_outside_corpus")
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError("image_too_large")
            raw = path.read_bytes()
            if meta["mode"] in {"image", "mixed"} and hashlib.sha256(
                raw
            ).hexdigest() != hashes[index].get("image_sha256"):
                raise ValueError("input_image_hash_mismatch")
            images[sample["id"]] = raw
        elif meta["mode"] in {"image", "mixed"}:
            raise ValueError("image_missing")
        entry = Entry(
            id=sample["id"],
            label=sample.get("display_name") or sample["id"],
            vector=tuple(vector.tolist()),
            text=text,
            category=sample.get("label"),
            category_origin="editorial_proxy" if sample.get("label") else "unknown",
            split=sample.get("split"),
            group_id=sample.get("group_id"),
            features=sample.get("features", {}),
        )
        entry = entry.model_copy(
            update={
                "content_hash": digest(
                    {
                        "text": text,
                        "image": hashlib.sha256(images[sample["id"]]).hexdigest()
                        if sample["id"] in images
                        else None,
                    }
                )
            }
        )
        if classifier is not None:
            entry = entry.model_copy(
                update={
                    "classification": classify(
                        classifier, space, entry.vector, entry.features
                    )
                }
            )
        entries.append(entry)
    return Bundle(
        space=space,
        entries=tuple(entries),
        synthetic=bool(manifest.get("metadata", {}).get("synthetic", False)),
        provenance=f"semantic-lab; manifest SHA256 {sha(manifest_path)}; embeddings SHA256 {sha(npz_path)}; etiquetas editoriales, sin validación industrial",
    ), images


def export_classifier(
    path: Path, expected_sha256: str, space: Space, feature_names: tuple[str, ...]
) -> NumericClassifier:
    # Only a numeric, versioned training artifact; legacy unbound pickles cannot
    # establish which encoder or feature schema produced their parameters.
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("classifier_too_large")
    if sha(path) != expected_sha256:
        raise ValueError("trusted_classifier_hash_mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("classifier_training_contract_missing")
    artifact = ClassifierArtifact.model_validate(payload)
    trained_space = artifact.space
    model = artifact.classifier
    if trained_space.id != space.id or model.vector_space_id != trained_space.id:
        raise ValueError("classifier_space_incompatible")
    if artifact.feature_names != feature_names or (
        model.kind == "logreg" and model.feature_names != feature_names
    ):
        raise ValueError("classifier_features_incompatible")
    return model


def extend_active(
    store: ExplorerStore, catalog: str, new: Bundle, images: dict[str, bytes]
) -> tuple[Bundle, dict[str, bytes]]:
    previous, old = store.load(catalog)
    if old.space.id != new.space.id:
        raise ValueError("embedding_space_incompatible")
    if {e.id for e in old.entries} & {e.id for e in new.entries}:
        raise ValueError("duplicate_ids_use_new_revision")
    existing_images = store.active_images(catalog, previous)
    if store.load(catalog)[0] != previous:
        raise ValueError("active_release_changed")
    combined = Bundle(
        space=old.space,
        entries=old.entries + new.entries,
        synthetic=old.synthetic or new.synthetic,
        provenance=f"Extiende release {previous}; {new.provenance}",
    )
    return combined, existing_images | images


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    publish = sub.add_parser("publish")
    publish.add_argument("--catalog", required=True)
    publish.add_argument("--manifest", type=Path, required=True)
    publish.add_argument("--embeddings", type=Path, required=True)
    publish.add_argument("--classifier", type=Path)
    publish.add_argument("--trusted-classifier-sha256")
    publish.add_argument("--activate", action="store_true")
    publish.add_argument(
        "--extend-active",
        action="store_true",
        help="Append new members to the active compatible space, preserving the prior release",
    )
    activate = sub.add_parser("activate")
    activate.add_argument("--catalog", required=True)
    activate.add_argument("--release", required=True)
    retire = sub.add_parser("retire")
    retire.add_argument("--catalog", required=True)
    retire.add_argument("--member", required=True)
    args = parser.parse_args(argv)
    store = ExplorerStore(args.db)
    if args.command == "publish":
        expected_release = store.load(args.catalog)[0] if args.extend_active else None
        bundle, images = build_bundle(args.manifest, args.embeddings)
        if args.classifier:
            if not args.trusted_classifier_sha256:
                parser.error(
                    "--classifier requires --trusted-classifier-sha256 for your own numeric training artifact"
                )
            classifier = export_classifier(
                args.classifier,
                args.trusted_classifier_sha256,
                bundle.space,
                tuple(sorted(bundle.entries[0].features)),
            )
            bundle, images = build_bundle(args.manifest, args.embeddings, classifier)
        if args.extend_active:
            bundle, images = extend_active(store, args.catalog, bundle, images)
        release = store.publish(args.catalog, bundle, images)
        if args.activate:
            store.activate(args.catalog, release, expected_release=expected_release)
        print(
            json.dumps(
                {
                    "release_id": release,
                    "members": len(bundle.entries),
                    "space_id": bundle.space.id,
                    "active": args.activate,
                }
            )
        )
    elif args.command == "activate":
        store.activate(args.catalog, args.release)
        print(json.dumps({"active": args.release}))
    else:
        store.retire(args.catalog, args.member)
        print(json.dumps({"retired": args.member}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
