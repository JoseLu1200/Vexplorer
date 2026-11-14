from __future__ import annotations

from backend.app.contratos.modelos import (
    Bounds3D,
    DrawingExtraction,
    Point3D,
    ReconstructionScene,
    ResolvedPiece,
    Result,
    SceneObject,
    Size3D,
    SeparatedPartsExtraction,
)
from backend.app.geometria.parts import recompute_reviewed_assembly_candidate


SUPPORTED_ROLES = {"side_panel", "top_panel", "base_panel", "shelf"}


def _scene_object(
    piece: ResolvedPiece,
    occurrence_index: int,
    position: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    placement_basis: str,
    part_observation_id: str | None = None,
) -> SceneObject:
    point = Point3D(x=position[0], y=position[1], z=position[2])
    size = Size3D(x=dimensions[0], y=dimensions[1], z=dimensions[2])
    return SceneObject(
        id=f"scene-{piece.id}-{occurrence_index}", piece_id=piece.id, proposal_id=piece.proposal_id,
        role=piece.role, label=piece.label, occurrence_index=occurrence_index,
        position_mm=point, dimensions_mm=size,
        bbox_mm=Bounds3D(
            min=point,
            max=Point3D(x=point.x + size.x, y=point.y + size.y, z=point.z + size.z),
        ),
        source_contour_ids=piece.source_contour_ids, evidence_ids=piece.evidence_ids,
        placement_basis=placement_basis, part_observation_id=part_observation_id,
    )


def _shelf_levels(extraction: DrawingExtraction, source_entity_ids: tuple[str, ...]) -> tuple[float, ...]:
    front = next((view for view in extraction.views if view.label == "FRONT"), None)
    if front is None:
        return ()
    front_ids = set(front.entity_ids)
    entities = {item.id: item for item in extraction.entities}
    front_contours = [
        contour for contour in extraction.contours
        if contour.view_id == front.id and contour.points_mm is not None
    ]
    if not front_contours:
        return ()
    outer = max(
        front_contours,
        key=lambda contour: (
            max(point.x for point in contour.points_mm or ()) - min(point.x for point in contour.points_mm or ())
        ) * (
            max(point.y for point in contour.points_mm or ()) - min(point.y for point in contour.points_mm or ())
        ),
    )
    min_y = min(point.y for point in outer.points_mm or ())
    levels = []
    for entity_id in source_entity_ids:
        entity = entities.get(entity_id)
        if entity_id not in front_ids or entity is None or entity.kind != "LINE" or not entity.points_mm or len(entity.points_mm) != 2:
            continue
        first, second = entity.points_mm
        if abs(first.y - second.y) <= 1e-6:
            levels.append(first.y - min_y)
    return tuple(sorted(set(levels)))


