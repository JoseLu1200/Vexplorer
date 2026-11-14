"""Run paired public-only general-furniture inference and freeze evidence locally.

This runner never reads evaluator references and never scores predictions.  It
freezes the first pass before invoking the automatic critic so a critic failure
cannot erase the baseline.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import time
from typing import Any, Callable
import zipfile

from dotenv import load_dotenv

from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.agente.runner import AgentLimits
from backend.app.geometria.extraction import extract_drawing
from backend.app.general_furniture.autonomous import (
    AutoReviewLimits,
    GENERAL_AUTO_REVIEW_PROMPT,
    GeneralAutonomousError,
    run_general_autonomous,
)
from backend.app.general_furniture.live import (
    GENERAL_FURNITURE_SYSTEM_PROMPT,
    GeneralLiveError,
    GeneralVisualPage,
    run_general_furniture_agent,
)
from backend.app.general_furniture.router import GeneralFurnitureContext
from backend.app.general_furniture.visual_evidence import render_visual_evidence


REPO = Path(__file__).resolve().parents[1]
MAX_DXF_BYTES = 20 * 1024 * 1024
MAX_CASE_JSON_BYTES = 64 * 1024
MAX_COMPRESSION_RATIO = 200
PUBLIC_INSTRUCTION = (
    "Use only geometry visible in the assembled orthographic views. "
    "Keep unsupported identity, dimensions, roles and quantities unknown."
)
CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
DATASET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
PUBLIC_METADATA_KEYS = {
    "id", "file", "format", "unit", "view_kind", "instruction", "sha256"
}


def _utc() -> str:
    return datetime.now(UTC).isoformat()


def _serial(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return {field.name: _serial(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, bytes):
        return {"sha256": sha256(value).hexdigest(), "bytes": len(value)}
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serial(item) for item in value]
    return value


def _write_new(path: Path, value: Any) -> str:
    encoded = (json.dumps(_serial(value), ensure_ascii=False, indent=2) + "\n").encode()
    with path.open("xb") as target:
        target.write(encoded)
    return sha256(encoded).hexdigest()


def _safe_error(exc: Exception) -> dict[str, str]:
    message = str(exc).replace("\r", " ").replace("\n", " ")[:400]
    return {"failure_type": type(exc).__name__, "message": message}


def tracked_code_fingerprints() -> dict[str, str]:
    paths = [
        *sorted((REPO / "backend" / "app").rglob("*.py")),
        Path(__file__).resolve(),
        REPO / "pyproject.toml",
        REPO / "requirements-demo.txt",
    ]
    return {
        path.relative_to(REPO).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def _action_evidence(exc: Exception) -> dict[str, Any]:
    if not isinstance(exc, (GeneralAutonomousError, GeneralLiveError)):
        return {}
    return {
        "action_evidence": {
            "trace": _serial(exc.trace),
            "model_calls": exc.model_calls,
            "tool_calls": exc.tool_calls,
        }
    }


def freeze_paired_outcome(
    *,
    case_id: str,
    case_dir: Path,
    metadata: dict[str, Any],
    first_pass: Callable[[], Any],
    critic: Callable[[Any], Any],
) -> dict[str, Any]:
    """Freeze P1 before P2 and preserve P1 when P2 fails."""

    started = time.monotonic()
    try:
        baseline = first_pass()
    except Exception as exc:
        failure = {
            "case_id": case_id,
            "status": "failed_before_baseline",
            **metadata,
            **_safe_error(exc),
            **_action_evidence(exc),
            "duration_s": round(time.monotonic() - started, 3),
        }
        _write_new(case_dir / "failure.json", failure)
        return failure

    baseline_sha = _write_new(
        case_dir / "baseline.json",
        {"case_id": case_id, **metadata, "frozen_at": _utc(), "outcome": baseline},
    )
    try:
        final = critic(baseline)
    except Exception as exc:
        failure = {
            "case_id": case_id,
            "status": "failed_after_baseline",
            **metadata,
            "baseline_sha256": baseline_sha,
            **_safe_error(exc),
            **_action_evidence(exc),
            "duration_s": round(time.monotonic() - started, 3),
        }
        _write_new(case_dir / "failure.json", failure)
        return failure

    final_sha = _write_new(
        case_dir / "final.json",
        {
            "case_id": case_id,
            **metadata,
            "frozen_at": _utc(),
            "baseline_sha256": baseline_sha,
            "duration_s": round(time.monotonic() - started, 3),
            "outcome": final,
        },
    )
    return {
        "case_id": case_id,
        "status": "succeeded",
        "baseline_sha256": baseline_sha,
        "final_sha256": final_sha,
        "duration_s": round(time.monotonic() - started, 3),
    }


def _validate_info(info: zipfile.ZipInfo, *, maximum: int) -> None:
    if info.is_dir() or info.flag_bits & 0x1:
        raise ValueError("unsafe_public_bundle_member")
    if info.file_size < 0 or info.file_size > maximum or info.compress_size > maximum:
        raise ValueError("public_bundle_member_too_large")
    if info.file_size and info.compress_size == 0:
        raise ValueError("unsafe_public_bundle_compression")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise ValueError("unsafe_public_bundle_compression")


def _read_valid_bundle(bundle: Path) -> tuple[str, bytes]:
    if not CASE_ID_RE.fullmatch(bundle.stem):
        raise ValueError("invalid_public_case_id")
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or set(names) != {"input.dxf", "case.json"}:
            raise ValueError("unexpected_public_bundle_members")
        by_name = {info.filename: info for info in infos}
        _validate_info(by_name["input.dxf"], maximum=MAX_DXF_BYTES)
        _validate_info(by_name["case.json"], maximum=MAX_CASE_JSON_BYTES)
        try:
            metadata = json.loads(archive.read("case.json").decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_public_bundle_metadata") from exc
        if not isinstance(metadata, dict) or set(metadata) != PUBLIC_METADATA_KEYS:
            raise ValueError("unexpected_public_bundle_metadata")
        case_id = metadata.get("id")
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            raise ValueError("invalid_public_case_id")
        if case_id != bundle.stem:
            raise ValueError("public_input_id_mismatch")
        expected = ("input.dxf", "dxf", "mm", "assembled_orthographic")
        if tuple(metadata.get(key) for key in ("file", "format", "unit", "view_kind")) != expected:
            raise ValueError("unexpected_public_bundle_format")
        if metadata.get("instruction") != PUBLIC_INSTRUCTION:
            raise ValueError("unexpected_public_bundle_instruction")
        digest = metadata.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("invalid_public_input_hash")
        raw = archive.read("input.dxf")
        if len(raw) != by_name["input.dxf"].file_size or sha256(raw).hexdigest() != digest:
            raise ValueError("public_input_hash_mismatch")
        return case_id, raw


def load_public_sources(
    input_path: Path, staging_dir: Path, *, strict_bundles: bool
) -> list[Path]:
    """Validate every bundle before creating a staging directory."""

    input_path = input_path.resolve()
    if "private" in str(input_path).lower():
        raise ValueError("only_public_inputs_are_allowed")
    bundles = sorted(input_path.glob("*.zip")) if input_path.is_dir() else []
    if strict_bundles and not bundles:
        raise ValueError("strict_mode_requires_public_bundles")
    if bundles:
        validated = [_read_valid_bundle(bundle) for bundle in bundles]
        staging_dir.mkdir(parents=True, exist_ok=False)
        sources: list[Path] = []
        for case_id, raw in validated:
            target = staging_dir / f"{case_id}.dxf"
            target.write_bytes(raw)
            sources.append(target)
        return sources

    sources = sorted(input_path.glob("*.dxf")) if input_path.is_dir() else [input_path]
    result = []
    for source in sources:
        if source.suffix.lower() != ".dxf" or not source.is_file():
            continue
        if not CASE_ID_RE.fullmatch(source.stem) or source.stat().st_size > MAX_DXF_BYTES:
            raise ValueError("invalid_public_dxf")
        result.append(source)
    if not result:
        raise ValueError("no_public_dxf_cases")
    return result


def _prediction_component(
    component: dict[str, Any],
    *,
    review_outcomes: dict[str, str],
    require_acceptance: bool,
) -> dict[str, Any]:
    component_id = component["id"]
    quantity = component["quantity"]
    fields = ("length", "width", "thickness")

    def accepted(field: str) -> bool:
        return not require_acceptance or review_outcomes.get(
            f"component:{component_id}.{field}"
        ) == "accepted"

    def review_status(field: str) -> str:
        target = f"component:{component_id}.{field}"
        return "auto_reviewed" if target in review_outcomes else "unreviewed"

    return {
        "key": component_id,
        "quantity": quantity.get("value") if accepted("quantity") else None,
        "quantity_state": quantity["state"] if accepted("quantity") else "unknown",
        "quantity_review_status": review_status("quantity"),
        "dimensions_mm": {
            field: component[field].get("value_mm") if accepted(field) else None
            for field in fields
        },
        "dimension_states": {
            field: component[field]["state"] if accepted(field) else "unknown"
            for field in fields
        },
        "dimension_review_statuses": {
            field: review_status(field) for field in fields
        },
    }


def _empty_prediction_case(case_id: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "components": [],
        "retrieved_item_ids": None,
        "cost": None,
        "hours": None,
        "assisted": None,
        "scenarios": [],
    }


def _prediction_case(case_dir: Path, case_id: str, *, phase: str) -> dict[str, Any]:
    path = case_dir / ("baseline.json" if phase == "baseline" else "final.json")
    if not path.is_file():
        return _empty_prediction_case(case_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    outcome = payload["outcome"]
    if phase == "baseline":
        components = outcome["draft"]["components"]
        review_outcomes: dict[str, str] = {}
        proposal_id = outcome["proposal"]["id"]
        scenarios = [
            {"key": proposal_id, "state": "hypothesis", "review_status": "unreviewed"}
        ]
    else:
        review = outcome["review"]
        components = review["components"]
        review_outcomes = {
            item["target_ref"]: item["status"]
            for item in review.get("machine_field_reviews", [])
        }
        snapshots = outcome.get("critic_snapshots", [])
        scenarios = (
            [
                {
                    "key": snapshots[-1]["scenario_id"],
                    "state": "hypothesis",
                    "review_status": "auto_reviewed",
                }
            ]
            if snapshots
            and snapshots[-1].get("status") in {"accepted", "incomplete"}
            and review.get("auto_review_status") in {"accepted", "incomplete"}
            else []
        )
    prediction = _empty_prediction_case(case_id)
    prediction["components"] = [
        _prediction_component(
            component,
            review_outcomes=review_outcomes,
            require_acceptance=phase == "final",
        )
        for component in components
    ]
    prediction["scenarios"] = scenarios
    return prediction


def export_prediction_manifests(
    output: Path, *, dataset_id: str, case_ids: tuple[str, ...]
) -> dict[str, str]:
    """Convert already-frozen native outcomes without consulting references."""

    hashes: dict[str, str] = {}
    for phase in ("baseline", "final"):
        manifest = {
            "schema_version": "1.0",
            "dataset_id": dataset_id,
            "cases": [
                _prediction_case(output / case_id, case_id, phase=phase)
                for case_id in sorted(case_ids)
            ],
        }
        digest = _write_new(output / f"{phase}-predictions.json", manifest)
        hashes[f"{phase}_predictions_sha256"] = digest
    return hashes


class _TracedProvider:
    def __init__(self, delegate: Any, directory: Path, phase: str):
        self.delegate = delegate
        self.directory = directory
        self.phase = phase
        self.calls = 0

    def create_response(self, **kwargs: Any) -> Any:
        self.calls += 1
        started = time.monotonic()
        try:
            response = self.delegate.create_response(**kwargs)
            _write_new(
                self.directory / f"{self.phase}-call-{self.calls}.json",
                {
                    "at": _utc(),
                    "duration_s": round(time.monotonic() - started, 3),
                    "response": response,
                },
            )
            return response
        except Exception as exc:
            _write_new(
                self.directory / f"{self.phase}-call-{self.calls}-error.json",
                {"at": _utc(), "duration_s": round(time.monotonic() - started, 3), **_safe_error(exc)},
            )
            raise


def _run_case(
    source: Path,
    output: Path,
    proposer_settings: ProviderSettings,
    reviewer_settings: ProviderSettings,
    *,
    total_timeout_s: float,
    max_review_calls: int,
    max_validation_repairs: int,
) -> dict[str, Any]:
    case_dir = output / source.stem
    case_dir.mkdir()
    started = time.monotonic()
    extraction = extract_drawing(source, input_kind="general_furniture")
    artifacts = render_visual_evidence(source, extraction=extraction)
    pages = []
    expected = {field.name for field in fields(GeneralVisualPage)}
    visual_metadata = []
    for index, artifact in enumerate(artifacts):
        image_path = case_dir / f"source-{index}.png"
        image_path.write_bytes(artifact.content)
        values = {field.name: getattr(artifact, field.name) for field in fields(artifact)}
        values["sha256"] = artifact.image_sha256
        pages.append(GeneralVisualPage(**{key: value for key, value in values.items() if key in expected}))
        visual_metadata.append(_serial(artifact))
    metadata = {
        "input_sha256": sha256(source.read_bytes()).hexdigest(),
        "visual_artifacts": visual_metadata,
    }
    proposer = _TracedProvider(
        OpenAIResponsesProvider(proposer_settings, instructions=GENERAL_FURNITURE_SYSTEM_PROMPT),
        case_dir,
        "proposer",
    )
    reviewer = _TracedProvider(
        OpenAIResponsesProvider(reviewer_settings, instructions=GENERAL_AUTO_REVIEW_PROMPT),
        case_dir,
        "reviewer",
    )

    def first_pass() -> Any:
        return run_general_furniture_agent(
            extraction,
            ledger_revision="paired-public-only-v1",
            provider=proposer,
            limits=AgentLimits(timeout_s=min(150, total_timeout_s)),
            visual_pages=tuple(pages),
        )

    def critic(baseline: Any) -> Any:
        remaining = total_timeout_s - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("paired_total_timeout")
        context = GeneralFurnitureContext(
            run_id=f"paired-{source.stem}",
            extraction=extraction,
            ledger_revision="paired-public-only-v1",
            visual_pages=tuple(pages),
        )
        return run_general_autonomous(
            context,
            baseline,
            reviewer_provider=reviewer,
            proposer_model=proposer_settings.model,
            limits=AutoReviewLimits(
                max_model_calls=max_review_calls,
                max_tool_calls=max_review_calls,
                max_validation_repairs=max_validation_repairs,
                timeout_s=remaining,
            ),
        )

    return freeze_paired_outcome(
        case_id=source.stem,
        case_dir=case_dir,
        metadata=metadata,
        first_pass=first_pass,
        critic=critic,
    )


def _run_case_safely(
    source: Path,
    output: Path,
    proposer_settings: ProviderSettings,
    reviewer_settings: ProviderSettings,
    *,
    total_timeout_s: float,
    max_review_calls: int,
    max_validation_repairs: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        return _run_case(
            source,
            output,
            proposer_settings,
            reviewer_settings,
            total_timeout_s=total_timeout_s,
            max_review_calls=max_review_calls,
            max_validation_repairs=max_validation_repairs,
        )
    except Exception as exc:
        case_dir = output / source.stem
        case_dir.mkdir(exist_ok=True)
        failure = {
            "case_id": source.stem,
            "status": "failed_before_baseline",
            "input_sha256": sha256(source.read_bytes()).hexdigest(),
            **_safe_error(exc),
            "duration_s": round(time.monotonic() - started, 3),
        }
        if not (case_dir / "failure.json").exists():
            _write_new(case_dir / "failure.json", failure)
        return failure


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--workers", type=int, default=2, choices=(1, 2, 3))
    parser.add_argument("--strict-bundles", action="store_true")
    parser.add_argument("--proposer-model", default="gpt-6.1-sol")
    parser.add_argument("--reviewer-model", default="gpt-6-astra")
    parser.add_argument("--max-output-tokens", type=int, default=16384)
    parser.add_argument("--max-review-calls", type=int, default=5)
    parser.add_argument("--max-validation-repairs", type=int, default=2)
    parser.add_argument("--total-timeout-s", type=float, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if DATASET_ID_RE.fullmatch(args.dataset_id) is None:
        raise SystemExit("invalid dataset id")
    if not 1 <= args.max_review_calls <= 5 or not 0 <= args.max_validation_repairs <= 2:
        raise SystemExit("invalid review budgets")
    if not 256 <= args.max_output_tokens <= 16384 or not 1 <= args.total_timeout_s <= 300:
        raise SystemExit("invalid provider budgets")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("output already exists")
    staging = output / "public-inputs"
    try:
        sources = load_public_sources(args.input, staging, strict_bundles=args.strict_bundles)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise SystemExit(f"public input error: {exc}") from exc
    if args.cases:
        selected = set(args.cases)
        sources = [source for source in sources if source.stem in selected]
        if {source.stem for source in sources} != selected:
            raise SystemExit("missing requested public case")
    if not output.exists():
        output.mkdir(parents=True)

    load_dotenv(REPO / ".env")
    settings = ProviderSettings.from_env()
    proposer = replace(settings, model=args.proposer_model, max_output_tokens=args.max_output_tokens)
    reviewer = replace(settings, model=args.reviewer_model, max_output_tokens=args.max_output_tokens)
    configuration = {
        "started_at": _utc(),
        "dataset_id": args.dataset_id,
        "proposer_model": proposer.model,
        "reviewer_model": reviewer.model,
        "max_output_tokens": args.max_output_tokens,
        "total_timeout_s": args.total_timeout_s,
        "max_review_calls": args.max_review_calls,
        "max_validation_repairs": args.max_validation_repairs,
        "source_sha256": {source.stem: sha256(source.read_bytes()).hexdigest() for source in sources},
        "code_sha256": tracked_code_fingerprints(),
        "private_reference_access": False,
    }
    _write_new(output / "configuration.json", configuration)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(
                _run_case_safely,
                source,
                output,
                proposer,
                reviewer,
                total_timeout_s=args.total_timeout_s,
                max_review_calls=args.max_review_calls,
                max_validation_repairs=args.max_validation_repairs,
            )
            for source in sources
        ]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    prediction_hashes = export_prediction_manifests(
        output,
        dataset_id=args.dataset_id,
        case_ids=tuple(source.stem for source in sources),
    )
    frozen = {
        "frozen_at": _utc(),
        "results": sorted(results, key=lambda item: item["case_id"]),
        "prediction_manifests": prediction_hashes,
        "files": {
            path.relative_to(output).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
        "chronology_note": (
            "Local timestamps and exclusive writes document process order; "
            "they are not tamper-proof proof of chronology."
        ),
    }
    manifest_sha = _write_new(output / "frozen-manifest.json", frozen)
    log_path = REPO / ".runtime" / "transcript-qa" / "paired-freeze-log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"time": _utc(), "path": str(output), "manifest_sha256": manifest_sha}) + "\n")
    print(
        json.dumps(
            {
                "frozen_manifest_sha256": manifest_sha,
                "succeeded": sum(result["status"] == "succeeded" for result in results),
                "total": len(results),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
