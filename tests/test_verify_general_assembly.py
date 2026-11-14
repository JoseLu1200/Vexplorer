from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from tools.verify_general_assembly import VerificationFailure, verify_existing_run


RUN_ID = "run-public-case"


def _general() -> dict:
    return {"data": {"status": "reviewed_incomplete", "proposal_revision": 2,
                     "review_revision": 3, "draft": {"components": []}}}


def _attempt(status: str = "validated", valid: bool = True) -> dict:
    return {"run_id": RUN_ID, "proposal_revision": 2,
                     "review_revision": 3, "assembly_revision": 1,
                     "status": status, "report": {
                         "status": "accepted" if valid else "rejected", "issues": []},
                     "candidate": {"occurrences": [{"occurrence_id": "side-1"}]},
                     "trace": [{"tool_name": "evaluate", "ok": valid}]}


def _derived(placed: bool = True) -> dict:
    items = ([{"occurrence_id": "side-1", "position_mm": [0, 0, 0]}]
             if placed else [])
    return {"data": {"package": {"proposal_revision": 2, "review_revision": 3,
                                   "scene": {"status": "assembly_validated" if placed else "schematic_incomplete",
                                             "items": items}}}}


def _state(attempt: dict) -> dict:
    accepted = attempt["report"]["status"] == "accepted"
    return {
        "status": "accepted" if accepted else "incomplete",
        "current": attempt,
        "accepted_alternatives": [attempt] if accepted else [],
        "ambiguous": False,
    }


def test_freezes_exact_revision_before_evaluation_with_content_hash(tmp_path) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/general"):
            return httpx.Response(200, json=_general())
        if request.url.path.endswith("/general/assembly/retry"):
            assert json.loads(request.content) == {"base_proposal_revision": 2,
                                                   "base_review_revision": 3}
            assert request.headers["Idempotency-Key"].startswith(
                "assembly-verify-public-plank-030-"
            )
            assert len(request.headers["Idempotency-Key"]) <= 128
            return httpx.Response(202, json={"data": {"id": "job-assembly"}})
        if request.url.path.endswith("/jobs/job-assembly"):
            return httpx.Response(200, json={"data": {"id": "job-assembly",
                                                       "state": "succeeded", "run_id": RUN_ID}})
        if request.url.path.endswith("/general/assembly"):
            assert dict(request.url.params) == {"proposal_revision": "2", "review_revision": "3"}
            return httpx.Response(200, json=_state(_attempt()))
        if request.url.path.endswith("/general/derived"):
            return httpx.Response(200, json=_derived())
        return httpx.Response(404)

    with httpx.Client(base_url="https://assembly.test",
                      transport=httpx.MockTransport(handler)) as client:
        summary = verify_existing_run(client, RUN_ID, output_dir=tmp_path,
                                      case_id="public-plank-030",
                                      expected_outcome="validated", poll_interval_s=0)

    snapshot = tmp_path / "public-plank-030-pre-evaluation.json"
    encoded = snapshot.read_bytes()
    digest = hashlib.sha256(encoded).hexdigest()
    assert (tmp_path / "public-plank-030-pre-evaluation.sha256").read_text("ascii") == f"{digest}  {snapshot.name}\n"
    assert summary["frozen_sha256"] == digest
    assert summary["assembly_revision"] == 1
    assert json.loads(encoded)["phase"] == "pre_private_evaluation"
    assert len(seen) == 5


def test_rejected_attempt_is_frozen_and_cannot_leak_into_scene(tmp_path) -> None:
    rejected = _attempt("rejected", False)
    rejected["report"]["issues"] = [{"code": "penetration"}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/general"):
            return httpx.Response(200, json=_general())
        if request.url.path.endswith("/general/assembly/retry"):
            return httpx.Response(202, json={"data": {"id": "job-rejected"}})
        if request.url.path.endswith("/jobs/job-rejected"):
            return httpx.Response(200, json={"data": {"id": "job-rejected",
                                                       "state": "failed", "run_id": RUN_ID}})
        if request.url.path.endswith("/general/assembly"):
            return httpx.Response(200, json=_state(rejected))
        if request.url.path.endswith("/general/derived"):
            return httpx.Response(200, json=_derived(False))
        return httpx.Response(404)

    with httpx.Client(base_url="https://assembly.test",
                      transport=httpx.MockTransport(handler)) as client:
        summary = verify_existing_run(client, RUN_ID, output_dir=tmp_path,
                                      case_id="insufficient-control",
                                      expected_outcome="abstained", poll_interval_s=0)
    frozen = json.loads((tmp_path / "insufficient-control-pre-evaluation.json").read_text("utf-8"))
    assert summary["outcome"] == "abstained"
    assert frozen["assembly_attempt"]["trace"]
    assert frozen["assembly_state"]["current"] == frozen["assembly_attempt"]
    assert frozen["assembly_attempt"]["report"]["issues"] == [{"code": "penetration"}]
    assert frozen["derived"]["package"]["scene"]["items"] == []


def test_refuses_to_overwrite_a_frozen_result(tmp_path) -> None:
    (tmp_path / "case-pre-evaluation.json").write_text("existing", encoding="utf-8")
    with httpx.Client(base_url="https://assembly.test") as client:
        with pytest.raises(VerificationFailure, match="frozen_output_exists"):
            verify_existing_run(client, RUN_ID, output_dir=tmp_path, case_id="case",
                                expected_outcome="validated")


def test_rejects_attempt_from_a_different_review_revision(tmp_path) -> None:
    wrong = _attempt()
    wrong["review_revision"] = 4

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/general"):
            return httpx.Response(200, json=_general())
        if request.url.path.endswith("/general/assembly/retry"):
            return httpx.Response(202, json={"data": {"id": "job-stale"}})
        if request.url.path.endswith("/jobs/job-stale"):
            return httpx.Response(200, json={"data": {"id": "job-stale",
                                                       "state": "succeeded", "run_id": RUN_ID}})
        if request.url.path.endswith("/general/assembly"):
            return httpx.Response(200, json=_state(wrong))
        return httpx.Response(404)

    with httpx.Client(base_url="https://assembly.test",
                      transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VerificationFailure, match="attempt_revision_mismatch"):
            verify_existing_run(client, RUN_ID, output_dir=tmp_path, case_id="stale",
                                expected_outcome="validated", poll_interval_s=0)
    assert not (tmp_path / "stale-pre-evaluation.json").exists()
