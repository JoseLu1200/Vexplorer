import json
import zipfile
from pathlib import Path

import pytest

from backend.app.agente.config import ProviderSettings
from backend.app.general_furniture.autonomous import GeneralAutonomousError
import tools.run_general_benchmark as benchmark
from tools.run_general_benchmark import (
    export_prediction_manifests,
    freeze_paired_outcome,
    load_public_sources,
)


def _bundle(path: Path, *, case_id: str = "plank-011", metadata_extra: dict | None = None) -> None:
    metadata = {
        "id": case_id,
        "file": "input.dxf",
        "format": "dxf",
        "unit": "mm",
        "view_kind": "assembled_orthographic",
        "instruction": (
            "Use only geometry visible in the assembled orthographic views. "
            "Keep unsupported identity, dimensions, roles and quantities unknown."
        ),
        "sha256": "placeholder",
    }
    raw = b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
    import hashlib

    metadata["sha256"] = hashlib.sha256(raw).hexdigest()
    metadata.update(metadata_extra or {})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("input.dxf", raw)
        archive.writestr("case.json", json.dumps(metadata))


def test_baseline_is_frozen_before_critic_and_survives_provider_failure(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-1"
    case_dir.mkdir()
    calls: list[str] = []

    def first_pass():
        calls.append("first")
        return {"proposal": "p1", "tool_actions": [{"tool": "inspect", "ok": True}]}

    def failing_critic(baseline):
        assert baseline["proposal"] == "p1"
        assert (case_dir / "baseline.json").is_file()
        calls.append("critic")
        raise RuntimeError("provider_request_failed")

    result = freeze_paired_outcome(
        case_id="case-1",
        case_dir=case_dir,
        metadata={"input_sha256": "a" * 64},
        first_pass=first_pass,
        critic=failing_critic,
    )

    assert calls == ["first", "critic"]
    assert result["status"] == "failed_after_baseline"
    assert result["baseline_sha256"]
    assert (case_dir / "baseline.json").is_file()
    assert not (case_dir / "final.json").exists()
    failure = json.loads((case_dir / "failure.json").read_text(encoding="utf-8"))
    assert failure["baseline_sha256"] == result["baseline_sha256"]
    assert failure["failure_type"] == "RuntimeError"
    assert "provider_request_failed" in failure["message"]


def test_critic_failure_records_only_structured_action_evidence(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-2"
    case_dir.mkdir()

    result = freeze_paired_outcome(
        case_id="case-2",
        case_dir=case_dir,
        metadata={"input_sha256": "b" * 64},
        first_pass=lambda: {"proposal": "p1"},
        critic=lambda _baseline: (_ for _ in ()).throw(
            GeneralAutonomousError(
                "general_auto_review_exhausted",
                trace=({"event": "tool_rejected", "tool": "entregar_revision_autonoma"},),
                model_calls=2,
                tool_calls=1,
            )
        ),
    )

    failure = json.loads((case_dir / "failure.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed_after_baseline"
    assert failure["action_evidence"] == {
        "model_calls": 2,
        "tool_calls": 1,
        "trace": [{"event": "tool_rejected", "tool": "entregar_revision_autonoma"}],
    }


def test_strict_bundle_validation_rejects_hostile_members_and_metadata_before_staging(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    staged = tmp_path / "staged"

    hostile = bundle_dir / "plank-011.zip"
    with zipfile.ZipFile(hostile, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("input.dxf", b"0\nEOF\n")
        archive.writestr("case.json", "{}")
        archive.writestr("../private-reference.json", "secret")
    with pytest.raises(ValueError, match="unexpected_public_bundle_members"):
        load_public_sources(bundle_dir, staged, strict_bundles=True)
    assert not staged.exists()

    hostile.unlink()
    _bundle(hostile, metadata_extra={"reference_path": "private/reference.json"})
    with pytest.raises(ValueError, match="unexpected_public_bundle_metadata"):
        load_public_sources(bundle_dir, staged, strict_bundles=True)
    assert not staged.exists()

    hostile.unlink()
    with zipfile.ZipFile(hostile, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("input.dxf", b"0\nEOF\n")
        archive.writestr("case.json", "x" * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="public_bundle_member_too_large"):
        load_public_sources(bundle_dir, staged, strict_bundles=True)
    assert not staged.exists()


def test_valid_bundle_stages_only_hash_verified_dxf(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    _bundle(bundle_dir / "plank-011.zip")

    sources = load_public_sources(bundle_dir, tmp_path / "staged", strict_bundles=True)

    assert [path.name for path in sources] == ["plank-011.dxf"]
    assert {path.name for path in (tmp_path / "staged").iterdir()} == {"plank-011.dxf"}


def test_code_fingerprint_includes_runner_and_native_backend() -> None:
    fingerprints = benchmark.tracked_code_fingerprints()

    assert "tools/run_general_benchmark.py" in fingerprints
    assert "backend/app/general_furniture/autonomous.py" in fingerprints
    assert all(len(digest) == 64 for digest in fingerprints.values())


def test_exporter_maps_native_states_and_auto_review_without_promoting_certainty(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "case-1"
    case_dir.mkdir()
    value = {"value_mm": 600.0, "state": "hypothesis"}
    quantity = {"value": 2, "state": "hypothesis"}
    (case_dir / "baseline.json").write_text(
        json.dumps(
            {
                "outcome": {
                    "proposal": {"id": "proposal-1"},
                    "draft": {
                        "components": [
                            {
                                "id": "panel-1",
                                "length": value,
                                "width": value | {"value_mm": 400.0},
                                "thickness": value | {"value_mm": 18.0},
                                "quantity": quantity,
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "final.json").write_text(
        json.dumps(
            {
                "outcome": {
                    "review": {
                        "components": [
                            {
                                "id": "panel-1-reviewed",
                                "length": value,
                                "width": value | {"value_mm": 400.0},
                                "thickness": value | {"value_mm": 18.0},
                                "quantity": quantity,
                            }
                        ],
                        "machine_field_reviews": [
                            {
                                "target_ref": "component:panel-1-reviewed.length",
                                "status": "accepted",
                            },
                            {
                                "target_ref": "component:panel-1-reviewed.width",
                                "status": "rejected",
                            },
                            {
                                "target_ref": "component:panel-1-reviewed.quantity",
                                "status": "abstained",
                            },
                        ],
                        "auto_review_status": "incomplete",
                    },
                    "critic_snapshots": [
                        {"scenario_id": "critic-scenario-1", "status": "incomplete"}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    hashes = export_prediction_manifests(
        tmp_path,
        dataset_id="public-cohort-v1",
        case_ids=("case-1", "failed-case"),
    )

    baseline = json.loads((tmp_path / "baseline-predictions.json").read_text(encoding="utf-8"))
    final = json.loads((tmp_path / "final-predictions.json").read_text(encoding="utf-8"))
    assert hashes.keys() == {"baseline_predictions_sha256", "final_predictions_sha256"}
    assert baseline["dataset_id"] == final["dataset_id"] == "public-cohort-v1"
    assert baseline["cases"][0]["components"][0]["quantity_state"] == "hypothesis"
    assert baseline["cases"][0]["components"][0]["quantity_review_status"] == "unreviewed"
    reviewed = final["cases"][0]["components"][0]
    assert reviewed["quantity"] is None
    assert reviewed["quantity_state"] == "unknown"
    assert reviewed["quantity_review_status"] == "auto_reviewed"
    assert reviewed["dimensions_mm"] == {
        "length": 600.0,
        "width": None,
        "thickness": None,
    }
    assert reviewed["dimension_states"] == {
        "length": "hypothesis",
        "width": "unknown",
        "thickness": "unknown",
    }
    assert reviewed["dimension_review_statuses"] == {
        "length": "auto_reviewed",
        "width": "auto_reviewed",
        "thickness": "unreviewed",
    }
    assert final["cases"][0]["scenarios"] == [
        {"key": "critic-scenario-1", "state": "hypothesis", "review_status": "auto_reviewed"}
    ]
    assert baseline["cases"][1]["components"] == []
    assert final["cases"][1]["components"] == []


def test_case_setup_failure_is_frozen_and_does_not_abort_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "broken-case.dxf"
    source.write_bytes(b"broken")
    output = tmp_path / "output"
    output.mkdir()

    def fail_setup(*_args, **_kwargs):
        raise ValueError("drawing_extract_failed")

    monkeypatch.setattr(benchmark, "_run_case", fail_setup)
    result = benchmark._run_case_safely(
        source,
        output,
        None,
        None,
        total_timeout_s=300,
        max_review_calls=5,
        max_validation_repairs=2,
    )

    assert result["status"] == "failed_before_baseline"
    failure = json.loads(
        (output / "broken-case" / "failure.json").read_text(encoding="utf-8")
    )
    assert failure["input_sha256"]
    assert failure["failure_type"] == "ValueError"


def test_cli_freezes_scoreable_paired_manifests_before_final_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "case-1.dxf").write_bytes(b"0\nEOF\n")
    output = tmp_path / "run"

    settings = ProviderSettings(api_key="not-logged", model="placeholder")
    monkeypatch.setattr(
        benchmark.ProviderSettings,
        "from_env",
        classmethod(lambda _cls: settings),
    )

    def fake_case(source, destination, *_args, **_kwargs):
        case_dir = destination / source.stem
        case_dir.mkdir()
        baseline = {
            "outcome": {
                "proposal": {"id": "proposal-1"},
                "draft": {"components": []},
            }
        }
        final = {
            "outcome": {
                "review": {"components": [], "machine_field_reviews": []},
                "critic_snapshots": [],
            }
        }
        (case_dir / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
        (case_dir / "final.json").write_text(json.dumps(final), encoding="utf-8")
        return {"case_id": source.stem, "status": "succeeded"}

    monkeypatch.setattr(benchmark, "_run_case_safely", fake_case)
    assert benchmark.main(
        [
            "--input",
            str(inputs),
            "--output",
            str(output),
            "--dataset-id",
            "public-cohort-v1",
            "--workers",
            "1",
        ]
    ) == 0

    frozen = json.loads((output / "frozen-manifest.json").read_text(encoding="utf-8"))
    assert (output / "baseline-predictions.json").is_file()
    assert (output / "final-predictions.json").is_file()
    assert frozen["prediction_manifests"]["baseline_predictions_sha256"]
    assert "baseline-predictions.json" in frozen["files"]
    assert "final-predictions.json" in frozen["files"]
    assert "not-logged" not in json.dumps(frozen)
