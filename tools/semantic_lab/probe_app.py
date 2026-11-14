"""Probe a frozen Vexplorer snapshot against public cross-dataset samples.

The orchestrator is stdlib-only.  App imports happen exclusively in a child
process whose first import root is the frozen snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable


EXCLUDED_CADBLOCK_CATEGORIES = frozenset({"beds", "buffets", "simple-tables", "sofas"})


def select_cadblock_samples(root: Path, *, limit: int = 20) -> list[Path]:
    """Round-robin sorted DXFs across non-core CADBlock categories."""
    category_root = root / "dxf_metric"
    queues = {
        folder.name: sorted(folder.glob("*.dxf"), key=lambda path: path.name.casefold())
        for folder in sorted(category_root.iterdir(), key=lambda path: path.name.casefold())
        if folder.is_dir() and folder.name not in EXCLUDED_CADBLOCK_CATEGORIES
    }
    selected: list[Path] = []
    depth = 0
    while len(selected) < limit:
        added = False
        for category in sorted(queues, key=str.casefold):
            paths = queues[category]
            if depth < len(paths):
                selected.append(paths[depth])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        depth += 1
    return selected


def classify_response(
    *,
    upload_status: int,
    upload_data: dict[str, Any],
    run_status: int | None,
    run_data: dict[str, Any] | None,
    general_status: int | None,
    general_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify semantic outcome independently from HTTP success."""
    upload_ok = upload_status == 201
    ingestion_state = (upload_data.get("ingestion") or {}).get("state") if upload_ok else None
    result = (run_data or {}).get("result") or {}
    pieces = result.get("pieces") or []
    dispositions = result.get("dispositions") or []
    review_count = sum(item.get("status") == "needs_review" for item in dispositions)
    proposal_present = general_status == 200 and bool((general_data or {}).get("proposal"))
    if not upload_ok:
        error = (upload_data.get("error") or {}).get("code", f"http_{upload_status}")
        outcome = f"upload_error:{error}"
    elif run_status != 201:
        error = (((run_data or {}).get("error") or {}).get("code", f"http_{run_status}"))
        outcome = f"run_error:{error}"
    elif result.get("state") == "completed" and pieces and proposal_present:
        outcome = "proposal_with_pieces"
    elif result.get("state") == "needs_review" and not proposal_present:
        outcome = "needs_review_without_proposal"
    elif result.get("state") == "needs_review":
        outcome = "needs_review_with_proposal"
    else:
        outcome = f"result:{result.get('state', 'unknown')}"
    return {
        "upload_ok": upload_ok,
        "ingestion_state": ingestion_state,
        "geometry_run_created": run_status == 201,
        "result_state": result.get("state"),
        "piece_count": len(pieces),
        "needs_review_count": review_count,
        "general_proposal_present": proposal_present,
        "outcome": outcome,
    }


