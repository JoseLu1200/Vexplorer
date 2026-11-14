"""Deterministic comparison of two proposals for the `comparar_candidatas` tool.

Relation kinds and statuses follow HARNESS.md. Similarity suggests a relation, it never proves interchangeability,
and nothing here confirms a piece or fills a value.
"""
from __future__ import annotations

from backend.app.contratos.modelos import ComponentProposal, DecompositionScenario

DIMENSION_TOLERANCE_MM = 0.1
FIELDS = ("quantity", "length_mm", "width_mm", "thickness_mm")


def _same_dimensions(first: ComponentProposal, second: ComponentProposal) -> str:
    pairs = [(first.length_mm, second.length_mm), (first.width_mm, second.width_mm), (first.thickness_mm, second.thickness_mm)]
    known = [(a, b) for a, b in pairs if a is not None and b is not None]
    if any(abs(a - b) > DIMENSION_TOLERANCE_MM for a, b in known):
        return "fail"
    if len(known) < len(pairs):
        return "unknown"
    return "pass"


def compare_candidates(first: tuple[DecompositionScenario, ComponentProposal], second: tuple[DecompositionScenario, ComponentProposal]) -> dict:
    (first_scenario, first_proposal), (second_scenario, second_proposal) = first, second
    shared = tuple(sorted(set(first_proposal.evidence_ids) & set(second_proposal.evidence_ids)))
    same_role = first_proposal.role == second_proposal.role
    incompatible = second_scenario.id in first_scenario.incompatible_with or first_scenario.id in second_scenario.incompatible_with
    if first_scenario.id == second_scenario.id:
        alternative = "fail"
    elif incompatible and same_role:
        alternative = "pass"
    elif incompatible:
        alternative = "unknown"
    else:
        alternative = "not_applicable"
    relations = [
        # Whether two proposals describe the same physical board needs human review; the ledger cannot establish it.
        {"kind": "same_physical_part", "status": "fail" if first_scenario.id == second_scenario.id else "unknown", "evidence_ids": list(shared)},
        {"kind": "same_dimensions", "status": _same_dimensions(first_proposal, second_proposal), "evidence_ids": list(shared)},
        # The ledger holds no handedness information, so mirroring cannot be evaluated.
        {"kind": "mirrored_variant", "status": "not_applicable", "evidence_ids": []},
        {"kind": "alternative_hypothesis", "status": alternative, "evidence_ids": list(shared)},
    ]
    unresolved = [field for field in FIELDS if getattr(first_proposal, field) is None or getattr(second_proposal, field) is None]
    return {
        "candidate_ids": [first_proposal.id, second_proposal.id],
        "scenario_ids": [first_scenario.id, second_scenario.id],
        "roles": [first_proposal.role, second_proposal.role],
        "relations": relations,
        "unresolved_fields": unresolved,
    }
