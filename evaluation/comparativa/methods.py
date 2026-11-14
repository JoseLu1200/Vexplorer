"""Methods under comparison.

A runs the repository's deterministic geometry path offline.  B, C and D are
model-backed: they only run behind an explicit flag and through an injectable
adapter, so tests and offline sessions use doubles and make no paid call.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .model import (
    MODEL_VARIANTS,
    ComparisonError,
    Component,
    MethodResult,
    ModelVariantsDisabled,
    PublicCase,
    RunLimits,
)

REPO = Path(__file__).resolve().parents[2]
# Only these precedent fields reach an adapter; ids used for exclusion stay harness-side.
PRECEDENT_PUBLIC_FIELDS = ("entry_id", "summary", "dimensions_mm", "components", "materials", "cost_eur", "hours")
# Only these adapter.describe() keys are written to freeze.json and outputs.
DESCRIBE_FIELDS = ("name", "provider", "model", "version", "prompt_sha256", "extractor", "parameters", "seed_supported")
RULES_VERSION = "geometry-rules-1"


class Method(Protocol):
    variant: str
    stochastic: bool

    def describe(self) -> dict[str, Any]: ...

    def run(self, case: PublicCase, *, repetition: int, limits: RunLimits, context: dict[str, Any]) -> MethodResult: ...


# --------------------------------------------------------------------------- #
# A: deterministic rules (the app's geometry_only path)
# --------------------------------------------------------------------------- #

def _file_sha(relative: str) -> str:
    path = REPO / relative
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


class RulesMethod:
    """Variant A: deterministic rules, offline.

    * A1 ``separated_part_views``: ``extract_drawing`` + ``extract_separated_parts``
      (the geometry the app uses for separated part sheets).
    * A2 ``assembled_orthographic``: ``extract_drawing(input_kind="general_furniture")``
      + ``derive_rectangular_hypotheses`` grouped by size.  A2 is an additional
      rule of this harness: the app's ``geometry_only`` run for general furniture
      stops at extraction and does not call ``derive_rectangular_hypotheses``.
      Hypotheses are projections, so quantity and thickness stay unknown.
    """

    variant = "A"
    stochastic = False

    def describe(self) -> dict[str, Any]:
        return {
            "variant": "A",
            "kind": "deterministic_rules",
            "rules_version": RULES_VERSION,
            "code_paths": {
                "assembled_orthographic": [
                    "backend.app.geometria.extraction.extract_drawing",
                    "backend.app.geometria.extraction.derive_rectangular_hypotheses",
                ],
                "separated_part_views": [
                    "backend.app.geometria.extraction.extract_drawing",
                    "backend.app.geometria.parts.extract_separated_parts",
                ],
            },
            "extractor_sha256": {
                "backend/app/geometria/extraction.py": _file_sha("backend/app/geometria/extraction.py"),
                "backend/app/geometria/parts.py": _file_sha("backend/app/geometria/parts.py"),
            },
            "harness_rules": {
                "A1": "separated part sheets: repository extraction, no harness rule added",
                "A2": (
                    "assembled views: rectangle hypotheses grouped by size is a harness rule, "
                    "not used by the app's geometry_only run for general furniture"
                ),
            },
            "model": None,
            "prompt": None,
        }

    def run(self, case: PublicCase, *, repetition: int, limits: RunLimits, context: dict[str, Any]) -> MethodResult:
        if case.format != "dxf":
            return MethodResult(status="not_applicable", reason=f"unsupported_format:{case.format}")
        if case.view_kind == "separated_part_views":
            return MethodResult(
                components=self._separated_parts(case), versions={"rule_path": "A1:separated_parts"}
            )
        if case.view_kind == "assembled_orthographic":
            return MethodResult(
                components=self._rectangle_hypotheses(case), versions={"rule_path": "A2:rectangle_hypotheses"}
            )
        return MethodResult(status="not_applicable", reason=f"unsupported_view_kind:{case.view_kind}")

    @staticmethod
    def _separated_parts(case: PublicCase) -> list[Component]:
        from backend.app.geometria.extraction import extract_drawing
        from backend.app.geometria.parts import extract_separated_parts

        extraction = extract_drawing(case.path, input_kind="separated_part_views")
        parts = extract_separated_parts(extraction)
        components = []
        for observation in parts.observations:
            dims: dict[str, float | None] = {}
            states: dict[str, str] = {}
            for name in ("length", "width", "thickness"):
                item = getattr(observation.dimensions, name)
                if item.state == "observed" and item.value_mm is not None:
                    dims[name], states[name] = float(item.value_mm), "observed"
                else:
                    dims[name], states[name] = None, "unknown"
            quantity = observation.quantity
            observed_quantity = quantity.state == "observed" and quantity.value is not None
            components.append(Component(
                key=observation.part_key or observation.id,
                dimensions_mm=dims,
                dimension_states=states,
                quantity=int(quantity.value) if observed_quantity else None,
                quantity_state="observed" if observed_quantity else "unknown",
                source_ids=tuple(observation.source_entity_ids),
            ))
        return components

    @staticmethod
    def _rectangle_hypotheses(case: PublicCase) -> list[Component]:
        from backend.app.geometria.extraction import (
            derive_rectangular_hypotheses,
            extract_drawing,
        )

        extraction = extract_drawing(case.path, input_kind="general_furniture")
        groups: dict[tuple[float, float], list[str]] = {}
        for hypothesis in derive_rectangular_hypotheses(extraction):
            sizes = tuple(sorted((round(v, 3) for v in hypothesis.observed_dimensions_mm), reverse=True))
            groups.setdefault(sizes, []).extend(hypothesis.contour_ids)
        components = []
        for index, (sizes, contour_ids) in enumerate(sorted(groups.items(), reverse=True), 1):
            components.append(Component(
                key=f"H{index}",
                dimensions_mm={"length": sizes[0], "width": sizes[1], "thickness": None},
                dimension_states={"length": "observed", "width": "observed", "thickness": "unknown"},
                quantity=None,
                quantity_state="unknown",
                source_ids=tuple(sorted(contour_ids)),
            ))
        return components


# --------------------------------------------------------------------------- #
# B / C / D: model-backed, injectable adapter
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AdapterRequest:
    """Everything an adapter receives.  Built only from the public case."""

    variant: str
    case: PublicCase
    repetition: int
    limits: RunLimits
    tools_enabled: bool
    precedents: tuple[dict[str, Any], ...] = ()


@dataclass
class AdapterResponse:
    components: list[Any]
    usage: dict[str, Any] = field(default_factory=dict)  # model_calls, tool_calls, tokens, cost_eur (only if observed)
    versions: dict[str, Any] = field(default_factory=dict)  # model, prompt_sha256, parameters, seed_supported
    input_artifact_hashes: dict[str, str] = field(default_factory=dict)
    trace_sha256: str | None = None
    notes: list[str] = field(default_factory=list)


Adapter = Callable[[AdapterRequest], AdapterResponse]


@dataclass(frozen=True)
class PrecedentIndex:
    """A historical index admitted for D.  Entries carry ``partition_id`` for exclusion."""

    index_id: str
    admitted: bool
    annotated: bool
    sha256: str
    entries: tuple[dict[str, Any], ...]
    admission_note: str = ""

    def __post_init__(self) -> None:
        # Fail closed: an entry that cannot be excluded cannot be offered.
        for position, entry in enumerate(self.entries):
            for key in ("entry_id", "case_id", "partition_id"):
                value = entry.get(key) if isinstance(entry, dict) else None
                if not isinstance(value, str) or not value.strip():
                    raise ComparisonError(f"precedent entry {position} needs a non-empty {key}")

    @classmethod
    def from_file(cls, path: Path) -> PrecedentIndex:
        raw = Path(path).read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ComparisonError(f"unreadable precedent index: {exc}") from exc
        entries = data.get("entries")
        if not isinstance(data, dict) or not isinstance(entries, list) or not isinstance(data.get("index_id"), str):
            raise ComparisonError("precedent index needs index_id and entries")
        return cls(
            index_id=data["index_id"],
            admitted=data.get("admitted") is True,
            annotated=data.get("annotated") is True,
            sha256=hashlib.sha256(raw).hexdigest(),
            entries=tuple(entries),
            admission_note=str(data.get("admission_note", "")),
        )

    def not_admitted_reason(self) -> str | None:
        if not self.admitted:
            return "precedent_index_not_admitted"
        if not self.annotated:
            return "precedent_index_not_annotated"
        return None

    def usable_for(self, case_id: str, partition_id: str) -> tuple[tuple[dict[str, Any], ...], int]:
        """Whitelisted fields of the entries outside the case's id and partition."""

        if not isinstance(partition_id, str) or not partition_id:
            raise ComparisonError("partition_id is required to exclude precedents")
        kept, excluded = [], 0
        for entry in self.entries:
            if entry["case_id"] == case_id or entry["partition_id"] == partition_id:
                excluded += 1
                continue
            kept.append({k: entry[k] for k in PRECEDENT_PUBLIC_FIELDS if k in entry})
        return tuple(kept), excluded


