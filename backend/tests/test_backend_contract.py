from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingView,
    Evidence,
    ObservedDimension,
    Point2D,
)


def _unknown_extraction() -> DrawingExtraction:
    source_points = (Point2D(x=0, y=0), Point2D(x=100, y=0))
    return DrawingExtraction(
        drawing_id="drawing-1",
        status="needs_review",
        source_unit="unknown",
        unit_scale_to_mm=None,
        entities=(
            DrawingEntity(
                id="entity-1",
                kind="LINE",
                layer="VIEW_GEOMETRY",
                source_points=source_points,
                points_mm=None,
            ),
        ),
        views=(
            DrawingView(
                id="view-1",
                label="UNKNOWN",
                entity_ids=("entity-1",),
                bounds_source=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=0),
                bounds_mm=None,
            ),
        ),
        contours=(
            DrawingContour(
                id="contour-1",
                view_id="view-1",
                source_entity_ids=("entity-1",),
                points_source=source_points,
                points_mm=None,
                closed=False,
            ),
        ),
        dimensions=(
            ObservedDimension(
                id="dimension-1",
                kind="overall",
                value_mm=None,
                source_entity_ids=("entity-1",),
                evidence_ids=("evidence-1",),
                origin="observed",
            ),
        ),
        evidence=(
            Evidence(
                id="evidence-1",
                kind="geometry",
                source_entity_ids=("entity-1",),
                description="Longitud visible sin unidad resuelta",
            ),
        ),
        observations=(),
        warnings=("unit_unknown",),
        synthetic=True,
    )


def test_contract_preserves_unknown_units_without_metric_values() -> None:
    extraction = _unknown_extraction()

    assert extraction.schema_version == "0.2.0"
    assert extraction.coordinate_unit == "source"
    assert extraction.entities[0].points_mm is None
    assert extraction.dimensions[0].value_mm is None


def test_contract_rejects_metric_values_when_source_unit_is_unknown() -> None:
    payload = _unknown_extraction().model_dump(mode="json")
    payload["entities"][0]["points_mm"] = [{"x": 0, "y": 0}, {"x": 100, "y": 0}]

    with pytest.raises(ValidationError, match="unknown unit"):
        DrawingExtraction.model_validate(payload)


def test_contract_rejects_duplicate_ids_extra_fields_and_non_finite_numbers() -> None:
    payload = _unknown_extraction().model_dump(mode="json")
    payload["entities"].append(payload["entities"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        DrawingExtraction.model_validate(payload)

    with pytest.raises(ValidationError):
        Point2D.model_validate({"x": 1, "y": 2, "z": 3})

    with pytest.raises(ValidationError):
        Point2D(x=math.inf, y=0)


def test_contract_json_schema_is_strict_and_is_the_single_source() -> None:
    schema = DrawingExtraction.model_json_schema()

    assert schema["properties"]["schema_version"]["const"] == "0.2.0"
    assert schema["additionalProperties"] is False
