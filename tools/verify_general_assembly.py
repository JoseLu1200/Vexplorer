"""Freeze a revision-bound live general-assembly attempt before evaluation.

This opt-in acceptance tool uses only the public run API.  It never opens an
evaluation reference.  Provider credentials remain in the server environment;
the report stores the persisted candidate, deterministic report, bounded trace,
job state, and derived scene returned by Vexplorer.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from getpass import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


Outcome = Literal["validated", "abstained", "any"]
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_TERMINAL_JOB_STATES = frozenset({"succeeded", "failed", "interrupted"})


class VerificationFailure(RuntimeError):
    """Raised when the live response cannot be frozen as trustworthy evidence."""


def _data(response: httpx.Response, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        raise VerificationFailure(f"unexpected_http_status:{response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise VerificationFailure("invalid_http_json") from exc
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise VerificationFailure("invalid_http_envelope")
    return data


def _object(response: httpx.Response, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        raise VerificationFailure(f"unexpected_http_status:{response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise VerificationFailure("invalid_http_json") from exc
    if not isinstance(body, dict):
        raise VerificationFailure("invalid_http_object")
    return body


def _numeric_position(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    )


def _has_numeric_placements(value: Any) -> bool:
    if isinstance(value, dict):
        if _numeric_position(value.get("position_mm")):
            return True
        return any(_has_numeric_placements(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_numeric_placements(item) for item in value)
    return False


def _attempt_valid(attempt: dict[str, Any]) -> bool:
    if attempt.get("status") == "validated":
        return True
    report = attempt.get("report")
    if not isinstance(report, dict):
        return False
    return report.get("valid") is True or report.get("status") in {
        "accepted",
        "validated",
    }


def _write_new(path: Path, content: bytes) -> None:
    if path.exists():
        raise VerificationFailure(f"frozen_output_exists:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_existing_run(
    client: httpx.Client,
    run_id: str,
    *,
    output_dir: Path,
    case_id: str,
    expected_outcome: Outcome = "any",
    timeout_s: float = 240.0,
    poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    """Spend once, retrieve the exact persisted attempt, and freeze it."""
    if not _CASE_ID.fullmatch(case_id):
        raise VerificationFailure("invalid_case_id")
    if expected_outcome not in {"validated", "abstained", "any"}:
        raise VerificationFailure("invalid_expected_outcome")
    snapshot_path = output_dir / f"{case_id}-pre-evaluation.json"
    digest_path = output_dir / f"{case_id}-pre-evaluation.sha256"
    if snapshot_path.exists() or digest_path.exists():
        raise VerificationFailure("frozen_output_exists")

    general = _data(client.get(f"/api/v1/runs/{run_id}/general"), 200)
    proposal_revision = general.get("proposal_revision")
    review_revision = general.get("review_revision")
    if not isinstance(proposal_revision, int) or not isinstance(review_revision, int):
        raise VerificationFailure("general_revision_missing")

    submitted = _data(
        client.post(
            f"/api/v1/runs/{run_id}/general/assembly/retry",
            json={
                "base_proposal_revision": proposal_revision,
                "base_review_revision": review_revision,
            },
            headers={
                "Idempotency-Key": (
                    f"assembly-verify-{case_id[:40]}-"
                    + sha256(
                        f"{run_id}:{proposal_revision}:{review_revision}".encode()
                    ).hexdigest()[:24]
                )
            },
        ),
        202,
    )
    job_id = submitted.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise VerificationFailure("assembly_job_id_missing")
    deadline = time.monotonic() + timeout_s
    while True:
        job = _data(client.get(f"/api/v1/jobs/{job_id}"), 200)
        state = job.get("state")
        if state in _TERMINAL_JOB_STATES:
            break
        if state not in {"queued", "running"}:
            raise VerificationFailure(f"unknown_job_state:{state}")
        if time.monotonic() >= deadline:
            raise VerificationFailure("assembly_job_timeout")
        time.sleep(poll_interval_s)

    params = {
        "proposal_revision": proposal_revision,
        "review_revision": review_revision,
    }
    assembly_state = _object(
        client.get(f"/api/v1/runs/{run_id}/general/assembly", params=params),
        200,
    )
    current = assembly_state.get("current")
    if isinstance(current, dict):
        attempt = current
    else:
        attempt = assembly_state
        assembly_state = {
            "status": attempt.get("report", {}).get("status"),
            "current": attempt,
            "accepted_alternatives": (
                [attempt] if _attempt_valid(attempt) else []
            ),
            "ambiguous": False,
        }
    if (
        attempt.get("run_id") != run_id
        or attempt.get("proposal_revision") != proposal_revision
        or attempt.get("review_revision") != review_revision
    ):
        raise VerificationFailure("attempt_revision_mismatch")
    assembly_revision = attempt.get("assembly_revision")
    if not isinstance(assembly_revision, int) or assembly_revision < 1:
        raise VerificationFailure("assembly_revision_missing")

    derived = _data(
        client.get(f"/api/v1/runs/{run_id}/general/derived", params=params),
        200,
    )
    package = derived.get("package")
    if not isinstance(package, dict):
        raise VerificationFailure("derived_package_missing")
    if (
        package.get("proposal_revision") != proposal_revision
        or package.get("review_revision") != review_revision
    ):
        raise VerificationFailure("derived_revision_mismatch")

    valid = _attempt_valid(attempt)
    outcome = "validated" if valid else "abstained"
    if expected_outcome != "any" and outcome != expected_outcome:
        raise VerificationFailure(
            f"unexpected_assembly_outcome:{outcome}:expected:{expected_outcome}"
        )
    if not valid and _has_numeric_placements(package.get("scene")):
        raise VerificationFailure("rejected_placement_leaked_into_scene")

    frozen = {
        "schema_version": "1.0",
        "phase": "pre_private_evaluation",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "case_id": case_id,
        "public_inputs_only": True,
        "run": {
            "run_id": run_id,
            "status": general.get("status"),
            "proposal_revision": proposal_revision,
            "review_revision": review_revision,
            "component_count": len(
                general.get("draft", {}).get("components", [])
                if isinstance(general.get("draft"), dict)
                else []
            ),
        },
        "job": job,
        "assembly_state": assembly_state,
        "assembly_attempt": attempt,
        "derived": derived,
        "assertions": {
            "exact_revision": True,
            "persisted_attempt_retrieved": True,
            "rejected_placement_not_served": not valid,
            "private_reference_not_read": True,
        },
        "outcome": outcome,
    }
    encoded = (json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    digest = sha256(encoded).hexdigest()
    _write_new(snapshot_path, encoded)
    try:
        _write_new(digest_path, f"{digest}  {snapshot_path.name}\n".encode("ascii"))
    except Exception:
        snapshot_path.unlink(missing_ok=True)
        raise
    return {
        "case_id": case_id,
        "run_id": run_id,
        "proposal_revision": proposal_revision,
        "review_revision": review_revision,
        "assembly_revision": assembly_revision,
        "job_state": job.get("state"),
        "outcome": outcome,
        "frozen_output": str(snapshot_path),
        "frozen_sha256": digest,
    }


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("base URL must be absolute HTTP(S)")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("base URL cannot contain credentials, query or fragment")
    return value.rstrip("/")


def _credentials() -> tuple[str, str] | None:
    username = os.getenv("VEXPLORER_QA_USERNAME")
    password = os.getenv("VEXPLORER_QA_PASSWORD")
    if username or password:
        if not username:
            username = input("Basic username: ").strip()
        if not password:
            password = getpass("Basic password: ")
        if not username or not password:
            raise SystemExit("both Basic credentials are required")
        return username, password
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=_base_url, default="https://localhost:8765")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-outcome", choices=("validated", "abstained", "any"), default="any"
    )
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument(
        "--verify-tls", action="store_true",
        help="Verify the TLS chain (off by default for the temporary localhost certificate).",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    auth = _credentials()
    try:
        with httpx.Client(
            base_url=args.base_url, auth=auth, verify=args.verify_tls,
            timeout=60, headers={"User-Agent": "Vexplorer-general-assembly-verification/1"},
        ) as client:
            summary = verify_existing_run(
                client, args.run_id, output_dir=args.output_dir.resolve(),
                case_id=args.case_id, expected_outcome=args.expected_outcome,
                timeout_s=args.timeout,
            )
    except Exception as exc:
        print(json.dumps({
            "status": "failed", "failure_type": type(exc).__name__,
            "failure": str(exc).split(":", 1)[0],
        }, ensure_ascii=False))
        raise SystemExit(1) from None
    print(json.dumps({"status": "frozen", **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
