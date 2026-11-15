from __future__ import annotations

import os
import json
from importlib.util import find_spec
from dataclasses import dataclass
from pathlib import Path

from backend.app.semantic.embeddings import (
    EMBEDDINGGEMMA2_DIMENSIONS,
    EMBEDDINGGEMMA2_MODEL_ID,
    EMBEDDINGGEMMA2_MODEL_KEY,
    EMBEDDINGGEMMA2_TEXT_PREPROCESSING,
    EmbeddingSpaceIdentity,
)


EMBEDDINGGEMMA2_PINNED_REVISION = "f9972ac22e696a105c482202646979e33e4b5a1e"


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str | None
    model: str | None
    base_url: str = "https://api.openai.com/v1"
    max_output_tokens: int = 4096
    vision_enabled: bool = False

    @classmethod
    def from_env(cls) -> "ProviderSettings":
        try:
            max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "4096"))
        except ValueError:
            max_output_tokens = 0
        vision_enabled = os.getenv("OPENAI_VISION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        return cls(api_key=os.getenv("OPENAI_API_KEY"), model=os.getenv("OPENAI_MODEL"), base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"), max_output_tokens=max_output_tokens, vision_enabled=vision_enabled)

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
    model_key: str
    snapshot_path: Path | None
    revision: str
    device: str = "cpu"
    model_id: str = EMBEDDINGGEMMA2_MODEL_ID
    dimensions: int = EMBEDDINGGEMMA2_DIMENSIONS
    modality: str = "text"
    preprocessing_version: str = EMBEDDINGGEMMA2_TEXT_PREPROCESSING

    @classmethod
    def from_env(cls) -> "EmbeddingSettings":
        raw_snapshot = os.getenv("VEXPLORER_EMBEDDING_SNAPSHOT")
        return cls(
            model_key=os.getenv("VEXPLORER_EMBEDDING_MODEL", EMBEDDINGGEMMA2_MODEL_KEY),
            snapshot_path=Path(raw_snapshot).expanduser() if raw_snapshot else None,
            revision=os.getenv("VEXPLORER_EMBEDDING_REVISION", EMBEDDINGGEMMA2_PINNED_REVISION),
            device=os.getenv("VEXPLORER_EMBEDDING_DEVICE", "cpu"),
        )

    @property
    def identity(self) -> EmbeddingSpaceIdentity:
        return EmbeddingSpaceIdentity.embeddinggemma2_text(self.revision)

    def _snapshot_error(self) -> str | None:
        if self.snapshot_path is None:
            return "missing_server_configuration:VEXPLORER_EMBEDDING_SNAPSHOT"
        snapshot = self.snapshot_path.resolve()
        if self.revision != EMBEDDINGGEMMA2_PINNED_REVISION or snapshot.name != self.revision:
            return "embedding_snapshot_revision_mismatch"
        required = (
            snapshot / "config.json",
            snapshot / "config_sentence_transformers.json",
            snapshot / "model.safetensors",
        )
        if not all(path.is_file() for path in required):
            return "embedding_snapshot_incomplete"
        try:
            config = json.loads(required[0].read_text(encoding="utf-8"))
            sentence_config = json.loads(required[1].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return "embedding_snapshot_config_incompatible"
        embedding_dim = config.get("embedding_dim")
        if embedding_dim is None and isinstance(config.get("text_config"), dict):
            embedding_dim = config["text_config"].get("embedding_dim")
        if (
            config.get("architectures") != ["EmbeddingGemma2Model"]
            or embedding_dim != EMBEDDINGGEMMA2_DIMENSIONS
            or str(sentence_config.get("prompts", {}).get("SentenceSimilarity", "")).strip()
            != "task: sentence similarity | query:"
        ):
            return "embedding_snapshot_config_incompatible"
        return None

    @property
    def available(self) -> bool:
        return (
            self.model_key == EMBEDDINGGEMMA2_MODEL_KEY
            and self.device == "cpu"
            and find_spec("sentence_transformers") is not None
            and self._snapshot_error() is None
        )

    @property
    def unavailable_reason(self) -> str | None:
        if self.model_key != EMBEDDINGGEMMA2_MODEL_KEY:
            return "unsupported_embedding_model"
        if self.device != "cpu":
            return "unsupported_embedding_device"
        snapshot_error = self._snapshot_error()
        if snapshot_error is not None:
            return snapshot_error
        if find_spec("sentence_transformers") is None:
            return "embedding_runtime_dependency_missing"
        return None