def reconstruct_scene(extraction: DrawingExtraction, result: Result) -> ReconstructionScene:
    review = result.review
    scenario_id = review.selected_scenario_id if review is not None else None
    if review is None or scenario_id is None:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            warnings=("human_review_required",), assumptions=("No 3D solid is created before mounting review.",),
        )
    if extraction.coordinate_unit != "mm":
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            selected_scenario_id=scenario_id, warnings=("metric_geometry_required",),
            assumptions=("Source coordinates are not treated as millimetres.",),
        )
    scenario = next((item for item in result.scenarios if item.id == scenario_id), None)
    if scenario is None:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            selected_scenario_id=scenario_id, warnings=("selected_scenario_missing",),
        )
    proposals = {item.id: item for item in scenario.components}
    warnings: list[str] = []
    complete: dict[str, ResolvedPiece] = {}
    duplicate_role = False
    for piece in result.pieces:
        if piece.proposal_id not in proposals or piece.role not in SUPPORTED_ROLES:
            warnings.append(f"unsupported_placement:{piece.id}")
            continue
        if (
            piece.quantity is None or piece.length_mm is None or piece.width_mm is None
            or piece.thickness_mm is None
        ):
            warnings.append(f"incomplete_piece:{piece.id}")
            continue
        if piece.role in complete:
            warnings.append(f"duplicate_resolved_role:{piece.role}")
            duplicate_role = True
            continue
        complete[piece.role] = piece
    if duplicate_role:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=scenario_id, warnings=tuple(warnings),
            assumptions=tuple(scenario.assumptions),
        )
    side = complete.get("side_panel")
    top = complete.get("top_panel")
    base = complete.get("base_panel")
    if side is None or top is None or base is None:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=scenario_id, warnings=tuple(warnings or ["envelope_pieces_missing"]),
            assumptions=tuple(scenario.assumptions),
        )
    thicknesses = {piece.thickness_mm for piece in complete.values()}
    depths = {piece.width_mm for piece in complete.values()}
    if len(thicknesses) != 1 or len(depths) != 1:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=scenario_id, warnings=tuple(warnings + ["inconsistent_panel_dimensions"]),
            assumptions=tuple(scenario.assumptions),
        )
    thickness = side.thickness_mm
    depth = side.width_mm
    if scenario_id == "scenario-between-sides":
        width = top.length_mm + 2 * thickness
        height = side.length_mm
        side_y = 0.0
        horizontal_x = thickness
        horizontal_width = width - 2 * thickness
    elif scenario_id == "scenario-cap-sides":
        width = top.length_mm
        height = side.length_mm + 2 * thickness
        side_y = thickness
        horizontal_x = 0.0
        horizontal_width = width
    else:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            selected_scenario_id=scenario_id, warnings=("unsupported_mounting_scenario",),
            assumptions=tuple(scenario.assumptions),
        )
    if abs(top.length_mm - horizontal_width) > 1e-6 or abs(base.length_mm - horizontal_width) > 1e-6:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=scenario_id,
            warnings=tuple(warnings + ["inconsistent_resolved_dimensions"]),
            assumptions=tuple(scenario.assumptions),
        )

    objects: list[SceneObject] = []
    if side.quantity == 2:
        for index, x in enumerate((0.0, width - thickness), start=1):
            objects.append(_scene_object(
                side, index, (x, side_y, 0.0), (thickness, side.length_mm, depth),
                f"{scenario_id}: reviewed side placement",
            ))
    else:
        warnings.append(f"unsupported_quantity:{side.id}")
    if top.quantity == 1:
        objects.append(_scene_object(
            top, 1, (horizontal_x, height - thickness, 0.0), (horizontal_width, thickness, depth),
            f"{scenario_id}: reviewed top placement",
        ))
    else:
        warnings.append(f"unsupported_quantity:{top.id}")
    if base.quantity == 1:
        objects.append(_scene_object(
            base, 1, (horizontal_x, 0.0, 0.0), (horizontal_width, thickness, depth),
            f"{scenario_id}: reviewed base placement",
        ))
    else:
        warnings.append(f"unsupported_quantity:{base.id}")
    shelf = complete.get("shelf")
    if shelf is not None:
        proposal = proposals[shelf.proposal_id]
        levels = _shelf_levels(extraction, proposal.source_entity_ids)
        if shelf.quantity is None or len(levels) != shelf.quantity:
            warnings.append(f"shelf_levels_incomplete:{shelf.id}")
        elif shelf.length_mm != width - 2 * thickness:
            warnings.append(f"shelf_width_inconsistent:{shelf.id}")
        else:
            for index, level in enumerate(levels, start=1):
                if level < 0 or level + shelf.thickness_mm > height:
                    warnings.append(f"shelf_level_out_of_bounds:{shelf.id}:{index}")
                    continue
                objects.append(_scene_object(
                    shelf, index, (thickness, level, 0.0),
                    (shelf.length_mm, shelf.thickness_mm, shelf.width_mm),
                    f"{scenario_id}: observed FRONT/SIDE level anchors the shelf lower face; entities {','.join(proposal.source_entity_ids)}",
                ))
    assumptions = tuple(scenario.assumptions) + (
        "Boxes are schematic reviewed panel occurrences, not manufacturing solids.",
        "Each observed shelf level is interpreted as the lower face of its reviewed shelf box.",
        "Collision checking is not certified and remains not_evaluated.",
    )
    return ReconstructionScene(
        run_id=result.run_id, result_revision=result.result_revision,
        state="incomplete" if warnings else "ready", selected_scenario_id=scenario_id,
        objects=tuple(objects), warnings=tuple(warnings), assumptions=assumptions,
    )


