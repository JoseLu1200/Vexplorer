"""Utility evaluation for authored sparse-CAD furniture-completion controls.

This module runs offline.  It receives an already-produced derived package and
a separate reference; it is not imported by the runtime or inference provider.
"""

from __future__ import annotations

from math import isfinite
import re
from typing import Any
import unicodedata


_SAFE_QUANTITY_STATES = {"hypothesis", "deduced", "estimated"}
_DIMENSION_NAMES = ("length", "width", "thickness")
_ROLE_ALIASES = {
    "work_surface": {
        "work_surface", "worktop", "tabletop", "table_top", "top_panel",
        "surface_panel", "encimera", "tablero_superior", "tapa",
        "superficie_horizontal",
    },
    "vertical_support": {
        "vertical_support", "leg", "table_leg", "support_leg", "pata",
        "apoyo_vertical", "soporte_vertical", "costados_portantes",
    },
    "longitudinal_apron": {
        "longitudinal_apron", "apron_long", "long_apron", "long_rail",
        "longitudinal_rail", "faldon_largo", "larguero_longitudinal",
        "arriostramiento_longitudinal",
    },
    "transverse_apron": {
        "transverse_apron", "apron_short", "short_apron", "cross_apron",
        "short_rail", "cross_rail", "faldon_corto", "travesano",
        "arriostramiento_transversal",
    },
    "side_panel": {
        "side_panel", "side", "cabinet_side", "carcass_side", "lateral", "costado",
        "carcasa_lateral", "costados_portantes",
    },
    "top_bottom_panel": {
        "top_bottom_panel", "horizontal_panel", "carcass_horizontal_panel",
        "top_panel", "bottom_panel", "tapa_base", "panel_superior_inferior",
        "carcasa_horizontal", "cierres_horizontales",
    },
    "back_panel": {
        "back_panel", "back", "rear_panel", "trasera", "fondo", "arriostramiento",
    },
    "internal_shelf": {
        "internal_shelf", "shelf", "adjustable_shelf", "balda", "estante",
        "estantes_interiores",
    },
    "drawer_front": {
        "drawer_front", "drawer_face", "front_drawer", "frente_cajon",
        "frentes_moviles",
    },
    "drawer_box_side": {
        "drawer_box_side", "drawer_side", "costado_cajon", "lateral_cajon",
        "paredes_laterales_cajones",
    },
    "drawer_box_front_back": {
        "drawer_box_front_back", "drawer_box_end", "drawer_front_back",
        "frente_trasera_cajon", "paredes_transversales_cajones",
    },
    "drawer_bottom": {
        "drawer_bottom", "drawer_base", "fondo_cajon", "fondos_cajones",
    },
}


def _normal(value: object) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.strip().lower()).strip("_")


def _role_matches(reference_role: object, predicted_role: object) -> bool:
    expected = _normal(reference_role)
    predicted = _normal(predicted_role)
    return predicted == expected or predicted in _ROLE_ALIASES.get(expected, {expected})


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_an_object")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label}_must_be_an_array")
    return list(value)


def _package(outcome: dict[str, Any]) -> dict[str, Any]:
    current = outcome.get("derived", outcome)
    current = _mapping(current, "derived_outcome")
    current = current.get("data", current)
    current = _mapping(current, "outcome")
    return _mapping(current.get("package", current), "derived_package")


def _construction(package: dict[str, Any]) -> dict[str, Any]:
    return _mapping(package.get("construction"), "construction_plan")