def summarize_geometry(status: int, payload: dict[str, Any] | None) -> dict[str, Any]:
    if status != 200 or payload is None:
        return {"status": f"http_{status}"}
    return {
        "status": payload.get("status"),
        "coordinate_unit": payload.get("coordinate_unit"),
        "entity_count": len(payload.get("entities") or []),
        "view_count": len(payload.get("views") or []),
        "contour_count": len(payload.get("contours") or []),
        "dimension_count": len(payload.get("dimensions") or []),
        "observation_count": len(payload.get("observations") or []),
        "warnings": payload.get("warnings") or [],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def _samples(dataset_root: Path) -> list[dict[str, str]]:
    engineering = sorted(
        (dataset_root / "engineering_evaluation_pilot_v3" / "agent_inputs").glob("cad-*.dxf")
    )
    plank = sorted((dataset_root / "plankassembly_adapter_test_v1").glob("plank-*.dxf"))
    plank_trial = sorted(
        (dataset_root / "plankassembly_adapter_trial_v1").glob("plank-*.dxf")
    )
    cadblock = select_cadblock_samples(dataset_root / "cadblock_2d", limit=20)
    pdfs = sorted(
        (dataset_root / "engineering_evaluation_pilot_v3" / "agent_inputs").glob("visual-*.pdf")
    )
    groups: Iterable[tuple[str, list[Path]]] = (
        ("engineering_mechanical", engineering),
        ("plankassembly_public", plank),
        ("plankassembly_trial_public", plank_trial),
        ("cadblock_non_core", cadblock),
        ("engineering_pdf", pdfs),
    )
    return [
        {"dataset": dataset, "path": str(path), "name": path.name, "sha256": _sha256(path)}
        for dataset, paths in groups
        for path in paths
    ]


def _sanitized_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        upper = name.upper()
        if any(token in upper for token in ("OPENAI", "ANTHROPIC", "API_KEY", "TOKEN")):
            environment.pop(name, None)
    environment["VEXPLORER_ENV"] = "local"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def build_worker_command(python_executable: Path, script: Path, request: Path) -> list[str]:
    return [str(python_executable), str(script), "_worker", str(request)]


def configure_worker_environment(output_dir: Path) -> Path:
    runtime_dir = output_dir / "runtime-data"
    os.environ["VEXPLORER_ENV"] = "local"
    os.environ["VEXPLORER_DATA_DIR"] = str(runtime_dir / "import-default")
    return runtime_dir


def execution_metadata(snapshot: Path, data_dir: Path) -> dict[str, Any]:
    return {
        "mode": "isolated_testclient_geometry_only",
        "provider_disabled_by_configuration": True,
        "network_activity_measured": False,
        "payment_activity_measured": False,
        "cost": None,
        "snapshot_import_root": str(snapshot),
        "runtime_data_persisted": True,
        "runtime_data_path": str(data_dir),
    }


def run_probe(
    snapshot: Path,
    dataset_root: Path,
    output_dir: Path,
    *,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    dataset_root = dataset_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    before = _tree_hashes(snapshot)
    request_path = output_dir / "request.json"
    result_path = output_dir / "results.json"
    request = {
        "snapshot": str(snapshot),
        "output_dir": str(output_dir.resolve()),
        "samples": _samples(dataset_root),
        "history_path": str(
            dataset_root / "public_furniture_history_2026-11-14" / "historical_import.json"
        ),
    }
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    worker_python = (python_executable or Path(sys.executable)).resolve()
    command = build_worker_command(worker_python, Path(__file__).resolve(), request_path)
    completed = subprocess.run(
        command,
        cwd=snapshot,
        env=_sanitized_environment(),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    after = _tree_hashes(snapshot)
    stability = {
        "stable": before == after,
        "before_file_count": len(before),
        "after_file_count": len(after),
        "changed": sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key)),
    }
    (output_dir / "snapshot_stability.json").write_text(
        json.dumps(stability, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "worker_process.json").write_text(
        json.dumps(
            {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "command": [str(worker_python), "probe_app.py", "_worker", "request.json"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"probe worker failed with exit code {completed.returncode}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["snapshot_stability"] = stability
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _response_payload(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        return {"text": response.text[:2000]}
    return body.get("data", body) if isinstance(body, dict) else {"body": body}


def _probe_one(client: Any, sample: dict[str, str], raw_dir: Path) -> dict[str, Any]:
    path = Path(sample["path"])
    media_type = "application/pdf" if path.suffix.casefold() == ".pdf" else "application/dxf"
    upload = client.post(
        "/api/v1/documents", files={"file": (path.name, path.read_bytes(), media_type)}
    )
    upload_payload = _response_payload(upload)
    general_run = general = drawing = legacy_run = None
    if upload.status_code == 201:
        document_id = upload_payload["document_id"]
        general_run = client.post(
            "/api/v1/runs",
            json={
                "document_id": document_id,
                "mode": "geometry_only",
                "input_kind": "general_furniture",
                "proposal_mode": "none",
            },
        )
        general_run_payload = _response_payload(general_run)
        if general_run.status_code == 201:
            run_id = general_run_payload["run"]["id"]
            general = client.get(f"/api/v1/runs/{run_id}/general")
            drawing = client.get(f"/api/v1/runs/{run_id}/drawing")
        legacy_run = client.post(
            "/api/v1/runs",
            json={"document_id": document_id, "mode": "geometry_only"},
        )
    general_run_payload = _response_payload(general_run) if general_run is not None else None
    general_payload = _response_payload(general) if general is not None else None
    drawing_payload = _response_payload(drawing) if drawing is not None else None
    legacy_payload = _response_payload(legacy_run) if legacy_run is not None else None
    classification = classify_response(
        upload_status=upload.status_code,
        upload_data=upload_payload,
        run_status=general_run.status_code if general_run is not None else None,
        run_data=general_run_payload,
        general_status=general.status_code if general is not None else None,
        general_data=general_payload,
    )
    classification["legacy_geometry_status"] = legacy_run.status_code if legacy_run is not None else None
    classification["legacy_error_code"] = (
        ((legacy_payload or {}).get("error") or {}).get("code")
        if legacy_run is not None and legacy_run.status_code != 201
        else None
    )
    classification["legacy_piece_count"] = len(
        (((legacy_payload or {}).get("result") or {}).get("pieces") or [])
    )
    classification["geometry"] = summarize_geometry(
        drawing.status_code if drawing is not None else 0, drawing_payload
    )
    record = {
        **sample,
        "classification": classification,
        "cost": None,
        "raw_file": f"raw/{sample['dataset']}--{path.stem}.json",
    }
    raw = {
        "sample": sample,
        "upload": {"status": upload.status_code, "payload": upload_payload},
        "general_geometry_run": {
            "status": general_run.status_code if general_run is not None else None,
            "payload": general_run_payload,
        },
        "general_record": {
            "status": general.status_code if general is not None else None,
            "payload": general_payload,
        },
        "drawing_extraction": {
            "status": drawing.status_code if drawing is not None else None,
            "payload": drawing_payload,
        },
        "legacy_geometry_run": {
            "status": legacy_run.status_code if legacy_run is not None else None,
            "payload": legacy_payload,
        },
    }
    raw_path = raw_dir / f"{sample['dataset']}--{path.stem}.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _worker(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    snapshot = Path(request["snapshot"])
    output_dir = Path(request["output_dir"])
    sys.path[:] = [str(snapshot)] + [item for item in sys.path if Path(item or ".").resolve() != Path.cwd()]
    runtime_dir = configure_worker_environment(output_dir)
    from fastapi.testclient import TestClient
    from backend.app.main import create_app

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    data_dir = runtime_dir / "probe"
    with TestClient(
        create_app(data_dir=data_dir, frontend_dir=runtime_dir / "no-frontend")
    ) as client:
        records = [_probe_one(client, sample, raw_dir) for sample in request["samples"]]
        history_payload = json.loads(Path(request["history_path"]).read_text(encoding="utf-8"))
        history_manifest = json.loads(
            (Path(request["history_path"]).parent / "manifest.json").read_text(encoding="utf-8")
        )
        expected_history_hash = next(
            item["sha256"] for item in history_manifest["files"]
            if item["path"] == "historical_import.json"
        )
        dry_run = client.post("/api/v1/history/import/json?dry_run=true", json=history_payload)
        imported = client.post("/api/v1/history/import/json", json=history_payload)
        listed = client.get("/api/v1/history?limit=20")
        history = {
            "source_sha256": _sha256(Path(request["history_path"])),
            "manifest_expected_sha256": expected_history_hash,
            "manifest_hash_match": _sha256(Path(request["history_path"])) == expected_history_hash,
            "source_record_count": len(history_payload.get("records", [])),
            "dry_run": {"status": dry_run.status_code, "payload": _response_payload(dry_run)},
            "import": {"status": imported.status_code, "payload": _response_payload(imported)},
            "list": {"status": listed.status_code, "payload": _response_payload(listed)},
            "cost": None,
        }
        (raw_dir / "history_import.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    by_dataset: dict[str, dict[str, Any]] = {}
    for record in records:
        summary = by_dataset.setdefault(
            record["dataset"], {"count": 0, "uploads_201": 0, "runs_201": 0, "outcomes": {}}
        )
        summary["count"] += 1
        classification = record["classification"]
        summary["uploads_201"] += int(classification["upload_ok"])
        summary["runs_201"] += int(classification["geometry_run_created"])
        outcome = classification["outcome"]
        summary["outcomes"][outcome] = summary["outcomes"].get(outcome, 0) + 1
    result = {
        "schema_version": 1,
        "execution": execution_metadata(snapshot, data_dir),
        "summary": {"total_samples": len(records), "by_dataset": by_dataset},
        "samples": records,
        "history": history,
    }
    (output_dir / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--snapshot", type=Path, required=True)
    run.add_argument("--dataset-root", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--python", type=Path, default=None)
    worker = subparsers.add_parser("_worker")
    worker.add_argument("request", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "_worker":
        return _worker(args.request)
    result = run_probe(
        args.snapshot,
        args.dataset_root,
        args.output_dir,
        python_executable=args.python,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
