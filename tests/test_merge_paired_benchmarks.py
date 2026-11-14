from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.evaluate_semantic import freeze_paired_semantic_outputs
from tools.merge_paired_benchmarks import MergeError, merge_paired_benchmarks


def _write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _proposal(case_id: str) -> dict[str, object]:
    dimension = {"value_mm": 100.0, "state": "hypothesis"}
    return {"components": [{"id": f"c-{case_id}", "label": "Panel", "role": "panel", "quantity": {"value": 1, "state": "hypothesis"}, "length": dimension, "width": dimension, "thickness": dimension}], "assembly_relations": [], "assembly_alternatives": []}


def _run(root: Path, cases: dict[str, str], *, dataset: str = "heldout-v1", code: str = "a") -> None:
    sources = {case_id: hashlib.sha256(f"input:{case_id}".encode()).hexdigest() for case_id in cases}
    _write(root / "configuration.json", {"dataset_id": dataset, "source_sha256": sources, "code_sha256": {"backend/app/main.py": code * 64}, "private_reference_access": False})
    results = []
    for case_id, status in cases.items():
        source = f"input:{case_id}".encode()
        input_path = root / "public-inputs" / f"{case_id}.dxf"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(source)
        case_dir = root / case_id
        case_dir.mkdir()
        if status in {"succeeded", "failed_after_baseline"}:
            baseline_sha = _write(case_dir / "baseline.json", {"case_id": case_id, "input_sha256": sources[case_id], "outcome": {"proposal": {"id": f"proposal-{case_id}", **_proposal(case_id)}, "draft": _proposal(case_id)}})
        if status == "succeeded":
            final_sha = _write(case_dir / "final.json", {"case_id": case_id, "input_sha256": sources[case_id], "baseline_sha256": baseline_sha, "outcome": {"effective_proposal_outcome": {"proposal": _proposal(case_id)}, "review": {"components": _proposal(case_id)["components"], "machine_field_reviews": [], "auto_review_status": "incomplete"}, "critic_snapshots": []}})
            results.append({"case_id": case_id, "status": status, "baseline_sha256": baseline_sha, "final_sha256": final_sha})
        else:
            failure = {"case_id": case_id, "input_sha256": sources[case_id], "status": status, "failure_type": "ValueError" if status == "failed_before_baseline" else "RuntimeError", "message": "visual_evidence_budget_exceeded" if status == "failed_before_baseline" else "provider_failed"}
            if status == "failed_after_baseline":
                failure["baseline_sha256"] = baseline_sha
            _write(case_dir / "failure.json", failure)
            result = {"case_id": case_id, "status": status}
            if status == "failed_after_baseline":
                result["baseline_sha256"] = baseline_sha
            results.append(result)
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*")) if path.is_file()}
    _write(root / "frozen-manifest.json", {"results": results, "files": files})


def _tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _manifest_sha(root: Path) -> str:
    return hashlib.sha256((root / "frozen-manifest.json").read_bytes()).hexdigest()


def _merge(original: Path, retry: Path, destination: Path, *, frozen_at: str) -> None:
    merge_paired_benchmarks(
        original,
        retry,
        destination,
        frozen_at=frozen_at,
        original_manifest_sha256=_manifest_sha(original),
        retry_manifest_sha256=_manifest_sha(retry),
    )


def test_merge_is_reproducible_preserves_denominator_and_semantic_compatibility(tmp_path: Path) -> None:
    original, retry = tmp_path / "original", tmp_path / "retry"
    _run(original, {"sx015": "succeeded", "sx016": "failed_before_baseline"}, code="a")
    _run(retry, {"sx016": "succeeded"}, code="b")
    first, second = tmp_path / "merged-a", tmp_path / "merged-b"
    for destination in (first, second):
        _merge(original, retry, destination, frozen_at="2026-11-14T08:00:00Z")

    assert _tree(first) == _tree(second)
    assert (first / "sx015" / "final.json").read_bytes() == (original / "sx015" / "final.json").read_bytes()
    assert (first / "sx016" / "final.json").read_bytes() == (retry / "sx016" / "final.json").read_bytes()
    assert (first / "merge-provenance/original-failures/sx016/failure.json").read_bytes() == (original / "sx016/failure.json").read_bytes()
    for origin in ("original", "retry"):
        assert (first / f"merge-provenance/{origin}/configuration.json").read_bytes() == ((original if origin == "original" else retry) / "configuration.json").read_bytes()
        assert (first / f"merge-provenance/{origin}/frozen-manifest.json").is_file()
    config = json.loads((first / "configuration.json").read_text())
    assert set(config["source_sha256"]) == {"sx015", "sx016"}
    assert config["code_sha256"] == {}
    assert config["selection_policy"] == "operational_recovery_of_original_preprovider_failures_v1"
    assert config["retry_qualification"]["qualified_case_ids"] == ["sx016"]
    assert config["per_case_provenance"]["sx016"]["recovery_qualification"]["no_provider_action_evidence"] is True
    assert config["per_case_provenance"]["sx015"]["origin"] == "original"
    assert config["per_case_provenance"]["sx016"]["origin"] == "retry"
    semantic = freeze_paired_semantic_outputs(first, tmp_path / "semantic")
    assert [case["scenario_id"] for case in json.loads(semantic["final"].read_text())["cases"]] == ["sx015", "sx016"]


