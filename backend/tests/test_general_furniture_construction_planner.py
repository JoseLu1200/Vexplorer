from __future__ import annotations

from backend.app.contratos.modelos import (
    GeneralComponentReview,
    GeneralConstructionDecision,
    GeneralConstructionDetail,
    GeneralConstructionDetailGeometry,
    GeneralConstructionIssue,
    GeneralConstructionValidation,
    GeneralDimensionRange,
    GeneralFurnitureReview,
    GeneralOccurrence,
    GeneralPieceGeometry,
    GeneralPiecePlacement,
    GeneralQuantity,
    GeneralResolvedConstructionParameter,
    GeneralReviewOperation,
    GeneralTextValue,
    GeneralValue,
    Point2D,
)
from backend.app.general_furniture.construction_planner import (
    plan_general_construction,
)
from backend.app.general_furniture.construction_drawings import (
    render_construction_artifacts,
)


def _parameter(
    parameter_id: str,
    nominal: float,
    state: str,
    minimum: float,
    maximum: float,
) -> GeneralResolvedConstructionParameter:
    estimated = state == "estimated"
    deduced = state == "deduced"
    return GeneralResolvedConstructionParameter(
        id=parameter_id,
        label=parameter_id,
        nominal_mm=nominal,
        range_mm=GeneralDimensionRange(min_mm=minimum, max_mm=maximum),
        state=state,
        method="construction_assumption" if estimated else "arithmetic" if deduced else "observed_copy",
        binding_id=f"binding:{parameter_id}" if not estimated else None,
        formula=f"formula:{parameter_id}" if deduced else None,
        dependency_refs=("dimension:overall",) if not estimated else ("premise:board",),
        source_refs=("dimension:overall",),
        assumption_refs=("premise:board",) if estimated else (),
        rationale=f"Fundamento de {parameter_id}.",
    )


def _review(*, placements: bool = True) -> GeneralFurnitureReview:
    length = GeneralValue(
        value_mm=720,
        state="observed",
        dependency_refs=("parameter:length",),
        evidence_ids=("evidence:length",),
        dimension_ids=("dimension:length",),
        method="observed_copy",
    )
    width = GeneralValue(
        value_mm=560,
        state="deduced",
        dependency_refs=("parameter:width",),
        formula="overall_height-clearance",
        method="arithmetic",
    )
    thickness = GeneralValue(
        value_mm=18,
        state="estimated",
        dependency_refs=("parameter:thickness",),
        range_mm=GeneralDimensionRange(min_mm=16, max_mm=19),
        method="construction_assumption",
        assumption_refs=("premise:board",),
    )
    component = GeneralComponentReview(
        id="side-panel",
        label="Costado lateral",
        kind="panel",
        role="side_panel",
        length=length,
        width=width,
        thickness=thickness,
        quantity=GeneralQuantity(
            value=2,
            state="estimated",
            dependency_refs=("premise:two-sides",),
        ),
        material=GeneralTextValue(value=None, state="unknown"),
        finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=("candidate:side",),
        source_view_ids=("view:front",),
        source_contour_ids=("contour:side",),
        source_evidence_ids=("evidence:length",),
        assumptions=("premise:board", "premise:two-sides"),
        scenario_id="cabinet-main",
        necessity="visible",
        geometry=GeneralPieceGeometry(
            shape_kind="rectangle",
            source_contour_ids=("contour:side",),
            basis_refs=("contour:side",),
            rationale="El escenario declara un panel rectangular.",
        ),
        construction_parameter_ids=("length", "width", "thickness", "bore-diameter"),
        detail_ids=("bore-1",),
        quantity_basis_refs=("premise:two-sides",),
    )
    placement_values = (
        GeneralPiecePlacement(
            occurrence_ref="scenario:side-panel:1",
            piece_id="side-panel",
            x_mm=0,
            y_mm=0,
            rotation_deg=0,
            state="estimated",
            source_refs=("contour:side",),
            assumption_refs=("premise:assembly",),
        ),
    ) if placements else ()
    return GeneralFurnitureReview(
        run_id="run-cabinet",
        proposal_id="proposal-cabinet",
        proposal_revision=2,
        review_revision=1,
        reviewer_name="Técnico",
        reason="Escenario constructivo revisado.",
        reviewed_at="2026-11-14T10:00:00Z",
        operations=(GeneralReviewOperation(
            kind="replace",
            source_component_ids=("candidate:side",),
            result_component_ids=("side-panel",),
            reason="Panel lateral necesario.",
        ),),
        components=(component,),
        occurrences=(),
        construction_scenario_id="cabinet-main",
        construction_parameters=(
            _parameter("length", 720, "observed", 720, 720),
            _parameter("width", 560, "deduced", 558, 562),
            _parameter("thickness", 18, "estimated", 16, 19),
            _parameter("bore-diameter", 6, "estimated", 5, 7),
        ),
        construction_details=(GeneralConstructionDetail(
            id="bore-1",
            kind="bore",
            component_ids=("side-panel",),
            parameter_refs=("parameter:bore-diameter",),
            quantity=2,
            state="estimated",
            source_refs=("contour:side",),
            assumption_refs=("premise:hardware",),
            rationale="Taladro propuesto para el herraje.",
            geometry=GeneralConstructionDetailGeometry(
                kind="circle",
                points_mm=(Point2D(x=40, y=40), Point2D(x=43, y=40)),
                dimension_refs=("parameter:bore-diameter",),
            ),
        ),),
        construction_decisions=(GeneralConstructionDecision(
            id="decision:board",
            category="dimension",
            summary="Se propone tablero de 18 mm.",
            target_refs=("component:side-panel.thickness",),
            basis_refs=("parameter:thickness",),
            alternatives=("16 mm", "19 mm"),
            rationale="Cierra el escenario dentro del rango.",
            impact="high",
        ),),
        construction_placements=placement_values,
        status="approved",
    )


