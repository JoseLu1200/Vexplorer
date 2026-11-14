import hashlib
import json

import numpy as np
import pytest

from backend.app.semantic_explorer.classification import NumericClassifier, classify
from backend.app.semantic_explorer.models import Space
from tools.publish_semantic_explorer import build_bundle, extend_active


def space():
    return Space(
        provider="test",
        model="fixture",
        revision="1",
        dimensions=2,
        mode="text",
        preprocessing="1",
    )


def test_logistic_binary_uses_scaler_and_returns_uncalibrated_proposal():
    model = NumericClassifier(
        kind="logreg",
        vector_space_id=space().id,
        labels=("a", "b"),
        feature_names=("size",),
        coefficients=((0, 0, 2),),
        intercept=(0,),
        mean=(0, 0, 10),
        scale=(1, 1, 2),
    )
    result = classify(model, space(), (1, 0), {"size": 12})
    assert result.label == "b"
    assert result.score == pytest.approx(1 / (1 + np.exp(-2)))
    assert result.state == "needs_review" and not result.calibrated
    with pytest.raises(ValueError, match="features"):
        classify(model, space(), (1, 0), {})
    with pytest.raises(ValueError, match="space"):
        classify(
            model, space().model_copy(update={"revision": "2"}), (1, 0), {"size": 12}
        )


def test_knn_exact_matches_dominate_and_geometry_does_not_change_neighbors():
    model = NumericClassifier(
        kind="knn",
        vector_space_id=space().id,
        labels=("a", "b"),
        train_vectors=((1, 0), (0, 1), (-1, 0), (0.8, 0.6), (0.6, 0.8)),
        train_labels=(0, 1, 1, 1, 1),
    )
    result = classify(model, space(), (1, 0), {})
    assert result.label == "a" and result.score == 1


def write_lab(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata": {"synthetic": True},
                "samples": [
                    {
                        "id": "a",
                        "label": "panel",
                        "text": "geometry",
                        "features": {},
                        "split": "train",
                    },
                    {
                        "id": "b",
                        "label": "desk",
                        "text": "geometry",
                        "features": {},
                        "split": "test",
                    },
                ],
            }
        )
    )
    vectors = tmp_path / "vectors.npz"
    np.savez_compressed(
        vectors, ids=np.array(["a", "b"]), embeddings=np.array([[1.0, 0.0], [0.0, 1.0]])
    )
    meta = {
        "schema_version": 1,
        "dimensions": 2,
        "model": {
            "model": "test",
            "revision": "abc",
            "precision": "float32",
            "config": {},
        },
        "mode": "text",
        "sample_count": 2,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "npz_sha256": hashlib.sha256(vectors.read_bytes()).hexdigest(),
        "ordered_input_hashes": [
            {"text_sha256": hashlib.sha256(b"geometry").hexdigest()}
        ]
        * 2,
        "config_identity": {
            "runner_version": "1",
            "postprocessing": "float32_l2_normalize_rows",
        },
    }
    vectors.with_suffix(".npz.json").write_text(json.dumps(meta))
    return manifest, vectors


def test_publish_import_validates_hash_ids_and_does_not_export_source_paths(tmp_path):
    manifest, vectors = write_lab(tmp_path)
    value, images = build_bundle(manifest, vectors)
    assert value.synthetic and len(value.entries) == 2 and images == {}
    assert value.entries[0].category_origin == "editorial_proxy"
    assert "source_path" not in value.model_dump_json()
    vectors.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        build_bundle(manifest, vectors)


def test_numeric_classifier_rejects_wrong_shapes_at_inference():
    model = NumericClassifier(
        kind="logreg",
        vector_space_id=space().id,
        labels=("a", "b"),
        coefficients=((1,),),
        intercept=(0,),
        mean=(0, 0),
        scale=(1, 1),
    )
    with pytest.raises(ValueError, match="classifier"):
        classify(model, space(), (1, 0), {})


def test_new_drawings_extend_same_space_and_keep_previous_release(tmp_path):
    from backend.app.semantic_explorer.models import Bundle, Entry
    from backend.app.semantic_explorer.store import ExplorerStore

    store = ExplorerStore(tmp_path / "store.sqlite3")
    base = Bundle(space=space(), entries=(Entry(id="old", label="old", vector=(1, 0)),))
    previous = store.publish("core", base, {})
    store.activate("core", previous)
    new = Bundle(
        space=space(), entries=(Entry(id="new", label="new", vector=(0.8, 0.6)),)
    )
    combined, images = extend_active(store, "core", new, {})
    assert [e.id for e in combined.entries] == ["old", "new"]
    assert store.load("core")[0] == previous
    incompatible = new.model_copy(
        update={"space": space().model_copy(update={"revision": "different"})}
    )
    with pytest.raises(ValueError, match="space"):
        extend_active(store, "core", incompatible, {})


