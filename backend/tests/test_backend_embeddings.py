from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from backend.app.agente.config import EmbeddingSettings
from backend.app.contratos.modelos import DescriptorDimensions, EmbeddingMetadata, FurnitureDescriptor, LibraryItem
from backend.app.semantic.embeddings import (
    EMBEDDINGGEMMA2_MODEL_ID,
    EMBEDDINGGEMMA2_MODEL_KEY,
    EMBEDDINGGEMMA2_TEXT_PREPROCESSING,
    EmbeddingGemma2Provider,
    EmbeddingProviderError,
    EmbeddingSpaceIdentity,
    embedding_cache_key,
    validate_embedding,
)
from backend.app.servicios.repository import DemoRepository
from backend.app.similarity.service import semantic_groups


def _snapshot(tmp_path: Path) -> Path:
    snapshot = tmp_path / "f9972ac22e696a105c482202646979e33e4b5a1e"
    snapshot.mkdir()
    (snapshot / "config.json").write_text(
        '{"architectures":["EmbeddingGemma2Model"],"embedding_dim":768}',
        encoding="utf-8",
    )
    (snapshot / "config_sentence_transformers.json").write_text(
        '{"prompts":{"SentenceSimilarity":"task: sentence similarity | query:"}}',
        encoding="utf-8",
    )
    (snapshot / "model.safetensors").write_bytes(b"weights")
    return snapshot


