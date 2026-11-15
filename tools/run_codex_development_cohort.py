"""Run a small public development cohort through isolated Codex relay harnesses."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


TERMINAL_STATES = {"succeeded", "failed", "interrupted"}
TEST_PROFILE = "interactive_codex_1800_v1"
COHORT_EXECUTION = "parallel_fresh_generation_v1"
_SAFE_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PRINT_LOCK = threading.Lock()
_PROCESS_LOCK = threading.Lock()
_TERMINATE_GRACE_S = 3


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        item for item in root.rglob("*")
        if item.is_file() and "__pycache__" not in item.parts
    ):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _save_json(path: Path, value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    digest = _sha256_bytes(payload)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="ascii"
    )
    return digest


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("evaluation_phase") != "development":
        raise ValueError("only a development manifest is accepted")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not 1 <= len(raw_cases) <= 2:
        raise ValueError("development cohort must contain at most two non-empty cases")
    cases = []
    seen: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("each case must be an object")
        case_id = item.get("case_id")
        if (
            not isinstance(case_id, str)
            or _SAFE_CASE_ID.fullmatch(case_id) is None
            or case_id in seen
        ):
            raise ValueError("each case_id must be unique and path-safe")
        if item.get("split") != "development":
            raise ValueError(f"case {case_id} is not in the development split")
        raw_dxf_path = item.get("dxf_path")
        if not isinstance(raw_dxf_path, str) or not raw_dxf_path:
            raise ValueError(f"case {case_id} requires a relative path inside the manifest directory")
        relative_source = Path(raw_dxf_path)
        manifest_root = path.parent.resolve()
        source = (manifest_root / relative_source).resolve()
        if (
            relative_source.is_absolute()
            or any(part in {"", ".", ".."} for part in relative_source.parts)
            or not source.is_relative_to(manifest_root)
        ):
            raise ValueError(f"case {case_id} requires a relative path inside the manifest directory")
        if source.suffix.lower() != ".dxf" or not source.is_file():
            raise ValueError(f"case {case_id} does not reference a readable DXF")
        seen.add(case_id)
        cases.append({"case_id": case_id, "split": "development", "source": source})
    return cases


def _validate_isolated_paths(output: Path, relay: Path) -> None:
    if output == relay or output in relay.parents or relay in output.parents:
        raise ValueError("output and relay must be separate non-nested paths")


def _child_command(
    *, harness: Path, runtime: Path, manifest: Path, output: Path, relay: Path
) -> list[str]:
    return [
        sys.executable,
        str(harness),
        "--manifest", str(manifest),
        "--runtime-dir", str(runtime),
        "--output", str(output),
        "--relay-dir", str(relay),
        "--workers", "1",
        "--test-job-timeout-s", "1800",
        "--execute",
    ]


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=_TERMINATE_GRACE_S)


def _terminate_all(processes: list[subprocess.Popen[str]]) -> None:
    with _PROCESS_LOCK:
        owned = list(processes)
    for process in owned:
        _terminate_process(process)


def _start_child(command: list[str], environment: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=Path.cwd(),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        bufsize=1,
        shell=False,
    )


def _forward_child(
    process: subprocess.Popen[str],
    processes: list[subprocess.Popen[str]],
    cancel: threading.Event,
) -> int:
    assert process.stdout is not None
    try:
        for line in process.stdout:
            with _PRINT_LOCK:
                print(line, end="", flush=True)
        return_code = process.wait()
        if return_code != 0:
            cancel.set()
            _terminate_all(processes)
        return return_code
    except BaseException:
        cancel.set()
        _terminate_all(processes)
        raise


def _validate_child(
    case: dict[str, Any], child_output: Path, expected: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle = json.loads((child_output / "prediction-bundle.json").read_text(encoding="utf-8"))
    provenance = json.loads((child_output / "runtime-provenance.json").read_text(encoding="utf-8"))
    cases = bundle.get("cases")
    if (
        bundle.get("evaluation_phase") != "development"
        or bundle.get("case_order") != [case["case_id"]]
        or not isinstance(cases, list)
        or len(cases) != 1
        or cases[0].get("case_id") != case["case_id"]
        or cases[0].get("prediction", {}).get("job_state") not in TERMINAL_STATES
    ):
        raise RuntimeError(f"child_case_not_terminal_or_mismatched:{case['case_id']}")
    config = bundle.get("runtime_config")
    if (
        not isinstance(config, dict)
        or config.get("execution_transport") != "codex_agent_relay"
        or config.get("test_profile") != TEST_PROFILE
        or config.get("api_key_loaded") is not False
    ):
        raise RuntimeError(f"child_runtime_config_invalid:{case['case_id']}")
    if (
        provenance.get("runtime_unchanged") is not True
        or provenance.get("relay_code_unchanged") is not True
        or provenance.get("api_key_loaded") is not False
        or provenance.get("execution_transport") != "codex_agent_relay"
        or provenance.get("test_profile") != TEST_PROFILE
        or provenance.get("runtime_sha256_before") != expected["runtime"]
        or provenance.get("runtime_sha256_after") != expected["runtime"]
        or provenance.get("harness_sha256_before") != expected["harness"]
        or provenance.get("harness_sha256_after") != expected["harness"]
        or provenance.get("bridge_sha256_before") != expected["bridge"]
        or provenance.get("bridge_sha256_after") != expected["bridge"]
    ):
        raise RuntimeError(f"child_provenance_invalid:{case['case_id']}")
    return bundle, provenance


def execute(args: argparse.Namespace, cases: list[dict[str, Any]]) -> Path:
    output = args.output.resolve()
    relay = args.relay_dir.resolve()
    runtime = args.runtime_dir.resolve()
    harness = args.harness.resolve()
    _validate_isolated_paths(output, relay)
    if output.exists() or relay.exists():
        raise ValueError("output and relay directories must both be new")
    if not (runtime / "backend" / "app" / "main.py").is_file():
        raise ValueError("runtime-dir is not a frozen Vexplorer runtime")
    if not harness.is_file():
        raise ValueError("harness is not a readable file")
    bridge = Path(__file__).with_name("codex_test_bridge.py").resolve()
    publisher = Path(__file__).with_name("publish_codex_response.py").resolve()
    if not bridge.is_file() or not publisher.is_file():
        raise ValueError("relay bridge and response publisher are required")

    before = {
        "runtime": _hash_tree(runtime),
        "harness": _sha256_file(harness),
        "bridge": _sha256_file(bridge),
        "publisher": _sha256_file(publisher),
        "wrapper": _sha256_file(Path(__file__).resolve()),
    }
    output.mkdir(parents=True)
    manifests_dir = output / "manifests"
    children_dir = output / "children"
    manifests_dir.mkdir()
    children_dir.mkdir()
    commands = []
    for case in cases:
        child_manifest = manifests_dir / f"{case['case_id']}.json"
        _save_json(child_manifest, {
            "evaluation_phase": "development",
            "cases": [{
                "case_id": case["case_id"],
                "split": "development",
                "dxf_path": str(case["source"]),
            }],
        })
        commands.append(_child_command(
            harness=harness,
            runtime=runtime,
            manifest=child_manifest,
            output=children_dir / case["case_id"],
            relay=relay,
        ))
    environment = dict(os.environ)
    environment.pop("OPENAI_API_KEY", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    processes: list[subprocess.Popen[str]] = []
    cancel = threading.Event()
    try:
        for command in commands:
            process = _start_child(command, environment)
            with _PROCESS_LOCK:
                processes.append(process)
        with ThreadPoolExecutor(max_workers=len(processes)) as executor:
            futures = [
                executor.submit(_forward_child, process, processes, cancel)
                for process in processes
            ]
            return_codes = [future.result() for future in futures]
    except BaseException:
        cancel.set()
        _terminate_all(processes)
        raise
    finally:
        if cancel.is_set():
            _terminate_all(processes)
    if any(code != 0 for code in return_codes):
        raise RuntimeError(f"cohort_child_failed:{return_codes}")

    after = {
        "runtime": _hash_tree(runtime),
        "harness": _sha256_file(harness),
        "bridge": _sha256_file(bridge),
        "publisher": _sha256_file(publisher),
        "wrapper": _sha256_file(Path(__file__).resolve()),
    }
    if before != after:
        raise RuntimeError("cohort_code_or_runtime_changed")
    child_bundles = []
    child_provenance = {}
    for case in cases:
        child_output = children_dir / case["case_id"]
        bundle, provenance = _validate_child(case, child_output, before)
        child_bundles.append(bundle)
        child_provenance[case["case_id"]] = {
            "bundle": str((child_output / "prediction-bundle.json").relative_to(output).as_posix()),
            "provenance": str((child_output / "runtime-provenance.json").relative_to(output).as_posix()),
            "runtime_sha256": provenance["runtime_sha256_after"],
        }
    canonical_configs = {
        json.dumps(bundle["runtime_config"], sort_keys=True, separators=(",", ":"))
        for bundle in child_bundles
    }
    if len(canonical_configs) != 1:
        raise RuntimeError("child_runtime_configs_differ")
    runtime_config = dict(child_bundles[0]["runtime_config"])
    runtime_config["cohort_execution"] = COHORT_EXECUTION
    combined = {
        "evaluation_phase": "development",
        "execution_transport": "codex_agent_relay",
        "runtime_config": runtime_config,
        "case_order": [case["case_id"] for case in cases],
        "cases": [bundle["cases"][0] for bundle in child_bundles],
        "child_receipts": child_provenance,
    }
    provenance = {
        "cohort_execution": COHORT_EXECUTION,
        "case_order": combined["case_order"],
        "runtime_sha256_before": before["runtime"],
        "runtime_sha256_after": after["runtime"],
        "runtime_unchanged": before["runtime"] == after["runtime"],
        "harness_sha256_before": before["harness"],
        "harness_sha256_after": after["harness"],
        "harness_unchanged": before["harness"] == after["harness"],
        "bridge_sha256_before": before["bridge"],
        "bridge_sha256_after": after["bridge"],
        "bridge_unchanged": before["bridge"] == after["bridge"],
        "publisher_sha256_before": before["publisher"],
        "publisher_sha256_after": after["publisher"],
        "publisher_unchanged": before["publisher"] == after["publisher"],
        "wrapper_sha256_before": before["wrapper"],
        "wrapper_sha256_after": after["wrapper"],
        "wrapper_unchanged": before["wrapper"] == after["wrapper"],
        "api_key_loaded": False,
        "child_receipts": child_provenance,
    }
    _save_json(output / "cohort-provenance.json", provenance)
    _save_json(output / "prediction-bundle.json", combined)
    return output / "prediction-bundle.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--relay-dir", type=Path, required=True)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


def main() -> int:
    _configure_utf8_stdio()
    args = _parser().parse_args()
    try:
        manifest = args.manifest.resolve(strict=True)
        cases = _load_manifest(manifest)
        runtime = args.runtime_dir.resolve()
        harness = args.harness.resolve()
        output = args.output.resolve()
        relay = args.relay_dir.resolve()
        _validate_isolated_paths(output, relay)
        if output.exists() or relay.exists():
            raise ValueError("output and relay directories must both be new")
        commands = [
            _child_command(
                harness=harness,
                runtime=runtime,
                manifest=output / "manifests" / f"{case['case_id']}.json",
                output=output / "children" / case["case_id"],
                relay=relay,
            )
            for case in cases
        ]
        if not args.execute:
            print(json.dumps({
                "dry_run": True,
                "case_order": [case["case_id"] for case in cases],
                "commands": commands,
                "provider_called": False,
            }, ensure_ascii=False, sort_keys=True))
            return 0
        bundle = execute(args, cases)
        print(json.dumps({"dry_run": False, "prediction_bundle": str(bundle)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"run_codex_development_cohort: error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