def _validation() -> GeneralConstructionValidation:
    return GeneralConstructionValidation(
        status="valid",
        parameter_order=("length", "width", "thickness", "bore-diameter"),
        max_depth=2,
        constraint_results=(),
        issues=(GeneralConstructionIssue(
            severity="warning",
            code="estimated_board",
            message="Confirmar espesor antes de fabricar.",
            target_refs=("parameter:thickness",),
        ),),
    )


def _review_with_complete_assembly() -> GeneralFurnitureReview:
    review = _review(placements=False)
    component = review.components[0].model_copy(update={
        "quantity": GeneralQuantity(
            value=2,
            state="deduced",
            dependency_refs=("premise:two-sides",),
        ),
    })
    occurrence_ids = ("occurrence:side-panel:1", "occurrence:side-panel:2")
    return review.model_copy(update={
        "components": (component,),
        "occurrences": tuple(
            GeneralOccurrence(id=occurrence_id, component_id="side-panel", occurrence_index=index)
            for index, occurrence_id in enumerate(occurrence_ids, start=1)
        ),
        "construction_placements": tuple(
            GeneralPiecePlacement(
                occurrence_ref=occurrence_id,
                piece_id="side-panel",
                x_mm=(index - 1) * 750,
                y_mm=0,
                rotation_deg=0,
                state="deduced",
                source_refs=("decision:assembly",),
                assumption_refs=(),
            )
            for index, occurrence_id in enumerate(occurrence_ids, start=1)
        ),
    })


