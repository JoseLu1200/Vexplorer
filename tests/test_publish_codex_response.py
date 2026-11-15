from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from tools.publish_codex_response import PublishError, publish_response


def _request(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "name": "proponer",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "detail_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                            "required": ["detail_ids"],
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _candidate(path: Path, arguments: object) -> Path:
    path.write_text(
        json.dumps(
            {
                "id": "codex-response-1",
                "tool_calls": [
                    {
                        "call_id": "call-1",
                        "name": "proponer",
                        "arguments": arguments,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_valid_candidate_is_published_atomically_without_rewriting_bytes(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path / "request.json")
    candidate = _candidate(tmp_path / "candidate.json", {"detail_ids": ["d1"]})
    original = candidate.read_bytes()

    response = publish_response(request, candidate)

    assert response == tmp_path / "response.json"
    assert response.read_bytes() == original
    assert candidate.read_bytes() == original
    assert not list(tmp_path.glob(".response.json.*.tmp"))


def test_schema_error_reports_exact_path_and_does_not_publish(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    candidate = _candidate(tmp_path / "candidate.json", {"detail_ids": None})

    with pytest.raises(
        PublishError,
        match=r"tool_calls/0/arguments/detail_ids: None is not of type 'array'",
    ):
        publish_response(request, candidate)

    assert not (tmp_path / "response.json").exists()


def test_existing_response_is_never_overwritten(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    candidate = _candidate(tmp_path / "candidate.json", {"detail_ids": ["d1"]})
    response = tmp_path / "response.json"
    response.write_bytes(b"already-consumed")

    with pytest.raises(PublishError, match="response_already_exists"):
        publish_response(request, candidate)

    assert response.read_bytes() == b"already-consumed"


def test_undeclared_tool_is_rejected_before_publication(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    candidate = _candidate(tmp_path / "candidate.json", {"detail_ids": []})
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["tool_calls"][0]["name"] = "otra_herramienta"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PublishError, match="undeclared_tool:otra_herramienta"):
        publish_response(request, candidate)

    assert not (tmp_path / "response.json").exists()


def test_cli_returns_local_schema_error_without_publishing(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    candidate = _candidate(tmp_path / "candidate.json", {"detail_ids": "d1"})

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.publish_codex_response",
            "--request",
            str(request),
            "--candidate",
            str(candidate),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "tool_calls/0/arguments/detail_ids" in completed.stderr
    assert not (tmp_path / "response.json").exists()


def test_remote_schema_reference_is_rejected_without_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path / "request.json")
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["tools"][0]["parameters"] = {
        "$ref": "https://schemas.example.invalid/tool.json"
    }
    request.write_text(json.dumps(payload), encoding="utf-8")
    candidate = _candidate(tmp_path / "candidate.json", {"detail_ids": []})
    network_attempts = []

    def fail_network(*args, **kwargs):
        network_attempts.append((args, kwargs))
        raise AssertionError("network access attempted")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)

    with pytest.raises(PublishError, match="unresolvable_schema_reference"):
        publish_response(request, candidate)

    assert network_attempts == []
    assert not (tmp_path / "response.json").exists()
