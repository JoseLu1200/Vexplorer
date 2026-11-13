from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Point2D(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class Bounds2D(StrictModel):
    min_x: float = Field(allow_inf_nan=False)
    min_y: float = Field(allow_inf_nan=False)
    max_x: float = Field(allow_inf_nan=False)
    max_y: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self) -> "Bounds2D":
        if self.min_x > self.max_x or self.min_y > self.max_y:
            raise ValueError("bounds must be ordered")
        return self


class DrawingEntity(StrictModel):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    layer: str
    source_points: tuple[Point2D, ...] = Field(min_length=1)
    points_mm: tuple[Point2D, ...] | None


class DrawingView(StrictModel):
    id: str = Field(min_length=1)
    label: Literal["FRONT", "TOP", "SIDE", "UNKNOWN"]
    entity_ids: tuple[str, ...]
    bounds_source: Bounds2D
    bounds_mm: Bounds2D | None


class DrawingContour(StrictModel):
    id: str = Field(min_length=1)
    view_id: str
    source_entity_ids: tuple[str, ...] = Field(min_length=1)
    points_source: tuple[Point2D, ...] = Field(min_length=1)
    points_mm: tuple[Point2D, ...] | None
    closed: bool


class ObservedDimension(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal["overall", "annotation"]
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    source_entity_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    origin: Literal["observed", "derived"]


class Evidence(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal["geometry", "annotation", "view_association"]
    source_entity_ids: tuple[str, ...]
    description: str = Field(min_length=1)


class DrawingObservation(StrictModel):
    id: str = Field(min_length=1)
    view_id: str
    contour_ids: tuple[str, ...]
    dimension_ids: tuple[str, ...]


class DrawingExtraction(StrictModel):
    schema_version: Literal["0.2.0"] = SCHEMA_VERSION
    drawing_id: str = Field(min_length=1)
    status: Literal["ready", "needs_review"]
    source_unit: Literal["mm", "cm", "m", "in", "unknown"]
    unit_scale_to_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    coordinate_unit: Literal["mm", "source"] = "source"
    entities: tuple[DrawingEntity, ...]
    views: tuple[DrawingView, ...]
    contours: tuple[DrawingContour, ...]
    dimensions: tuple[ObservedDimension, ...]
    evidence: tuple[Evidence, ...]
    observations: tuple[DrawingObservation, ...]
    warnings: tuple[str, ...] = ()
    synthetic: bool = False

    @model_validator(mode="after")
    def validate_ledger(self) -> "DrawingExtraction":
        collections = (self.entities, self.views, self.contours, self.dimensions, self.evidence, self.observations)
        all_ids = [item.id for collection in collections for item in collection]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("duplicate ids are not allowed")
        entity_ids = {item.id for item in self.entities}
        view_ids = {item.id for item in self.views}
        contour_ids = {item.id for item in self.contours}
        dimension_ids = {item.id for item in self.dimensions}
        evidence_ids = {item.id for item in self.evidence}
        for view in self.views:
            if not set(view.entity_ids) <= entity_ids:
                raise ValueError("view references an unknown entity")
        for contour in self.contours:
            if contour.view_id not in view_ids or not set(contour.source_entity_ids) <= entity_ids:
                raise ValueError("contour has an unknown reference")
        for dimension in self.dimensions:
            if not set(dimension.source_entity_ids) <= entity_ids or not set(dimension.evidence_ids) <= evidence_ids:
                raise ValueError("dimension has an unknown reference")
        for item in self.evidence:
            if not set(item.source_entity_ids) <= entity_ids:
                raise ValueError("evidence references an unknown entity")
        for observation in self.observations:
            if observation.view_id not in view_ids or not set(observation.contour_ids) <= contour_ids or not set(observation.dimension_ids) <= dimension_ids:
                raise ValueError("observation has an unknown reference")
        metric_values_present = any(entity.points_mm is not None for entity in self.entities)
        metric_values_present |= any(view.bounds_mm is not None for view in self.views)
        metric_values_present |= any(contour.points_mm is not None for contour in self.contours)
        metric_values_present |= any(item.value_mm is not None for item in self.dimensions)
        if self.source_unit == "unknown":
            if self.unit_scale_to_mm is not None or self.coordinate_unit != "source" or metric_values_present:
                raise ValueError("unknown unit cannot contain metric values")
        elif self.unit_scale_to_mm is None or self.coordinate_unit != "mm":
            raise ValueError("resolved units require scale and mm coordinates")
        return self
