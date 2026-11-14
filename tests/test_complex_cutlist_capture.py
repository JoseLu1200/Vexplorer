from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from evaluation.complex_cutlist import load_frozen_prediction_bundle
from tools.capture_complex_cutlist_live import capture_cases


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _Client:
    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        self.uploads = 0

    def get(self, path: str):
        if path == "/api/v1/config":
            return _Response(200, {"data": {"capabilities": {"general_furniture": {
                "autonomous_review": {
                    "reviewer_model": "gpt-6-astra",
                    "limits": {"job_timeout_s": self.timeout},
                },
            }}}})
        if path == "/api/v1/jobs/job-1":
            return _Response(200, {"data": {"id": "job-1", "state": "succeeded", "run_id": "run-1", "error": None}})
        if path == "/api/v1/runs/run-1/general":
            return _Response(200, {"data": {
                "draft": {"components": []},
                "review": {"machine_field_reviews": [], "machine_provenance": {"model": "gpt-6-astra"}},
                "proposal_revision": 1,
                "review_revision": 1,
            }})
        if path == "/api/v1/runs/run-1/general/derived?proposal_revision=1&review_revision=1":
            return _Response(200, {"data": {"package": {
                "proposal_revision": 1, "review_revision": 1, "bom_rows": [],
            }}})
        raise AssertionError(path)

    def post(self, path: str, **kwargs):
        if path == "/api/v1/documents":
            self.uploads += 1
            source_bytes = kwargs["files"]["file"][1]
            return _Response(201, {"data": {"document_id": "doc-1", "sha256": hashlib.sha256(source_bytes).hexdigest()}})
        if path == "/api/v1/jobs":
            return _Response(202, {"data": {"id": "job-1"}})
        raise AssertionError(path)


def test_capture_uses_only_public_dxf_and_freezes_terminal_prediction(tmp_path: Path) -> None:
    source = tmp_path / "blind-001.dxf"
    source.write_bytes(b"public-dxf-only")
    output = tmp_path / "predictions.json"
    client = _Client()

    capture_cases(
        client,
        cases=[{"case_id": "blind-001", "split": "development", "dxf_path": source}],
        output_path=output,
        poll_interval_s=0,
        evaluation_phase="unit",
    )

    frozen = load_frozen_prediction_bundle(output)
    assert client.uploads == 1
    assert frozen["runtime_config"]["config_evidence"]["job_timeout_s"] == 600
    assert frozen["runtime_config"]["config_evidence"]["reviewer_model"] == "gpt-6-astra"
    assert frozen["cases"][0]["prediction"]["job_state"] == "succeeded"
    assert frozen["cases"][0]["split"] == "development"
    assert frozen["cases"][0]["prediction"]["derived"]["bom_rows"] == []


def test_capture_rejects_non_production_timeout_before_upload(tmp_path: Path) -> None:
    source = tmp_path / "blind-001.dxf"
    source.write_bytes(b"public-dxf-only")
    client = _Client(timeout=300)

    with pytest.raises(ValueError, match="job_timeout_s=600"):
        capture_cases(
            client,
            cases=[{"case_id": "blind-001", "dxf_path": source}],
            output_path=tmp_path / "predictions.json",
            poll_interval_s=0,
            evaluation_phase="unit",
        )
    assert client.uploads == 0

