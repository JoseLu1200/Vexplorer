from __future__ import annotations

import hashlib
import json
from pathlib import Path

import ezdxf
import numpy as np
import pytest

from tools.semantic_lab.probe_datasets import (
    CORE_CATEGORIES,
    EXTRA_CATEGORIES,
    cad_extra_diagnostics,
    closed_set_probe,
    evaluate_cad_extra,
    freeze_preregistration,
    identity_retrieval,
    prepare_cad_extra,
    prepare_engineering_manifest,
    prepare_plank_views,
    verify_preregistration,
)


def _write_dxf(path: Path, layers: tuple[str, ...] = ("0",)) -> str:
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    for index, layer in enumerate(layers):
        if layer != "0":
            document.layers.add(layer)
        modelspace.add_line((index * 10, 0), (index * 10 + 5, 5), dxfattribs={"layer": layer})
    document.saveas(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_cases(path: Path, cases: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(cases), encoding="utf-8")


def _write_manifest(path: Path, samples: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps({"schema_version": 1, "metadata": {}, "samples": samples}),
        encoding="utf-8",
    )
    return path


def _write_embeddings(path: Path, ids: list[str], vectors: list[list[float]]) -> Path:
    matrix = np.asarray(vectors, dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    np.savez_compressed(
        path,
        ids=np.asarray(ids),
        embeddings=matrix,
    )
    return path


def test_extra_categories_exclude_every_core_class() -> None:
    assert set(EXTRA_CATEGORIES).isdisjoint(CORE_CATEGORIES)
    assert EXTRA_CATEGORIES == (
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


def test_plank_preparation_keeps_only_public_layers_and_hash_verified_files(tmp_path: Path) -> None:
    source = tmp_path / "public"
    source.mkdir()
    dxf = source / "plank-001.dxf"
    digest = _write_dxf(dxf, ("ORTHO_FRONT", "ORTHO_TOP", "ORTHO_SIDE", "PRIVATE_NOTES"))
    _write_cases(
        source / "cases.json",
        [
            {
                "id": "plank-001",
                "file": dxf.name,
                "format": "dxf",
                "sha256": digest,
                "family_hash": "must-not-be-used-as-label",
                "split": "development",
            }
        ],
    )

    manifest = prepare_plank_views(source, tmp_path / "prepared")

    assert [sample["id"] for sample in manifest["samples"]] == [
        "plank-001:front",
        "plank-001:side",
        "plank-001:top",
    ]
    assert {sample["label"] for sample in manifest["samples"]} == {"plank-001"}
    assert all("must-not-be-used" not in sample["text"] for sample in manifest["samples"])
    for sample in manifest["samples"]:
        prepared = ezdxf.readfile(sample["source_path"])
        assert {entity.dxf.layer for entity in prepared.modelspace()} == {
            f"ORTHO_{sample['id'].split(':')[1].upper()}"
        }


def test_plank_preparation_rejects_changed_public_input(tmp_path: Path) -> None:
    dxf = tmp_path / "plank-001.dxf"
    _write_dxf(dxf, ("ORTHO_FRONT", "ORTHO_TOP", "ORTHO_SIDE"))
    _write_cases(
        tmp_path / "cases.json",
        [{"id": "plank-001", "file": dxf.name, "format": "dxf", "sha256": "0" * 64}],
    )

    with pytest.raises(ValueError, match="sha256"):
        prepare_plank_views(tmp_path, tmp_path / "prepared")


def test_engineering_preparation_uses_only_public_dxf_cases(tmp_path: Path) -> None:
    dxf = tmp_path / "cad-001.dxf"
    digest = _write_dxf(dxf)
    pdf = tmp_path / "visual-001.pdf"
    pdf.write_bytes(b"%PDF fixture")
    _write_cases(
        tmp_path / "cases.json",
        [
            {"id": "cad-001", "file": dxf.name, "format": "dxf", "sha256": digest},
            {
                "id": "visual-001",
                "file": pdf.name,
                "format": "raster_pdf",
                "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            },
        ],
    )

    manifest = prepare_engineering_manifest(tmp_path, tmp_path / "prepared")

    assert [sample["id"] for sample in manifest["samples"]] == ["cad-001"]
    assert manifest["metadata"]["excluded_formats"] == {"raster_pdf": 1}
    assert manifest["samples"][0]["label"] == "outside_core_domain"


def test_cad_extra_preparation_records_one_bad_file_without_aborting_batch(tmp_path: Path) -> None:
    source = tmp_path / "cadblock"
    category = source / "dxf_metric" / "bathroom-set"
    category.mkdir(parents=True)
    _write_dxf(category / "valid.dxf")
    (category / "broken.dxf").write_text("not a dxf", encoding="utf-8")

    manifest = prepare_cad_extra(
        source,
        tmp_path / "prepared",
        categories=("bathroom-set",),
        seed=20261114,
    )

    assert manifest["metadata"]["candidate_count"] == 2
    assert manifest["metadata"]["sample_count"] == 1
    assert manifest["metadata"]["excluded_count"] == 1
    assert manifest["metadata"]["excluded"][0]["source_path"].endswith("broken.dxf")
    assert manifest["metadata"]["excluded"][0]["exception_type"]


def test_preregistration_detects_manifest_change_before_scoring(tmp_path: Path) -> None:
    manifests = {
        "cad_extra": _write_manifest(tmp_path / "cad.json", []),
        "plank_views": _write_manifest(tmp_path / "plank.json", []),
        "engineering": _write_manifest(tmp_path / "engineering.json", []),
    }
    preregistration = freeze_preregistration(manifests, tmp_path / "preregistration.json")
    assert preregistration["protocol"]["classifier"] == {
        "name": "knn",
        "neighbors": 5,
        "metric": "cosine",
        "weights": "distance",
        "pca": None,
    }
    manifests["engineering"].write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="changed after preregistration"):
        verify_preregistration(tmp_path / "preregistration.json")


def test_cad_extra_evaluation_uses_fixed_train_for_validation_and_test(tmp_path: Path) -> None:
    samples = [
        {"id": "a", "label": "alpha", "split": "train"},
        {"id": "b", "label": "beta", "split": "train"},
        {"id": "va", "label": "alpha", "split": "validation"},
        {"id": "vb", "label": "beta", "split": "validation"},
        {"id": "ta", "label": "alpha", "split": "test"},
        {"id": "tb", "label": "beta", "split": "test"},
    ]
    manifest = _write_manifest(tmp_path / "manifest.json", samples)
    embeddings = _write_embeddings(
        tmp_path / "vectors.npz",
        ["a", "b", "va", "vb", "ta", "tb"],
        [[1, 0], [0, 1], [1, 0], [0, 1], [1, 0], [0, 1]],
    )

    result = evaluate_cad_extra(manifest, embeddings, neighbors=5, retrieval_k=5)

    assert result["validation"]["classification"]["macro_f1"] == 1.0
    assert result["test"]["classification"]["balanced_accuracy"] == 1.0
    assert result["validation"]["retrieval"] == {
        "precision_at_k": 0.5,
        "hit_at_k": 1.0,
        "effective_k": 2,
    }


def test_cad_diagnostics_exports_test_confusion_without_model_selection(tmp_path: Path) -> None:
    samples = [
        {"id": "a", "label": "alpha", "split": "train"},
        {"id": "b", "label": "beta", "split": "train"},
        {"id": "ta", "label": "alpha", "split": "test"},
        {"id": "tb", "label": "beta", "split": "test"},
    ]
    manifest = _write_manifest(tmp_path / "manifest.json", samples)
    embeddings = _write_embeddings(
        tmp_path / "vectors.npz",
        ["a", "b", "ta", "tb"],
        [[1, 0], [0, 1], [1, 0], [1, 0]],
    )

    output = tmp_path / "diagnostics.json"
    result = cad_extra_diagnostics(manifest, embeddings, neighbors=5, output_path=output)

    assert result["phase"] == "posthoc_fixed_protocol_replay"
    assert result["labels"] == ["alpha", "beta"]
    assert result["confusion_matrix"] == [[1, 0], [1, 0]]
    assert result["per_class"]["alpha"] == {"support": 1, "recall": 1.0}
    assert result["per_class"]["beta"] == {"support": 1, "recall": 0.0}
    assert result["selection_or_tuning"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_identity_retrieval_excludes_query_and_scores_same_object(tmp_path: Path) -> None:
    samples = [
        {"id": "one:front", "label": "one"},
        {"id": "one:top", "label": "one"},
        {"id": "two:front", "label": "two"},
        {"id": "two:top", "label": "two"},
    ]
    manifest = _write_manifest(tmp_path / "manifest.json", samples)
    embeddings = _write_embeddings(
        tmp_path / "vectors.npz",
        [sample["id"] for sample in samples],
        [[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]],
    )

    result = identity_retrieval(manifest, embeddings, k=2)

    assert result == {"hit_at_1": 1.0, "hit_at_2": 1.0, "queries": 4, "k": 2}


def test_closed_set_probe_reports_forced_labels_without_accuracy_claim(tmp_path: Path) -> None:
    core = _write_manifest(
        tmp_path / "core.json",
        [
            {"id": "a", "label": "alpha", "split": "train"},
            {"id": "b", "label": "beta", "split": "train"},
        ],
    )
    probe = _write_manifest(
        tmp_path / "probe.json",
        [{"id": "x", "label": "outside_core_domain", "split": "probe"}],
    )
    core_vectors = _write_embeddings(tmp_path / "core.npz", ["a", "b"], [[1, 0], [0, 1]])
    probe_vectors = _write_embeddings(tmp_path / "probe.npz", ["x"], [[0.8, 0.2]])

    result = closed_set_probe(core, core_vectors, probe, probe_vectors, neighbors=5)

    assert result["prediction_counts"] == {"alpha": 1}
    assert result["samples"][0]["id"] == "x"
    assert result["samples"][0]["forced_proxy_label"] == "alpha"
    assert "accuracy" not in result
