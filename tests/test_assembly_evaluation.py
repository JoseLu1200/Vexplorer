from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from evaluation.assembly import (
    AssemblyEvaluationError,
    evaluate_assembly,
    evaluate_assembly_files,
)


ROTATE_Z_90 = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]


# Independently specified physical occurrences. The varied dimensions and
# irregular positions make the fixture asymmetric and prevent accidental
# per-piece alignment from satisfying the checks.
PIECES_16 = [
    ("p01", [0, 0, 0], [18, 410, 703]),
    ("p02", [982, 7, 3], [18, 397, 701]),
    ("p03", [21, 11, 682], [957, 391, 21]),
    ("p04", [23, 15, 94], [951, 383, 19]),
    ("p05", [29, 19, 211], [943, 379, 17]),
    ("p06", [31, 23, 337], [937, 373, 23]),
    ("p07", [37, 29, 509], [929, 367, 13]),
    ("p08", [47, 43, 31], [211, 29, 317]),
    ("p09", [719, 53, 41], [233, 31, 293]),
    ("p10", [271, 61, 67], [401, 37, 173]),
    ("p11", [73, 311, 83], [157, 43, 263]),
    ("p12", [797, 277, 101], [149, 47, 251]),
    ("p13", [307, 109, 419], [359, 53, 137]),
    ("p14", [113, 127, 571], [271, 59, 89]),
    ("p15", [607, 139, 593], [313, 61, 71]),
    ("p16", [421, 151, 257], [167, 67, 109]),
]


def _scene(rows=PIECES_16):
    return {
        "pieces": [
            {
                "id": identifier,
                "position_mm": position,
                "position_kind": "local_corner",
                "dimensions_mm": {
                    "length": dimensions[0],
                    "width": dimensions[1],
                    "thickness": dimensions[2],
                },
                "orientation": {
                    "length": [1, 0, 0],
                    "width": [0, 1, 0],
                    "thickness": [0, 0, 1],
                },
            }
            for identifier, position, dimensions in rows
        ]
    }


def _transform_scene(scene, rotation, translation):
    transformed = copy.deepcopy(scene)
    for piece in transformed["pieces"]:
        position = piece["position_mm"]
        piece["position_mm"] = [
            sum(rotation[row][column] * position[column] for column in range(3))
            + translation[row]
            for row in range(3)
        ]
        for name in ("length", "width", "thickness"):
            axis = piece["orientation"][name]
            piece["orientation"][name] = [
                sum(rotation[row][column] * axis[column] for column in range(3))
                for row in range(3)
            ]
    transformed["pieces"].reverse()
    return transformed


def test_matches_all_16_occurrences_after_one_global_proper_transform() -> None:
    reference = _scene()
    prediction = _transform_scene(reference, ROTATE_Z_90, [321, -117, 53])

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is True
    assert report["counts"] == {
        "reference": 16,
        "predicted": 16,
        "matched": 16,
        "missing": 0,
        "extra": 0,
    }
    assert report["coverage"] == 1.0
    assert report["center_error_mm"]["max"] == pytest.approx(0.0, abs=1e-8)
    assert report["face_error_mm"]["max"] == pytest.approx(0.0, abs=1e-8)
    assert report["dimension_error_mm"]["max"] == pytest.approx(0.0, abs=1e-8)
    assert report["orientation"]["all_normals_agree"] is True
    assert report["alignment"]["determinant"] == 1


@pytest.mark.parametrize("fault", ["moved", "rotated"])
def test_one_wrong_occurrence_cannot_be_hidden_by_per_piece_alignment(fault: str) -> None:
    reference = _scene()
    prediction = copy.deepcopy(reference)
    piece = prediction["pieces"][7]
    if fault == "moved":
        piece["position_mm"][0] += 3.0
    else:
        piece["orientation"] = {
            "length": [0, 1, 0],
            "width": [-1, 0, 0],
            "thickness": [0, 0, 1],
        }

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is False
    if fault == "moved":
        # The single least-squares translation distributes 3 mm over all 16
        # boxes, but cannot hide the outlier below the 1 mm threshold.
        assert report["center_error_mm"]["max"] >= 2.8
    else:
        assert report["orientation"]["all_axes_equivalent"] is False


