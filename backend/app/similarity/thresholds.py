from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SimilarityMode = Literal["geometric", "semantic"]
ThresholdKind = Literal["similarity", "group", "near_duplicate"]

ABSTENTION_REASON_NO_PRECEDENTS: Literal["sin_precedentes_suficientes"] = "sin_precedentes_suficientes"
CALIBRATION_FILE_ENV_VAR = "VEXPLORER_SIMILARITY_THRESHOLDS_FILE"

# Legacy safety defaults retained for API compatibility. They are not an
# EmbeddingGemma 2 calibration; deployments must supply model-specific values
# through VEXPLORER_SIMILARITY_THRESHOLDS_FILE before treating them as gates.
DEFAULT_SIMILARITY_THRESHOLDS: dict[SimilarityMode, float] = {
    "geometric": 0.78,
    "semantic": 0.90,
}

DEFAULT_GROUP_THRESHOLDS: dict[SimilarityMode, float] = {
    "geometric": 0.85,
    "semantic": 0.92,
}

NEAR_DUPLICATE_THRESHOLDS: dict[SimilarityMode, float] = {
    "geometric": 0.97,
    "semantic": 0.97,
}

_DEFAULTS_BY_KIND: dict[ThresholdKind, dict[SimilarityMode, float]] = {
    "similarity": DEFAULT_SIMILARITY_THRESHOLDS,
    "group": DEFAULT_GROUP_THRESHOLDS,
    "near_duplicate": NEAR_DUPLICATE_THRESHOLDS,
}


@dataclass(frozen=True, slots=True)
class AbstentionResult:
    """Outcome of evaluating similarity matches against a calibrated threshold."""

    abstained: bool
    abstention_reason: Literal["sin_precedentes_suficientes"] | None
    threshold_used: float
    filtered_matches: tuple[Any, ...]


def _is_valid_threshold(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and -1.0 <= float(value) <= 1.0
    )


def _load_calibration_data(config_path: Path | str | None = None) -> dict[str, Any]:
    raw_path = config_path if config_path is not None else os.getenv(CALIBRATION_FILE_ENV_VAR)
    if not raw_path:
        return {}
    path = Path(raw_path)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _candidate_keys(
    mode: SimilarityMode,
    descriptor_version: str | None,
    model: str | None,
) -> tuple[str, ...]:
    keys: list[str] = []
    if descriptor_version and model:
        keys.append(f"{mode}:{descriptor_version}:{model}")
    if descriptor_version:
        keys.append(f"{mode}:{descriptor_version}")
    if model:
        keys.append(f"{mode}::{model}")
    keys.append(mode)
    return tuple(keys)


def resolve_threshold(
    kind: ThresholdKind,
    mode: SimilarityMode,
    descriptor_version: str | None = None,
    model: str | None = None,
    *,
    config_path: Path | str | None = None,
) -> float:
    """Resolve a calibrated threshold for `(kind, mode, descriptor_version, model)`."""
    defaults = _DEFAULTS_BY_KIND[kind]
    if mode not in defaults:
        raise ValueError(f"unsupported_similarity_mode:{mode}")
    data = _load_calibration_data(config_path)
    section = data.get(kind)
    if mode == "semantic" and model and model.startswith("embeddinggemma2:"):
        exact_key = f"{mode}:{descriptor_version}:{model}" if descriptor_version else None
        candidate = section.get(exact_key) if exact_key and isinstance(section, Mapping) else None
        if _is_valid_threshold(candidate):
            return float(candidate)
        raise ValueError("semantic_threshold_uncalibrated")
    if isinstance(section, Mapping):
        for key in _candidate_keys(mode, descriptor_version, model):
            candidate = section.get(key)
            if _is_valid_threshold(candidate):
                return float(candidate)
    return defaults[mode]


def resolve_similarity_threshold(
    mode: SimilarityMode,
    descriptor_version: str | None = None,
    model: str | None = None,
    *,
    config_path: Path | str | None = None,
) -> float:
    """Resolve the calibrated similarity search threshold for the given space."""
    return resolve_threshold("similarity", mode, descriptor_version, model, config_path=config_path)


def resolve_group_threshold(
    mode: SimilarityMode,
    descriptor_version: str | None = None,
    model: str | None = None,
    *,
    config_path: Path | str | None = None,
) -> float:
    """Resolve the calibrated library grouping threshold for the given space."""
    return resolve_threshold("group", mode, descriptor_version, model, config_path=config_path)


def resolve_near_duplicate_threshold(
    mode: SimilarityMode,
    descriptor_version: str | None = None,
    model: str | None = None,
    *,
    config_path: Path | str | None = None,
) -> float:
    """Resolve the calibrated near-duplicate threshold for the given space."""
    return resolve_threshold("near_duplicate", mode, descriptor_version, model, config_path=config_path)


def _match_score(match: Any) -> float:
    if isinstance(match, Mapping):
        return float(match["score"])
    return float(match.score)


def evaluate_similarity_abstention(
    matches: Sequence[Any],
    threshold: float,
) -> AbstentionResult:
    """Filter matches by `threshold` and abstain when no precedent meets it."""
    if not _is_valid_threshold(threshold):
        raise ValueError("invalid_similarity_threshold")
    resolved_threshold = float(threshold)
    filtered = tuple(match for match in matches if _match_score(match) >= resolved_threshold)
    abstained = len(filtered) == 0
    return AbstentionResult(
        abstained=abstained,
        abstention_reason=ABSTENTION_REASON_NO_PRECEDENTS if abstained else None,
        threshold_used=resolved_threshold,
        filtered_matches=filtered,
    )
