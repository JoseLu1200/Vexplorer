from __future__ import annotations

from backend.app.contratos.modelos import (
    Bounds3D,
    DrawingExtraction,
    EvaluatedTableComponent,
    EvaluatedTableProgram,
    MountedTableAnalysis,
    Point2D,
    Point3D,
    ReconstructionScene,
    Result,
    SceneObject,
    TableDrawingPlan,
    TableDrawingPrimitive,
    TableSheetPlan,
)


DIMENSION_OFFSET_MM = 50.0
VIEW_GAP_MM = 100.0


def _dimension(
    primitive_id: str,
    start: tuple[float, float],
    end: tuple[float, float],
    anchor: tuple[float, float],
    value: float,
    state: str,
    dependencies: tuple[str, ...],
) -> TableDrawingPrimitive:
    return TableDrawingPrimitive(
        id=primitive_id, kind="dimension",
        points_mm=tuple(Point2D(x=x, y=y) for x, y in (start, end, anchor)),
        text=f"{value:g} mm", value_mm=value, state=state,
        dependency_refs=dependencies,
    )


def _overall_state(
    analysis: MountedTableAnalysis,
    evaluated: EvaluatedTableProgram,
    semantic: str,
) -> str:
    measure = next(item for item in analysis.measures if item.semantic == semantic)
    value = {
        "overall_width": evaluated.overall_dimensions.width_mm,
        "overall_height": evaluated.overall_dimensions.height_mm,
        "overall_depth": evaluated.overall_dimensions.depth_mm,
    }[semantic]
    if measure.state == "observed":
        return "observed"
    if value is not None:
        return "confirmed"
    return measure.state


def _general_sheet(
    analysis: MountedTableAnalysis,
    evaluated: EvaluatedTableProgram,
) -> TableSheetPlan:
    width = evaluated.overall_dimensions.width_mm
    height = evaluated.overall_dimensions.height_mm
    depth = evaluated.overall_dimensions.depth_mm
    measure_refs = {
        item.semantic: f"measure:{item.id}"
        for item in analysis.measures
        if item.semantic in {"overall_width", "overall_height", "overall_depth"}
    }
    primitives: list[TableDrawingPrimitive] = []
    warnings: list[str] = []
    if width is not None and height is not None:
        primitives.append(TableDrawingPrimitive(
            id="general-front-envelope", kind="rect",
            points_mm=(Point2D(x=0.0, y=0.0), Point2D(x=width, y=height)),
            state="calculated" if evaluated.state == "completed" else "proposed",
            dependency_refs=(measure_refs["overall_width"], measure_refs["overall_height"]),
        ))
        primitives.extend((
            _dimension(
                "general-width", (0.0, 0.0), (width, 0.0), (0.0, -DIMENSION_OFFSET_MM),
                width, _overall_state(analysis, evaluated, "overall_width"),
                (measure_refs["overall_width"],),
            ),
            _dimension(
                "general-height", (width, 0.0), (width, height),
                (width + DIMENSION_OFFSET_MM, 0.0), height,
                _overall_state(analysis, evaluated, "overall_height"),
                (measure_refs["overall_height"],),
            ),
        ))
    else:
        warnings.append("overall_front_dimensions_unknown")
    if width is not None and depth is not None:
        top_y = (height or 0.0) + VIEW_GAP_MM
        primitives.append(TableDrawingPrimitive(
            id="general-top-envelope", kind="rect",
            points_mm=(Point2D(x=0.0, y=top_y), Point2D(x=width, y=top_y + depth)),
            state="calculated" if evaluated.state == "completed" else "proposed",
            dependency_refs=(measure_refs["overall_width"], measure_refs["overall_depth"]),
        ))
        primitives.append(_dimension(
            "general-depth", (0.0, top_y), (0.0, top_y + depth),
            (-DIMENSION_OFFSET_MM, top_y), depth,
            _overall_state(analysis, evaluated, "overall_depth"),
            (measure_refs["overall_depth"],),
        ))
    else:
        warnings.append("overall_top_dimensions_unknown")
    if width is not None and height is not None and depth is not None:
        top_y = height + VIEW_GAP_MM
        side_x = width + VIEW_GAP_MM
        for label, position in (
            ("FRONT", Point2D(x=0.0, y=height + 25.0)),
            ("TOP", Point2D(x=0.0, y=top_y + depth + 25.0)),
            ("SIDE", Point2D(x=side_x, y=height + 25.0)),
        ):
            primitives.append(TableDrawingPrimitive(
                id=f"general-view-label-{label.lower()}", kind="text",
                points_mm=(position,), text=label, state="calculated",
                dependency_refs=(),
            ))
        for placement in evaluated.placements:
            if placement.position_mm is None or placement.dimensions_mm is None:
                warnings.append(f"occurrence_projection_unknown:{placement.occurrence_id}")
                continue
            position = placement.position_mm
            size = placement.dimensions_mm
            primitive_state = "calculated" if placement.state == "pass" else "proposed"
            projections = {
                "front": (
                    Point2D(x=position.x, y=position.y),
                    Point2D(x=position.x + size.x, y=position.y + size.y),
                ),
                "top": (
                    Point2D(x=position.x, y=top_y + position.z),
                    Point2D(x=position.x + size.x, y=top_y + position.z + size.z),
                ),
                "side": (
                    Point2D(x=side_x + position.z, y=position.y),
                    Point2D(x=side_x + position.z + size.z, y=position.y + size.y),
                ),
            }
            for projection, points in projections.items():
                primitives.append(TableDrawingPrimitive(
                    id=f"general-occurrence-{placement.occurrence_id}-{projection}",
                    kind="rect", points_mm=points, state=primitive_state,
                    dependency_refs=placement.dependency_refs,
                ))
    else:
        warnings.append("occurrence_projections_unknown")
    if evaluated.state != "completed":
        warnings.append("program_not_fully_reviewed")
    return TableSheetPlan(
        sheet_id="table-general", kind="general", title="Mesa · vistas generales",
        page=1, status="ready" if not warnings else "incomplete",
        primitives=tuple(primitives), warnings=tuple(warnings),
    )


