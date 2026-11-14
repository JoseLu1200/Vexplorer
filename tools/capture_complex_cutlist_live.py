"""Capture blind complex-furniture predictions; this command never accepts GT."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any

import httpx

from evaluation.complex_cutlist import freeze_prediction_bundle


TERMINAL_JOB_STATES = {"succeeded", "failed", "cancelled"}
REQUIRED_JOB_TIMEOUT_S = 600


def _data(response: Any, expected_status: int = 200) -> dict[str, Any]:
    if response.status_code != expected_status:
        response.raise_for_status()
        raise RuntimeError(f"unexpected HTTP status {response.status_code}")
    payload = response.json()
    return payload.get("data", payload)


def capture_cases(
    client: Any,
    *,
    cases: list[dict[str, Any]],
    output_path: Path,
    poll_interval_s: float = 2.0,
    evaluation_phase: str = "development",
) -> dict[str, Any]:
    config = _data(client.get("/api/v1/config"))
    configured_timeout = (
        config.get("autonomous_review", {}).get("limits", {}).get("job_timeout_s")
    )
    if configured_timeout != REQUIRED_JOB_TIMEOUT_S:
        raise ValueError("blind capture requires published job_timeout_s=600")
    frozen_cases: list[dict[str, Any]] = []
    for item in cases:
        case_id = str(item["case_id"])
        source = Path(item["dxf_path"]).resolve()
        source_bytes = source.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        upload = _data(
            client.post(
                "/api/v1/documents",
                files={"file": (source.name, source_bytes, "application/dxf")},
            ),
            201,
        )
        if upload.get("sha256") not in {None, source_sha256}:
            raise ValueError(f"source hash mismatch for {case_id}")
        submitted = _data(
            client.post(
                "/api/v1/jobs",
                json={
                    "document_id": upload["document_id"],
                    "mode": "live",
                    "input_kind": "general_furniture",
                    "proposal_mode": "model_generated",
                },
                headers={"Idempotency-Key": f"complex-cutlist-v1-{case_id}-{source_sha256[:16]}"},
            ),
            202,
        )
        job_id = submitted["id"]
        deadline = monotonic() + REQUIRED_JOB_TIMEOUT_S + 60
        while True:
            job = _data(client.get(f"/api/v1/jobs/{job_id}"))
            if job.get("state") in TERMINAL_JOB_STATES:
                break
            if monotonic() > deadline:
                raise TimeoutError(f"job polling deadline exceeded for {case_id}")
            sleep(poll_interval_s)
        general: dict[str, Any] = {}
        derived: dict[str, Any] = {}
        if job.get("run_id"):
            response = client.get(f"/api/v1/runs/{job['run_id']}/general")
            if response.status_code == 200:
                general = _data(response)
            proposal_revision = general.get("proposal_revision")
            review_revision = general.get("review_revision")
            if proposal_revision and review_revision:
                response = client.get(
                    f"/api/v1/runs/{job['run_id']}/general/derived"
                    f"?proposal_revision={proposal_revision}&review_revision={review_revision}"
                )
                if response.status_code == 200:
                    derived = _data(response).get("package") or {}
        error = job.get("error") or {}
        frozen_cases.append({
            "case_id": case_id,
            "split": item["split"],
            "public_dxf_sha256": source_sha256,
            "prediction": {
                "job_state": job.get("state"),
                "failure_code": error.get("code"),
                "job_id": job_id,
                "run_id": job.get("run_id"),
                "proposal_revision": general.get("proposal_revision"),
                "review_revision": general.get("review_revision"),
                "draft": general.get("draft") or {"components": []},
                "review": general.get("review"),
                "derived": derived,
            },
        })
    return freeze_prediction_bundle(
        output_path,
        cases=frozen_cases,
        runtime_config={
            "config_evidence": {
                "job_timeout_s": configured_timeout,
                "reviewer_model": config.get("autonomous_review", {}).get("reviewer_model"),
                "response_sha256": hashlib.sha256(
                    json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            },
            "evaluation_phase": evaluation_phase,
            "case_order": [item["case_id"] for item in frozen_cases],
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cases", required=True, type=Path, help="Public DXF manifest; never GT")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = json.loads(args.cases.read_text(encoding="utf-8"))
    raw_cases = manifest.get("cases") if isinstance(manifest, dict) else manifest
    if not isinstance(raw_cases, list):
        raise ValueError("public cases manifest must be a list")
    cases = [
        {
            "case_id": item["case_id"],
            "split": item["split"],
            "dxf_path": (args.cases.parent / item["dxf_path"]).resolve(),
        }
        for item in raw_cases
    ]
    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        capture_cases(
            client,
            cases=cases,
            output_path=args.output,
            evaluation_phase=(
                manifest.get("evaluation_phase", "development")
                if isinstance(manifest, dict)
                else "development"
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
