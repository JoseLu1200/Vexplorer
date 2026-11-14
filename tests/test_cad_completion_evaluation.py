from __future__ import annotations

import json
from pathlib import Path
import sys

from evaluation.cad_completion import evaluate_cad_completion
from tools.prepare_cad_completion_controls import build_controls
from tools.evaluate_cad_completion import main as evaluate_main


def _dimension(value: float, state: str, *, ranged: bool = False) -> dict:
    return {
        "value_mm": value,
        "range_mm": {"min_mm": value - 2, "max_mm": value + 2} if ranged else None,
        "state": state,
        "assumption_refs": ["premise:hidden"] if ranged else [],
        "method": "construction_assumption" if ranged else "arithmetic",
    }


def _piece(
    role: str,
    quantity: int,
    dimensions: tuple[dict, dict, dict],
    *,
    sheet: str,
) -> dict:
    return {
        "id": f"piece-{role}",
        "role": role,
        "quantity": {
            "value": quantity,
            "state": "hypothesis",
            "dependency_refs": ["premise:scenario"],
        },
        "dimensions": dict(zip(("length", "width", "thickness"), dimensions)),
        "sheet_ids": [sheet],
    }


def _f01_success() -> dict:
    pieces = [
        _piece(
            "work_surface",
            1,
            (_dimension(1200, "observed"), _dimension(600, "observed"), _dimension(30, "observed")),
            sheet="sheet-top",
        ),
        _piece(
            "vertical_support",
            4,
            (_dimension(720, "deduced"), _dimension(50, "deduced"), _dimension(50, "deduced")),
            sheet="sheet-support",
        ),
        _piece(
            "longitudinal_apron",
            2,
            (_dimension(980, "deduced"), _dimension(100, "deduced"), _dimension(20, "estimated", ranged=True)),
            sheet="sheet-long",
        ),
        _piece(
            "transverse_apron",
            2,
            (_dimension(380, "deduced"), _dimension(100, "deduced"), _dimension(20, "estimated", ranged=True)),
            sheet="sheet-short",
        ),
    ]
    artifacts = [
        {"kind": kind, "sheet_id": sheet, "component_id": None, "status": "ready"}
        for sheet in ("sheet-top", "sheet-support", "sheet-long", "sheet-short")
        for kind in ("piece_sheet_svg", "piece_sheet_dxf")
    ]
    return {
        "data": {
            "package": {
                "construction": {
                    "scenario_id": "proposal-scenario-not-oracle-key",
                    "validation": {"status": "valid", "constraint_results": []},
                    "pieces": pieces,
                    "sheets": [],
                },
                "artifacts": artifacts,
            }
        }
    }


def test_utility_evaluator_accepts_numeric_coherent_f01_without_human_gate(
    tmp_path: Path,
) -> None:
    build_controls(tmp_path / "public", tmp_path / "private", case_ids=("F01",))
    reference = json.loads((tmp_path / "private" / "F01.reference.json").read_text("utf-8"))

    report = evaluate_cad_completion(reference, _f01_success())

    assert report["case_id"] == "F01"
    assert report["selected_reference_scenario"] == "four_supports_with_perimeter_aprons"
    assert report["necessary_piece_types"] == {"matched": 4, "required": 4, "coverage": 1.0}
    assert report["scenario_quantities"]["correct"] == 4
    assert report["dimensions"]["correct"] == 12
    assert report["dimensions"]["basis_correct"] == 12
    assert report["estimates"]["declared_with_range_and_premise"] == 2
    assert report["piece_drawings"]["with_svg_and_dxf"] == 4
    assert report["occurrence_authority"]["hypothesis_safe"] is True
    assert report["closure"]["server_validation"] == "valid"
    assert report["utility_pass"] is True
    assert "acceptable_scenarios" not in report


def test_utility_evaluator_does_not_mix_scenarios_or_promote_occurrences(
    tmp_path: Path,
) -> None:
    build_controls(tmp_path / "public", tmp_path / "private", case_ids=("F03",))
    reference = json.loads((tmp_path / "private" / "F03.reference.json").read_text("utf-8"))
    outcome = {
        "package": {
            "construction": {
                "scenario_id": "candidate",
                "validation": {"status": "valid", "constraint_results": []},
                "pieces": [
                    _piece(
                        "side_panel",
                        2,
                        (_dimension(1800, "observed"), _dimension(300, "observed"), _dimension(18, "deduced")),
                        sheet="side",
                    ),
                    _piece(
                        "top_bottom_panel",
                        2,
                        (_dimension(764, "deduced"), _dimension(300, "observed"), _dimension(18, "deduced")),
                        sheet="horizontal",
                    ),
                    _piece(
                        "internal_shelf",
                        4,
                        (_dimension(764, "deduced"), _dimension(300, "observed"), _dimension(18, "deduced")),
                        sheet="shelf",
                    ),
                    _piece(
                        "back_panel",
                        1,
                        (_dimension(1800, "deduced"), _dimension(800, "deduced"), _dimension(4, "observed")),
                        sheet="back",
                    ),
                ],
            },
            "artifacts": [],
        }
    }
    outcome["package"]["construction"]["pieces"][0]["quantity"]["state"] = "confirmed"

    report = evaluate_cad_completion(reference, outcome)

    assert report["selected_reference_scenario"] == "thin_structural_back"
    assert report["necessary_piece_types"]["required"] == 4
    assert report["dimensions"]["correct"] == 12
    assert report["dimensions"]["basis_correct"] == 11
    assert report["estimates"]["required"] == 1
    assert report["estimates"]["declared_with_range_and_premise"] == 0
    assert report["occurrence_authority"] == {
        "hypothesis_safe": False,
        "unsafe_piece_types": ["side_panel"],
    }
    assert report["utility_pass"] is False


