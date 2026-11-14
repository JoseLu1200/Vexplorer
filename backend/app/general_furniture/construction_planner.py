"""Deterministic 2D sheet planning for a reviewed construction scenario."""
from __future__ import annotations

from math import cos, radians, sin

from backend.app.contratos.modelos import (
    GeneralConstructionDimension,
    GeneralConstructionPiece,
    GeneralConstructionPlan,
    GeneralConstructionQuantity,
    GeneralConstructionSummary,
    GeneralConstructionValidation,
    GeneralConstructionWarning,
    GeneralFurnitureReview,
    GeneralSheetPlan,
    GeneralSheetPrimitive,
    Point2D,
)


_VIEW_GAP_MM = 100.0
_DIMENSION_OFFSET_MM = 45.0
_CALLOUT_LINE_MAX_CHARS = 120


def _refs(*values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(reference for items in values for reference in items))


def _split_preserving_text(text: str, limits: tuple[int, ...]) -> tuple[str, ...]:
    """Wrap at word boundaries while retaining every source character."""
    chunks: list[str] = []
    remaining = text
    index = 0
    while remaining:
        limit = limits[min(index, len(limits) - 1)]
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        boundary = remaining.rfind(" ", 0, limit + 1)
        take = limit if boundary <= 0 else boundary + 1
        chunks.append(remaining[:take])
        remaining = remaining[take:]
        index += 1
    return tuple(chunks)


def _review_status(review: GeneralFurnitureReview, component_id: str, field: str) -> str:
    if review.reviewer_kind == "human":
        return "accepted"
    target = f"component:{component_id}.{field}"
    decision = next((item for item in review.machine_field_reviews if item.target_ref == target), None)
    return decision.status if decision is not None else "unreviewed"


def _dimension(review: GeneralFurnitureReview, component, field: str) -> GeneralConstructionDimension:
    value = getattr(component, field)
    review_status = _review_status(review, component.id, field)
    state = value.state
    if review_status != "accepted" or state in {"unknown", "conflict"}:
        return GeneralConstructionDimension(
            value_mm=None,
            range_mm=None,
            state="conflict" if state == "conflict" or review_status == "conflict" else "unknown",
            review_status=review_status,
            source_refs=_refs(value.dependency_refs, value.evidence_ids, value.dimension_ids),
            explanation=f"{field} no aceptado para el escenario constructivo.",
        )
    if state in {"derived", "deduced"}:
        authority = "deduced"
    elif state in {"estimated", "hypothesis"}:
        authority = "estimated"
    else:
        authority = "observed"
    parameter_id = next(
        (reference.removeprefix("parameter:") for reference in value.dependency_refs if reference.startswith("parameter:")),
        None,
    )
    parameter = next((item for item in review.construction_parameters if item.id == parameter_id), None)
    if parameter is not None:
        authority = parameter.state
    range_mm = value.range_mm or (parameter.range_mm if parameter is not None else None)
    assumption_refs = value.assumption_refs or (parameter.assumption_refs if parameter is not None else ())
    method = value.method or (parameter.method if parameter is not None else None)
    formula = value.formula or (parameter.formula if parameter is not None else None)
    operand_refs = value.dependency_refs or (parameter.dependency_refs if parameter is not None else ())
    if authority == "estimated" and (range_mm is None or not assumption_refs):
        return GeneralConstructionDimension(
            value_mm=None,
            state="unknown",
            review_status="unreviewed",
            source_refs=_refs(value.dependency_refs, value.evidence_ids, value.dimension_ids),
            explanation=f"{field} estimado sin rango o premisa cerrada.",
        )
    if authority == "deduced" and not formula:
        formula = parameter.rationale if parameter is not None else f"deduced:{field}"
    return GeneralConstructionDimension(
        value_mm=value.value_mm,
        range_mm=range_mm,
        state=authority,
        review_status=review_status,
        method=method,
        formula=formula,
        operand_refs=operand_refs,
        source_refs=_refs(
            value.dependency_refs,
            value.evidence_ids,
            value.dimension_ids,
            parameter.source_refs if parameter is not None else (),
        ),
        assumption_refs=assumption_refs,
        explanation=parameter.rationale if parameter is not None else f"{field} del escenario revisado.",
    )