def test_embedding_settings_require_pinned_local_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("backend.app.agente.config.find_spec", lambda name: object())
    monkeypatch.delenv("VEXPLORER_EMBEDDING_SNAPSHOT", raising=False)
    monkeypatch.setenv("VEXPLORER_EMBEDDING_MODEL", EMBEDDINGGEMMA2_MODEL_KEY)
    missing = EmbeddingSettings.from_env()
    assert not missing.available
    assert missing.unavailable_reason == "missing_server_configuration:VEXPLORER_EMBEDDING_SNAPSHOT"

    snapshot = _snapshot(tmp_path)
    monkeypatch.setenv("VEXPLORER_EMBEDDING_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("VEXPLORER_EMBEDDING_REVISION", snapshot.name)
    configured = EmbeddingSettings.from_env()
    assert configured.available
    assert configured.model_key == "embeddinggemma2"
    assert configured.model_id == "google/embeddinggemma-2"
    assert configured.dimensions == 768
    assert configured.modality == "text"
    assert configured.preprocessing_version == EMBEDDINGGEMMA2_TEXT_PREPROCESSING


def test_embedding_settings_reject_snapshot_revision_or_config_mismatch(tmp_path: Path, monkeypatch) -> None:
    snapshot = _snapshot(tmp_path)
    monkeypatch.setenv("VEXPLORER_EMBEDDING_MODEL", EMBEDDINGGEMMA2_MODEL_KEY)
    monkeypatch.setenv("VEXPLORER_EMBEDDING_SNAPSHOT", str(snapshot))
    monkeypatch.setenv("VEXPLORER_EMBEDDING_REVISION", "different-revision")
    assert EmbeddingSettings.from_env().unavailable_reason == "embedding_snapshot_revision_mismatch"

    monkeypatch.setenv("VEXPLORER_EMBEDDING_REVISION", snapshot.name)
    (snapshot / "config.json").write_text('{"architectures":["OtherModel"]}', encoding="utf-8")
    assert EmbeddingSettings.from_env().unavailable_reason == "embedding_snapshot_config_incompatible"


def test_embeddinggemma2_provider_uses_local_text_pipeline_and_l2_output(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    captured: dict[str, object] = {}

    class FakeModel:
        def get_embedding_dimension(self) -> int:
            return 768

        def encode(self, inputs, **kwargs):
            captured["inputs"] = inputs
            captured["encode"] = kwargs
            vector = np.zeros((1, 768), dtype=np.float32)
            vector[0, :2] = (3.0, 4.0)
            return vector

    def factory(path: str, **kwargs):
        captured["path"] = path
        captured["load"] = kwargs
        return FakeModel()

    identity = EmbeddingSpaceIdentity.embeddinggemma2_text(snapshot.name)
    provider = EmbeddingGemma2Provider(snapshot_path=snapshot, identity=identity, model_factory=factory)
    result = provider.embed("canonical descriptor")

    assert captured["path"] == str(snapshot)
    assert captured["load"] == {
        "device": "cpu",
        "model_kwargs": {"local_files_only": True, "trust_remote_code": False, "torch_dtype": "float32"},
        "config_kwargs": {"vision_config": None, "audio_config": None},
    }
    assert captured["inputs"] == ["canonical descriptor"]
    assert captured["encode"] == {
        "prompt_name": "SentenceSimilarity",
        "convert_to_numpy": True,
        "normalize_embeddings": True,
        "show_progress_bar": False,
    }
    assert result.model == EMBEDDINGGEMMA2_MODEL_ID
    assert result.dimensions == 768
    assert result.vector[:2] == pytest.approx((0.6, 0.8))
    assert math.sqrt(sum(item * item for item in result.vector)) == pytest.approx(1.0)


def test_embeddinggemma2_provider_serializes_cpu_inference(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)

    class FakeModel:
        active = 0
        maximum = 0

        def get_embedding_dimension(self) -> int:
            return 768

        def encode(self, inputs, **kwargs):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            time.sleep(0.02)
            self.active -= 1
            vector = np.zeros((1, 768), dtype=np.float32)
            vector[0, 0] = 1
            return vector

    model = FakeModel()
    provider = EmbeddingGemma2Provider(
        snapshot_path=snapshot,
        identity=EmbeddingSpaceIdentity.embeddinggemma2_text(snapshot.name),
        model_factory=lambda *args, **kwargs: model,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(provider.embed, ("one", "two")))

    assert model.maximum == 1


@pytest.mark.parametrize("vector,dimensions", (([1.0], 2), ([0.0, 0.0], 2), ([math.nan, 1.0], 2)))
def test_embeddinggemma2_provider_rejects_corrupt_vectors(vector, dimensions) -> None:
    with pytest.raises(EmbeddingProviderError, match="invalid_embedding"):
        validate_embedding(vector, dimensions)


def test_embedding_cache_identity_includes_complete_vector_space() -> None:
    identity = EmbeddingSpaceIdentity.embeddinggemma2_text("revision-a")
    base = embedding_cache_key(identity, "furniture-v2", "same")
    assert base != embedding_cache_key(EmbeddingSpaceIdentity.embeddinggemma2_text("revision-b"), "furniture-v2", "same")
    assert base != embedding_cache_key(identity.model_copy(update={"preprocessing_version": "other"}), "furniture-v2", "same")
    assert base != embedding_cache_key(identity, "furniture-v3", "same")
    assert base != embedding_cache_key(identity, "furniture-v2", "different")


def test_repository_cache_requires_exact_space_identity(tmp_path: Path) -> None:
    repository = DemoRepository(tmp_path / "runtime.sqlite3")
    identity = EmbeddingSpaceIdentity.embeddinggemma2_text("revision-a")
    cache_key = embedding_cache_key(identity, "furniture-v2", "same")

    repository.save_embedding(
        cache_key,
        identity.model,
        identity.dimensions,
        "furniture-v2",
        tuple([1.0] + [0.0] * 767),
        space_id=identity.space_id,
        identity_json=identity.model_dump_json(),
    )

    assert repository.get_embedding(
        cache_key,
        identity.model,
        identity.dimensions,
        "furniture-v2",
        space_id=identity.space_id,
    )[0] == 1.0
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        repository.get_embedding(
            cache_key,
            identity.model,
            identity.dimensions,
            "furniture-v2",
            space_id="different-space",
        )


def test_semantic_groups_reject_mixed_embedding_spaces() -> None:
    descriptor = FurnitureDescriptor(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=900, depth_mm=300, height_mm=1200), roles=(), structure="unknown", unknown_fields=("structure",))
    items = tuple(
        LibraryItem(
            id=f"item-{index}", run_id=f"run-{index}", result_revision=2, label=str(index),
            descriptor=descriptor, descriptor_fingerprint="a" * 64, created_at="2026-11-13T00:00:00Z",
            embedding=EmbeddingMetadata(
                provider=provider, model=model, model_revision="revision-a", modality="text",
                normalization="l2", preprocessing_version=EMBEDDINGGEMMA2_TEXT_PREPROCESSING,
                prompt_name="SentenceSimilarity",
                dimensions=768 if provider == "embeddinggemma2" else 2,
                cache_key=f"key-{index}", status="generated",
            ),
        )
        for index, (provider, model) in enumerate((("embeddinggemma2", EMBEDDINGGEMMA2_MODEL_ID), ("openai", "text-embedding-3-small")))
    )
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        semantic_groups(items, {"item-0": (1.0, 0.0), "item-1": (1.0, 0.0)}, 0.8)
