"""Merge frozen paired benchmark retries without references or score selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any

from tools.run_general_benchmark import export_prediction_manifests


HEX64 = re.compile(r"[0-9a-f]{64}")
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
DATASET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
POLICY = "operational_recovery_of_original_preprovider_failures_v1"
FORBIDDEN_PATH_MARKERS = ("reference", "oracle", "ground-truth", "ground_truth", "answer-key", "answer_key")


class MergeError(ValueError):
    """Raised when frozen inputs or recovery selection are unsafe."""


@dataclass(frozen=True)
class FrozenRun:
    root: Path
    manifest: dict[str, Any]
    manifest_raw: bytes
    manifest_sha256: str
    configuration: dict[str, Any]
    configuration_raw: bytes
    configuration_sha256: str
    files: dict[str, str]
    results: dict[str, dict[str, Any]]
    dataset_id: str
    source_sha256: dict[str, str]


def _json_mapping(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MergeError(f"invalid json: {label}") from exc
    if not isinstance(value, dict):
        raise MergeError(f"json object required: {label}")
    return value


def _safe_relative(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) == value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_run(root: Path, expected_manifest_sha256: str) -> FrozenRun:
    if HEX64.fullmatch(expected_manifest_sha256) is None:
        raise MergeError("invalid expected frozen manifest hash")
    if root.is_symlink():
        raise MergeError("frozen run root may not be a symlink")
    root = root.resolve()
    manifest_path = root / "frozen-manifest.json"
    try:
        manifest_raw = manifest_path.read_bytes()
    except OSError as exc:
        raise MergeError("cannot read frozen manifest") from exc
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha != expected_manifest_sha256:
        raise MergeError("frozen manifest hash mismatch")
    manifest = _json_mapping(manifest_raw, "frozen-manifest.json")
    raw_files, raw_results = manifest.get("files"), manifest.get("results")
    if not isinstance(raw_files, dict) or not isinstance(raw_results, list):
        raise MergeError("frozen manifest lacks files or results")
    files: dict[str, str] = {}
    if any(path.is_symlink() for path in root.rglob("*")):
        raise MergeError("frozen run contains symlink")
    for relative, digest in raw_files.items():
        if not isinstance(relative, str) or not _safe_relative(relative):
            raise MergeError("unsafe frozen path")
        if any(marker in relative.lower() for marker in FORBIDDEN_PATH_MARKERS):
            raise MergeError(f"forbidden frozen path: {relative}")
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise MergeError(f"invalid frozen hash: {relative}")
        path = root / Path(relative)
        if path.is_symlink() or not path.is_file():
            raise MergeError(f"missing or unsafe frozen file: {relative}")
        if _file_sha(path) != digest:
            raise MergeError(f"frozen hash mismatch: {relative}")
        files[relative] = digest
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual != set(files):
        raise MergeError("frozen file set differs from manifest")
    config_raw = (root / "configuration.json").read_bytes()
    if files.get("configuration.json") != hashlib.sha256(config_raw).hexdigest():
        raise MergeError("configuration is not frozen")
    config = _json_mapping(config_raw, "configuration.json")
    dataset_id, source_hashes = config.get("dataset_id"), config.get("source_sha256")
    if not isinstance(dataset_id, str) or DATASET_ID.fullmatch(dataset_id) is None:
        raise MergeError("invalid dataset id")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise MergeError("missing source hashes")
    code_hashes = config.get("code_sha256")
    if not isinstance(code_hashes, dict) or not code_hashes or any(
        not isinstance(path, str)
        or not _safe_relative(path)
        or not isinstance(digest, str)
        or HEX64.fullmatch(digest) is None
        for path, digest in code_hashes.items()
    ):
        raise MergeError("invalid code fingerprints")
    normalized_sources: dict[str, str] = {}
    for case_id, digest in source_hashes.items():
        if not isinstance(case_id, str) or CASE_ID.fullmatch(case_id) is None:
            raise MergeError("invalid case id")
        if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
            raise MergeError("invalid source hash")
        source_relative = f"public-inputs/{case_id}.dxf"
        if files.get(source_relative) is None or _file_sha(root / source_relative) != digest:
            raise MergeError(f"public input hash mismatch: {case_id}")
        normalized_sources[case_id] = digest
    if config.get("private_reference_access") is not False:
        raise MergeError("run does not attest public-only reference access")
    results: dict[str, dict[str, Any]] = {}
    for value in raw_results:
        if not isinstance(value, dict):
            raise MergeError("invalid frozen result")
        case_id, status = value.get("case_id"), value.get("status")
        if not isinstance(case_id, str) or case_id not in normalized_sources or case_id in results:
            raise MergeError("invalid or duplicate frozen result case id")
        if status not in {"succeeded", "failed_after_baseline", "failed_before_baseline"}:
            raise MergeError("unsupported frozen result status")
        results[case_id] = value
    if set(results) != set(normalized_sources):
        raise MergeError("frozen denominator differs from configuration")
    _validate_case_wrappers(root, files, results, normalized_sources)
    return FrozenRun(root, manifest, manifest_raw, manifest_sha, config, config_raw, hashlib.sha256(config_raw).hexdigest(), files, results, dataset_id, normalized_sources)


def _validate_case_wrappers(root: Path, files: dict[str, str], results: dict[str, dict[str, Any]], sources: dict[str, str]) -> None:
    for case_id, result in results.items():
        status = result["status"]
        expected = ["failure.json"] if status == "failed_before_baseline" else ["baseline.json"]
        if status == "succeeded":
            expected.append("final.json")
        elif status == "failed_after_baseline":
            expected.append("failure.json")
        for filename in expected:
            relative = f"{case_id}/{filename}"
            if relative not in files:
                raise MergeError(f"missing frozen case wrapper: {relative}")
            wrapper = _json_mapping((root / relative).read_bytes(), relative)
            if wrapper.get("case_id") != case_id or wrapper.get("input_sha256") != sources[case_id]:
                raise MergeError(f"case wrapper identity mismatch: {relative}")
        for phase in ("baseline", "final"):
            declared = result.get(f"{phase}_sha256")
            relative = f"{case_id}/{phase}.json"
            if declared is not None and declared != files.get(relative):
                raise MergeError(f"result {phase} hash mismatch: {case_id}")


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(raw)
    return hashlib.sha256(raw).hexdigest()


def _qualify_preprovider_visual_failure(run: FrozenRun, case_id: str) -> dict[str, Any]:
    relative = f"{case_id}/failure.json"
    failure = _json_mapping((run.root / relative).read_bytes(), relative)
    forbidden = {"action_evidence", "model_calls", "tool_calls"}
    qualified = (
        failure.get("status") == "failed_before_baseline"
        and failure.get("failure_type") == "ValueError"
        and failure.get("message") == "visual_evidence_budget_exceeded"
        and forbidden.isdisjoint(failure)
    )
    if not qualified:
        raise MergeError(
            f"original case is not a qualified pre-provider visual budget failure: {case_id}"
        )
    return {
        "original_failure_sha256": run.files[relative],
        "failure_type": "ValueError",
        "message": "visual_evidence_budget_exceeded",
        "no_provider_action_evidence": True,
    }


def _copy_frozen_prefix(run: FrozenRun, prefix: str, destination: Path) -> None:
    for relative in sorted(path for path in run.files if path.startswith(prefix)):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((run.root / relative).read_bytes())


def merge_paired_benchmarks(
    original: Path,
    retry: Path,
    destination: Path,
    *,
    frozen_at: str,
    original_manifest_sha256: str,
    retry_manifest_sha256: str,
) -> dict[str, str]:
    """Create a new frozen cohort using retries only for original pre-provider failures."""
    original_run = _load_run(original, original_manifest_sha256)
    retry_run = _load_run(retry, retry_manifest_sha256)
    if original_run.dataset_id != retry_run.dataset_id:
        raise MergeError("retry dataset mismatch")
    retry_ids = set(retry_run.source_sha256)
    if not retry_ids or not retry_ids <= set(original_run.source_sha256):
        raise MergeError("retry ids must be a non-empty subset of original denominator")
    invalid = sorted(case_id for case_id in retry_ids if original_run.results[case_id]["status"] != "failed_before_baseline")
    if invalid:
        raise MergeError("retry may only select original failed_before_baseline cases")
    qualifications = {
        case_id: _qualify_preprovider_visual_failure(original_run, case_id)
        for case_id in sorted(retry_ids)
    }
    for case_id in retry_ids:
        if retry_run.source_sha256[case_id] != original_run.source_sha256[case_id]:
            raise MergeError(f"retry source hash mismatch: {case_id}")
    destination = destination.resolve()
    if destination.exists():
        raise MergeError("destination already exists")
    destination.mkdir(parents=True)
    try:
        provenance: dict[str, Any] = {}
        selected_results = []
        for case_id in sorted(original_run.source_sha256):
            selected = retry_run if case_id in retry_ids else original_run
            _copy_frozen_prefix(selected, f"{case_id}/", destination)
            public_relative = f"public-inputs/{case_id}.dxf"
            target = destination / public_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((original_run.root / public_relative).read_bytes())
            selected_results.append(selected.results[case_id])
            provenance[case_id] = {
                "origin": "retry" if selected is retry_run else "original",
                "status": selected.results[case_id]["status"],
                "frozen_manifest_sha256": selected.manifest_sha256,
                "configuration_sha256": selected.configuration_sha256,
                "code_sha256": selected.configuration.get("code_sha256", {}),
            }
            if case_id in retry_ids:
                provenance[case_id]["recovery_qualification"] = qualifications[case_id]
                archive_root = destination / "merge-provenance" / "original-failures" / case_id
                for relative in sorted(path for path in original_run.files if path.startswith(f"{case_id}/")):
                    archived = archive_root / PurePosixPath(relative).relative_to(case_id)
                    archived.parent.mkdir(parents=True, exist_ok=True)
                    archived.write_bytes((original_run.root / relative).read_bytes())
        for label, run in (("original", original_run), ("retry", retry_run)):
            base = destination / "merge-provenance" / label
            base.mkdir(parents=True)
            (base / "configuration.json").write_bytes(run.configuration_raw)
            (base / "frozen-manifest.json").write_bytes(run.manifest_raw)
        configuration = {
            "dataset_id": original_run.dataset_id,
            "source_sha256": original_run.source_sha256,
            "code_sha256": {},
            "private_reference_access": False,
            "selection_policy": POLICY,
            "selection_note": "Operational recovery fixed before scoring; only original failed_before_baseline cases may use retry outcomes.",
            "retry_qualification": {
                "required_failure_type": "ValueError",
                "required_message": "visual_evidence_budget_exceeded",
                "provider_action_evidence_must_be_absent": True,
                "qualified_case_ids": sorted(retry_ids),
            },
            "frozen_at": frozen_at,
            "per_case_provenance": provenance,
        }
        _write_json(destination / "configuration.json", configuration)
        prediction_hashes = export_prediction_manifests(destination, dataset_id=original_run.dataset_id, case_ids=tuple(original_run.source_sha256))
        files = {path.relative_to(destination).as_posix(): _file_sha(path) for path in sorted(destination.rglob("*")) if path.is_file()}
        frozen = {
            "frozen_at": frozen_at,
            "results": selected_results,
            "prediction_manifests": prediction_hashes,
            "files": files,
            "merge_policy": POLICY,
            "original_frozen_manifest_sha256": original_run.manifest_sha256,
            "retry_frozen_manifest_sha256": retry_run.manifest_sha256,
            "chronology_note": "The fixed provenance timestamp is descriptive metadata, not cryptographic proof of chronology.",
        }
        merged_sha = _write_json(destination / "frozen-manifest.json", frozen)
        return {"frozen_manifest_sha256": merged_sha, **prediction_hashes}
    except Exception:
        shutil.rmtree(destination)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--retry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--original-manifest-sha256", required=True)
    parser.add_argument("--retry-manifest-sha256", required=True)
    args = parser.parse_args(argv)
    result = merge_paired_benchmarks(args.original, args.retry, args.output, frozen_at=args.frozen_at, original_manifest_sha256=args.original_manifest_sha256, retry_manifest_sha256=args.retry_manifest_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
