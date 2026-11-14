"""Conservative, deterministic comparisons over candidates already in runner context."""
from __future__ import annotations

from typing import Any

from backend.app.contratos.modelos import (
    AssemblyCandidate,
    ComponentProposal,
    DecompositionScenario,
    TableProgramProposal,
)


_KINDS = ("same_physical_part", "same_dimensions", "mirrored_variant", "alternative_hypothesis")


def _relations(*, physical: str, dimensions: str, mirrored: str, alternative: str) -> list[dict[str, str]]:
    statuses = (physical, dimensions, mirrored, alternative)
    return [{"kind": kind, "status": status} for kind, status in zip(_KINDS, statuses, strict=True)]


def _known_dimension_relation(first: tuple[Any, ...], second: tuple[Any, ...], *, shared_source: bool) -> str:
    if not first:
        return "unknown"
    known = [(left, right) for left, right in zip(first, second, strict=True) if left is not None and right is not None]
    if any(left != right for left, right in known):
        return "fail"
    if len(known) == len(first) and shared_source:
        return "pass"
    return "unknown"


def compare_legacy_candidates(
    first: tuple[DecompositionScenario, ComponentProposal],
    second: tuple[DecompositionScenario, ComponentProposal],
) -> dict[str, Any]:
    (first_scenario, first_item), (second_scenario, second_item) = first, second
    shared_evidence = tuple(sorted(set(first_item.evidence_ids) & set(second_item.evidence_ids)))
    first_values = (first_item.quantity, first_item.length_mm, first_item.width_mm, first_item.thickness_mm)
    second_values = (second_item.quantity, second_item.length_mm, second_item.width_mm, second_item.thickness_mm)
    incompatible = (
        second_scenario.id in first_scenario.incompatible_with
        or first_scenario.id in second_scenario.incompatible_with
    )
    alternative = "fail" if first_scenario.id == second_scenario.id else "pass" if incompatible else "unknown"
    unresolved = tuple(
        field for field, left, right in zip(
            ("quantity", "length_mm", "width_mm", "thickness_mm"), first_values, second_values, strict=True,
        ) if left is None or right is None
    )
    return {
        "candidate_kind": "component_proposal",
        "candidate_ids": [first_item.id, second_item.id],
        "relations": _relations(
            physical="unknown",
            dimensions=_known_dimension_relation(first_values, second_values, shared_source=bool(shared_evidence)),
            mirrored="not_applicable",
            alternative=alternative,
        ),
        "shared_evidence_ids": list(shared_evidence),
        "unresolved_fields": list(unresolved),
    }


def compare_assembly_candidates(first: AssemblyCandidate, second: AssemblyCandidate) -> dict[str, Any]:
    shared_evidence = tuple(sorted(set(first.evidence_ids) & set(second.evidence_ids)))
    first_dimensions = tuple(item.value_mm if item.state == "derived" else None for item in first.derived_dimensions)
    second_by_axis = {item.axis: item for item in second.derived_dimensions}
    second_dimensions = tuple(
        second_by_axis[item.axis].value_mm if second_by_axis.get(item.axis) and second_by_axis[item.axis].state == "derived" else None
        for item in first.derived_dimensions
    )
    unresolved = tuple(sorted(set(first.unknown_fields) | set(second.unknown_fields)))
    return {
        "candidate_kind": "assembly",
        "candidate_ids": [first.id, second.id],
        "relations": _relations(
            physical="not_applicable",
            dimensions=_known_dimension_relation(first_dimensions, second_dimensions, shared_source=bool(shared_evidence)),
            mirrored="unknown",
            alternative="pass",
        ),
        "shared_evidence_ids": list(shared_evidence),
        "unresolved_fields": list(unresolved),
        "roles": [sorted(item.role for item in first.uses), sorted(item.role for item in second.uses)],
    }


def compare_table_programs(first: TableProgramProposal, second: TableProgramProposal) -> dict[str, Any]:
    shared_evidence = tuple(sorted(set(first.evidence_ids) & set(second.evidence_ids)))
    first_shape = tuple((item.role, item.length_binding_id, item.width_binding_id, item.thickness_binding_id) for item in first.components)
    second_shape = tuple((item.role, item.length_binding_id, item.width_binding_id, item.thickness_binding_id) for item in second.components)
    dimensions = "pass" if first_shape == second_shape and shared_evidence else "unknown"
    return {
        "candidate_kind": "table_program",
        "candidate_ids": [first.id, second.id],
        "relations": _relations(
            physical="not_applicable", dimensions=dimensions,
            mirrored="not_applicable", alternative="pass",
        ),
        "shared_evidence_ids": list(shared_evidence),
        "unresolved_fields": [],
        "templates": [first.table_template_id, second.table_template_id],
        "roles": [sorted(item.role for item in first.components), sorted(item.role for item in second.components)],
    }