@pytest.mark.parametrize("fault", ["missing", "extra"])
def test_missing_and_extra_occurrences_fail_coverage(fault: str) -> None:
    reference = _scene()
    prediction = copy.deepcopy(reference)
    if fault == "missing":
        prediction["pieces"].pop()
    else:
        extra = copy.deepcopy(prediction["pieces"][0])
        extra["id"] = "extra"
        extra["position_mm"] = [1700, 900, 800]
        prediction["pieces"].append(extra)

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is False
    assert report["counts"][fault] == 1
    if fault == "missing":
        assert report["coverage"] < 1.0
    else:
        assert report["precision"] < 1.0


def test_global_reflection_is_not_accepted_for_asymmetric_fixture() -> None:
    reference = _scene()
    reflected = copy.deepcopy(reference)
    for piece in reflected["pieces"]:
        dimensions = piece["dimensions_mm"]
        center = [
            piece["position_mm"][0] + dimensions["length"] / 2,
            piece["position_mm"][1] + dimensions["width"] / 2,
            piece["position_mm"][2] + dimensions["thickness"] / 2,
        ]
        piece["position_mm"] = [-center[0], center[1], center[2]]
        piece["position_kind"] = "center"
        # Axis signs do not change a box, and the second sign flip keeps each
        # local frame proper while the whole asymmetric fixture is mirrored.
        piece["orientation"] = {
            "length": [-1, 0, 0],
            "width": [0, 1, 0],
            "thickness": [0, 0, -1],
        }

    report = evaluate_assembly(reflected, reference)

    assert report["passed"] is False
    assert report["alignment"]["determinant"] == 1
    assert report["center_error_mm"]["max"] >= 1.0


def test_square_panel_accepts_indistinguishable_in_plane_axis_swap() -> None:
    reference = {
        "pieces": [{
            "id": "square",
            "position_mm": [10, 20, 30],
            "position_kind": "center",
            "dimensions_mm": {"length": 100, "width": 100, "thickness": 10},
            "orientation": {
                "length": [1, 0, 0], "width": [0, 1, 0], "thickness": [0, 0, 1]
            },
        }]
    }
    prediction = copy.deepcopy(reference)
    prediction["pieces"][0]["orientation"] = {
        "length": [0, 1, 0], "width": [-1, 0, 0], "thickness": [0, 0, 1]
    }

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is True
    assert report["orientation"]["all_axes_equivalent"] is True


def test_core_report_aabb_min_and_world_extents_adapter_is_explicit() -> None:
    core_report = {
        "placements": [{
            "occurrence_id": "door-1",
            "position_mm": {"x": 10, "y": 20, "z": 0},
            "size_mm": {"x": 100, "y": 200, "z": 15},
            "orientation": {
                "length_axis": "+y",
                "width_axis": "-x",
                "thickness_axis": "+z",
            },
        }]
    }
    canonical_reference = {
        "pieces": [{
            "id": "door-reference",
            "position_mm": [60, 120, 7.5],
            "position_kind": "center",
            "dimensions_mm": {"length": 200, "width": 100, "thickness": 15},
            "orientation": {
                "length": [0, 1, 0], "width": [-1, 0, 0], "thickness": [0, 0, 1]
            },
        }]
    }

    # The verifier freezes the complete public wrapper without reconstructing
    # placements: assembly_attempt.report.placements.
    frozen_wrapper = {"assembly_attempt": {"report": core_report}}
    assert evaluate_assembly(frozen_wrapper, canonical_reference)["passed"] is True


def test_reports_unexplained_penetration_over_tolerance() -> None:
    reference = _scene(PIECES_16[:2])
    prediction = copy.deepcopy(reference)
    prediction["pieces"][1]["position_mm"] = [10, 10, 10]

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is False
    assert report["penetration"]["predicted_max_mm"] > 1.0
    assert report["penetration"]["predicted_pairs_over_tolerance"] == 1
    assert report["penetration"]["max_unexplained_mm"] > 1.0
    assert report["penetration"]["unexplained_pairs"] == 1


def test_reference_present_overlap_is_reported_raw_even_when_not_unexplained() -> None:
    overlapping = _scene([
        ("a", [0, 0, 0], [10, 20, 30]),
        ("b", [5, 0, 0], [10, 20, 30]),
    ])

    report = evaluate_assembly(copy.deepcopy(overlapping), overlapping)

    assert report["penetration"] == {
        "predicted_max_mm": 5.0,
        "predicted_pairs_over_tolerance": 1,
        "reference_max_mm": 5.0,
        "reference_pairs_over_tolerance": 1,
        "max_unexplained_mm": 0.0,
        "unexplained_pairs": 0,
    }
    assert report["passes_reference_relative_acceptance"] is True
    assert report["collision_free_at_tolerance"] is False


