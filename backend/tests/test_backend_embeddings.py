from __future__ import annotations

import math

import httpx
import pytest

from backend.app.semantic.embeddings import EmbeddingProviderError, OpenAIEmbeddingProvider, embedding_cache_key


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