def _quantity(review: GeneralFurnitureReview, component) -> GeneralConstructionQuantity:
    value = component.quantity
    review_status = _review_status(review, component.id, "quantity")
    if review_status != "accepted" or value.value is None or value.state in {"unknown", "conflict"}:
        return GeneralConstructionQuantity(
            value=None,
            state="conflict" if value.state == "conflict" or review_status == "conflict" else "unknown",
            review_status=review_status,
            source_refs=_refs(value.dependency_refs, value.evidence_ids),
            explanation="Cantidad no aceptada para el escenario constructivo.",
        )
    state = "deduced" if value.state in {"derived", "deduced"} else "estimated" if value.state in {"estimated", "hypothesis"} else "observed"
    assumptions = component.quantity_basis_refs or tuple(
        reference for reference in value.dependency_refs if reference.startswith("premise:")
    )
    return GeneralConstructionQuantity(
        value=value.value,
        min_value=value.value if state == "estimated" else None,
        max_value=value.value if state == "estimated" else None,
        state=state,
        review_status=review_status,
        method="scenario_quantity" if state == "estimated" else "reviewed_quantity",
        source_refs=_refs(value.dependency_refs, value.evidence_ids),
        assumption_refs=assumptions,
        explanation="Cantidad del escenario; no deriva del número de vistas.",
    )


def _dimension_text(dimension: GeneralConstructionDimension) -> str:
    if dimension.value_mm is None:
        return "?"
    value = f"{dimension.value_mm:g} mm"
    if dimension.state == "estimated" and dimension.range_mm is not None:
        return f"≈ {value} [{dimension.range_mm.min_mm:g}–{dimension.range_mm.max_mm:g}]"
    return value