def reconstruct_parts_scene(
    extraction: DrawingExtraction,
    parts: SeparatedPartsExtraction,
    result: Result,
) -> ReconstructionScene:
    candidate_id = result.selected_assembly_candidate_id
    if (
        result.input_semantics != "separated_part_views"
        or result.review is None
        or result.review.selected_assembly_candidate_id is None
        or candidate_id is None
    ):
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            warnings=("assembly_review_required",),
            assumptions=("No part solid is created before explicit assembly-candidate review.",),
        )
    if extraction.coordinate_unit != "mm" or extraction.drawing_id != parts.drawing_id:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            selected_scenario_id=candidate_id, warnings=("metric_parts_geometry_required",),
        )
    candidate = next((item for item in result.assembly_candidates if item.id == candidate_id), None)
    if candidate is None:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="unavailable",
            selected_scenario_id=candidate_id, warnings=("selected_assembly_candidate_missing",),
        )
    candidate = recompute_reviewed_assembly_candidate(
        candidate, parts, result.pieces, result_revision=result.result_revision,
    )
    pieces = {item.proposal_id: item for item in result.pieces}
    warnings = []
    occurrence_indices_by_use: dict[str, tuple[int, ...]] = {}
    for use in candidate.uses:
        piece = pieces.get(use.id)
        if piece is None or any(value is None for value in (piece.quantity, piece.length_mm, piece.width_mm, piece.thickness_mm)):
            warnings.append(f"incomplete_piece:{use.id}")
            continue
        assert piece.quantity is not None
        if use.allocated_quantity is not None and use.occurrence_indices:
            if len(use.occurrence_indices) != piece.quantity:
                warnings.append(f"resolved_quantity_mismatch:{use.id}")
                continue
            occurrence_indices_by_use[use.id] = use.occurrence_indices
        elif use.allocated_quantity is None and piece.field_states.get("quantity") == "confirmed":
            occurrence_indices_by_use[use.id] = tuple(range(1, piece.quantity + 1))
        else:
            warnings.append(f"resolved_occurrences_missing:{use.id}")
    if result.state != "completed" or warnings:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=candidate_id, warnings=tuple(warnings or ("assembly_constraints_incomplete",)),
            assumptions=tuple(candidate.assumptions),
        )
    if any(item.status != "pass" for item in candidate.constraints) or any(item.state != "derived" for item in candidate.derived_dimensions):
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=candidate_id, warnings=("assembly_constraints_incomplete",),
            assumptions=tuple(candidate.assumptions),
        )
    dimensions = {item.axis: item.value_mm for item in candidate.derived_dimensions}
    width, height, depth = dimensions.get("width"), dimensions.get("height"), dimensions.get("depth")
    if width is None or height is None or depth is None:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=candidate_id, warnings=("assembly_dimensions_incomplete",),
            assumptions=tuple(candidate.assumptions),
        )

    by_role = {role: [pieces[use.id] for use in candidate.uses if use.role == role] for role in SUPPORTED_ROLES}
    if len(by_role["side_panel"]) != 1 or len(by_role["top_panel"]) != 1 or len(by_role["base_panel"]) != 1:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=candidate_id, warnings=("envelope_pieces_missing",),
            assumptions=tuple(candidate.assumptions),
        )
    side, top, base = by_role["side_panel"][0], by_role["top_panel"][0], by_role["base_panel"][0]
    shelf = by_role["shelf"][0] if len(by_role["shelf"]) == 1 else None
    thickness = side.thickness_mm
    assert thickness is not None
    all_pieces = (side, top, base) + ((shelf,) if shelf else ())
    if any(piece.width_mm != depth or piece.thickness_mm != thickness for piece in all_pieces):
        warnings.append("inconsistent_panel_dimensions")
    if candidate.layout == "between_sides":
        horizontal_x, side_y = thickness, 0.0
        expected_side_length, expected_horizontal_length = height, width - 2 * thickness
    elif candidate.layout == "cap_sides":
        horizontal_x, side_y = 0.0, thickness
        expected_side_length, expected_horizontal_length = height - 2 * thickness, width
    else:
        warnings.append("unsupported_mounting_scenario")
        expected_side_length = expected_horizontal_length = -1.0
        horizontal_x = side_y = 0.0
    expected_shelf_length = width - 2 * thickness
    if side.length_mm != expected_side_length or top.length_mm != expected_horizontal_length or base.length_mm != expected_horizontal_length:
        warnings.append("inconsistent_resolved_dimensions")
    if shelf is not None and shelf.length_mm != expected_shelf_length:
        warnings.append("shelf_width_inconsistent")
    if side.quantity != 2 or top.quantity != 1 or base.quantity != 1:
        warnings.append("unsupported_envelope_quantity")
    if warnings:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=candidate_id, warnings=tuple(warnings),
            assumptions=tuple(candidate.assumptions),
        )

    objects = []
    for use in candidate.uses:
        piece = pieces[use.id]
        observation_id = use.part_observation_id
        indices = occurrence_indices_by_use[use.id]
        if piece.role == "side_panel":
            for occurrence_index, x in zip(indices, (0.0, width - thickness), strict=True):
                objects.append(_scene_object(
                    piece, occurrence_index, (x, side_y, 0.0), (thickness, piece.length_mm, depth),
                    f"{candidate.id}: reviewed side placement", observation_id,
                ))
        elif piece.role == "top_panel":
            objects.append(_scene_object(
                piece, indices[0], (horizontal_x, height - thickness, 0.0),
                (piece.length_mm, thickness, depth), f"{candidate.id}: reviewed top placement", observation_id,
            ))
        elif piece.role == "base_panel":
            objects.append(_scene_object(
                piece, indices[0], (horizontal_x, 0.0, 0.0),
                (piece.length_mm, thickness, depth), f"{candidate.id}: reviewed base placement", observation_id,
            ))
        elif piece.role == "shelf":
            count = len(indices)
            for rank, occurrence_index in enumerate(indices, start=1):
                level = (height - thickness) * rank / (count + 1)
                objects.append(_scene_object(
                    piece, occurrence_index, (thickness, level, 0.0),
                    (piece.length_mm, thickness, depth),
                    f"{candidate.id}: schematic evenly spaced shelf placement; height not observed", observation_id,
                ))
    assumptions = tuple(candidate.assumptions) + (
        "Boxes are schematic reviewed panel occurrences, not manufacturing solids.",
        "Shelf heights are schematic evenly spaced hypotheses because separate part views do not observe assembly levels.",
        "Collision checking is not certified and remains not_evaluated.",
    )
    return ReconstructionScene(
        run_id=result.run_id, result_revision=result.result_revision, state="ready",
        selected_scenario_id=candidate_id, objects=tuple(objects), assumptions=assumptions,
    )
