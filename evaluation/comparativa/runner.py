"""Phase 1 (run and freeze) and phase 2 (score) of the comparison.

``execute_run`` never opens the private reference: it only calls
``reader.public_cases()`` / ``reader.case_meta()``.  ``score_run`` is the only
place that asks for the reference, and it does so with a verified freeze token.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
from .model import OUTPUT_STATUSES, ComparisonError, MethodResult, PublicCase, RunLimits, parse_component
from .report import build_report
from .scoring import score_outputs


@dataclass(frozen=True)
class Clock:
    perf: Callable[[], float] = time.perf_counter
    now_iso: Callable[[], str] = field(default=lambda: datetime.now(UTC).isoformat())


_PATH_RE = re.compile(r"\\\\[^\s'\"]+|[A-Za-z]:[\\/][^\s'\"]*|(?<![\w<])/(?:[\w.\-]+/)+[\w.\-]*")


def _safe_error(exc: Exception) -> dict[str, str]:
    message = _PATH_RE.sub("<path>", str(exc)).replace("\r", " ").replace("\n", " ")
    return {"failure_type": type(exc).__name__, "message": message[:300]}


def _count(usage: dict[str, Any], name: str) -> int:
    value = usage.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class _InputMutation(ComparisonError):
    """A method changed or removed the private copy of its public input."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_isolated(
    method: Method,
    case: PublicCase,
    *,
    repetition: int,
    limits: RunLimits,
    context: dict[str, Any],
) -> MethodResult:
    source = case.path.read_bytes()
    if hashlib.sha256(source).hexdigest() != case.sha256:
        raise _InputMutation("public input hash differs before method execution")
    with tempfile.TemporaryDirectory(prefix=".comparativa-input-", dir=case.path.parent) as directory:
        isolated_path = Path(directory) / case.path.name
        isolated_path.write_bytes(source)
        isolated = PublicCase(
            case.case_id,
            isolated_path,
            case.sha256,
            case.format,
            case.unit,
            case.view_kind,
            case.instruction,
        )
        try:
            result = method.run(isolated, repetition=repetition, limits=limits, context=context)
        finally:
            try:
                isolated_hash = _sha256_file(isolated_path)
                source_hash = _sha256_file(case.path)
            except OSError as exc:
                raise _InputMutation("method input was removed or became unreadable") from exc
            if isolated_hash != case.sha256:
                raise _InputMutation("method mutated its isolated input")
            if source_hash != case.sha256:
                raise _InputMutation("public input changed during method execution")
        return result


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
                    result = _run_isolated(
                        method,
                        case,
                        repetition=repetition,
                        limits=limits,
                        context={"partition_id": meta[case.case_id].partition_id},
                    )
                except _InputMutation as exc:
                    result = MethodResult(status="failed", reason="input_mutated")
                    error = _safe_error(exc)
                except Exception as exc:  # noqa: BLE001 - recorded, never imputed as a zero score
                    result = MethodResult(status="failed", reason="method_raised")
                    error = _safe_error(exc)
                duration = clock.perf() - started
                status, reason = result.status, result.reason
                components: list[dict[str, Any]] = []
                usage = result.usage or {}
                if status not in OUTPUT_STATUSES:
                    status, reason, error = "failed", "invalid_status", _safe_error(ComparisonError(f"invalid result status: {status!r}"))
                elif status == "ok" and duration > limits.timeout_s:
                    # The timeout is not preventive: it is checked after the method returned.
                    status, reason = "failed", "timeout_exceeded"
                elif status == "ok" and (
                    _count(usage, "model_calls") > limits.max_model_calls
                    or _count(usage, "tool_calls") > limits.max_tool_calls
                ):
                    status, reason = "failed", "limit_exceeded"
                elif status == "ok" and len(result.components) > 500:
                    status, reason, error = "failed", "limit_exceeded", _safe_error(ComparisonError("component limit exceeded (> 500)"))
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