def _piece_sheet(
    piece: GeneralConstructionPiece,
    details,
    parameter_dimensions: dict[str, GeneralConstructionDimension],
    validation_warnings: tuple[GeneralConstructionWarning, ...],
) -> GeneralSheetPlan:
    warnings: list[GeneralConstructionWarning] = list(validation_warnings)
    primitives: list[GeneralSheetPrimitive] = []
    dimensions = (piece.length, piece.width, piece.thickness)
    drawable = (
        piece.geometry.shape_kind in {"rectangle", "linear"}
        and all(item.value_mm is not None and item.review_status == "accepted" for item in dimensions)
    )
    if not drawable:
        warnings.append(GeneralConstructionWarning(
            severity="warning",
            code="piece_geometry_incomplete",
            message="La pieza no tiene forma explícita y tres dimensiones aceptadas.",
            component_refs=(piece.component_id,),
            field_refs=("length", "width", "thickness"),
            consequence="provisional_only",
        ))
    else:
        length = float(piece.length.value_mm)
        width = float(piece.width.value_mm)
        thickness = float(piece.thickness.value_mm)
        source_refs = _refs(piece.source_refs, piece.geometry.basis_refs)
        outline_state = "estimated" if any(item.state == "estimated" for item in dimensions) else "deduced" if any(item.state == "deduced" for item in dimensions) else "observed"
        primitives.extend((
            GeneralSheetPrimitive(
                kind="polyline",
                points_mm=tuple(Point2D(x=x, y=y) for x, y in ((0, 0), (length, 0), (length, width), (0, width), (0, 0))),
                state=outline_state,
                source_refs=source_refs,
            ),
            GeneralSheetPrimitive(
                kind="polyline",
                points_mm=tuple(Point2D(x=x, y=y) for x, y in ((length + _VIEW_GAP_MM, 0), (length + _VIEW_GAP_MM + thickness, 0), (length + _VIEW_GAP_MM + thickness, width), (length + _VIEW_GAP_MM, width), (length + _VIEW_GAP_MM, 0))),
                state=piece.thickness.state,
                source_refs=piece.thickness.source_refs,
            ),
            GeneralSheetPrimitive(
                kind="dimension",
                points_mm=(Point2D(x=0, y=0), Point2D(x=length, y=0), Point2D(x=0, y=-_DIMENSION_OFFSET_MM)),
                text=_dimension_text(piece.length), state=piece.length.state, source_refs=piece.length.source_refs,
            ),
            GeneralSheetPrimitive(
                kind="dimension",
                points_mm=(Point2D(x=0, y=0), Point2D(x=0, y=width), Point2D(x=-_DIMENSION_OFFSET_MM, y=0)),
                text=_dimension_text(piece.width), state=piece.width.state, source_refs=piece.width.source_refs,
            ),
            GeneralSheetPrimitive(
                kind="dimension",
                points_mm=(Point2D(x=length + _VIEW_GAP_MM, y=0), Point2D(x=length + _VIEW_GAP_MM + thickness, y=0), Point2D(x=length + _VIEW_GAP_MM, y=-_DIMENSION_OFFSET_MM)),
                text=_dimension_text(piece.thickness), state=piece.thickness.state, source_refs=piece.thickness.source_refs,
            ),
        ))
        callout_x = length + _VIEW_GAP_MM + thickness + 80
        callout_row = 0
        for detail in details:
            if detail.geometry is None:
                continue
            state = detail.state
            detail_refs = _refs(detail.source_refs, detail.assumption_refs, detail.parameter_refs)
            primitives.append(GeneralSheetPrimitive(
                kind=detail.geometry.kind,
                points_mm=detail.geometry.points_mm,
                state=state,
                source_refs=_refs(detail_refs, detail.geometry.dimension_refs),
            ))
            dimension = next((
                parameter_dimensions[reference.removeprefix("parameter:")]
                for reference in detail.geometry.dimension_refs
                if reference.removeprefix("parameter:") in parameter_dimensions
            ), None)
            if detail.geometry.kind == "circle" and dimension is not None and dimension.value_mm is not None:
                center = detail.geometry.points_mm[0]
                radius = dimension.value_mm / 2
                primitives.append(GeneralSheetPrimitive(
                    kind="dimension",
                    points_mm=(
                        Point2D(x=center.x - radius, y=center.y),
                        Point2D(x=center.x + radius, y=center.y),
                        Point2D(x=center.x - radius, y=center.y - 20),
                    ),
                    text=_dimension_text(dimension),
                    state=dimension.state,
                    source_refs=dimension.source_refs,
                ))
            target = detail.geometry.points_mm[0]
            prefix = f"{detail.id} · {detail.kind}: "
            rationale_lines = _split_preserving_text(
                detail.rationale,
                (max(1, _CALLOUT_LINE_MAX_CHARS - len(prefix)), _CALLOUT_LINE_MAX_CHARS),
            )
            label_point = Point2D(x=callout_x, y=width + 35 + callout_row * 20)
            edge_x = length + 30
            primitives.append(GeneralSheetPrimitive(
                kind="detail_callout",
                points_mm=(
                    target,
                    Point2D(x=edge_x, y=target.y),
                    Point2D(x=edge_x, y=label_point.y),
                    label_point,
                ),
                text=prefix + rationale_lines[0],
                state=state,
                source_refs=detail_refs,
            ))
            for line_index, line in enumerate(rationale_lines[1:], start=1):
                primitives.append(GeneralSheetPrimitive(
                    kind="text",
                    points_mm=(Point2D(x=callout_x, y=label_point.y - 5 + line_index * 18),),
                    text=line,
                    state=state,
                    source_refs=detail_refs,
                ))
            callout_row += len(rationale_lines) + 1
    quantity_prefix = "≈ " if piece.quantity.state == "estimated" else ""
    quantity_text = "?" if piece.quantity.value is None else f"{quantity_prefix}{piece.quantity.value} uds."
    label_y = (piece.width.value_mm or 0) + 60
    primitives.append(GeneralSheetPrimitive(
        kind="text",
        points_mm=(Point2D(x=0, y=label_y),),
        text=f"Cantidad propuesta: {quantity_text}",
        state=piece.quantity.state if piece.quantity.state not in {"unknown", "conflict"} else "unknown",
        source_refs=piece.quantity.source_refs,
    ))
    return GeneralSheetPlan(
        sheet_id=f"construction:piece:{piece.piece_id}",
        kind="piece",
        piece_id=piece.piece_id,
        title=f"Pieza · {piece.label}",
        primitives=tuple(primitives),
        warnings=tuple(warnings),
    )


