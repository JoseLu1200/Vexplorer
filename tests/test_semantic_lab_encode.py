from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tools.semantic_lab.encode import EncoderInfo, encode_manifest, main


class FakeEncoder:
    def __init__(self, vectors: object = None) -> None:
        self.calls: list[tuple[list[object], str, int | None]] = []
        self.vectors = vectors

    @property
    def info(self) -> EncoderInfo:
        return EncoderInfo(
            model="fake/model",
            revision="0123456789abcdef",
            precision="float32",
            native_dimensions=3,
            config={"implementation": "fake-v1"},
        )

    def encode(self, inputs: list[object], *, mode: str, truncate_dim: int | None) -> np.ndarray:
        self.calls.append((inputs, mode, truncate_dim))
        if self.vectors is not None:
            return np.asarray(self.vectors)
        dimensions = truncate_dim or 3
        return np.arange(1, len(inputs) * dimensions + 1, dtype=np.float32).reshape(
            len(inputs), dimensions
        )


def _sample(
    sample_id: str,
    *,
    text: str = "four straight segments and two supports",
    image_path: str = "render.png",
    label: str = "chair",
) -> dict:
    return {
        "id": sample_id,
        "source_path": f"private/{label}/{sample_id}.dxf",
        "image_path": image_path,
        "label": label,
        "label_source": "folder_proxy",
        "group_id": f"group-{sample_id}",
        "split": "train",
        "features": {"line_count": 4.0},
        "text": text,
    }


def _write_manifest(path: Path, samples: list[dict], *, synthetic: bool = False) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metadata": {"synthetic": synthetic, "name": "neutral-corpus"},
                "samples": samples,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_model_boundary_receives_only_neutral_text_and_image_bytes(tmp_path: Path) -> None:
    image = tmp_path / "revealing-chair-name.png"
    image.write_bytes(b"not-decoded-by-fake")
    manifest = _write_manifest(
        tmp_path / "manifest.json",
        [_sample("secret-id", image_path=image.name, label="secret-label")],
    )
    encoder = FakeEncoder()

    metadata = encode_manifest(
        manifest_path=manifest,
        model="fake",
        mode="mixed",
        output_path=tmp_path / "vectors.npz",
        cache_dir=tmp_path / "cache",
        encoder=encoder,
    )

    assert encoder.calls == [
        (
            [("four straight segments and two supports", b"not-decoded-by-fake")],
            "mixed",
            None,
        )
    ]
    table = np.load(tmp_path / "vectors.npz", allow_pickle=False)
    assert table["ids"].tolist() == ["secret-id"]
    assert table["embeddings"].shape == (1, 3)
    assert metadata["sample_count"] == 1
    assert metadata["model"]["revision"] == "0123456789abcdef"
    assert metadata["synthetic_corpus"] is False
    assert metadata["npz_sha256"]


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ([[1.0, float("nan"), 2.0]], "finite"),
        ([[1.0, 2.0]], "dimension"),
        ([[1.0, 2.0, 3.0], [3.0, 2.0, 1.0]], "row count"),
        ([1.0, 2.0, 3.0], "two-dimensional"),
    ],
)
def test_rejects_corrupt_encoder_output_before_writing(
    tmp_path: Path, vectors: object, message: str
) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", [_sample("a")])
    output = tmp_path / "vectors.npz"

    with pytest.raises(ValueError, match=message):
        encode_manifest(
            manifest_path=manifest,
            model="fake",
            mode="text",
            output_path=output,
            cache_dir=tmp_path / "cache",
            encoder=FakeEncoder(vectors),
        )

    assert not output.exists()