def _pieces(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw = plan.get("pieces", plan.get("piece_plans", ()))
    return [_mapping(item, "construction_piece") for item in _sequence(raw, "construction_pieces")]


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if isfinite(result) else None


def _dimension(piece: dict[str, Any], name: str) -> dict[str, Any]:
    dimensions = piece.get("dimensions")
    if isinstance(dimensions, dict) and isinstance(dimensions.get(name), dict):
        return dimensions[name]
    value = piece.get(name)
    return value if isinstance(value, dict) else {}


def _dimension_value(field: dict[str, Any]) -> float | None:
    return _number(field.get("value_mm", field.get("nominal_mm")))


def _range(field: dict[str, Any]) -> tuple[float, float] | None:
    value = field.get("range_mm")
    if not isinstance(value, dict):
        return None
    minimum = _number(value.get("min_mm"))
    maximum = _number(value.get("max_mm"))
    if minimum is None or maximum is None or minimum > maximum:
        return None
    return minimum, maximum


def _assumption_refs(field: dict[str, Any]) -> list[Any]:
    refs = field.get("assumption_refs", ())
    return list(refs) if isinstance(refs, (list, tuple)) else []


def _quantity(piece: dict[str, Any]) -> dict[str, Any]:
    value = piece.get("quantity")
    return value if isinstance(value, dict) else {}


def _quantity_value(piece: dict[str, Any]) -> int | None:
    value = _quantity(piece).get("value")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _expected_dimension_score(expected: dict[str, Any], predicted: dict[str, Any]) -> tuple[int, int, int]:
    """Return numeric correctness, basis correctness, declared-estimate correctness."""

    value = _dimension_value(predicted)
    if value is None:
        return 0, 0, 0
    kind = expected.get("kind")
    if "exact" in expected:
        exact = _number(expected.get("exact"))
        correct = int(exact is not None and abs(value - exact) <= 1.0)
    else:
        minimum = _number(expected.get("minimum"))
        maximum = _number(expected.get("maximum"))
        correct = int(
            minimum is not None and maximum is not None and minimum <= value <= maximum
        )
    state = predicted.get("state")
    observed_copy = (
        kind == "observed"
        and state == "deduced"
        and predicted.get("method") == "observed_copy"
        and bool(predicted.get("source_refs"))
    )
    basis_correct = int(correct == 1 and (state == kind or observed_copy))
    declared_estimate = 0
    if kind == "estimated":
        interval = _range(predicted)
        declared_estimate = int(
            correct == 1
            and predicted.get("state") == "estimated"
            and interval is not None
            and interval[0] <= value <= interval[1]
            and bool(_assumption_refs(predicted))
        )
    return correct, basis_correct, declared_estimate


def _candidate_score(reference_piece: dict[str, Any], piece: dict[str, Any]) -> tuple[int, int, int]:
    quantity = int(_quantity_value(piece) == reference_piece.get("quantity"))
    correct = 0
    basis = 0
    for name in _DIMENSION_NAMES:
        dimension_score = _expected_dimension_score(
            _mapping(reference_piece["dimensions_mm"][name], "reference_dimension"),
            _dimension(piece, name),
        )
        correct += dimension_score[0]
        basis += dimension_score[1]
    return quantity, correct, basis


def _align(reference_pieces: list[dict[str, Any]], pieces: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    remaining = list(pieces)
    aligned: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for reference_piece in reference_pieces:
        candidates = [
            piece
            for piece in remaining
            if _role_matches(reference_piece.get("role"), piece.get("role"))
        ]
        selected = max(candidates, key=lambda item: _candidate_score(reference_piece, item), default=None)
        aligned.append((reference_piece, selected))
        if selected is not None:
            remaining.remove(selected)
    return aligned


def _scenario_metrics(scenario: dict[str, Any], pieces: list[dict[str, Any]]) -> dict[str, Any]:
    reference_pieces = [
        _mapping(item, "reference_piece")
        for item in _sequence(scenario.get("necessary_piece_types"), "necessary_piece_types")
    ]
    aligned = _align(reference_pieces, pieces)
    matched = sum(piece is not None for _, piece in aligned)
    quantity_correct = 0
    numeric_dimensions = 0
    dimension_correct = 0
    basis_correct = 0
    estimates_required = 0
    estimates_declared = 0
    matched_piece_ids: list[str] = []
    unsafe_roles: list[str] = []
    for reference_piece, piece in aligned:
        estimates_required += sum(
            reference_piece["dimensions_mm"][name].get("kind") == "estimated"
            for name in _DIMENSION_NAMES
        )
        if piece is None:
            continue
        matched_piece_ids.append(
            str(piece.get("piece_id") or piece.get("component_id") or piece.get("id", ""))
        )
        quantity_correct += int(_quantity_value(piece) == reference_piece.get("quantity"))
        if _quantity(piece).get("state") not in _SAFE_QUANTITY_STATES:
            unsafe_roles.append(str(reference_piece.get("role")))
        for name in _DIMENSION_NAMES:
            predicted = _dimension(piece, name)
            numeric_dimensions += int(_dimension_value(predicted) is not None)
            correct, basis, estimate = _expected_dimension_score(
                _mapping(reference_piece["dimensions_mm"][name], "reference_dimension"),
                predicted,
            )
            dimension_correct += correct
            basis_correct += basis
            estimates_declared += estimate
    return {
        "key": scenario.get("key"),
        "aligned": aligned,
        "matched": matched,
        "required": len(reference_pieces),
        "quantity_correct": quantity_correct,
        "numeric_dimensions": numeric_dimensions,
        "dimension_correct": dimension_correct,
        "basis_correct": basis_correct,
        "dimension_required": len(reference_pieces) * 3,
        "estimates_required": estimates_required,
        "estimates_declared": estimates_declared,
        "matched_piece_ids": matched_piece_ids,
        "unsafe_roles": sorted(unsafe_roles),
    }


def _artifact_formats(package: dict[str, Any], plan: dict[str, Any], piece: dict[str, Any]) -> set[str]:
    artifacts = package.get("artifacts", plan.get("artifacts", ()))
    sheet_ids = set(piece.get("sheet_ids", ()))
    piece_id = piece.get("component_id") or piece.get("piece_id") or piece.get("id")
    result: set[str] = set()
    for raw in artifacts if isinstance(artifacts, (list, tuple)) else ():
        if not isinstance(raw, dict) or raw.get("status") != "ready":
            continue
        if raw.get("sheet_id") not in sheet_ids and raw.get("component_id") != piece_id:
            continue
        kind = raw.get("kind")
        if kind in {"drawing_svg", "piece_sheet_svg"}:
            result.add("svg")
        elif kind in {"drawing_dxf", "piece_sheet_dxf"}:
            result.add("dxf")
    return result


def _construction_requirements(
    scenario: dict[str, Any],
    plan: dict[str, Any],
    aligned: list[tuple[dict[str, Any], dict[str, Any] | None]],
) -> dict[str, Any]:
    constraints = scenario.get("closure_constraints", ())
    constraint_text = " ".join(str(item) for item in constraints).lower()
    requires_stabilization = any(
        token in constraint_text
        for token in ("anchoring", "anti-racking", "anti racking", "bracing")
    )
    if not requires_stabilization:
        return {"satisfied": 0, "required": 0, "missing": []}

    has_structural_back = False
    for reference_piece, piece in aligned:
        if _normal(reference_piece.get("role")) != "back_panel" or piece is None:
            continue
        quantity_correct, dimensions_correct, _ = _candidate_score(
            reference_piece, piece
        )
        if quantity_correct == 1 and dimensions_correct == 3:
            has_structural_back = True
            break
    details = plan.get("details", ())
    has_explicit_anchor = any(
        isinstance(detail, dict)
        and detail.get("kind") == "fastener"
        and bool(detail.get("source_refs") or detail.get("assumption_refs"))
        and any(
            token in str(detail.get("rationale", "")).lower()
            for token in ("anchor", "ancl", "wall", "muro", "anti-rack", "antivuelco")
        )
        for detail in details if isinstance(details, (list, tuple))
    )
    satisfied = has_structural_back or has_explicit_anchor
    return {
        "satisfied": int(satisfied),
        "required": 1,
        "missing": [] if satisfied else ["anti_racking_or_anchoring_detail"],
    }


def _validation(outcome: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    direct = plan.get("validation")
    if isinstance(direct, dict):
        return direct
    roots = [outcome]
    for key in ("data", "record", "general_record", "latest", "derived"):
        nested = outcome.get(key)
        if isinstance(nested, dict):
            roots.append(nested)
            if isinstance(nested.get("data"), dict):
                roots.append(nested["data"])
    for root in roots:
        review = root.get("review")
        if isinstance(review, dict) and isinstance(review.get("construction_validation"), dict):
            return review["construction_validation"]
    return {}


def evaluate_cad_completion(reference: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    """Score one frozen derived package against one separately supplied control."""

    reference = _mapping(reference, "reference")
    outcome = _mapping(outcome, "outcome")
    package = _package(outcome)
    plan = _construction(package)
    pieces = _pieces(plan)
    scenarios = [
        _mapping(item, "reference_scenario")
        for item in _sequence(reference.get("acceptable_scenarios"), "acceptable_scenarios")
    ]
    if not scenarios:
        raise ValueError("reference_requires_acceptable_scenarios")
    candidates = [_scenario_metrics(scenario, pieces) for scenario in scenarios]
    selected = max(
        candidates,
        key=lambda item: (
            item["matched"],
            item["quantity_correct"],
            item["dimension_correct"],
            item["basis_correct"],
        ),
    )
    aligned_pieces = [piece for _, piece in selected["aligned"] if piece is not None]
    drawing_complete = sum(
        _artifact_formats(package, plan, piece) == {"svg", "dxf"}
        for piece in aligned_pieces
    )
    validation = _validation(outcome, plan)
    constraint_results = validation.get("constraint_results", ())
    constraints_clean = isinstance(constraint_results, (list, tuple)) and not any(
        isinstance(item, dict) and item.get("status") == "fail" for item in constraint_results
    )
    closure_valid = validation.get("status") == "valid" and constraints_clean
    selected_scenario = next(
        item for item in scenarios if item.get("key") == selected["key"]
    )
    construction_requirements = _construction_requirements(
        selected_scenario, plan, selected["aligned"]
    )
    required = selected["required"]
    dimension_required = selected["dimension_required"]
    utility_pass = all(
        (
            selected["matched"] == required,
            selected["quantity_correct"] == required,
            selected["numeric_dimensions"] == dimension_required,
            selected["dimension_correct"] == dimension_required,
            selected["basis_correct"] == dimension_required,
            selected["estimates_declared"] == selected["estimates_required"],
            drawing_complete == required,
            not selected["unsafe_roles"],
            closure_valid,
            construction_requirements["satisfied"]
            == construction_requirements["required"],
        )
    )
    return {
        "schema_version": "1.0",
        "case_id": reference.get("case_id"),
        "control_kind": reference.get("reference_kind"),
        "selected_reference_scenario": selected["key"],
        "role_matching": "postfreeze_generic_furniture_aliases_v2",
        "necessary_piece_types": {
            "matched": selected["matched"],
            "required": required,
            "coverage": selected["matched"] / required if required else None,
        },
        "scenario_quantities": {
            "correct": selected["quantity_correct"],
            "required": required,
        },
        "dimensions": {
            "numeric_primary": selected["numeric_dimensions"],
            "correct": selected["dimension_correct"],
            "basis_correct": selected["basis_correct"],
            "required": dimension_required,
            "tolerance_mm": 1.0,
        },
        "estimates": {
            "declared_with_range_and_premise": selected["estimates_declared"],
            "required": selected["estimates_required"],
        },
        "closure": {
            "server_validation": validation.get("status", "missing"),
            "no_failed_constraints": constraints_clean,
        },
        "construction_requirements": construction_requirements,
        "piece_drawings": {
            "with_svg_and_dxf": drawing_complete,
            "required": required,
        },
        "occurrence_authority": {
            "hypothesis_safe": not selected["unsafe_roles"],
            "unsafe_piece_types": selected["unsafe_roles"],
        },
        "unmatched_predicted_piece_types": max(0, len(pieces) - selected["matched"]),
        "utility_pass": utility_pass,
        "limitations": [
            "Authored developer control; not blind or independent evidence.",
            "Passing means one coherent accepted scenario, not manufacturing certification.",
            "Role aliases v2 were added after F01-F03 outputs froze; role-aligned results are diagnostic, not preregistered evidence.",
        ],
    }
