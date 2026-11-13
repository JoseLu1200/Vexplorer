from __future__ import annotations

import math

import httpx
import pytest

from backend.app.semantic.embeddings import EmbeddingProviderError, OpenAIEmbeddingProvider, embedding_cache_key
from backend.app.contratos.modelos import DescriptorDimensions, EmbeddingMetadata, FurnitureDescriptor, LibraryItem
from backend.app.similarity.service import semantic_groups


def test_openai_embedding_provider_uses_documented_request_shape() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.25]}], "model": "text-embedding-3-small", "usage": {"prompt_tokens": 2, "total_tokens": 2}})

    provider = OpenAIEmbeddingProvider(api_key="test-key", model="text-embedding-3-small", dimensions=2, base_url="https://example.test/v1", transport=httpx.MockTransport(handler))
    result = provider.embed("canonical descriptor")

    assert captured == {"input": "canonical descriptor", "model": "text-embedding-3-small", "encoding_format": "float", "dimensions": 2}
    assert result.vector == (0.5, 0.25)
    assert result.model == "text-embedding-3-small" and result.dimensions == 2


@pytest.mark.parametrize("vector", ([1.0], [0.0, 0.0], [math.nan, 1.0]))
def test_openai_embedding_provider_rejects_corrupt_vectors(vector) -> None:
    payload = __import__("json").dumps({"data": [{"index": 0, "embedding": vector}], "model": "text-embedding-3-small", "usage": {}}).encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=payload, headers={"content-type": "application/json"}))
    provider = OpenAIEmbeddingProvider(api_key="test-key", model="text-embedding-3-small", dimensions=2, base_url="https://example.test/v1", transport=transport)

    with pytest.raises(EmbeddingProviderError, match="invalid_embedding"):
        provider.embed("descriptor")


def test_embedding_cache_identity_includes_version_model_dimensions_and_text() -> None:
    base = embedding_cache_key("furniture-v1", "text-embedding-3-small", 256, "same")
    assert base != embedding_cache_key("furniture-v2", "text-embedding-3-small", 256, "same")
    assert base != embedding_cache_key("furniture-v1", "other", 256, "same")
    assert base != embedding_cache_key("furniture-v1", "text-embedding-3-small", 512, "same")
    assert base != embedding_cache_key("furniture-v1", "text-embedding-3-small", 256, "different")


def test_semantic_groups_reject_mixed_embedding_spaces() -> None:
    descriptor = FurnitureDescriptor(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=900, depth_mm=300, height_mm=1200), roles=(), structure="unknown", unknown_fields=("structure",))
    items = tuple(LibraryItem(id=f"item-{index}", run_id=f"run-{index}", result_revision=2, label=str(index), descriptor=descriptor, descriptor_fingerprint="a" * 64, created_at="2026-11-13T00:00:00Z", embedding=EmbeddingMetadata(model=model, dimensions=2, cache_key=f"key-{index}", status="generated")) for index, model in enumerate(("text-embedding-3-small", "other-space")))
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        semantic_groups(items, {"item-0": (1.0, 0.0), "item-1": (1.0, 0.0)}, 0.8)
