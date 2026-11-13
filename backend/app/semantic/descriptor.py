from __future__ import annotations

import hashlib
import json

from backend.app.contratos.modelos import DescriptorDimensions, FurnitureDescriptor, Result, RoleQuantity


def _structure(result: Result) -> str:
    selected = result.review.selected_scenario_id if result.review else None
    scenario = next((item for item in result.scenarios if item.id == selected), None)
    if scenario is None:
        return "unknown"
    by_role = {item.role: item for item in scenario.components}
    top, side = by_role.get("top_panel"), by_role.get("side_panel")
    if top and top.length_derivation == "overall_width_minus_two_thickness":
        return "top_base_between_sides"
    if side and side.length_derivation == "overall_height_minus_two_thickness":
        return "top_base_cap_sides"
    return "unknown"


def _dimensions(result: Result) -> DescriptorDimensions:
    scenarios = result.scenarios
    selected = result.review.selected_scenario_id if result.review else None
    scenario = next((item for item in scenarios if item.id == selected), scenarios[0] if scenarios else None)
    if scenario is None:
        return DescriptorDimensions()
    by_role = {item.role: item for item in scenario.components}
    top, side = by_role.get("top_panel"), by_role.get("side_panel")
    width = top.length_basis_mm if top else None
    height = side.length_basis_mm if side else None
    depth = (top.width_mm if top else None) or (side.width_mm if side else None)
    return DescriptorDimensions(width_mm=width, depth_mm=depth, height_mm=height)


def _uniform(values: list[str | None]) -> str | None:
    known = {item.strip() for item in values if item and item.strip()}
    return next(iter(known)) if len(known) == 1 else None


def build_descriptor(result: Result) -> FurnitureDescriptor:
    dimensions = _dimensions(result)
    if result.pieces:
        quantities: dict[str, int | None] = {}
        for piece in result.pieces:
            previous = quantities.get(piece.role)
            quantities[piece.role] = None if piece.quantity is None or (piece.role in quantities and previous is None) else (previous or 0) + piece.quantity
        roles = tuple(RoleQuantity(role=role, quantity=quantity) for role, quantity in sorted(quantities.items()))
    else:
        scenario = result.scenarios[0] if result.scenarios else None
        roles = tuple(RoleQuantity(role=item.role, quantity=item.quantity) for item in sorted(scenario.components, key=lambda value: value.role)) if scenario else ()
    material = _uniform([item.material for item in result.pieces])
    finish = _uniform([item.finish for item in result.pieces])
    unknowns: list[str] = []
    for field, value in dimensions.model_dump().items():
        if value is None:
            unknowns.append(f"dimensions.{field}")
    if material is None:
        unknowns.append("material")
    if finish is None:
        unknowns.append("finish")
    structure = _structure(result)
    if structure == "unknown":
        unknowns.append("structure")
    if not result.pieces:
        unknowns.append("confirmed_components")
    return FurnitureDescriptor(family="rectangular_shelving" if result.scenarios else "unknown", dimensions=dimensions, roles=roles, structure=structure, material=material, finish=finish, unknown_fields=tuple(sorted(unknowns)))


def descriptor_fingerprint(descriptor: FurnitureDescriptor) -> str:
    canonical = json.dumps(descriptor.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def semantic_text(descriptor: FurnitureDescriptor) -> str:
    roles = ", ".join(f"{item.role}:{item.quantity if item.quantity is not None else 'unknown'}" for item in descriptor.roles)
    dimensions = descriptor.dimensions
    return (
        f"descriptor={descriptor.descriptor_version}; family={descriptor.family}; structure={descriptor.structure}; "
        f"dimensions_mm=width:{dimensions.width_mm},depth:{dimensions.depth_mm},height:{dimensions.height_mm}; "
        f"roles={roles}; material={descriptor.material or 'unknown'}; finish={descriptor.finish or 'unknown'}; "
        f"unknowns={','.join(descriptor.unknown_fields) or 'none'}"
    )