def _component_sheet(component: EvaluatedTableComponent, page: int) -> TableSheetPlan:
    fields = (component.length, component.width, component.thickness)
    values = tuple(item.value_mm for item in fields)
    primitives: list[TableDrawingPrimitive] = []
    warnings: list[str] = []
    if all(value is not None for value in values):
        length, width, thickness = (float(value) for value in values if value is not None)
        state = "proposed" if any(item.state == "proposed" for item in fields) else "calculated"
        primitives.extend((
            TableDrawingPrimitive(
                id=f"{component.id}-face", kind="rect",
                points_mm=(Point2D(x=0.0, y=0.0), Point2D(x=length, y=width)),
                state=state, dependency_refs=tuple(sorted({ref for item in fields for ref in item.dependency_refs})),
            ),
            TableDrawingPrimitive(
                id=f"{component.id}-section", kind="rect",
                points_mm=(
                    Point2D(x=length + VIEW_GAP_MM, y=0.0),
                    Point2D(x=length + VIEW_GAP_MM + thickness, y=width),
                ),
                state=state, dependency_refs=component.thickness.dependency_refs,
            ),
            _dimension(
                f"{component.id}-length", (0.0, 0.0), (length, 0.0),
                (0.0, -DIMENSION_OFFSET_MM), length, component.length.state,
                component.length.dependency_refs,
            ),
            _dimension(
                f"{component.id}-width", (0.0, 0.0), (0.0, width),
                (-DIMENSION_OFFSET_MM, 0.0), width, component.width.state,
                component.width.dependency_refs,
            ),
            _dimension(
                f"{component.id}-thickness",
                (length + VIEW_GAP_MM, 0.0),
                (length + VIEW_GAP_MM + thickness, 0.0),
                (length + VIEW_GAP_MM, -DIMENSION_OFFSET_MM),
                thickness, component.thickness.state, component.thickness.dependency_refs,
            ),
        ))
    else:
        warnings.append("component_dimensions_unknown")
        for index, (label, field) in enumerate(zip(("length", "width", "thickness"), fields)):
            if field.value_mm is None:
                primitives.append(TableDrawingPrimitive(
                    id=f"{component.id}-{label}-unknown", kind="text",
                    points_mm=(Point2D(x=0.0, y=index * 30.0),), text=f"{label}: ?",
                    state=field.state, dependency_refs=field.dependency_refs,
                ))
    if not component.accepted:
        warnings.append("component_not_accepted")
    primitives.append(TableDrawingPrimitive(
        id=f"{component.id}-quantity", kind="text",
        points_mm=(Point2D(x=0.0, y=(float(values[1]) if values[1] is not None else 90.0) + 50.0),),
        text=f"QTY={component.quantity}" if component.quantity is not None else "QTY=?",
        state="calculated" if component.accepted and component.quantity is not None else "proposed",
        dependency_refs=(f"quantity_rule:{component.quantity_rule_id}",),
    ))
    return TableSheetPlan(
        sheet_id=f"table-component-{component.id}", kind="component",
        title=f"Detalle · {component.role}", component_id=component.id, page=page,
        status="ready" if not warnings else "incomplete",
        primitives=tuple(primitives), warnings=tuple(warnings),
    )