def test_planner_builds_dimensioned_piece_sheet_and_typed_bore_detail() -> None:
    plan = plan_general_construction(_review(), _validation())

    assert plan.scenario_id == "cabinet-main"
    assert plan.basis_revision == "run:run-cabinet:proposal:2:review:1:scenario:cabinet-main"
    assert plan.authority == "provisional_not_manufacturing"
    assert len(plan.pieces) == 1
    piece = plan.pieces[0]
    assert piece.quantity.value == 2
    assert piece.quantity.state == "estimated"
    assert piece.length.state == "observed"
    assert piece.width.state == "deduced"
    assert piece.thickness.state == "estimated"
    assert piece.thickness.range_mm == GeneralDimensionRange(min_mm=16, max_mm=19)

    sheet = next(item for item in plan.sheets if item.kind == "piece")
    assert sheet.piece_id == "side-panel"
    assert any(warning.code == "estimated_board" for warning in sheet.warnings)
    dimensions = [item for item in sheet.primitives if item.kind == "dimension"]
    assert len(dimensions) >= 4
    assert any(item.text == "≈ 18 mm [16–19]" for item in dimensions)
    assert any(item.text == "≈ 6 mm [5–7]" for item in dimensions)
    assert any(item.kind == "circle" for item in sheet.primitives)
    assert any(
        item.kind == "text" and item.text == "Cantidad propuesta: ≈ 2 uds."
        for item in sheet.primitives
    )
    callout = next(item for item in sheet.primitives if item.kind == "detail_callout")
    assert len(callout.points_mm) == 4
    assert callout.points_mm[1].x > 720
    assert callout.points_mm[1].y == callout.points_mm[0].y


def test_planner_wraps_maximum_detail_rationale_without_losing_content() -> None:
    review = _review()
    rationale = (
        "Conjunto estabilizador con escuadras repartidas y anclajes antivuelco; "
        "la geometría identifica el perímetro propuesto, conserva la autoridad "
        "estimada y documenta que la capacidad de carga no está certificada. "
    )
    rationale = (rationale * 4)[:500]
    detail = review.construction_details[0].model_copy(update={"rationale": rationale})
    review = review.model_copy(update={"construction_details": (detail,)})

    plan = plan_general_construction(review, _validation())

    sheet = next(item for item in plan.sheets if item.kind == "piece")
    detail_lines = [
        item for item in sheet.primitives
        if item.kind in {"detail_callout", "text"}
        and item.source_refs == ("contour:side", "premise:hardware", "parameter:bore-diameter")
    ]
    assert len(detail_lines) > 1
    assert detail_lines[0].kind == "detail_callout"
    assert all(len(item.text or "") <= 120 for item in detail_lines)
    prefix = f"{detail.id} · {detail.kind}: "
    rendered_rationale = (detail_lines[0].text or "").removeprefix(prefix) + "".join(
        item.text or "" for item in detail_lines[1:]
    )
    assert rendered_rationale == rationale


def test_planner_omits_assembly_without_explicit_placements_but_keeps_piece_sheet() -> None:
    plan = plan_general_construction(_review(placements=False), _validation())

    assert [sheet.kind for sheet in plan.sheets] == ["piece"]
    assert any(warning.code == "assembly_placements_unavailable" for warning in plan.warnings)


def test_planner_omits_assembly_when_placement_coverage_is_not_exact() -> None:
    plan = plan_general_construction(_review(placements=True), _validation())

    assert [sheet.kind for sheet in plan.sheets] == ["piece"]
    assert plan.placements == ()
    assert any(warning.code == "assembly_placement_coverage_mismatch" for warning in plan.warnings)


def test_planner_emits_assembly_for_unique_exact_occurrence_coverage() -> None:
    plan = plan_general_construction(_review_with_complete_assembly(), _validation())

    assembly = next(sheet for sheet in plan.sheets if sheet.kind == "assembly")
    assert len([item for item in assembly.primitives if item.kind == "polyline"]) == 2


def test_renderer_returns_snapshot_exact_svg_and_dxf_per_sheet() -> None:
    plan = plan_general_construction(_review_with_complete_assembly(), _validation())

    artifacts = render_construction_artifacts(plan)

    assert len(artifacts) == 4
    assert {item.kind for item in artifacts} == {
        "construction_overview_svg",
        "construction_overview_dxf",
        "piece_sheet_svg",
        "piece_sheet_dxf",
    }
    piece_artifacts = [item for item in artifacts if item.component_id == "side-panel"]
    assert len(piece_artifacts) == 2
    assert {item.sheet_id for item in piece_artifacts} == {"construction:piece:side-panel"}
    assert all("p2-r1" in item.id for item in artifacts)
    assert all(item.review_revision == 1 for item in artifacts)
    assert {item.media_type for item in artifacts} == {"image/svg+xml", "application/dxf"}

