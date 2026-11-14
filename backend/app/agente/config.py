from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str | None
    model: str | None
    base_url: str = "https://api.openai.com/v1"
    max_output_tokens: int = 4096

    @classmethod
    def from_env(cls) -> "ProviderSettings":
        try:
            max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "4096"))
        except ValueError:
            max_output_tokens = 0
        return cls(api_key=os.getenv("OPENAI_API_KEY"), model=os.getenv("OPENAI_MODEL"), base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"), max_output_tokens=max_output_tokens)

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model and 256 <= self.max_output_tokens <= 16384)

    @property
    def unavailable_reason(self) -> str | None:
        missing = []
        if not self.api_key:
            missing.append("OPENAI_API_KEY")
        if not self.model:
            missing.append("OPENAI_MODEL")
        if missing:
            return "missing_server_configuration:" + ",".join(missing)
        if not 256 <= self.max_output_tokens <= 16384:
            return "invalid_max_output_tokens"
        return None


@dataclass(frozen=True)
class EmbeddingSettings:
    api_key: str | None
    model: str
    dimensions: int
    base_url: str = "https://api.openai.com/v1"

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        raw_dimensions = os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "256")
        try:
            dimensions = int(raw_dimensions)
        except ValueError:
            dimensions = 0
        return cls(api_key=os.getenv("OPENAI_API_KEY"), model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"), dimensions=dimensions, base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model == "text-embedding-3-small" and 1 <= self.dimensions <= 1536)

    @property
    def unavailable_reason(self) -> str | None:
        if not self.api_key:
            return "missing_server_configuration:OPENAI_API_KEY"
        if self.model != "text-embedding-3-small":
            return "unsupported_embedding_model"
        if not 1 <= self.dimensions <= 1536:
            return "invalid_embedding_dimensions"
        return None
