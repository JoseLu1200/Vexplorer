from __future__ import annotations

import hashlib
import json

from backend.app.contratos.modelos import AssemblyCandidate, DescriptorDimensions, DescriptorPartFeature, FurnitureDescriptor, FurnitureDescriptorV2, FurnitureDescriptorV3, Result, RoleQuantity, TableDescriptorComponentFeature

Descriptor = FurnitureDescriptor | FurnitureDescriptorV2 | FurnitureDescriptorV3


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
    if not values or any(item is None or not item.strip() for item in values):
        return None
    known = {item.strip() for item in values if item and item.strip()}
    return next(iter(known)) if len(known) == 1 else None


def _candidate_roles(candidate: AssemblyCandidate) -> tuple[RoleQuantity, ...]:
    values: dict[str, int | None] = {}
    for use in candidate.uses:
        if use.role not in values:
            values[use.role] = use.allocated_quantity
        elif values[use.role] is None or use.allocated_quantity is None:
            values[use.role] = None
        else:
            values[use.role] += use.allocated_quantity
    return tuple(RoleQuantity(role=role, quantity=quantity) for role, quantity in sorted(values.items()))


def _consensus(values):
    first = values[0] if values else None
    return first if values and all(item == first for item in values) else None


def _build_parts_descriptor(result: Result) -> FurnitureDescriptorV2:
    selected = next((item for item in result.assembly_candidates if item.id == result.selected_assembly_candidate_id), None)
    candidates = (selected,) if selected is not None else result.assembly_candidates
    family = _consensus([item.family for item in candidates]) or "unknown"
    layout = _consensus([item.layout for item in candidates]) or "unknown"
    structure = {"between_sides": "top_base_between_sides", "cap_sides": "top_base_cap_sides"}.get(layout, "unknown")
    if selected is not None and result.review is not None and result.pieces:
        role_quantities: dict[str, int | None] = {}
        for piece in result.pieces:
            current = role_quantities.get(piece.role)
            role_quantities[piece.role] = None if piece.quantity is None or (piece.role in role_quantities and current is None) else (current or 0) + piece.quantity
        roles = tuple(RoleQuantity(role=role, quantity=quantity) for role, quantity in sorted(role_quantities.items()))
    else:
        role_options = [_candidate_roles(item) for item in candidates]
        roles = _consensus(role_options) or ()
    dimensions_by_candidate = [{item.axis: item.value_mm if item.state == "derived" else None for item in candidate.derived_dimensions} for candidate in candidates]
    dimensions = DescriptorDimensions(
        width_mm=_consensus([item.get("width") for item in dimensions_by_candidate]),
        depth_mm=_consensus([item.get("depth") for item in dimensions_by_candidate]),
        height_mm=_consensus([item.get("height") for item in dimensions_by_candidate]),
    )
    thicknesses = sorted({piece.thickness_mm for piece in result.pieces if piece.thickness_mm is not None})
    if not thicknesses and result.part_analysis is not None:
        thicknesses = sorted({item.dimensions.thickness.value_mm for item in result.part_analysis.observations if item.dimensions.thickness.state == "observed" and item.dimensions.thickness.value_mm is not None})
    material = _uniform([item.material for item in result.pieces])
    finish = _uniform([item.finish for item in result.pieces])
    unknowns = {field for candidate in candidates for field in candidate.unknown_fields}
    for field, value in dimensions.model_dump().items():
        if value is None:
            unknowns.add(f"dimensions.{field}")
    if family == "unknown":
        unknowns.add("family")
    if structure == "unknown":
        unknowns.add("structure")
    if not thicknesses:
        unknowns.add("thicknesses_mm")
    if material is None:
        unknowns.add("material")
    if finish is None:
        unknowns.add("finish")
    classification_status = "confirmed" if selected is not None and result.review is not None else "hypothesis"
    features = []
    if result.part_analysis is not None:
        pieces_by_observation: dict[str, list] = {}
        for piece in result.pieces:
            for observation_id in piece.source_part_observation_ids:
                pieces_by_observation.setdefault(observation_id, []).append(piece)
        for observation in result.part_analysis.observations:
            resolved = pieces_by_observation.get(observation.id, [])
            observed_values = {
                "length_mm": observation.dimensions.length.value_mm,
                "width_mm": observation.dimensions.width.value_mm,
                "thickness_mm": observation.dimensions.thickness.value_mm,
                "quantity": observation.quantity.value,
            }
            values = dict(observed_values)
            states = {
                "length_mm": "observed" if observed_values["length_mm"] is not None else "unknown",
                "width_mm": "observed" if observed_values["width_mm"] is not None else "unknown",
                "thickness_mm": "observed" if observed_values["thickness_mm"] is not None else "unknown",
                "quantity": "observed" if observed_values["quantity"] is not None else "unknown",
            }
            if resolved:
                for field in ("length_mm", "width_mm", "thickness_mm"):
                    effective = {getattr(piece, field) for piece in resolved if getattr(piece, field) is not None}
                    values[field] = next(iter(effective)) if len(effective) == 1 else None
                    piece_states = {piece.field_states[field] for piece in resolved}
                    states[field] = "confirmed" if values[field] is not None and "confirmed" in piece_states else "observed" if values[field] is not None else "unknown"
                quantities = [piece.quantity for piece in resolved]
                values["quantity"] = sum(quantities) if quantities and all(value is not None for value in quantities) else None
                quantity_states = {piece.field_states["quantity"] for piece in resolved}
                states["quantity"] = "confirmed" if values["quantity"] is not None and "confirmed" in quantity_states else "observed" if values["quantity"] is not None else "unknown"
                if selected is not None:
                    for use in selected.uses:
                        if use.part_observation_id != observation.id:
                            continue
                        for field, value in values.items():
                            if value is not None:
                                unknowns.discard(f"uses.{use.id}.{field.removesuffix('_mm')}")
            features.append(DescriptorPartFeature(
                **values,
                unknown_fields=tuple(field for field, value in values.items() if value is None),
                field_states=states,
            ))
    if result.review is not None and result.pieces and all(piece.role != "unknown" for piece in result.pieces):
        unknowns.discard("roles.top_panel")
        unknowns.discard("roles.base_panel")
    features.sort(key=lambda item: (
        tuple((value is None, value or 0) for value in (item.length_mm, item.width_mm, item.thickness_mm, item.quantity)),
        tuple(item.field_states.get(field, "") for field in ("length_mm", "width_mm", "thickness_mm", "quantity")),
    ))
    return FurnitureDescriptorV2(family=family, dimensions=dimensions, roles=roles, structure=structure, material=material, finish=finish, thicknesses_mm=tuple(thicknesses), classification_status=classification_status, part_features=tuple(features), unknown_fields=tuple(sorted(unknowns)))