def _assembly_sheet(
    pieces: tuple[GeneralConstructionPiece, ...],
    placements,
    validation_warnings: tuple[GeneralConstructionWarning, ...],
) -> GeneralSheetPlan:
    by_id = {piece.piece_id: piece for piece in pieces}
    primitives: list[GeneralSheetPrimitive] = []
    warnings: list[GeneralConstructionWarning] = list(validation_warnings)
    for placement in placements:
        piece = by_id.get(placement.piece_id)
        if piece is None or piece.length.value_mm is None or piece.width.value_mm is None:
            warnings.append(GeneralConstructionWarning(
                severity="warning", code="assembly_piece_unavailable",
                message=f"No se puede proyectar {placement.occurrence_ref}.",
                component_refs=(placement.piece_id,), field_refs=(), consequence="provisional_only",
            ))
            continue
        angle = radians(placement.rotation_deg)
        length, width = piece.length.value_mm, piece.width.value_mm
        local = ((0.0, 0.0), (length, 0.0), (length, width), (0.0, width), (0.0, 0.0))
        points = tuple(Point2D(
            x=placement.x_mm + x * cos(angle) - y * sin(angle),
            y=placement.y_mm + x * sin(angle) + y * cos(angle),
        ) for x, y in local)
        primitives.append(GeneralSheetPrimitive(
            kind="polyline", points_mm=points, state=placement.state,
            source_refs=_refs(placement.source_refs, placement.assumption_refs, (placement.occurrence_ref,)),
        ))
        primitives.append(GeneralSheetPrimitive(
            kind="text", points_mm=(points[0],), text=f"{piece.label} · {placement.occurrence_ref}",
            state=placement.state, source_refs=(placement.occurrence_ref,),
        ))
    return GeneralSheetPlan(
        sheet_id="construction:assembly", kind="assembly", piece_id=None,
        title="Conjunto 2D · posiciones propuestas", primitives=tuple(primitives), warnings=tuple(warnings),
    )