def test_complete_identity_cache_reuses_exact_run_but_not_changed_content(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", [_sample("a", text="neutral one")])
    output = tmp_path / "first.npz"
    encoder = FakeEncoder()
    first = encode_manifest(
        manifest_path=manifest,
        model="fake",
        mode="text",
        output_path=output,
        cache_dir=tmp_path / "cache",
        truncate_dim=2,
        encoder=encoder,
    )
    second = encode_manifest(
        manifest_path=manifest,
        model="fake",
        mode="text",
        output_path=tmp_path / "second.npz",
        cache_dir=tmp_path / "cache",
        truncate_dim=2,
        encoder=encoder,
    )

    assert len(encoder.calls) == 1
    assert first["cache_key"] == second["cache_key"]
    assert second["cache_status"] == "hit"
    np.testing.assert_array_equal(
        np.load(output)["embeddings"], np.load(tmp_path / "second.npz")["embeddings"]
    )

    _write_manifest(manifest, [_sample("a", text="neutral two")])
    changed = encode_manifest(
        manifest_path=manifest,
        model="fake",
        mode="text",
        output_path=tmp_path / "changed.npz",
        cache_dir=tmp_path / "cache",
        truncate_dim=2,
        encoder=encoder,
    )
    assert len(encoder.calls) == 2
    assert changed["cache_key"] != first["cache_key"]
    assert changed["cache_status"] == "miss"


def test_manifest_rejects_duplicate_ids_and_missing_required_modality(tmp_path: Path) -> None:
    duplicate = _write_manifest(
        tmp_path / "duplicate.json", [_sample("same"), _sample("same")]
    )
    with pytest.raises(ValueError, match="duplicate sample id"):
        encode_manifest(
            manifest_path=duplicate,
            model="fake",
            mode="text",
            output_path=tmp_path / "x.npz",
            cache_dir=tmp_path / "cache",
            encoder=FakeEncoder(),
        )

    missing_image = _write_manifest(
        tmp_path / "missing.json", [_sample("a", image_path="missing.png")]
    )
    with pytest.raises(ValueError, match="image.*does not exist"):
        encode_manifest(
            manifest_path=missing_image,
            model="fake",
            mode="image",
            output_path=tmp_path / "y.npz",
            cache_dir=tmp_path / "cache",
            encoder=FakeEncoder(),
        )


def test_synthetic_manifest_is_explicit_in_metadata(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "manifest.json", [_sample("a")], synthetic=True
    )
    metadata = encode_manifest(
        manifest_path=manifest,
        model="fake",
        mode="text",
        output_path=tmp_path / "vectors.npz",
        cache_dir=tmp_path / "cache",
        encoder=FakeEncoder(),
    )
    assert metadata["synthetic_corpus"] is True


def test_persisted_vectors_are_l2_normalized_in_float32(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", [_sample("a")])
    output = tmp_path / "vectors.npz"
    encode_manifest(
        manifest_path=manifest,
        model="fake",
        mode="text",
        output_path=output,
        cache_dir=tmp_path / "cache",
        encoder=FakeEncoder([[3.0, 4.0, 0.0]]),
    )

    vector = np.load(output, allow_pickle=False)["embeddings"][0]
    np.testing.assert_allclose(vector, np.array([0.6, 0.8, 0.0]), atol=1e-7)
    assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-7)


def test_truncation_is_limited_to_declared_embeddinggemma2_dimensions(
    tmp_path: Path,
) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", [_sample("a")])
    with pytest.raises(ValueError, match="does not declare native Matryoshka"):
        encode_manifest(
            manifest_path=manifest,
            model="dinov3",
            mode="image",
            output_path=tmp_path / "dino.npz",
            cache_dir=tmp_path / "cache",
            truncate_dim=2,
            encoder=FakeEncoder(),
        )
    with pytest.raises(ValueError, match="must be 128, 256, 512 or 768"):
        encode_manifest(
            manifest_path=manifest,
            model="embeddinggemma2",
            mode="text",
            output_path=tmp_path / "eg2.npz",
            cache_dir=tmp_path / "cache",
            truncate_dim=64,
            encoder=FakeEncoder(),
        )


def test_cli_records_a_structured_failure_without_model_loading(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "manifest.json", [_sample("a")])
    output = tmp_path / "failure.npz"

    result = main(
        [
            "--manifest",
            str(manifest),
            "--model",
            "dinov3",
            "--mode",
            "text",
            "--output",
            str(output),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )

    assert result == 1
    failure = json.loads(
        output.with_suffix(".npz.json").read_text(encoding="utf-8")
    )
    assert failure["errors"] == [
        {
            "type": "ValueError",
            "message": "model dinov3 does not support mode text",
        }
    ]
    assert not output.exists()