def _build_table_descriptor(result: Result) -> FurnitureDescriptorV3:
    evaluated = result.evaluated_table_program
    if result.state != "completed" or evaluated is None or evaluated.state != "completed" or result.selected_table_program_id is None:
        raise ValueError("table_revision_not_accepted")
    features = []
    cost_scope = result.table_cost_scope
    for component in evaluated.components:
        if not component.accepted or component.quantity is None:
            raise ValueError("table_revision_not_accepted")
        values = (component.length, component.width, component.thickness)
        if any(item.value_mm is None or item.state not in ("calculated", "confirmed") for item in values):
            raise ValueError("table_revision_not_accepted")
        features.append(TableDescriptorComponentFeature(
            role=component.role,
            quantity=component.quantity,
            length_mm=component.length.value_mm,
            width_mm=component.width.value_mm,
            thickness_mm=component.thickness.value_mm,
            material_tariff_id=(
                cost_scope.component_material_tariff_ids.get(component.id, cost_scope.material_tariff_id)
                if cost_scope is not None
                else None
            ),
            field_states={
                "quantity": "calculated",
                "length_mm": component.length.state,
                "width_mm": component.width.state,
                "thickness_mm": component.thickness.state,
            },
        ))
    features.sort(key=lambda item: (item.role, item.length_mm, item.width_mm, item.thickness_mm, item.quantity))
    dimensions = DescriptorDimensions(**evaluated.overall_dimensions.model_dump())
    if any(value is None for value in dimensions.model_dump().values()):
        raise ValueError("table_revision_not_accepted")
    roles = {item.role for item in features}
    structure = "side_support_table" if "side_support" in roles else "corner_support_table"
    uniform_material = None
    if cost_scope is not None and not cost_scope.component_material_tariff_ids:
        uniform_material = cost_scope.material_tariff_id
    unknown_fields = () if all(item.material_tariff_id is not None for item in features) else ("material_tariff_id",)
    return FurnitureDescriptorV3(
        dimensions=dimensions,
        structure=structure,
        components=tuple(features),
        material_tariff_id=uniform_material,
        unknown_fields=unknown_fields,
    )


def build_descriptor(result: Result) -> Descriptor:
    if result.input_semantics == "mounted_orthographic_views":
        return _build_table_descriptor(result)
    if result.input_semantics == "separated_part_views":
        return _build_parts_descriptor(result)
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


def descriptor_fingerprint(descriptor: Descriptor) -> str:
    canonical = json.dumps(descriptor.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def semantic_text(descriptor: Descriptor) -> str:
    roles = ", ".join(f"{item.role}:{item.quantity if item.quantity is not None else 'unknown'}" for item in descriptor.roles) if not isinstance(descriptor, FurnitureDescriptorV3) else ", ".join(f"{item.role}:{item.quantity}" for item in descriptor.components)
    dimensions = descriptor.dimensions
    parts_suffix = ""
    if isinstance(descriptor, FurnitureDescriptorV2):
        feature_text = "|".join(
            f"L:{item.length_mm}:{item.field_states.get('length_mm', 'legacy')},"
            f"W:{item.width_mm}:{item.field_states.get('width_mm', 'legacy')},"
            f"T:{item.thickness_mm}:{item.field_states.get('thickness_mm', 'legacy')},"
            f"Q:{item.quantity}:{item.field_states.get('quantity', 'legacy')}"
            for item in descriptor.part_features
        )
        parts_suffix = f"; thicknesses_mm:{','.join(f'{item:g}' for item in descriptor.thicknesses_mm) or 'unknown'}; classification_status={descriptor.classification_status}; part_features={feature_text or 'none'}"
    elif isinstance(descriptor, FurnitureDescriptorV3):
        parts_suffix = "; components=" + "|".join(
            f"role:{item.role},q:{item.quantity},l:{item.length_mm:g},w:{item.width_mm:g},t:{item.thickness_mm:g},material_tariff:{item.material_tariff_id or 'unknown'}"
            for item in descriptor.components
        )
    return (
        f"descriptor={descriptor.descriptor_version}; family={descriptor.family}; structure={descriptor.structure}; "
        f"dimensions_mm=width:{dimensions.width_mm},depth:{dimensions.depth_mm},height:{dimensions.height_mm}; "
        f"roles={roles}; material={getattr(descriptor, 'material', None) or 'unknown'}; finish={getattr(descriptor, 'finish', None) or 'unknown'}; "
        f"unknowns={','.join(descriptor.unknown_fields) or 'none'}{parts_suffix}"
    )
