"""Phase 1 (run and freeze) and phase 2 (score) of the comparison.

``execute_run`` never opens the private reference: it only calls
``reader.public_cases()`` / ``reader.case_meta()``.  ``score_run`` is the only
place that asks for the reference, and it does so with a verified freeze token.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from .freeze import (
    OUTPUT_SCHEMA,
    freeze_run,
    load_freeze_record,
    load_outputs,
    verify_freeze,
    write_output,
)
from .manifest import ManifestReader
from .methods import Method
from .model import ComparisonError, MethodResult, RunLimits, parse_component
from .report import build_report
from .scoring import score_outputs


@dataclass(frozen=True)
class Clock:
    perf: Callable[[], float] = time.perf_counter
    now_iso: Callable[[], str] = field(default=lambda: datetime.now(UTC).isoformat())


def _safe_error(exc: Exception) -> dict[str, str]:
    return {
        "failure_type": type(exc).__name__,
        "message": str(exc).replace("\r", " ").replace("\n", " ")[:300],
    }


def execute_run(
    reader: ManifestReader,
    methods: list[Method],
    run_dir: Path,
    *,
    limits: RunLimits | None = None,
    clock: Clock | None = None,
    requested_variants: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run every method on every public case, write the outputs and freeze them."""

    limits = limits or RunLimits()
    clock = clock or Clock()
    run_dir = Path(run_dir)
    if (run_dir / "freeze.json").exists():
        raise ComparisonError("run directory is already frozen")
    run_dir.mkdir(parents=True, exist_ok=True)
    cases = reader.public_cases()
    meta = reader.case_meta()
    entries: list[dict[str, Any]] = []
    for method in methods:
        method_info = method.describe()
        repetitions = limits.repetitions_stochastic if method.stochastic else 1
        for case in cases:
            for repetition in range(1, repetitions + 1):
                started = clock.perf()
                error: dict[str, str] | None = None
                try:
                    result = method.run(case, repetition=repetition, limits=limits, context={"meta": meta.get(case.case_id)})
                except Exception as exc:  # noqa: BLE001 - recorded, never imputed as a zero score
                    result = MethodResult(status="failed", reason="method_raised")
                    error = _safe_error(exc)
                duration = clock.perf() - started
                status, reason = result.status, result.reason
                components: list[dict[str, Any]] = []
                if status == "ok" and duration > limits.timeout_s:
                    status, reason = "failed", "timeout_exceeded"
                elif status == "ok":
                    try:
                        components = [parse_component(item, f"{case.case_id}.components[{i}]").to_json()
                                      for i, item in enumerate(result.components)]
                        keys = [item["key"] for item in components]
                        if len(keys) != len(set(keys)):
                            raise ComparisonError("duplicate component keys")
                    except ComparisonError as exc:
                        status, reason, components, error = "failed", "invalid_output", [], _safe_error(exc)
                output = {
                    "schema": OUTPUT_SCHEMA,
                    "case_id": case.case_id,
                    "variant": method.variant,
                    "repetition": repetition,
                    "status": status,
                    "reason": reason,
                    "components": components,
                    "input_sha256": case.sha256,
                    "versions": {"method": method_info, "run": result.versions},
                    "limits": limits.to_json(),
                    "timing": {"duration_s": round(duration, 6)},
                    "usage": result.usage,
                    "input_artifact_hashes": result.input_artifact_hashes,
                    "trace_sha256": result.trace_sha256,
                    "notes": result.notes,
                    "error": error,
                }
                relative, digest = write_output(run_dir, output)
                entries.append({
                    "variant": method.variant, "case_id": case.case_id,
                    "repetition": repetition, "path": relative, "sha256": digest,
                })
    run_variants = sorted({method.variant for method in methods})
    metadata = {
        "corpus": reader.corpus_info(),
        "inputs": {case.case_id: case.sha256 for case in cases},
        "methods": {method.variant: method.describe() for method in methods},
        "variants_requested": list(requested_variants or run_variants),
        "limits": limits.to_json(),
    }
    return freeze_run(run_dir, entries=entries, metadata=metadata, frozen_at=clock.now_iso())


def score_run(
    reader: ManifestReader,
    run_dir: Path,
    *,
    tolerance_mm: float = 1.0,
    match_tolerance_mm: float = 5.0,
) -> dict[str, Any]:
    """Verify the freeze, open the private reference, and build the report."""

    run_dir = Path(run_dir)
    token = verify_freeze(run_dir)
    record = load_freeze_record(run_dir)
    # Public-side cross-checks against the seal, before any private read.
    if {case.case_id: case.sha256 for case in reader.public_cases()} != record.get("inputs"):
        raise ComparisonError("public inputs differ from the frozen run (changed, added or missing case)")
    if json.loads(json.dumps(reader.corpus_info())) != record.get("corpus"):
        raise ComparisonError("corpus description differs from the frozen run")
    outputs = load_outputs(run_dir, token)
    references = reader.load_references(token)
    scores = score_outputs(
        outputs, reader.case_meta(), references,
        tolerance_mm=tolerance_mm, match_tolerance_mm=match_tolerance_mm,
    )
    return build_report(
        scores,
        freeze=record,
        settings={"tolerance_mm": tolerance_mm, "match_tolerance_mm": match_tolerance_mm},
    )
