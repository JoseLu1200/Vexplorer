"""Shared value types of the A/B/C/D comparison harness.

These types belong to the evaluation harness only.  They are NOT the product
contract in ``backend/app/contratos`` and must not be imported by the runtime.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DIMENSION_FIELDS = ("length", "width", "thickness")
FIELD_STATES = ("observed", "derived", "hypothesis", "unknown")
PUBLIC_PAYLOAD_KEYS = ("id", "file", "format", "unit", "view_kind", "instruction", "sha256")
OUTPUT_STATUSES = ("ok", "not_evaluated", "not_applicable", "failed")
VARIANTS = ("A", "B", "C", "D")
MODEL_VARIANTS = ("B", "C", "D")

PUBLIC_INSTRUCTION = (
    "Use only geometry visible in the assembled orthographic views. "
    "Keep unsupported identity, dimensions, roles and quantities unknown."
)


class ComparisonError(ValueError):
    """Malformed harness input (manifest, output, freeze record)."""


class ReferenceNotFrozen(ComparisonError):
    """The private reference was requested before every output was frozen."""


class ModelVariantsDisabled(ComparisonError):
    """A model-backed variant (B/C/D) was requested without the explicit flag."""


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True)
class PublicCase:
    """Everything a method may see about a case (plus the staged input file)."""

    case_id: str
    path: Path
    sha256: str
    format: str
    unit: str
    view_kind: str
    instruction: str

    @property
    def payload(self) -> dict[str, str]:
        """The method-visible metadata: exactly ``PUBLIC_PAYLOAD_KEYS``."""
        return {
            "id": self.case_id,
            "file": self.path.name,
            "format": self.format,
            "unit": self.unit,
            "view_kind": self.view_kind,
            "instruction": self.instruction,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class CaseMeta:
    """Harness-only grouping data.  Never forwarded to a method."""

    case_id: str
    family: str
    split: str
    partition_id: str
    development: bool


@dataclass(frozen=True)
class Component:
    key: str
    dimensions_mm: dict[str, float | None]
    dimension_states: dict[str, str]
    quantity: int | None
    quantity_state: str
    source_ids: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "dimensions_mm": {name: self.dimensions_mm[name] for name in DIMENSION_FIELDS},
            "dimension_states": {name: self.dimension_states[name] for name in DIMENSION_FIELDS},
            "quantity": self.quantity,
            "quantity_state": self.quantity_state,
            "source_ids": list(self.source_ids),
        }


def parse_component(raw: Any, label: str = "component") -> Component:
    """Validate a component produced by a method (or read back from a frozen output)."""

    if isinstance(raw, Component):
        raw = raw.to_json()
    if not isinstance(raw, dict):
        raise ComparisonError(f"{label} must be an object")
    key = raw.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ComparisonError(f"{label}.key must be a non-empty string")
    dims_raw = raw.get("dimensions_mm")
    if not isinstance(dims_raw, dict):
        raise ComparisonError(f"{label}.dimensions_mm must be an object")
    states_raw = raw.get("dimension_states") or {}
    if not isinstance(states_raw, dict):
        raise ComparisonError(f"{label}.dimension_states must be an object")
    dims: dict[str, float | None] = {}
    states: dict[str, str] = {}
    for name in DIMENSION_FIELDS:
        value = dims_raw.get(name)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ComparisonError(f"{label}.dimensions_mm.{name} must be a number or null")
            if not math.isfinite(value) or value <= 0:
                raise ComparisonError(f"{label}.dimensions_mm.{name} must be positive and finite")
            value = float(value)
        state = states_raw.get(name, "hypothesis" if value is not None else "unknown")
        if state not in FIELD_STATES:
            raise ComparisonError(f"{label}.dimension_states.{name} is invalid")
        if (value is None) != (state == "unknown"):
            raise ComparisonError(f"{label}.{name}: value and state 'unknown' must agree")
        dims[name] = value
        states[name] = state
    quantity = raw.get("quantity")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1):
        raise ComparisonError(f"{label}.quantity must be a positive integer or null")
    quantity_state = raw.get("quantity_state", "hypothesis" if quantity is not None else "unknown")
    if quantity_state not in FIELD_STATES or (quantity is None) != (quantity_state == "unknown"):
        raise ComparisonError(f"{label}.quantity_state is invalid or disagrees with quantity")
    source_ids = raw.get("source_ids") or []
    if not isinstance(source_ids, (list, tuple)) or not all(isinstance(item, str) for item in source_ids):
        raise ComparisonError(f"{label}.source_ids must be a list of strings")
    return Component(key.strip(), dims, states, quantity, quantity_state, tuple(source_ids))


@dataclass(frozen=True)
class RefField:
    """A reference value plus whether the public input can identify it.

    ``identifiable`` is True (resolvable), False (must be left unknown) or None
    (not annotated: excluded from coverage and abstention denominators).
    """

    value: float | None
    identifiable: bool | None


@dataclass(frozen=True)
class RefComponent:
    key: str
    dimensions: dict[str, RefField]
    quantity: RefField


@dataclass(frozen=True)
class ReferenceCase:
    case_id: str
    components: tuple[RefComponent, ...]


@dataclass(frozen=True)
class RunLimits:
    """Limits recorded with every output.  They are caps, not measurements."""

    max_model_calls: int = 15
    max_tool_calls: int = 30
    timeout_s: float = 120.0
    repetitions_stochastic: int = 3
    source: str = "backend/app/main.py capabilities limits; PLAN.md budgets"

    def to_json(self) -> dict[str, Any]:
        return {
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "timeout_s": self.timeout_s,
            "repetitions_stochastic": self.repetitions_stochastic,
            "source": self.source,
        }


@dataclass
class MethodResult:
    """What a method returns for one case/repetition (before harness wrapping)."""

    status: str = "ok"
    reason: str | None = None
    components: list[Any] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    versions: dict[str, Any] = field(default_factory=dict)
    input_artifact_hashes: dict[str, str] = field(default_factory=dict)
    trace_sha256: str | None = None
    notes: list[str] = field(default_factory=list)
