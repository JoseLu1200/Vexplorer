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
)


SUPPORTED_ROLES = {"side_panel", "top_panel", "base_panel", "shelf"}


def _scene_object(
    piece: ResolvedPiece,
    occurrence_index: int,
    position: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    placement_basis: str,
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
        placement_basis=placement_basis,
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
        complete[piece.role] = piece
    side = complete.get("side_panel")
    top = complete.get("top_panel")
    base = complete.get("base_panel")
    if side is None or top is None or base is None:
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision, state="incomplete",
            selected_scenario_id=scenario_id, warnings=tuple(warnings or ["envelope_pieces_missing"]),
            assumptions=tuple(scenario.assumptions),
        )
    thicknesses = {side.thickness_mm, top.thickness_mm, base.thickness_mm}
    depths = {side.width_mm, top.width_mm, base.width_mm}
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
                    f"{scenario_id}: observed FRONT/SIDE level entities {','.join(proposal.source_entity_ids)}",
                ))
    assumptions = tuple(scenario.assumptions) + (
        "Boxes are schematic reviewed panel occurrences, not manufacturing solids.",
        "Collision checking is not certified and remains not_evaluated.",
    )
    return ReconstructionScene(
        run_id=result.run_id, result_revision=result.result_revision,
        state="incomplete" if warnings else "ready", selected_scenario_id=scenario_id,
        objects=tuple(objects), warnings=tuple(warnings), assumptions=assumptions,
    )