def test_cli_writes_machine_report_without_overwriting_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    build_controls(tmp_path / "public", tmp_path / "private", case_ids=("F01",))
    reference = tmp_path / "private" / "F01.reference.json"
    outcome = tmp_path / "outcome.json"
    derived = _f01_success()
    validation = derived["data"]["package"]["construction"].pop("validation")
    qa_report = {
        "derived": derived["data"],
        "latest": {"review": {"construction_validation": validation}},
    }
    outcome.write_text(json.dumps(qa_report), encoding="utf-8")
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_cad_completion.py",
            "--reference",
            str(reference),
            "--outcome",
            str(outcome),
            "--output",
            str(report),
        ],
    )

    assert evaluate_main() == 0
    assert json.loads(report.read_text("utf-8"))["utility_pass"] is True


def test_postfreeze_generic_role_aliases_measure_construction_not_word_choice(
    tmp_path: Path,
) -> None:
    build_controls(tmp_path / "public", tmp_path / "private", case_ids=("F01",))
    reference = json.loads((tmp_path / "private" / "F01.reference.json").read_text("utf-8"))
    outcome = _f01_success()
    pieces = outcome["data"]["package"]["construction"]["pieces"]
    for piece, role in zip(pieces, ("tabletop", "leg", "apron_long", "faldón corto")):
        piece["role"] = role

    report = evaluate_cad_completion(reference, outcome)

    assert report["necessary_piece_types"]["matched"] == 4
    assert report["role_matching"] == "postfreeze_generic_furniture_aliases_v2"
    assert report["utility_pass"] is True


def test_actual_contract_piece_ids_and_observed_copy_are_adapted_honestly(
    tmp_path: Path,
) -> None:
    build_controls(tmp_path / "public", tmp_path / "private", case_ids=("F03",))
    reference = json.loads((tmp_path / "private" / "F03.reference.json").read_text("utf-8"))
    outcome = {
        "derived": {
            "package": {
                "construction": {
                    "scenario_id": "scenario-source",
                    "pieces": [
                        _piece(
                            "costados_portantes",
                            2,
                            (_dimension(1800, "deduced"), _dimension(300, "deduced"), _dimension(18, "deduced")),
                            sheet="side",
                        ),
                        _piece(
                            "cierres_horizontales",
                            2,
                            (_dimension(764, "deduced"), _dimension(300, "deduced"), _dimension(18, "deduced")),
                            sheet="closures",
                        ),
                        _piece(
                            "estantes_interiores",
                            4,
                            (_dimension(764, "deduced"), _dimension(300, "deduced"), _dimension(18, "deduced")),
                            sheet="shelves",
                        ),
                    ],
                    "sheets": [],
                },
                "artifacts": [],
            }
        },
        "latest": {
            "review": {
                "construction_validation": {"status": "valid", "constraint_results": []}
            }
        },
    }
    for piece in outcome["derived"]["package"]["construction"]["pieces"]:
        piece["piece_id"] = piece.pop("id")
        piece["component_id"] = piece["piece_id"]
        for name in ("length", "width", "thickness"):
            field = piece["dimensions"][name]
            if field["state"] == "deduced":
                field["method"] = "observed_copy"
                field["source_refs"] = ["dimension:source"]

    report = evaluate_cad_completion(reference, outcome)

    assert report["necessary_piece_types"]["matched"] == 3
    assert report["dimensions"]["correct"] == 9
    # Four reference fields are source dimensions copied into a semantically
    # deduced piece assignment; this is compatible, not source confirmation.
    assert report["dimensions"]["basis_correct"] == 9
    assert report["piece_drawings"]["with_svg_and_dxf"] == 0
    assert report["construction_requirements"] == {
        "satisfied": 0,
        "required": 1,
        "missing": ["anti_racking_or_anchoring_detail"],
    }
    assert report["utility_pass"] is False


def test_incomplete_extra_back_does_not_satisfy_selected_structural_back_scenario(
    tmp_path: Path,
) -> None:
    build_controls(tmp_path / "public", tmp_path / "private", case_ids=("F03",))
    reference = json.loads((tmp_path / "private" / "F03.reference.json").read_text("utf-8"))
    outcome = {
        "package": {
            "construction": {
                "scenario_id": "candidate",
                "validation": {"status": "valid", "constraint_results": []},
                "pieces": [
                    _piece(
                        "side_panel", 2,
                        (_dimension(1800, "observed"), _dimension(300, "observed"), _dimension(18, "deduced")),
                        sheet="side",
                    ),
                    _piece(
                        "top_bottom_panel", 2,
                        (_dimension(764, "deduced"), _dimension(300, "observed"), _dimension(18, "deduced")),
                        sheet="horizontal",
                    ),
                    _piece(
                        "internal_shelf", 4,
                        (_dimension(764, "deduced"), _dimension(300, "observed"), _dimension(18, "deduced")),
                        sheet="shelf",
                    ),
                    _piece(
                        "back_panel", 1,
                        ({"value_mm": None, "state": "unknown"}, _dimension(800, "deduced"), _dimension(4, "estimated", ranged=True)),
                        sheet="back",
                    ),
                ],
                "details": [],
            },
            "artifacts": [],
        }
    }

    report = evaluate_cad_completion(reference, outcome)

    assert report["selected_reference_scenario"] == "thin_structural_back"
    assert report["construction_requirements"]["satisfied"] == 0
    assert report["construction_requirements"]["missing"] == [
        "anti_racking_or_anchoring_detail"
    ]
    assert report["utility_pass"] is False
