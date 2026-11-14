from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field


EMBEDDINGGEMMA2_MODEL_KEY = "embeddinggemma2"
EMBEDDINGGEMMA2_MODEL_ID = "google/embeddinggemma-2"
EMBEDDINGGEMMA2_DIMENSIONS = 768
EMBEDDINGGEMMA2_TEXT_PREPROCESSING = "semantic-descriptor-sentence-similarity-v1"
EMBEDDINGGEMMA2_TEXT_PROMPT = "SentenceSimilarity"


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingSpaceIdentity(BaseModel):
    """Immutable identity of vectors that may be compared with each other."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["embeddinggemma2", "openai"]
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    modality: Literal["text", "mixed"]
    dimensions: int = Field(gt=0)
    normalization: Literal["l2"] = "l2"
    preprocessing_version: str = Field(min_length=1)
    prompt_name: str | None = None

    @classmethod
    def embeddinggemma2_text(cls, revision: str) -> "EmbeddingSpaceIdentity":
        return cls(
            provider="embeddinggemma2",
            model=EMBEDDINGGEMMA2_MODEL_ID,
            model_revision=revision,
            modality="text",
            dimensions=EMBEDDINGGEMMA2_DIMENSIONS,
            preprocessing_version=EMBEDDINGGEMMA2_TEXT_PREPROCESSING,
            prompt_name=EMBEDDINGGEMMA2_TEXT_PROMPT,
        )

    @property
    def space_id(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmbeddingResult:
    vector: tuple[float, ...]
    model: str
    dimensions: int


def embedding_cache_key(
    identity: EmbeddingSpaceIdentity,
    descriptor_version: str,
    normalized_text: str,
) -> str:
    payload = json.dumps(
        {
            "descriptor_version": descriptor_version,
            "space": identity.model_dump(mode="json"),
            "normalized_text": normalized_text,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_embedding(vector: object, dimensions: int) -> tuple[float, ...]:
    if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
        raise EmbeddingProviderError("invalid_embedding")
    try:
        values = tuple(float(item) for item in vector)
    except (TypeError, ValueError) as exc:
        raise EmbeddingProviderError("invalid_embedding") from exc
    if not all(math.isfinite(item) for item in values):
        raise EmbeddingProviderError("invalid_embedding")
    norm = math.sqrt(sum(item * item for item in values))
    if not math.isfinite(norm) or norm == 0:
        raise EmbeddingProviderError("invalid_embedding")
    return values


def normalize_embedding(vector: object, dimensions: int) -> tuple[float, ...]:
    values = validate_embedding(vector, dimensions)
    norm = math.sqrt(sum(item * item for item in values))
    return tuple(item / norm for item in values)


ModelFactory = Callable[..., Any]


class EmbeddingGemma2Provider:
    """Pinned, offline, text-only runtime adapter for EmbeddingGemma 2."""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        identity: EmbeddingSpaceIdentity,
        device: str = "cpu",
        model_factory: ModelFactory | None = None,
    ) -> None:
        if identity != EmbeddingSpaceIdentity.embeddinggemma2_text(identity.model_revision):
            raise ValueError("unsupported_embedding_space")
        self.snapshot_path = Path(snapshot_path).resolve()
        self.identity = identity
        self.model = identity.model
        self.dimensions = identity.dimensions
        self.device = device
        self._model_factory = model_factory
        self._loaded_model: Any | None = None
        self._load_lock = Lock()
        self._encode_lock = Lock()

    def _factory(self) -> ModelFactory:
        if self._model_factory is not None:
            return self._model_factory
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderError("embedding_runtime_dependency_missing") from exc
        return SentenceTransformer

    def _load(self) -> Any:
        if self._loaded_model is not None:
            return self._loaded_model
        with self._load_lock:
            if self._loaded_model is None:
                try:
                    model = self._factory()(
                        str(self.snapshot_path),
                        device=self.device,
                        model_kwargs={
                            "local_files_only": True,
                            "trust_remote_code": False,
                            "torch_dtype": "float32",
                        },
                        config_kwargs={"vision_config": None, "audio_config": None},
                    )
                except EmbeddingProviderError:
                    raise
                except Exception as exc:
                    raise EmbeddingProviderError("semantic_provider_failed") from exc
                if int(model.get_embedding_dimension()) != self.dimensions:
                    raise EmbeddingProviderError("embedding_space_incompatible")
                self._loaded_model = model
        return self._loaded_model

    def embed(self, text: str) -> EmbeddingResult:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingProviderError("invalid_embedding_input")
        try:
            with self._encode_lock:
                matrix = self._load().encode(
                    [text],
                    prompt_name=self.identity.prompt_name,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            vector = matrix[0].tolist() if hasattr(matrix[0], "tolist") else list(matrix[0])
        except EmbeddingProviderError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError("semantic_provider_failed") from exc
        return EmbeddingResult(
            vector=normalize_embedding(vector, self.dimensions),
            model=self.model,
            dimensions=self.dimensions,
        )