def _cut_sheet(evaluated: EvaluatedTableProgram, page: int) -> TableSheetPlan:
    components = {item.id: item for item in evaluated.components}
    primitives: list[TableDrawingPrimitive] = []
    warnings: list[str] = []
    cursor_x = 0.0
    for occurrence in evaluated.occurrences:
        component = components[occurrence.component_id]
        if component.length.value_mm is None or component.width.value_mm is None:
            warnings.append(f"occurrence_dimensions_unknown:{occurrence.id}")
            primitives.append(TableDrawingPrimitive(
                id=f"{occurrence.id}-unknown", kind="text",
                points_mm=(Point2D(x=cursor_x, y=0.0),), text=f"{occurrence.id}: ?",
                state="unknown", dependency_refs=(),
            ))
            cursor_x += VIEW_GAP_MM
            continue
        length = component.length.value_mm
        width = component.width.value_mm
        primitives.extend((
            TableDrawingPrimitive(
                id=f"{occurrence.id}-rect", kind="rect",
                points_mm=(Point2D(x=cursor_x, y=0.0), Point2D(x=cursor_x + length, y=width)),
                state="calculated" if evaluated.state == "completed" else "proposed",
                dependency_refs=tuple(sorted(set(component.length.dependency_refs + component.width.dependency_refs))),
            ),
            TableDrawingPrimitive(
                id=f"{occurrence.id}-label", kind="text",
                points_mm=(Point2D(x=cursor_x, y=width + 25.0),),
                text=(
                    f"{component.role} · {occurrence.occurrence_index} · "
                    f"T={component.thickness.value_mm:g} mm"
                    if component.thickness.value_mm is not None
                    else f"{component.role} · {occurrence.occurrence_index} · T=?"
                ),
                state="calculated" if evaluated.state == "completed" else "proposed",
                dependency_refs=(f"component:{component.id}", *component.thickness.dependency_refs),
            ),
            _dimension(
                f"{occurrence.id}-length", (cursor_x, 0.0), (cursor_x + length, 0.0),
                (cursor_x, -DIMENSION_OFFSET_MM), length, component.length.state,
                component.length.dependency_refs,
            ),
            _dimension(
                f"{occurrence.id}-width", (cursor_x, 0.0), (cursor_x, width),
                (cursor_x - DIMENSION_OFFSET_MM, 0.0), width, component.width.state,
                component.width.dependency_refs,
            ),
        ))
        cursor_x += length + VIEW_GAP_MM
    if evaluated.state != "completed":
        warnings.append("program_not_fully_reviewed")
    return TableSheetPlan(
        sheet_id="table-cut-sheet", kind="cut_sheet", title="Hoja de despiece",
        page=page, status="ready" if not warnings else "incomplete",
        primitives=tuple(primitives), warnings=tuple(warnings),
    )


