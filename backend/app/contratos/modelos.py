from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Point2D(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class Point3D(StrictModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    z: float = Field(allow_inf_nan=False)


class Size3D(StrictModel):
    x: float = Field(gt=0, allow_inf_nan=False)
    y: float = Field(gt=0, allow_inf_nan=False)
    z: float = Field(gt=0, allow_inf_nan=False)


class Bounds3D(StrictModel):
    min: Point3D
    max: Point3D

    @model_validator(mode="after")
    def ordered(self) -> "Bounds3D":
        if self.min.x > self.max.x or self.min.y > self.max.y or self.min.z > self.max.z:
            raise ValueError("bounds must be ordered")
        return self


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


class DrawingText(StrictModel):
    id: str = Field(min_length=1)
    source_entity_id: str = Field(min_length=1)
    view_id: str = Field(min_length=1)
    layer: str
    text: str
    position_source: Point2D
    position_mm: Point2D | None


class DimensionGraphic(StrictModel):
    id: str = Field(min_length=1)
    dimension_id: str = Field(min_length=1)
    source_entity_id: str = Field(min_length=1)
    view_id: str = Field(min_length=1)
    layer: str
    display_text: str
    raw_text: str
    extension_start_a_source: Point2D
    extension_start_a_mm: Point2D | None
    extension_start_b_source: Point2D
    extension_start_b_mm: Point2D | None
    dimension_start_source: Point2D
    dimension_start_mm: Point2D | None
    dimension_end_source: Point2D
    dimension_end_mm: Point2D | None
    text_position_source: Point2D
    text_position_mm: Point2D | None


class ObservedDimension(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal["overall", "annotation"]
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    source_entity_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    origin: Literal["observed", "derived"]
    view_id: str | None = None
    graphic_id: str | None = None


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
    texts: tuple[DrawingText, ...] = ()
    dimension_graphics: tuple[DimensionGraphic, ...] = ()
    warnings: tuple[str, ...] = ()
    synthetic: bool = False

    @model_validator(mode="after")
    def validate_ledger(self) -> "DrawingExtraction":
        collections = (self.entities, self.views, self.contours, self.dimensions, self.evidence, self.observations, self.texts, self.dimension_graphics)
        all_ids = [item.id for collection in collections for item in collection]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("duplicate ids are not allowed")
        entity_ids = {item.id for item in self.entities}
        view_ids = {item.id for item in self.views}
        contour_ids = {item.id for item in self.contours}
        dimension_ids = {item.id for item in self.dimensions}
        evidence_ids = {item.id for item in self.evidence}
        graphic_ids = {item.id for item in self.dimension_graphics}
        for view in self.views:
            if not set(view.entity_ids) <= entity_ids:
                raise ValueError("view references an unknown entity")
        for contour in self.contours:
            if contour.view_id not in view_ids or not set(contour.source_entity_ids) <= entity_ids:
                raise ValueError("contour has an unknown reference")
        for dimension in self.dimensions:
            if not set(dimension.source_entity_ids) <= entity_ids or not set(dimension.evidence_ids) <= evidence_ids:
                raise ValueError("dimension has an unknown reference")
            if dimension.view_id is not None and dimension.view_id not in view_ids:
                raise ValueError("dimension has an unknown reference")
            if dimension.graphic_id is not None and dimension.graphic_id not in graphic_ids:
                raise ValueError("dimension has an unknown reference")
        for item in self.evidence:
            if not set(item.source_entity_ids) <= entity_ids:
                raise ValueError("evidence references an unknown entity")
        for observation in self.observations:
            if observation.view_id not in view_ids or not set(observation.contour_ids) <= contour_ids or not set(observation.dimension_ids) <= dimension_ids:
                raise ValueError("observation has an unknown reference")
        for item in self.texts:
            if item.source_entity_id not in entity_ids or item.view_id not in view_ids:
                raise ValueError("text has an unknown reference")
        for item in self.dimension_graphics:
            if item.dimension_id not in dimension_ids or item.source_entity_id not in entity_ids or item.view_id not in view_ids:
                raise ValueError("dimension graphic has an unknown reference")
        metric_values_present = any(entity.points_mm is not None for entity in self.entities)
        metric_values_present |= any(view.bounds_mm is not None for view in self.views)
        metric_values_present |= any(contour.points_mm is not None for contour in self.contours)
        metric_values_present |= any(item.value_mm is not None for item in self.dimensions)
        metric_values_present |= any(item.position_mm is not None for item in self.texts)
        metric_values_present |= any(value is not None for item in self.dimension_graphics for value in (item.extension_start_a_mm, item.extension_start_b_mm, item.dimension_start_mm, item.dimension_end_mm, item.text_position_mm))
        if self.source_unit == "unknown":
            if self.unit_scale_to_mm is not None or self.coordinate_unit != "source" or metric_values_present:
                raise ValueError("unknown unit cannot contain metric values")
        elif self.unit_scale_to_mm is None or self.coordinate_unit != "mm":
            raise ValueError("resolved units require scale and mm coordinates")
        return self


class ComponentProposal(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: Literal["side_panel", "shelf", "top_panel", "base_panel", "back_panel", "door", "divider", "unknown"] = "unknown"
    quantity: int | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    thickness_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    length_derivation: Literal["direct_observation", "overall_width_minus_two_thickness", "overall_height_minus_two_thickness"] = "direct_observation"
    length_basis_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    source_observation_ids: tuple[str, ...]
    source_contour_ids: tuple[str, ...]
    source_entity_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...] = Field(min_length=1)
    information_class: Literal["hypothesis"] = "hypothesis"


class DecompositionScenario(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    components: tuple[ComponentProposal, ...]
    assumptions: tuple[str, ...] = Field(min_length=1)
    incompatible_with: tuple[str, ...] = ()
    state: Literal["hypothesis"] = "hypothesis"


class ReviewDecision(StrictModel):
    proposal_id: str = Field(min_length=1)
    action: Literal["confirm", "reject"]
    role: Literal["side_panel", "shelf", "top_panel", "base_panel", "back_panel", "door", "divider", "unknown"] = "unknown"
    quantity: int | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    thickness_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    material: str | None = None
    finish: str | None = None
    notes: str = Field(min_length=1)


class ReviewRequest(StrictModel):
    base_result_revision: int = Field(gt=0)
    reviewer_name: str = Field(min_length=1)
    decisions: tuple[ReviewDecision, ...] = ()
    scenario_id: str | None = None
    confirmed_thickness_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    material: str | None = None
    finish: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def unique_proposals(self) -> "ReviewRequest":
        if not self.decisions and self.scenario_id is None:
            raise ValueError("a scenario selection or explicit decisions are required")
        if self.decisions and self.scenario_id is not None:
            raise ValueError("scenario selection and explicit decisions are mutually exclusive")
        if self.scenario_id is not None and (self.confirmed_thickness_mm is None or not self.notes):
            raise ValueError("scenario selection requires thickness and notes")
        ids = [item.proposal_id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate proposal decisions")
        return self


class ResolvedPiece(StrictModel):
    id: str
    proposal_id: str
    label: str
    role: str
    quantity: int | None
    length_mm: float | None
    width_mm: float | None
    thickness_mm: float | None
    material: str | None
    finish: str | None
    source_observation_ids: tuple[str, ...]
    source_contour_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    human_confirmation: str
    field_states: dict[str, Literal["observed", "calculated", "confirmed", "unknown"]]


class HumanReview(StrictModel):
    reviewer_name: str
    reason: str
    timestamp: str
    selected_scenario_id: str | None


class Result(StrictModel):
    schema_version: Literal["0.2.0"] = SCHEMA_VERSION
    run_id: str
    result_revision: int = Field(gt=0)
    state: Literal["completed", "needs_review"]
    scenarios: tuple[DecompositionScenario, ...]
    pieces: tuple[ResolvedPiece, ...]
    rejected_proposal_ids: tuple[str, ...] = ()
    created_at: str
    review: HumanReview | None = None
    agent_selected_scenario_id: str | None = None


class SceneObject(StrictModel):
    id: str = Field(min_length=1)
    piece_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    label: str = Field(min_length=1)
    occurrence_index: int = Field(ge=1)
    position_mm: Point3D
    dimensions_mm: Size3D
    bbox_mm: Bounds3D
    source_contour_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    placement_basis: str = Field(min_length=1)


class ReconstructionScene(StrictModel):
    schema_version: Literal["0.3.0"] = "0.3.0"
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    state: Literal["ready", "incomplete", "unavailable"]
    selected_scenario_id: str | None = None
    coordinate_system: Literal["x=width,y=height,z=depth; origin=front-left-bottom"] = "x=width,y=height,z=depth; origin=front-left-bottom"
    objects: tuple[SceneObject, ...] = ()
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    collision_status: Literal["not_evaluated"] = "not_evaluated"


class FormulaExplanation(StrictModel):
    field: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    operands_mm: dict[str, float]
    result_mm: float = Field(gt=0, allow_inf_nan=False)


class PieceExplanation(StrictModel):
    piece_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    source_entity_ids: tuple[str, ...]
    source_contour_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    dimension_ids: tuple[str, ...]
    measurements: dict[str, float | int | None]
    formulas: tuple[FormulaExplanation, ...]
    premises: tuple[str, ...]
    unknown_fields: tuple[str, ...]
    field_states: dict[str, Literal["observed", "calculated", "confirmed", "hypothesis", "unknown"]]


class ExplanationBundle(StrictModel):
    schema_version: Literal["0.3.0"] = "0.3.0"
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    pieces: tuple[PieceExplanation, ...]
    warnings: tuple[str, ...] = ()


class DescriptorDimensions(StrictModel):
    width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    depth_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    height_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class RoleQuantity(StrictModel):
    role: str = Field(min_length=1)
    quantity: int | None = Field(default=None, gt=0)


class FurnitureDescriptor(StrictModel):
    descriptor_version: Literal["furniture-v1"] = "furniture-v1"
    family: Literal["rectangular_shelving", "unknown"]
    dimensions: DescriptorDimensions
    roles: tuple[RoleQuantity, ...]
    structure: Literal["top_base_between_sides", "top_base_cap_sides", "unknown"]
    material: str | None = None
    finish: str | None = None
    unknown_fields: tuple[str, ...]


class EmbeddingMetadata(StrictModel):
    provider: Literal["openai"] = "openai"
    model: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    descriptor_version: Literal["furniture-v1"] = "furniture-v1"
    cache_key: str = Field(min_length=1)
    status: Literal["generated", "cache"]


class LibraryItem(StrictModel):
    schema_version: Literal["0.3.0"] = "0.3.0"
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    label: str = Field(min_length=1)
    descriptor: FurnitureDescriptor
    descriptor_fingerprint: str = Field(min_length=64, max_length=64)
    created_at: str = Field(min_length=1)
    embedding: EmbeddingMetadata | None = None


class SimilarityDifference(StrictModel):
    field: str = Field(min_length=1)
    query_value: str
    candidate_value: str


class SimilarityMatch(StrictModel):
    library_item_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    method: Literal["geometric", "semantic"]
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    score_kind: Literal["geometric_similarity", "cosine_similarity"]
    score_components: dict[str, float]
    differences: tuple[SimilarityDifference, ...]
    embedding: EmbeddingMetadata | None = None


class SimilarityGroup(StrictModel):
    id: str = Field(min_length=1)
    member_ids: tuple[str, ...] = Field(min_length=2)
    method: Literal["geometric", "semantic"]
    score_kind: Literal["geometric_similarity", "cosine_similarity"]
    threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)
    explanation: str = Field(min_length=1)


class RunSnapshot(StrictModel):
    schema_version: Literal["0.2.0"] = SCHEMA_VERSION
    id: str
    mode: Literal["live", "geometry_only"]
    state: Literal["completed", "needs_review", "failed", "cancelled", "timed_out"]
    reason_code: str | None = None
    candidate_revision: str
    result_revision: int | None
    created_at: str
    agent_selected_scenario_id: str | None = None
    document_id: str | None = None


class Comparable(StrictModel):
    id: str
    name: str
    family: str
    width_mm: float
    depth_mm: float
    height_mm: float
    material: str
    finish: str
    score: float = Field(ge=0, le=1)
    differences: tuple[str, ...]
    fixed_cost_eur: float = Field(ge=0)
    material_cost_eur: float = Field(ge=0)
    reference_area_mm2: float = Field(gt=0)
    hours: float | None = Field(default=None, ge=0)
    synthetic: Literal[True] = True


class CostConcept(StrictModel):
    id: str
    label: str
    cost_type: Literal["fixed", "material", "labor", "finish"]
    base_amount: float = Field(ge=0)
    factor: float = Field(gt=0)
    amount: float = Field(ge=0)
    explanation: str
    comparable_id: str


class Estimate(StrictModel):
    schema_version: Literal["0.2.0"] = SCHEMA_VERSION
    run_id: str
    result_revision: int = Field(gt=0)
    currency: Literal["EUR"] = "EUR"
    concepts: tuple[CostConcept, ...]
    total: float = Field(ge=0)
    hours: float | None = Field(default=None, ge=0)
    assumptions: tuple[str, ...]
    comparable_ids: tuple[str, ...]
    synthetic: Literal[True] = True


class InspectEvidenceArgs(StrictModel):
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class SelectScenarioArgs(StrictModel):
    scenario_id: str = Field(min_length=1)


class ExplainPieceArgs(StrictModel):
    piece_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
