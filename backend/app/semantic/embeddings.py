from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import httpx


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingResult:
    vector: tuple[float, ...]
    model: str
    dimensions: int


def embedding_cache_key(descriptor_version: str, model: str, dimensions: int, normalized_text: str) -> str:
    payload = json.dumps({"descriptor_version": descriptor_version, "model": model, "dimensions": dimensions, "encoding_format": "float", "normalized_text": normalized_text}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_embedding(vector: object, dimensions: int) -> tuple[float, ...]:
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise EmbeddingProviderError("invalid_embedding")
    try:
        values = tuple(float(item) for item in vector)
    except (TypeError, ValueError) as exc:
        raise EmbeddingProviderError("invalid_embedding") from exc
    if not all(math.isfinite(item) for item in values) or math.sqrt(sum(item * item for item in values)) == 0:
        raise EmbeddingProviderError("invalid_embedding")
    return values


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, dimensions: int, base_url: str = "https://api.openai.com/v1", transport: httpx.BaseTransport | None = None) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, timeout=30, transport=transport)

    def embed(self, text: str) -> EmbeddingResult:
        try:
            response = self._client.post("/embeddings", json={"input": text, "model": self.model, "encoding_format": "float", "dimensions": self.dimensions})
            response.raise_for_status()
            payload = response.json()
            returned_model = payload["model"]
            vector = payload["data"][0]["embedding"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("semantic_provider_failed") from exc
        if returned_model != self.model:
            raise EmbeddingProviderError("embedding_space_incompatible")
        return EmbeddingResult(vector=validate_embedding(vector, self.dimensions), model=returned_model, dimensions=self.dimensions)