def derive_table_drawing_plan(
    extraction: DrawingExtraction,
    analysis: MountedTableAnalysis,
    evaluated: EvaluatedTableProgram,
    *,
    result_revision: int,
) -> TableDrawingPlan:
    if extraction.drawing_id != analysis.drawing_id or extraction.coordinate_unit != "mm":
        raise ValueError("table drawing plan requires matching metric extraction")
    sheets = [_general_sheet(analysis, evaluated)]
    sheets.extend(
        _component_sheet(component, page=index)
        for index, component in enumerate(evaluated.components, start=2)
    )
    sheets.append(_cut_sheet(evaluated, page=len(sheets) + 1))
    return TableDrawingPlan(
        drawing_id=extraction.drawing_id, result_revision=result_revision,
        program_hash=evaluated.program_hash, registry_versions=evaluated.registry_versions,
        overall_dimensions=evaluated.overall_dimensions, components=evaluated.components,
        occurrences=evaluated.occurrences, placements=evaluated.placements,
        sheets=tuple(sheets),
    )


def reconstruct_table_scene(
    extraction: DrawingExtraction,
    analysis: MountedTableAnalysis,
    result: Result,
) -> ReconstructionScene:
    evaluated = result.evaluated_table_program
    selected_id = result.selected_table_program_id
    if (
        result.input_semantics != "mounted_orthographic_views"
        or result.review is None
        or selected_id is None
        or evaluated is None
        or result.state != "completed"
        or evaluated.state != "completed"
    ):
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision,
            state="incomplete", selected_scenario_id=selected_id,
            warnings=("table_review_required",),
            assumptions=("No table solids are created before a complete explicit review.",),
        )
    if (
        extraction.drawing_id != analysis.drawing_id
        or result.table_analysis is None
        or result.table_analysis.ledger_revision != analysis.ledger_revision
        or evaluated.raw_program.id != selected_id
        or extraction.coordinate_unit != "mm"
    ):
        return ReconstructionScene(
            run_id=result.run_id, result_revision=result.result_revision,
            state="unavailable", selected_scenario_id=selected_id,
            warnings=("table_revision_mismatch",),
        )
    components = {item.id: item for item in evaluated.components}
    occurrences = {item.id: item for item in evaluated.occurrences}
    evidence = {item.id: item for item in extraction.evidence}
    contours = extraction.contours
    objects: list[SceneObject] = []
    warnings: list[str] = []
    for placement in evaluated.placements:
        occurrence = occurrences.get(placement.occurrence_id)
        if (
            occurrence is None or placement.state != "pass"
            or placement.position_mm is None or placement.dimensions_mm is None
        ):
            warnings.append(f"incomplete_table_placement:{placement.occurrence_id}")
            continue
        component = components[occurrence.component_id]
        source_entities = {
            entity_id
            for evidence_id in component.evidence_ids
            if evidence_id in evidence
            for entity_id in evidence[evidence_id].source_entity_ids
        }
        source_contours = tuple(sorted(
            item.id for item in contours if set(item.source_entity_ids) & source_entities
        ))
        position = placement.position_mm
        dimensions = placement.dimensions_mm
        objects.append(SceneObject(
            id=f"scene-{occurrence.id}", piece_id=component.id,
            proposal_id=evaluated.raw_program.id, role=component.role,
            label=component.role.replace("_", " "),
            occurrence_index=occurrence.occurrence_index,
            position_mm=position, dimensions_mm=dimensions,
            bbox_mm=Bounds3D(
                min=position,
                max=Point3D(
                    x=position.x + dimensions.x,
                    y=position.y + dimensions.y,
                    z=position.z + dimensions.z,
                ),
            ),
            source_contour_ids=source_contours, evidence_ids=component.evidence_ids,
            placement_basis=f"{placement.rule_id}@{placement.rule_version}; program {evaluated.program_hash}",
            placement_status="human_selected",
            placement_constraint_ids=placement.dependency_refs,
        ))
    state = "ready" if not warnings and len(objects) == len(evaluated.occurrences) else "incomplete"
    return ReconstructionScene(
        run_id=result.run_id, result_revision=result.result_revision,
        state=state, selected_scenario_id=selected_id, objects=tuple(objects),
        warnings=tuple(warnings), assumptions=(
            "Objects are reviewed schematic occurrences generated by versioned placement rules.",
            "No joinery, material, strength, collision certification, or manufacturing readiness is inferred.",
        ),
    )