def test_retry_failure_is_latest_outcome_and_original_failure_is_archived(tmp_path: Path) -> None:
    original, retry = tmp_path / "original", tmp_path / "retry"
    _run(original, {"sx015": "succeeded", "sx016": "failed_before_baseline"})
    _run(retry, {"sx016": "failed_before_baseline"}, code="b")
    destination = tmp_path / "merged"
    _merge(original, retry, destination, frozen_at="fixed")
    manifest = json.loads((destination / "frozen-manifest.json").read_text())
    statuses = {item["case_id"]: item["status"] for item in manifest["results"]}
    assert statuses == {"sx015": "succeeded", "sx016": "failed_before_baseline"}
    assert (destination / "sx016/failure.json").read_bytes() == (retry / "sx016/failure.json").read_bytes()
    assert (destination / "merge-provenance/original-failures/sx016/failure.json").is_file()


@pytest.mark.parametrize("status", ["succeeded", "failed_after_baseline"])
def test_retry_rejects_any_case_not_original_preprovider_failure(tmp_path: Path, status: str) -> None:
    original, retry = tmp_path / "original", tmp_path / "retry"
    _run(original, {"sx015": status, "sx016": "failed_before_baseline"})
    _run(retry, {"sx015": "succeeded"}, code="b")
    with pytest.raises(MergeError, match="retry may only select original failed_before_baseline"):
        _merge(original, retry, tmp_path / "merged", frozen_at="fixed")


@pytest.mark.parametrize("fault", ["tamper", "source", "reference"])
def test_merge_rejects_unverified_mismatched_or_reference_inputs(tmp_path: Path, fault: str) -> None:
    original, retry = tmp_path / "original", tmp_path / "retry"
    _run(original, {"sx016": "failed_before_baseline"})
    _run(retry, {"sx016": "succeeded"}, code="b")
    if fault == "tamper":
        (retry / "sx016/final.json").write_text("{}")
        match = "frozen hash mismatch"
    elif fault == "source":
        config = json.loads((retry / "configuration.json").read_text())
        config["source_sha256"]["sx016"] = "f" * 64
        _write(retry / "configuration.json", config)
        manifest = json.loads((retry / "frozen-manifest.json").read_text())
        manifest["files"]["configuration.json"] = hashlib.sha256((retry / "configuration.json").read_bytes()).hexdigest()
        _write(retry / "frozen-manifest.json", manifest)
        match = "public input hash mismatch"
    else:
        _write(retry / "private-reference.json", {"answer": 1})
        manifest = json.loads((retry / "frozen-manifest.json").read_text())
        manifest["files"]["private-reference.json"] = hashlib.sha256((retry / "private-reference.json").read_bytes()).hexdigest()
        _write(retry / "frozen-manifest.json", manifest)
        match = "forbidden frozen path"
    with pytest.raises(MergeError, match=match):
        _merge(original, retry, tmp_path / "merged", frozen_at="fixed")


def test_merge_requires_independently_expected_manifest_hashes(tmp_path: Path) -> None:
    original, retry = tmp_path / "original", tmp_path / "retry"
    _run(original, {"sx015": "succeeded", "sx016": "failed_before_baseline"})
    _run(retry, {"sx016": "succeeded"}, code="b")
    with pytest.raises(MergeError, match="frozen manifest hash mismatch"):
        merge_paired_benchmarks(
            original,
            retry,
            tmp_path / "merged",
            frozen_at="fixed",
            original_manifest_sha256="0" * 64,
            retry_manifest_sha256=_manifest_sha(retry),
        )


@pytest.mark.parametrize(
    ("failure_type", "extra"),
    [
        ("ProviderError", {}),
        ("GeneralLiveError", {"model_calls": 1, "tool_calls": 0}),
        ("ValueError", {"action_evidence": {"model_calls": 1}}),
    ],
)
def test_merge_rejects_retry_when_original_failure_may_have_called_provider(
    tmp_path: Path, failure_type: str, extra: dict[str, object]
) -> None:
    original, retry = tmp_path / "original", tmp_path / "retry"
    _run(original, {"sx015": "succeeded", "sx016": "failed_before_baseline"})
    _run(retry, {"sx016": "succeeded"}, code="b")
    failure_path = original / "sx016/failure.json"
    failure = json.loads(failure_path.read_text())
    failure.update({"failure_type": failure_type, **extra})
    _write(failure_path, failure)
    manifest = json.loads((original / "frozen-manifest.json").read_text())
    manifest["files"]["sx016/failure.json"] = hashlib.sha256(failure_path.read_bytes()).hexdigest()
    _write(original / "frozen-manifest.json", manifest)

    with pytest.raises(MergeError, match="not a qualified pre-provider visual budget failure"):
        _merge(original, retry, tmp_path / "merged", frozen_at="fixed")
