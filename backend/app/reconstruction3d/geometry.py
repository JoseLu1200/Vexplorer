from __future__ import annotations

from .models import AssemblyProposal


def inspect_assembly(proposal: AssemblyProposal, tolerance: float = 0.5) -> dict:
    """Axis-aligned contacts are diagnostics, never a structural certification."""
    parts = proposal.components
    if proposal.unit == "relative" and parts:
        tolerance = max(max(p.size_mm) for p in parts) * 0.0005
    contacts, overlaps = [], []
    neighbours = {p.id: set() for p in parts}
    for i, a in enumerate(parts):
        for b in parts[i + 1 :]:
            intersection = [
                min(a.origin_mm[k] + a.size_mm[k], b.origin_mm[k] + b.size_mm[k])
                - max(a.origin_mm[k], b.origin_mm[k])
                for k in range(3)
            ]
            if all(v > tolerance for v in intersection):
                overlaps.append(
                    {
                        "ids": [a.id, b.id],
                        "intersection_volume": intersection[0]
                        * intersection[1]
                        * intersection[2],
                    }
                )
            elif sum(v > tolerance for v in intersection) == 2 and all(
                v >= -tolerance for v in intersection
            ):
                contacts.append([a.id, b.id])
                neighbours[a.id].add(b.id)
                neighbours[b.id].add(a.id)
    grounded = {p.id for p in parts if abs(p.origin_mm[2]) <= tolerance}
    connected = set(grounded)
    frontier = list(grounded)
    while frontier:
        for other in neighbours[frontier.pop()] - connected:
            connected.add(other)
            frontier.append(other)
    return {
        "contacts": contacts,
        "overlaps": overlaps,
        "grounded_ids": sorted(grounded),
        "floating_ids": sorted(set(neighbours) - connected),
        "below_ground_ids": [p.id for p in parts if p.origin_mm[2] < -tolerance],
        "load_capacity": "not_evaluated",
        "joint_design": "not_evaluated",
        "functional_certification": False,
    }
