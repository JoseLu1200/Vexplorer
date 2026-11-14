from __future__ import annotations

import pytest

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingExtraction,
    DrawingContour,
    DrawingObservation,
    DrawingView,
    Evidence,
    GeneralBinding,
    GeneralComponentProposal,
    GeneralFurnitureProposal,
    GeneralPremise,
    GeneralQuantity,
    ObservedDimension,
    Point2D,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.proposal import materialize_general_proposal


def _extraction() -> DrawingExtraction:
    bounds = Bounds2D(min_x=0, min_y=0, max_x=800, max_y=720)
    return DrawingExtraction(
        drawing_id="drawing-1", input_kind="mounted_views_legacy", status="ready",
        source_unit="mm", unit_scale_to_mm=1, coordinate_unit="mm", entities=(),
        views=(DrawingView(id="view-front", label="FRONT", entity_ids=(), bounds_source=bounds, bounds_mm=bounds),),
        contours=(),
        dimensions=(ObservedDimension(id="dim-width", kind="overall", value_mm=800, source_entity_ids=(), evidence_ids=("evidence-width",), origin="observed", view_id="view-front"),),
        evidence=(Evidence(id="evidence-width", kind="annotation", source_entity_ids=(), description="Cota exterior de ancho."),),
        observations=(DrawingObservation(id="observation-front", view_id="view-front", contour_ids=(), dimension_ids=("dim-width",)),),
    )


def _proposal() -> GeneralFurnitureProposal:
    return GeneralFurnitureProposal(
        id="proposal-1", drawing_id="drawing-1", ledger_revision="ledger-1", proposal_origin="native_tool",
        bindings=(GeneralBinding(id="width", operation="copy", operand_refs=("dimension:dim-width",)),),
        premises=(GeneralPremise(id="p1", description="Panel rectangular hipotético."),),
        components=(GeneralComponentProposal(
            id="panel", label="Panel", kind="panel", role="unknown",
            length_binding_id="width", width_binding_id=None, thickness_binding_id=None,
            quantity=GeneralQuantity(value=None, state="unknown"), premise_ids=("p1",),
            source_view_ids=("view-front",), source_observation_ids=("observation-front",),
            source_evidence_ids=("evidence-width",), source_dimension_ids=("dim-width",),
            assumptions=("Rol pendiente.",), unknown_fields=("width", "thickness", "quantity"),
        ),), assumptions=("No implica aptitud industrial.",),
    )


def test_materialize_keeps_component_assignment_hypothetical_even_when_source_measure_is_observed() -> None:
    draft = materialize_general_proposal(_extraction(), _proposal())

    assert draft.components[0].length.value_mm == 800
    assert draft.components[0].length.state == "hypothesis"
    assert draft.components[0].length.dimension_ids == ("dim-width",)
    assert draft.components[0].width.state == "unknown"


def test_materialize_rejects_reference_outside_drawing_ledger() -> None:
    component = _proposal().components[0].model_copy(update={"source_view_ids": ("view-missing",)})
    proposal = GeneralFurnitureProposal(**(_proposal().model_dump() | {"components": (component,)}))

    with pytest.raises(ValueError, match="proposal_reference_outside_ledger"):
        materialize_general_proposal(_extraction(), proposal)


def test_contour_extents_become_deterministic_bindable_measures_with_provenance() -> None:
    extraction = _extraction().model_copy(update={
        "contours": (DrawingContour(
            id="contour-panel", view_id="view-front", source_entity_ids=("entity-placeholder",),
            points_source=(Point2D(x=0, y=0), Point2D(x=800, y=0), Point2D(x=800, y=400), Point2D(x=0, y=400)),
            points_mm=(Point2D(x=0, y=0), Point2D(x=800, y=0), Point2D(x=800, y=400), Point2D(x=0, y=400)), closed=True,
        ),),
    })
    measures = derive_geometry_measurements(extraction)

    assert [(item.id, item.value_mm) for item in measures[:2]] == [
        ("contour:contour-panel:span-x", 800),
        ("contour:contour-panel:span-y", 400),
    ]
    assert measures[0].source_contour_ids == ("contour-panel",)


def test_materialize_binds_metric_geometry_measurement_as_component_hypothesis() -> None:
    from backend.tests.test_general_furniture_measurements import _extraction as measurement_extraction

    extraction = measurement_extraction()
    proposal = GeneralFurnitureProposal(
        id="proposal-measurement", drawing_id=extraction.drawing_id, ledger_revision="ledger-geometry",
        proposal_origin="native_tool",
        bindings=(GeneralBinding(id="panel-length", operation="copy", operand_refs=("measurement:contour:contour-panel:span-x",)),),
        premises=(GeneralPremise(id="p1", description="El contorno puede corresponder a un panel."),),
        components=(GeneralComponentProposal(
            id="panel", label="Panel", kind="panel", role="unknown", length_binding_id="panel-length",
            width_binding_id=None, thickness_binding_id=None, quantity=GeneralQuantity(value=None, state="unknown"),
            premise_ids=("p1",), source_view_ids=("view-front",), source_observation_ids=("observation-front",),
            source_contour_ids=("contour-panel",), source_evidence_ids=("evidence-panel",),
            assumptions=("Asignación semántica pendiente.",), unknown_fields=("width", "thickness", "quantity"),
        ),), assumptions=("No es una instrucción de fabricación.",),
    )

    draft = materialize_general_proposal(extraction, proposal)

    assert draft.components[0].length.value_mm == 100
    assert draft.components[0].length.state == "hypothesis"
    assert draft.components[0].length.dependency_refs == ("binding:panel-length",)