def plan_general_construction(
    review: GeneralFurnitureReview,
    validation: GeneralConstructionValidation,
) -> GeneralConstructionPlan:
    """Create exact 2D sheets from reviewed construction values and placements."""
    warnings = [GeneralConstructionWarning(
        severity=issue.severity,
        code=issue.code,
        message=issue.message,
        component_refs=tuple(ref for ref in issue.target_refs if ref.startswith("component:")),
        field_refs=issue.target_refs,
        consequence="blocks_fabrication" if issue.severity == "error" else "provisional_only",
    ) for issue in validation.issues]
    if validation.status == "invalid":
        warnings.append(GeneralConstructionWarning(
            severity="error", code="construction_validation_invalid",
            message="El escenario contiene restricciones constructivas en conflicto.",
            component_refs=(), field_refs=(), consequence="blocks_fabrication",
        ))
    parameter_dimensions = {
        parameter.id: GeneralConstructionDimension(
            value_mm=parameter.nominal_mm,
            range_mm=parameter.range_mm,
            state=parameter.state,
            review_status="accepted",
            method=parameter.method,
            formula=parameter.formula or (parameter.rationale if parameter.state == "deduced" else None),
            operand_refs=parameter.dependency_refs,
            source_refs=parameter.source_refs,
            assumption_refs=parameter.assumption_refs,
            explanation=parameter.rationale,
        )
        for parameter in review.construction_parameters
    }
    pieces: list[GeneralConstructionPiece] = []
    for component in review.components:
        length = _dimension(review, component, "length")
        width = _dimension(review, component, "width")
        thickness = _dimension(review, component, "thickness")
        pieces.append(GeneralConstructionPiece(
            piece_id=component.id,
            component_id=component.id,
            scenario_id=component.scenario_id,
            label=component.label,
            role=component.role,
            quantity=_quantity(review, component),
            occurrence_ids=tuple(item.id for item in review.occurrences if item.component_id == component.id),
            scenario_occurrence_ids=tuple(item.id for item in review.scenario_occurrences if item.component_id == component.id),
            geometry=component.geometry,
            length=length,
            width=width,
            thickness=thickness,
            detail_ids=component.detail_ids,
            source_refs=_refs(
                component.source_view_ids, component.source_observation_ids,
                component.source_contour_ids, component.source_evidence_ids,
                component.source_dimension_ids, component.source_document_refs,
            ),
            sheet_ids=(f"construction:piece:{component.id}",),
        ))
    piece_tuple = tuple(pieces)
    components_by_id = {component.id: component for component in review.components}

    def warnings_for_piece(piece: GeneralConstructionPiece) -> tuple[GeneralConstructionWarning, ...]:
        component = components_by_id[piece.component_id]
        accepted_refs = {
            f"component:{piece.component_id}",
            *(f"parameter:{parameter_id}" for parameter_id in component.construction_parameter_ids),
        }
        return tuple(
            warning
            for warning in warnings
            if not warning.field_refs
            or any(
                reference in accepted_refs
                or reference.startswith(f"component:{piece.component_id}.")
                for reference in warning.field_refs
            )
        )

    sheets = [
        _piece_sheet(
            piece,
            tuple(detail for detail in review.construction_details if detail.id in piece.detail_ids),
            parameter_dimensions,
            warnings_for_piece(piece),
        )
        for piece in piece_tuple
    ]
    expected_occurrences = {
        occurrence_id: piece.piece_id
        for piece in piece_tuple
        for occurrence_id in (*piece.occurrence_ids, *piece.scenario_occurrence_ids)
    }
    placement_refs = tuple(item.occurrence_ref for item in review.construction_placements)
    quantity_coverage_matches = all(
        piece.quantity.value is not None
        and piece.quantity.value == len(piece.occurrence_ids) + len(piece.scenario_occurrence_ids)
        for piece in piece_tuple
    )
    placement_coverage_matches = (
        len(placement_refs) == len(set(placement_refs))
        and set(placement_refs) == set(expected_occurrences)
        and all(expected_occurrences.get(item.occurrence_ref) == item.piece_id for item in review.construction_placements)
        and quantity_coverage_matches
    )
    accepted_placements = review.construction_placements if placement_coverage_matches else ()
    if review.construction_placements and placement_coverage_matches:
        sheets.insert(0, _assembly_sheet(piece_tuple, review.construction_placements, tuple(warnings)))
    elif review.construction_placements:
        warnings.append(GeneralConstructionWarning(
            severity="warning", code="assembly_placement_coverage_mismatch",
            message="No se dibuja montaje: las posiciones no cubren exactamente las ocurrencias del escenario.",
            component_refs=tuple(piece.component_id for piece in piece_tuple),
            field_refs=("quantity", "placements"), consequence="provisional_only",
        ))
    else:
        warnings.append(GeneralConstructionWarning(
            severity="info", code="assembly_placements_unavailable",
            message="No se dibuja montaje: el escenario no declara posiciones 2D.",
            component_refs=tuple(piece.component_id for piece in piece_tuple),
            field_refs=(), consequence="provisional_only",
        ))
    occurrence_count = sum(piece.quantity.value or 0 for piece in piece_tuple)
    return GeneralConstructionPlan(
        run_id=review.run_id,
        proposal_revision=review.proposal_revision,
        review_revision=review.review_revision,
        basis_revision=(
            f"run:{review.run_id}:proposal:{review.proposal_revision}:"
            f"review:{review.review_revision}:scenario:{review.construction_scenario_id}"
        ),
        scenario_id=review.construction_scenario_id,
        summary=GeneralConstructionSummary(
            label=f"Escenario constructivo {review.construction_scenario_id}",
            component_count=len(piece_tuple), occurrence_count=occurrence_count,
            source_refs=_refs(*(piece.source_refs for piece in piece_tuple)),
            top_decision_ids=tuple(item.id for item in review.construction_decisions if item.impact == "high")[:3],
            warnings=tuple(warnings),
        ),
        pieces=piece_tuple,
        placements=accepted_placements,
        details=review.construction_details,
        decisions=review.construction_decisions,
        warnings=tuple(warnings),
        sheets=tuple(sheets),
    )

