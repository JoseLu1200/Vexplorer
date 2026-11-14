"""Experimental constructive similarity for already-extracted furniture descriptors.

This module is deliberately outside the product runtime.  Its score is an
explainable weighted similarity, not a probability or a cost-equivalence claim.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.optimize import linprog

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    TableDescriptorComponentFeature,
)

Descriptor = FurnitureDescriptorV2 | FurnitureDescriptorV3

FIELD_WEIGHTS = {
    "role": 0.15,
    "quantity": 0.10,
    "length_mm": 0.20,
    "width_mm": 0.20,
    "thickness_mm": 0.25,
    "material": 0.10,
}
DIMENSION_SCALE = 0.5
ORIENTATION_FREE_ROLES = {None, "tabletop"}


@dataclass(frozen=True)
class _Component:
    role: str | None
    quantity: int
    quantity_known: bool
    length_mm: float | None
    width_mm: float | None
    thickness_mm: float | None
    material: str | None


def _canonical_planar(
    role: str | None, length: float | None, width: float | None
) -> tuple[float | None, float | None]:
    """Canonicalize local planar axes only where orientation has no semantics."""
    if role in ORIENTATION_FREE_ROLES and length is not None and width is not None:
        return max(length, width), min(length, width)
    return length, width


def _components(descriptor: Descriptor) -> list[_Component]:
    if isinstance(descriptor, FurnitureDescriptorV3):
        values = []
        for item in descriptor.components:
            length, width = _canonical_planar(item.role, item.length_mm, item.width_mm)
            values.append(
                _Component(
                    role=item.role,
                    quantity=item.quantity,
                    quantity_known=True,
                    length_mm=length,
                    width_mm=width,
                    thickness_mm=item.thickness_mm,
                    material=item.material_tariff_id or descriptor.material_tariff_id,
                )
            )
        return values

    values = []
    for item in descriptor.part_features:
        length, width = _canonical_planar(None, item.length_mm, item.width_mm)
        # A V2 feature with unknown quantity represents one observed feature,
        # not one asserted physical occurrence.  The matching report exposes
        # this distinction and never labels the resulting weight as physical.
        values.append(
            _Component(
                role=None,
                quantity=item.quantity or 1,
                quantity_known=item.quantity is not None,
                length_mm=length,
                width_mm=width,
                thickness_mm=item.thickness_mm,
                material=descriptor.material,
            )
        )
    return values


def _dimension_similarity(left: float, right: float) -> float:
    return math.exp(-abs(math.log(left / right)) / DIMENSION_SCALE)


def _pair_affinity(left: _Component, right: _Component) -> float:
    total = 0.0
    for field in ("length_mm", "width_mm", "thickness_mm"):
        left_value = getattr(left, field)
        right_value = getattr(right, field)
        if left_value is not None and right_value is not None:
            total += FIELD_WEIGHTS[field] * _dimension_similarity(left_value, right_value)
    if left.material is not None and right.material is not None:
        total += FIELD_WEIGHTS["material"] * float(left.material == right.material)
    return total


def _optimal_transport(
    left: Sequence[_Component], right: Sequence[_Component]
) -> list[tuple[int, int, float]]:
    """Maximize attribute affinity as a compact transportation problem."""
    if not left or not right:
        return []
    rows, columns = len(left), len(right)
    affinities = np.array(
        [[_pair_affinity(a, b) for b in right] for a in left], dtype=float
    )
    bounds = [
        (0.0, None)
        if a.role is None or b.role is None or a.role == b.role
        else (0.0, 0.0)
        for a in left
        for b in right
    ]
    constraints: list[np.ndarray] = []
    limits: list[float] = []
    for row, item in enumerate(left):
        constraint = np.zeros(rows * columns)
        constraint[row * columns : (row + 1) * columns] = 1.0
        constraints.append(constraint)
        limits.append(float(item.quantity))
    for column, item in enumerate(right):
        constraint = np.zeros(rows * columns)
        constraint[column::columns] = 1.0
        constraints.append(constraint)
        limits.append(float(item.quantity))
    # Lexicographic objective: first preserve every compatible comparison
    # opportunity, then choose the most similar allocation.  Optimizing only
    # affinity lets a solver omit zero-affinity pairs and thereby hide a known
    # difference (for example two dimensionless observations with distinct
    # materials).
    maximum_mass = linprog(
        c=-np.ones(rows * columns),
        A_ub=np.vstack(constraints),
        b_ub=np.asarray(limits),
        bounds=bounds,
        method="highs",
    )
    if not maximum_mass.success:  # pragma: no cover - defensive SciPy guard
        raise RuntimeError(f"component mass matching failed: {maximum_mass.message}")
    matched_mass = float(np.sum(maximum_mass.x))
    if matched_mass <= 1e-8:
        return []
    result = linprog(
        c=-affinities.ravel(),
        A_ub=np.vstack(constraints),
        b_ub=np.asarray(limits),
        A_eq=np.ones((1, rows * columns)),
        b_eq=np.asarray([matched_mass]),
        bounds=bounds,
        method="highs",
    )
    if not result.success:  # pragma: no cover - defensive guard around SciPy
        raise RuntimeError(f"component affinity matching failed: {result.message}")
    flow = result.x.reshape(rows, columns)
    return [
        (row, column, float(flow[row, column]))
        for row in range(rows)
        for column in range(columns)
        if flow[row, column] > 1e-8
    ]


def _role_profile(descriptor: Descriptor) -> tuple[dict[str, int], bool]:
    if isinstance(descriptor, FurnitureDescriptorV3):
        profile: dict[str, int] = {}
        for item in descriptor.components:
            profile[item.role] = profile.get(item.role, 0) + item.quantity
        return profile, True
    profile: dict[str, int] = {}
    known = bool(descriptor.roles)
    for item in descriptor.roles:
        if item.quantity is None:
            known = False
            continue
        profile[item.role] = profile.get(item.role, 0) + item.quantity
    return profile, known


def _role_similarity(left: Descriptor, right: Descriptor) -> tuple[float, bool]:
    left_profile, left_known = _role_profile(left)
    right_profile, right_known = _role_profile(right)
    if not left_known or not right_known:
        return 0.0, False
    denominator = max(sum(left_profile.values()), sum(right_profile.values()), 1)
    overlap = sum(
        min(left_profile.get(role, 0), right_profile.get(role, 0))
        for role in set(left_profile) | set(right_profile)
    )
    return overlap / denominator, True


def _different(left: float, right: float) -> bool:
    return not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def compare_components(left: Descriptor, right: Descriptor) -> dict[str, Any]:
    """Compare constructive component multisets without using IDs or input order.

    ``score`` already includes evidence coverage: unknown fields contribute zero,
    while ``coverage`` reports how much of the weighted comparison was supported.
    Contributions are descriptive, not calibrated probabilities.
    """
    if not isinstance(left, (FurnitureDescriptorV2, FurnitureDescriptorV3)):
        raise TypeError("left must be FurnitureDescriptorV2 or FurnitureDescriptorV3")
    if not isinstance(right, (FurnitureDescriptorV2, FurnitureDescriptorV3)):
        raise TypeError("right must be FurnitureDescriptorV2 or FurnitureDescriptorV3")

    left_components = _components(left)
    right_components = _components(right)
    matches = _optimal_transport(left_components, right_components)
    left_total = sum(item.quantity for item in left_components)
    right_total = sum(item.quantity for item in right_components)
    denominator = max(left_total, right_total, 1)
    matched_quantity = sum(quantity for _, _, quantity in matches)

    contributions = {
        field: {"weighted_score": 0.0, "coverage": 0.0}
        for field in ("length_mm", "width_mm", "thickness_mm", "material")
    }
    differences: list[dict[str, Any]] = []
    for left_index, right_index, quantity in matches:
        left_item = left_components[left_index]
        right_item = right_components[right_index]
        role = left_item.role or right_item.role or "unassigned"
        for field in ("length_mm", "width_mm", "thickness_mm"):
            left_value = getattr(left_item, field)
            right_value = getattr(right_item, field)
            if left_value is None or right_value is None:
                continue
            similarity = _dimension_similarity(left_value, right_value)
            contributions[field]["weighted_score"] += (
                quantity * FIELD_WEIGHTS[field] * similarity / denominator
            )
            contributions[field]["coverage"] += (
                quantity * FIELD_WEIGHTS[field] / denominator
            )
            if _different(left_value, right_value):
                differences.append(
                    {
                        "kind": "value_difference",
                        "role": role,
                        "field": field,
                        "left": left_value,
                        "right": right_value,
                        "quantity": _json_number(quantity),
                        "log_ratio": round(abs(math.log(left_value / right_value)), 6),
                    }
                )
        if left_item.material is not None and right_item.material is not None:
            equal = left_item.material == right_item.material
            contributions["material"]["weighted_score"] += (
                quantity * FIELD_WEIGHTS["material"] * float(equal) / denominator
            )
            contributions["material"]["coverage"] += (
                quantity * FIELD_WEIGHTS["material"] / denominator
            )
            if not equal:
                differences.append(
                    {
                        "kind": "value_difference",
                        "role": role,
                        "field": "material",
                        "left": left_item.material,
                        "right": right_item.material,
                        "quantity": _json_number(quantity),
                    }
                )

    role_score, role_known = _role_similarity(left, right)
    role_weighted = FIELD_WEIGHTS["role"] * role_score if role_known else 0.0
    role_coverage = FIELD_WEIGHTS["role"] if role_known else 0.0
    quantities_known = bool(left_components and right_components) and all(
        item.quantity_known for item in (*left_components, *right_components)
    )
    quantity_score = matched_quantity / denominator if quantities_known else 0.0
    quantity_weighted = (
        FIELD_WEIGHTS["quantity"] * quantity_score if quantities_known else 0.0
    )
    quantity_coverage = FIELD_WEIGHTS["quantity"] if quantities_known else 0.0

    left_profile, _ = _role_profile(left)
    right_profile, _ = _role_profile(right)
    if role_known and left_profile != right_profile:
        differences.append(
            {
                "kind": "multiset_difference",
                "role": "all",
                "field": "role",
                "left": left_profile,
                "right": right_profile,
            }
        )
    if quantities_known and left_total != right_total:
        differences.append(
            {
                "kind": "multiset_difference",
                "role": "all",
                "field": "quantity",
                "left": left_total,
                "right": right_total,
            }
        )

    component_report: dict[str, Any] = {}
    for field, values in contributions.items():
        nominal_weight = FIELD_WEIGHTS[field]
        observed_mass = values["coverage"] / nominal_weight if nominal_weight else 0.0
        conditional_score = (
            values["weighted_score"] / values["coverage"]
            if values["coverage"] > 0
            else 0.0
        )
        component_report[field] = {
            "score": round(conditional_score, 6),
            "coverage": round(min(observed_mass, 1.0), 6),
            "weight": nominal_weight,
            "weighted_contribution": round(values["weighted_score"], 6),
            "status": "observed" if observed_mass >= 1 - 1e-8 else (
                "partial" if observed_mass > 0 else "unknown"
            ),
        }
    component_report["role"] = {
        "score": round(role_score, 6),
        "coverage": float(role_known),
        "weight": FIELD_WEIGHTS["role"],
        "weighted_contribution": round(role_weighted, 6),
        "status": "observed" if role_known else "unknown",
    }
    component_report["quantity"] = {
        "score": round(quantity_score, 6),
        "coverage": float(quantities_known),
        "weight": FIELD_WEIGHTS["quantity"],
        "weighted_contribution": round(quantity_weighted, 6),
        "status": "observed" if quantities_known else "unknown",
    }

    total_score = role_weighted + quantity_weighted + sum(
        values["weighted_score"] for values in contributions.values()
    )
    coverage = role_coverage + quantity_coverage + sum(
        values["coverage"] for values in contributions.values()
    )
    unknown_fields = [
        field
        for field, details in component_report.items()
        if field not in {"matching"} and details["status"] != "observed"
    ]
    for field in unknown_fields:
        differences.append(
            {
                "kind": "unknown_evidence",
                "role": "all",
                "field": field,
                "left": "unknown_or_partial",
                "right": "unknown_or_partial",
            }
        )

    component_report["matching"] = {
        "method": "aggregated_optimal_transport",
        "matched_quantity": _json_number(matched_quantity),
        "unmatched_left_quantity": _json_number(left_total - matched_quantity),
        "unmatched_right_quantity": _json_number(right_total - matched_quantity),
        "matched_quantity_kind": (
            "physical_component_quantity"
            if quantities_known
            else "observation_weight_not_physical_quantity"
        ),
        "unknown_quantity_observations": {
            "left": sum(not item.quantity_known for item in left_components),
            "right": sum(not item.quantity_known for item in right_components),
        },
        "expanded_occurrences": 0,
        "orientation_canonicalized_roles": ["tabletop", "unassigned"],
    }
    differences.sort(
        key=lambda item: (
            str(item["field"]),
            str(item["role"]),
            str(item.get("left")),
            str(item.get("right")),
        )
    )
    return {
        "score": round(min(max(total_score, 0.0), 1.0), 6),
        "coverage": round(min(max(coverage, 0.0), 1.0), 6),
        "score_kind": "constructive_similarity_not_probability",
        "components": component_report,
        "differences": differences,
    }


def _json_number(value: float) -> int | float:
    rounded = round(value)
    return int(rounded) if math.isclose(value, rounded, abs_tol=1e-7) else round(value, 6)


def _control_descriptor(
    *, support_width: float = 550, thickness: float = 18, material: str = "board-a"
) -> FurnitureDescriptorV3:
    states = {
        "quantity": "confirmed",
        "length_mm": "confirmed",
        "width_mm": "confirmed",
        "thickness_mm": "confirmed",
    }
    return FurnitureDescriptorV3(
        dimensions=DescriptorDimensions(width_mm=1200, depth_mm=600, height_mm=750),
        structure="side_support_table",
        components=(
            TableDescriptorComponentFeature(
                role="tabletop", quantity=1, length_mm=1200, width_mm=600,
                thickness_mm=thickness, material_tariff_id=material,
                field_states=states,
            ),
            TableDescriptorComponentFeature(
                role="side_support", quantity=2, length_mm=720,
                width_mm=support_width, thickness_mm=thickness,
                material_tariff_id=material, field_states=states,
            ),
        ),
    )


def synthetic_control_report() -> dict[str, Any]:
    baseline = _control_descriptor()
    reordered = baseline.model_copy(update={"components": tuple(reversed(baseline.components))})
    cases = [
        ("exact_reordered", reordered),
        ("support_width_changed", _control_descriptor(support_width=200)),
        ("thickness_doubled", _control_descriptor(thickness=36)),
        ("material_changed", _control_descriptor(material="board-b")),
    ]
    return {
        "schema_version": 1,
        "evidence_kind": "synthetic-control",
        "description": "Development fixtures only; no reserved references or real accuracy evaluation.",
        "claims": {"real_accuracy": False, "cost_equivalence": False},
        "cases": [
            {"id": case_id, "comparison": compare_components(baseline, candidate)}
            for case_id, candidate in cases
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    control = subparsers.add_parser("control", help="write the labeled synthetic control")
    control.add_argument(
        "--output",
        type=Path,
        default=Path("D:/Vexplorer-semantic-lab/components-control.json"),
    )
    args = parser.parse_args(argv)
    if args.command == "control":
        report = synthetic_control_report()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