@pytest.mark.parametrize("invalid_width", [[1, 0, 0], [0, -1, 0]])
def test_rejects_non_orthogonal_or_left_handed_piece_frame(invalid_width) -> None:
    scene = _scene(PIECES_16[:1])
    scene["pieces"][0]["orientation"]["width"] = invalid_width

    with pytest.raises(AssemblyEvaluationError, match="proper orthogonal"):
        evaluate_assembly(scene, _scene(PIECES_16[:1]))


def test_duplicate_geometry_still_uses_each_reference_exactly_once() -> None:
    reference = _scene([
        ("left", [0, 0, 0], [10, 20, 30]),
        ("right", [100, 0, 0], [10, 20, 30]),
    ])
    prediction = _scene([
        ("candidate-a", [0, 0, 0], [10, 20, 30]),
        ("candidate-b", [0, 0, 0], [10, 20, 30]),
    ])

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is False
    assert report["within_tolerance"] == 0
    assert report["bijection"] == {
        "unique_predictions": True,
        "unique_references": True,
        "reference_reuse": 0,
    }
    assert len({match["reference_id"] for match in report["matches"]}) == 2


def test_reprojection_reports_every_declared_used_view() -> None:
    reference = _scene(PIECES_16[:2])
    reference["used_views"] = ["front_xy", "side_yz"]

    report = evaluate_assembly(copy.deepcopy(reference), reference)

    assert set(report["reprojection"]) == {"front_xy", "side_yz"}
    assert all(metrics["max"] == pytest.approx(0.0) for metrics in report["reprojection"].values())


def test_global_translation_is_optimized_across_the_whole_bijection() -> None:
    reference = _scene([
        ("a", [0, 0, 0], [10, 20, 30]),
        ("b", [100, 0, 0], [11, 21, 31]),
    ])
    prediction = _scene([
        ("candidate-a", [0.9, 0, 0], [10, 20, 30]),
        ("candidate-b", [99.1, 0, 0], [11, 21, 31]),
    ])

    report = evaluate_assembly(prediction, reference)

    assert report["passed"] is True
    assert report["alignment"]["translation_mm"][0] == pytest.approx(0.0)
    assert report["center_error_mm"]["max"] == pytest.approx(0.9)


def test_file_evaluation_requires_the_frozen_prediction_hash(tmp_path: Path) -> None:
    prediction_path = tmp_path / "prediction.json"
    reference_path = tmp_path / "reference.json"
    prediction_bytes = json.dumps(_scene(PIECES_16[:1]), sort_keys=True).encode("utf-8")
    prediction_path.write_bytes(prediction_bytes)
    reference_path.write_text(
        json.dumps({
            **_scene(PIECES_16[:1]),
            "prediction_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
            "access_policy": {"evaluator_only": True, "runtime_allowed": False},
        }),
        encoding="utf-8",
    )

    report = evaluate_assembly_files(prediction_path, reference_path)

    assert report["passed"] is True
    assert report["frozen_prediction_sha256"] == hashlib.sha256(prediction_bytes).hexdigest()

    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["prediction_sha256"] = "0" * 64
    reference_path.write_text(json.dumps(reference), encoding="utf-8")
    with pytest.raises(AssemblyEvaluationError, match="prediction_sha256 mismatch"):
        evaluate_assembly_files(prediction_path, reference_path)


def test_assembly_evaluator_cli_writes_only_the_aggregate_report(tmp_path: Path) -> None:
    prediction_path = tmp_path / "prediction.json"
    reference_path = tmp_path / "reference.json"
    output_path = tmp_path / "report.json"
    prediction_bytes = json.dumps(_scene(PIECES_16[:1]), sort_keys=True).encode("utf-8")
    prediction_path.write_bytes(prediction_bytes)
    reference_path.write_text(json.dumps({
        **_scene(PIECES_16[:1]),
        "prediction_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
        "access_policy": {"evaluator_only": True, "runtime_allowed": False},
    }), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.evaluate_assembly",
            "--predictions",
            str(prediction_path),
            "--references",
            str(reference_path),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert "pieces" not in report and "components" not in report