class ModelMethod:
    variant: str
    stochastic = True

    def __init__(
        self,
        variant: str,
        adapter: Adapter | None,
        *,
        enabled: bool,
        precedent_index: PrecedentIndex | None = None,
    ) -> None:
        if variant not in MODEL_VARIANTS:
            raise ComparisonError(f"{variant!r} is not a model-backed variant")
        if not enabled:
            raise ModelVariantsDisabled(
                f"variant {variant} calls a model; pass the explicit enable flag and an adapter"
            )
        if adapter is None:
            raise ModelVariantsDisabled(f"variant {variant} needs an injected adapter")
        self.variant = variant
        self.adapter = adapter
        self.precedent_index = precedent_index

    def describe(self) -> dict[str, Any]:
        described = getattr(self.adapter, "describe", None)
        info: dict[str, Any] = {
            "variant": self.variant,
            "kind": {"B": "direct_visual_model", "C": "model_with_tools", "D": "model_with_tools_and_precedents"}[self.variant],
            "tools_enabled": self.variant in {"C", "D"},
            "adapter": (
                {k: v for k, v in described().items() if k in DESCRIBE_FIELDS}
                if callable(described)
                else {"name": getattr(self.adapter, "__name__", type(self.adapter).__name__)}
            ),
        }
        if self.variant == "D":
            index = self.precedent_index
            info["precedent_index"] = None if index is None else {
                "index_id": index.index_id, "admitted": index.admitted,
                "annotated": index.annotated, "sha256": index.sha256, "entries": len(index.entries),
            }
        return info

    def run(self, case: PublicCase, *, repetition: int, limits: RunLimits, context: dict[str, Any]) -> MethodResult:
        precedents: tuple[dict[str, Any], ...] = ()
        notes: list[str] = []
        if self.variant == "D":
            index = self.precedent_index
            if index is None:
                return MethodResult(status="not_evaluated", reason="precedent_index_not_provided")
            reason = index.not_admitted_reason()
            if reason is not None:
                return MethodResult(status="not_evaluated", reason=reason)
            precedents, excluded = index.usable_for(case.case_id, context.get("partition_id"))
            notes.append(f"precedents_excluded_same_case_or_partition={excluded}")
            if not precedents:
                return MethodResult(status="not_evaluated", reason="precedent_index_empty_after_exclusions", notes=notes)
        request = AdapterRequest(
            variant=self.variant, case=case, repetition=repetition, limits=limits,
            tools_enabled=self.variant in {"C", "D"}, precedents=precedents,
        )
        response = self.adapter(request)
        if not isinstance(response, AdapterResponse):
            raise ComparisonError("adapter must return an AdapterResponse")
        return MethodResult(
            components=list(response.components),
            usage=dict(response.usage),
            versions=dict(response.versions),
            input_artifact_hashes=dict(response.input_artifact_hashes),
            trace_sha256=response.trace_sha256,
            notes=[*notes, *response.notes],
        )


def build_methods(
    variants: tuple[str, ...],
    *,
    enable_model_variants: bool = False,
    adapter: Adapter | None = None,
    precedent_index: PrecedentIndex | None = None,
) -> list[Method]:
    """Build the requested methods; B/C/D refuse to exist without the flag."""

    methods: list[Method] = []
    for variant in variants:
        if variant == "A":
            methods.append(RulesMethod())
        elif variant in MODEL_VARIANTS:
            methods.append(ModelMethod(variant, adapter, enabled=enable_model_variants, precedent_index=precedent_index))
        else:
            raise ComparisonError(f"unknown variant {variant!r}")
    return methods