@pytest.mark.parametrize("absolute", [False, True])
def test_import_rejects_images_outside_manifest_directory(tmp_path, absolute):
    from backend.tests.test_semantic_explorer import png

    root = tmp_path / "corpus"
    root.mkdir()
    outside = tmp_path / "private.png"
    outside.write_bytes(png())
    manifest, vectors = write_lab(root)
    data = json.loads(manifest.read_text())
    data["samples"][0]["image_path"] = str(outside) if absolute else "../private.png"
    manifest.write_text(json.dumps(data))
    meta_path = vectors.with_suffix(".npz.json")
    meta = json.loads(meta_path.read_text())
    meta["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="image_path"):
        build_bundle(manifest, vectors)


def test_classifier_artifact_rejects_encoder_and_schema_relabeling(tmp_path):
    from tools.publish_semantic_explorer import export_classifier, sha

    artifact = tmp_path / "classifier.json"
    model = NumericClassifier(
        kind="knn",
        vector_space_id=space().id,
        labels=("a", "b"),
        train_vectors=((1, 0), (0, 1)),
        train_labels=(0, 1),
        neighbors=1,
    )
    artifact.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "space": space().model_dump(mode="json"),
                "feature_names": ["size"],
                "training": {
                    "manifest_sha256": "a" * 64,
                    "npz_sha256": "b" * 64,
                    "split": "train",
                },
                "classifier": model.model_dump(mode="json"),
            }
        )
    )
    assert export_classifier(artifact, sha(artifact), space(), ("size",)) == model
    with pytest.raises(ValueError, match="space"):
        export_classifier(
            artifact,
            sha(artifact),
            space().model_copy(update={"model": "different"}),
            ("size",),
        )
    with pytest.raises(ValueError, match="features"):
        export_classifier(artifact, sha(artifact), space(), ("other",))


@pytest.mark.parametrize("kind", ["knn", "logreg"])
def test_training_numeric_artifact_uses_only_train_and_preserves_sklearn_prediction(
    tmp_path, kind
):
    from backend.app.semantic_explorer.models import Bundle, Entry
    from tools.train_semantic_classifier import train_numeric

    entries = tuple(
        Entry(
            id=f"p{i}",
            label=str(i),
            vector=v,
            features={"size": i},
            category="a" if i < 3 else "b",
            split="train",
        )
        for i, v in enumerate(
            [(1, 0), (0.9, 0.1), (0.8, 0.2), (0.1, 0.9), (0, 1), (-0.1, 0.9)]
        )
    )
    value = Bundle(
        space=space(),
        entries=entries
        + (
            Entry(
                id="heldout",
                label="heldout",
                vector=(-1, 0),
                features={"size": 999},
                category="UNSEEN",
                split="test",
            ),
        ),
    )
    model, fitted = train_numeric(value, kind)
    assert model.labels == ("a", "b")
    assert model.feature_names == (("size",) if kind == "logreg" else ())
    if kind == "knn":
        assert len(model.train_vectors) == 6
    for query in [(0.7, 0.3), (0.2, 0.8)]:
        actual = classify(model, space(), query, {"size": 4})
        geometry, embeddings = np.array([[4]]), np.array([query])
        assert actual.label == fitted.predict(geometry, embeddings)[0]
        assert actual.score == pytest.approx(
            fitted.closed_set_score(geometry, embeddings)[0]
        )


def test_stage_legacy_corpus_preserves_vectors_and_bounds_absolute_images(tmp_path):
    from backend.tests.test_semantic_explorer import png
    from tools.stage_semantic_explorer import stage_corpus

    original = tmp_path / "original"
    original.mkdir()
    manifest, vectors = write_lab(original)
    image = original / "render.png"
    image.write_bytes(png())
    data = json.loads(manifest.read_text())
    data["samples"][0]["image_path"] = str(image)
    manifest.write_text(json.dumps(data))
    meta_path = vectors.with_suffix(".npz.json")
    meta = json.loads(meta_path.read_text())
    meta["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    meta_path.write_text(json.dumps(meta))
    staged, copied = stage_corpus(manifest, vectors, tmp_path / "portable")
    assert copied.read_bytes() == vectors.read_bytes()
    assert json.loads(manifest.read_text())["samples"][0]["image_path"] == str(image)
    bundle, images = build_bundle(staged, copied)
    assert images["a"] == png() and len(bundle.entries) == 2
    assert (
        not __import__("pathlib")
        .Path(json.loads(staged.read_text())["samples"][0]["image_path"])
        .is_absolute()
    )
