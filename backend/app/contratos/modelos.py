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
    input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"] = "mounted_views_legacy"
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


class PartViewReference(StrictModel):
    view_id: str = Field(min_length=1)
    role: Literal["FRONT", "TOP", "SIDE"]
    contour_ids: tuple[str, ...] = Field(min_length=1)
    local_origin_source: Point2D
    local_origin_mm: Point2D | None = None
    local_bounds_source: Bounds2D
    local_bounds_mm: Bounds2D | None


class ObservedPartDimension(StrictModel):
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    state: Literal["observed", "unknown", "conflict"]
    origin: Literal["observed"] = "observed"
    measurement_ids: tuple[str, ...] = ()
    view_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_state(self) -> "ObservedPartDimension":
        if self.state == "observed" and (self.value_mm is None or not self.view_ids or not self.evidence_ids):
            raise ValueError("observed dimension requires value, view and evidence references")
        if self.state != "observed" and self.value_mm is not None:
            raise ValueError("unknown or conflict dimension must have null value")
        if self.state == "conflict" and (not self.view_ids or not self.measurement_ids or len(self.evidence_ids) < 2):
            raise ValueError("conflict dimension requires a view, measurement and incompatible evidence references")
        return self


class PartDimensions(StrictModel):
    length: ObservedPartDimension
    width: ObservedPartDimension
    thickness: ObservedPartDimension


class ObservedQuantity(StrictModel):
    value: int | None = Field(default=None, gt=0)
    state: Literal["observed", "unknown", "ambiguous"]
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_state(self) -> "ObservedQuantity":
        if self.state == "observed" and (self.value is None or not self.evidence_ids):
            raise ValueError("observed quantity requires value and evidence references")
        if self.state != "observed" and self.value is not None:
            raise ValueError("unknown or ambiguous quantity must have null value")
        return self


class SeparatedPartObservation(StrictModel):
    id: str = Field(min_length=1)
    part_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    association_basis: Literal["explicit_key", "unassociated", "ambiguous"]
    views: tuple[PartViewReference, ...] = Field(min_length=1)
    dimensions: PartDimensions
    quantity: ObservedQuantity
    status: Literal["complete", "partial", "ambiguous"]
    source_entity_ids: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def association_is_explicit(self) -> "SeparatedPartObservation":
        if self.association_basis == "explicit_key" and self.part_key is None:
            raise ValueError("explicit association requires part_key")
        if self.association_basis == "unassociated" and self.part_key is not None:
            raise ValueError("unassociated observation cannot have part_key")
        view_ids = [item.view_id for item in self.views]
        roles = [item.role for item in self.views]
        if len(view_ids) != len(set(view_ids)) or len(roles) != len(set(roles)):
            raise ValueError("part observation views and roles must be unique")
        return self


class SeparatedPartsExtraction(StrictModel):
    schema_version: Literal["0.4.0"] = "0.4.0"
    drawing_id: str = Field(min_length=1)
    candidate_revision: str = Field(min_length=1)
    input_kind: Literal["separated_part_views"] = "separated_part_views"
    observations: tuple[SeparatedPartObservation, ...]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_observations(self) -> "SeparatedPartsExtraction":
        ids = [item.id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate part observation ids")
        view_ids = [view.view_id for item in self.observations for view in item.views]
        if len(view_ids) != len(set(view_ids)):
            raise ValueError("view belongs to more than one part observation")
        explicit_keys = [item.part_key for item in self.observations if item.association_basis == "explicit_key"]
        if len(explicit_keys) != len(set(explicit_keys)):
            raise ValueError("explicit part_key belongs to more than one observation")
        return self


class AssemblyPartUse(StrictModel):
    id: str = Field(min_length=1)
    part_observation_id: str = Field(min_length=1)
    role: Literal["side_panel", "shelf", "top_panel", "base_panel", "back_panel", "door", "divider", "unknown"]
    role_status: Literal["hypothesis"] = "hypothesis"
    source_quantity: int | None = Field(default=None, gt=0)
    allocated_quantity: int | None = Field(default=None, gt=0)
    occurrence_indices: tuple[int, ...] = ()
    quantity_source: Literal["observed_annotation", "human_confirmed", "unknown"]
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def quantity_matches_source(self) -> "AssemblyPartUse":
        if self.quantity_source == "unknown":
            if self.source_quantity is not None or self.allocated_quantity is not None or self.occurrence_indices:
                raise ValueError("unknown quantity source must have null quantities and no occurrences")
            return self
        if self.source_quantity is None or self.allocated_quantity is None:
            raise ValueError("observed or confirmed quantity source requires source and allocated quantities")
        if len(self.occurrence_indices) != self.allocated_quantity or len(self.occurrence_indices) != len(set(self.occurrence_indices)):
            raise ValueError("allocated quantity must match unique occurrence indices")
        if any(index < 1 or index > self.source_quantity for index in self.occurrence_indices):
            raise ValueError("occurrence index is outside source quantity")
        return self


class AssemblyConstraint(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal["equal_dimensions", "exterior_from_parts", "role_compatibility"]
    operation: Literal["equal", "sum", "difference", "compatibility"]
    dimension: Literal["length", "width", "thickness", "assembled_width", "assembled_height", "assembled_depth"]
    operand_refs: tuple[str, ...] = Field(min_length=1)
    result_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    status: Literal["pass", "unknown", "conflict"]
    tolerance_mm: float = Field(default=0.1, gt=0, allow_inf_nan=False)
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def result_matches_status(self) -> "AssemblyConstraint":
        if self.status == "pass" and (self.result_mm is None or not self.evidence_ids):
            raise ValueError("passing constraint requires a result and evidence")
        if self.status != "pass" and self.result_mm is not None:
            raise ValueError("unknown or conflict constraint must have null result")
        if self.status == "conflict" and (len(self.operand_refs) < 2 or len(self.evidence_ids) < 2):
            raise ValueError("conflict constraint requires incompatible operands and evidence")
        return self


class DerivedAssemblyDimension(StrictModel):
    axis: Literal["width", "height", "depth"]
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    state: Literal["derived", "unknown", "conflict"]
    operand_refs: tuple[str, ...]
    constraint_id: str | None = None

    @model_validator(mode="after")
    def value_matches_state(self) -> "DerivedAssemblyDimension":
        if self.state == "derived" and (self.value_mm is None or not self.operand_refs or self.constraint_id is None):
            raise ValueError("derived assembly dimension requires value, operands and constraint")
        if self.state != "derived" and self.value_mm is not None:
            raise ValueError("unknown or conflict assembly dimension must have null value")
        return self


class AssemblyCandidate(StrictModel):
    id: str = Field(min_length=1)
    family: Literal["rectangular_shelving", "unknown"]
    family_status: Literal["hypothesis"] = "hypothesis"
    layout: Literal["between_sides", "cap_sides", "unknown"]
    layout_status: Literal["hypothesis"] = "hypothesis"
    uses: tuple[AssemblyPartUse, ...]
    unassigned_part_observation_ids: tuple[str, ...] = ()
    constraints: tuple[AssemblyConstraint, ...]
    derived_dimensions: tuple[DerivedAssemblyDimension, ...]
    unknown_fields: tuple[str, ...]
    assumptions: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    state: Literal["hypothesis"] = "hypothesis"
    needs_review: Literal[True] = True

    @model_validator(mode="after")
    def unique_part_uses(self) -> "AssemblyCandidate":
        use_ids = [item.id for item in self.uses]
        if len(use_ids) != len(set(use_ids)):
            raise ValueError("duplicate assembly use ids")
        identities = [(item.part_observation_id, item.role) for item in self.uses]
        if len(identities) != len(set(identities)):
            raise ValueError("part observation and role allocation must be unique")
        ids = [item.part_observation_id for item in self.uses]
        if set(ids) & set(self.unassigned_part_observation_ids):
            raise ValueError("part observation cannot be both used and unassigned")
        if len(self.unassigned_part_observation_ids) != len(set(self.unassigned_part_observation_ids)):
            raise ValueError("duplicate unassigned part observation")
        axes = [item.axis for item in self.derived_dimensions]
        if len(axes) != len(set(axes)):
            raise ValueError("derived assembly axes must be unique")
        for observation_id in set(ids):
            allocations = [item for item in self.uses if item.part_observation_id == observation_id]
            sources = {item.source_quantity for item in allocations}
            if len(sources) != 1:
                raise ValueError("allocations must share one source quantity")
            source_quantity = next(iter(sources))
            if source_quantity is None:
                if len(allocations) != 1:
                    raise ValueError("unknown quantity cannot be split across roles")
                continue
            occurrence_indices = [index for item in allocations for index in item.occurrence_indices]
            if len(occurrence_indices) != len(set(occurrence_indices)):
                raise ValueError("occurrence indices overlap across role allocations")
            if sum(item.allocated_quantity or 0 for item in allocations) != source_quantity:
                raise ValueError("allocated quantities must cover source quantity exactly")
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
    source_part_observation_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = Field(min_length=1)
    information_class: Literal["hypothesis"] = "hypothesis"


class DecompositionScenario(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    components: tuple[ComponentProposal, ...]
    assumptions: tuple[str, ...] = Field(min_length=1)
    incompatible_with: tuple[str, ...] = ()
    state: Literal["hypothesis"] = "hypothesis"


TableValueState = Literal["observed", "calculated", "confirmed", "proposed", "unknown", "conflict"]


class TableMeasure(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    semantic: Literal["overall_width", "overall_height", "overall_depth", "tabletop_thickness", "support_width", "support_depth", "support_thickness", "unknown"]
    axis: Literal["width", "height", "depth", "section", "unknown"]
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    state: Literal["observed", "unknown", "conflict"]
    measurement_ids: tuple[str, ...] = ()
    view_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_entity_ids: tuple[str, ...] = ()
    slot_origin: Literal["drawing", "profile_required_slot"] = "drawing"
    geometry_relation: Literal["dimension_annotation", "envelope_extent", "offset_from_min_x", "offset_from_max_x", "offset_from_min_y", "offset_from_max_y", "opposite_offsets", "profile_required_slot"] = "dimension_annotation"

    @model_validator(mode="after")
    def value_matches_state(self) -> "TableMeasure":
        if self.state == "observed" and (self.value_mm is None or not self.view_ids or not self.evidence_ids or not (self.measurement_ids or self.source_entity_ids)):
            raise ValueError("observed table measure requires value and drawing provenance")
        if self.state != "observed" and self.value_mm is not None:
            raise ValueError("unknown or conflict table measure must have null value")
        if self.state == "conflict" and len(self.evidence_ids) < 2:
            raise ValueError("conflict table measure requires incompatible evidence")
        if self.slot_origin == "profile_required_slot" and (self.state != "unknown" or self.geometry_relation != "profile_required_slot" or self.measurement_ids or self.view_ids or self.evidence_ids or self.source_entity_ids):
            raise ValueError("profile slot must be an unobserved unknown")
        if self.slot_origin == "drawing" and self.geometry_relation == "profile_required_slot":
            raise ValueError("drawing measure cannot claim a profile slot relation")
        return self


class MountedTableAnalysis(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    drawing_id: str = Field(min_length=1)
    ledger_revision: str = Field(min_length=1)
    input_kind: Literal["mounted_orthographic_views"] = "mounted_orthographic_views"
    profile: Literal["rectangular_table_v1"] = "rectangular_table_v1"
    measures: tuple[TableMeasure, ...]
    admitted_measurement_ids: tuple[str, ...]
    state: Literal["ready", "needs_review"]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def measure_ids_are_exact(self) -> "MountedTableAnalysis":
        ids = [item.id for item in self.measures]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate table measure ids")
        if len(self.admitted_measurement_ids) != len(set(self.admitted_measurement_ids)) or set(ids) != set(self.admitted_measurement_ids):
            raise ValueError("admitted measurement ids must exactly cover measures")
        return self


class TableOperandRef(StrictModel):
    ref_type: Literal["measure", "binding"]
    ref_id: str = Field(min_length=1, max_length=120)


class TableBinding(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    operation: Literal["copy", "add", "subtract"]
    operand_refs: tuple[TableOperandRef, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def operation_arity(self) -> "TableBinding":
        if self.operation == "copy" and len(self.operand_refs) != 1:
            raise ValueError("copy requires exactly one operand")
        if self.operation in ("add", "subtract") and len(self.operand_refs) < 2:
            raise ValueError(f"{self.operation} requires at least two operands")
        return self


class TablePremise(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    kind: Literal["topology", "flush_placement", "rectangular_components", "section_assignment", "other"]
    required: Literal[True] = True
    description: str = Field(min_length=1, max_length=300)


class TableComponentSpec(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    role: Literal["tabletop", "side_support", "corner_support"]
    length_binding_id: str = Field(min_length=1)
    width_binding_id: str = Field(min_length=1)
    thickness_binding_id: str = Field(min_length=1)
    quantity_rule_id: Literal["top_one", "two_side_supports", "four_corner_supports"]
    quantity_rule_version: Literal["1"] = "1"
    placement_rule_id: Literal["top_flush", "side_supports_flush", "corner_supports_flush"]
    placement_rule_version: Literal["1"] = "1"
    evidence_ids: tuple[str, ...] = ()
    premise_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def rules_match_role(self) -> "TableComponentSpec":
        expected = {
            "tabletop": ("top_one", "top_flush"),
            "side_support": ("two_side_supports", "side_supports_flush"),
            "corner_support": ("four_corner_supports", "corner_supports_flush"),
        }[self.role]
        if (self.quantity_rule_id, self.placement_rule_id) != expected:
            raise ValueError("quantity and placement rules must match component role")
        return self


class TableProgramProposal(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    id: str = Field(min_length=1, max_length=120)
    ledger_revision: str = Field(min_length=1)
    profile: Literal["rectangular_table_v1"] = "rectangular_table_v1"
    proposal_origin: Literal["model_generated", "catalog_baseline"]
    table_template_id: Literal["side_supports_v1", "corner_supports_v1"] | None = None
    bindings: tuple[TableBinding, ...] = Field(min_length=1, max_length=24)
    components: tuple[TableComponentSpec, ...] = Field(min_length=2, max_length=2)
    premises: tuple[TablePremise, ...] = Field(min_length=1, max_length=16)
    assumptions: tuple[str, ...] = Field(min_length=1, max_length=16)
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_program_graph_and_topology(self) -> "TableProgramProposal":
        binding_ids = [item.id for item in self.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("duplicate table binding ids")
        seen: set[str] = set()
        for binding in self.bindings:
            for operand in binding.operand_refs:
                if operand.ref_type == "binding" and operand.ref_id not in seen:
                    raise ValueError("binding reference must target a previous binding")
            seen.add(binding.id)
        component_ids = [item.id for item in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("duplicate table component ids")
        roles = [item.role for item in self.components]
        if roles.count("tabletop") != 1 or sum(role in ("side_support", "corner_support") for role in roles) != 1:
            raise ValueError("program requires exactly one tabletop and one support system")
        binding_set = set(binding_ids)
        root_bindings = {value for item in self.components for value in (item.length_binding_id, item.width_binding_id, item.thickness_binding_id)}
        if not root_bindings <= binding_set:
            raise ValueError("component references an unknown binding")
        dependencies = {
            item.id: {operand.ref_id for operand in item.operand_refs if operand.ref_type == "binding"}
            for item in self.bindings
        }
        reachable = set(root_bindings)
        pending = list(root_bindings)
        while pending:
            current = pending.pop()
            for dependency in dependencies[current]:
                if dependency not in reachable:
                    reachable.add(dependency)
                    pending.append(dependency)
        if reachable != binding_set:
            raise ValueError("dead bindings are not allowed")
        premise_ids = [item.id for item in self.premises]
        if len(premise_ids) != len(set(premise_ids)):
            raise ValueError("duplicate table premise ids")
        if any(not set(item.premise_ids) <= set(premise_ids) for item in self.components):
            raise ValueError("component references an unknown premise")
        support_role = next(role for role in roles if role != "tabletop")
        expected_template = "side_supports_v1" if support_role == "side_support" else "corner_supports_v1"
        if self.proposal_origin == "catalog_baseline" and self.table_template_id != expected_template:
            raise ValueError("catalog baseline requires the matching explicit template")
        if self.proposal_origin == "model_generated" and self.table_template_id is not None:
            raise ValueError("model generated program cannot claim a catalog template")
        return self


class ProposeTableProgramArgs(StrictModel):
    bindings: tuple[TableBinding, ...] = Field(min_length=1, max_length=24)
    components: tuple[TableComponentSpec, ...] = Field(min_length=2, max_length=2)
    premises: tuple[TablePremise, ...] = Field(min_length=1, max_length=16)
    assumptions: tuple[str, ...] = Field(min_length=1, max_length=16)
    evidence_ids: tuple[str, ...] = ()


class InspectTableMeasuresArgs(StrictModel):
    measurement_ids: tuple[str, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def unique_measurements(self) -> "InspectTableMeasuresArgs":
        if len(self.measurement_ids) != len(set(self.measurement_ids)):
            raise ValueError("duplicate table measurement ids")
        return self


class TableReviewDecision(StrictModel):
    target_kind: Literal["program", "component", "premise"]
    target_id: str = Field(min_length=1)
    action: Literal["accept", "reject"]
    reason: str = Field(min_length=1, max_length=500)


class TableConfirmedValue(StrictModel):
    target_kind: Literal["measurement_slot"] = "measurement_slot"
    target_id: str = Field(min_length=1)
    value_mm: float = Field(gt=0, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=500)
    source: Literal["human"] = "human"


class TableMeasurementDisposition(StrictModel):
    measurement_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=300)
    blocking: bool


class TableFieldValue(StrictModel):
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    state: TableValueState
    dependency_refs: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def value_matches_state(self) -> "TableFieldValue":
        if self.state in ("unknown", "conflict") and self.value_mm is not None:
            raise ValueError("unknown or conflict field must have null value")
        if self.state not in ("unknown", "conflict") and self.value_mm is None:
            raise ValueError("resolved field requires a value")
        return self


class EvaluatedTableBinding(StrictModel):
    id: str
    operation: Literal["copy", "add", "subtract"]
    operand_refs: tuple[TableOperandRef, ...]
    result: TableFieldValue


class EvaluatedTableComponent(StrictModel):
    id: str
    role: Literal["tabletop", "side_support", "corner_support"]
    length: TableFieldValue
    width: TableFieldValue
    thickness: TableFieldValue
    quantity: int | None = Field(default=None, gt=0)
    quantity_rule_id: str
    placement_rule_id: str
    accepted: bool
    premise_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class TableOccurrence(StrictModel):
    id: str
    component_id: str
    occurrence_index: int = Field(gt=0)


class TablePlacement(StrictModel):
    occurrence_id: str
    position_mm: Point3D | None = None
    dimensions_mm: Size3D | None = None
    rule_id: str
    rule_version: str
    state: Literal["pass", "proposed", "unknown", "conflict"]
    dependency_refs: tuple[str, ...]


class TableProgramIssue(StrictModel):
    code: str = Field(min_length=1)
    severity: Literal["error", "review", "warning"]
    message: str = Field(min_length=1)
    target_ids: tuple[str, ...] = ()


class TableOverallDimensions(StrictModel):
    width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    depth_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    height_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class EvaluatedTableProgram(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    raw_program: TableProgramProposal
    normalized_program: TableProgramProposal
    program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_revision: str
    registry_versions: dict[str, str]
    bindings: tuple[EvaluatedTableBinding, ...]
    components: tuple[EvaluatedTableComponent, ...]
    occurrences: tuple[TableOccurrence, ...]
    placements: tuple[TablePlacement, ...]
    overall_dimensions: TableOverallDimensions
    consumed_measurement_ids: tuple[str, ...]
    measurement_dispositions: tuple[TableMeasurementDisposition, ...]
    accepted_target_ids: tuple[str, ...] = ()
    rejected_target_ids: tuple[str, ...] = ()
    issues: tuple[TableProgramIssue, ...] = ()
    state: Literal["hypothesis", "needs_review", "completed", "rejected"]

    @model_validator(mode="after")
    def decisions_and_coverage_are_unique(self) -> "EvaluatedTableProgram":
        if set(self.accepted_target_ids) & set(self.rejected_target_ids):
            raise ValueError("accepted and rejected targets must be disjoint")
        disposed = [item.measurement_id for item in self.measurement_dispositions]
        if len(disposed) != len(set(disposed)) or set(disposed) & set(self.consumed_measurement_ids):
            raise ValueError("measurement coverage must be disjoint")
        if self.state == "completed" and (any(item.blocking for item in self.measurement_dispositions) or any(item.severity != "warning" for item in self.issues)):
            raise ValueError("completed program cannot contain blockers")
        return self


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
    assembly_candidate_id: str | None = None
    table_program_id: str | None = None
    table_decisions: tuple[TableReviewDecision, ...] = ()
    table_confirmed_values: tuple[TableConfirmedValue, ...] = ()

    @model_validator(mode="after")
    def unique_proposals(self) -> "ReviewRequest":
        table_review = self.table_program_id is not None or bool(self.table_decisions) or bool(self.table_confirmed_values)
        if not self.decisions and self.scenario_id is None and self.assembly_candidate_id is None and not table_review:
            raise ValueError("a scenario selection or explicit decisions are required")
        if table_review and (self.decisions or self.scenario_id is not None or self.assembly_candidate_id is not None or self.confirmed_thickness_mm is not None):
            raise ValueError("table review and legacy review fields are mutually exclusive")
        if table_review and (self.table_program_id is None or not self.notes):
            raise ValueError("table review requires program id and notes")
        if self.scenario_id is not None and (self.decisions or self.assembly_candidate_id is not None):
            raise ValueError("scenario selection and explicit decisions are mutually exclusive")
        if self.assembly_candidate_id is not None and self.scenario_id is not None:
            raise ValueError("legacy scenario and assembly candidate are mutually exclusive")
        if self.scenario_id is not None and (self.confirmed_thickness_mm is None or not self.notes):
            raise ValueError("scenario selection requires thickness and notes")
        if self.assembly_candidate_id is not None and not self.notes:
            raise ValueError("assembly candidate selection requires notes")
        ids = [item.proposal_id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate proposal decisions")
        table_targets = [(item.target_kind, item.target_id) for item in self.table_decisions]
        if len(table_targets) != len(set(table_targets)):
            raise ValueError("duplicate table review targets")
        confirmed_targets = [item.target_id for item in self.table_confirmed_values]
        if len(confirmed_targets) != len(set(confirmed_targets)):
            raise ValueError("duplicate table confirmed values")
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
    source_part_observation_ids: tuple[str, ...] = ()
    human_confirmation: str
    field_states: dict[str, Literal["observed", "calculated", "confirmed", "unknown"]]


class HumanReview(StrictModel):
    reviewer_name: str
    reason: str
    timestamp: str
    selected_scenario_id: str | None
    selected_assembly_candidate_id: str | None = None
    selected_table_program_id: str | None = None


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
    input_semantics: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"] = "mounted_views_legacy"
    part_analysis: SeparatedPartsExtraction | None = None
    assembly_candidates: tuple[AssemblyCandidate, ...] = ()
    selected_assembly_candidate_id: str | None = None
    table_analysis: MountedTableAnalysis | None = None
    table_programs: tuple[TableProgramProposal, ...] = ()
    selected_table_program_id: str | None = None
    evaluated_table_program: EvaluatedTableProgram | None = None
    table_review_decisions: tuple[TableReviewDecision, ...] = ()
    table_confirmed_values: tuple[TableConfirmedValue, ...] = ()
    table_cost_scope: TableCostScope | None = None

    @model_validator(mode="after")
    def parts_payload_matches_semantics(self) -> "Result":
        if self.input_semantics == "separated_part_views" and self.part_analysis is None:
            raise ValueError("separated part result requires part_analysis")
        if self.selected_assembly_candidate_id is not None and self.selected_assembly_candidate_id not in {item.id for item in self.assembly_candidates}:
            raise ValueError("selected assembly candidate is unknown")
        if self.input_semantics == "mounted_orthographic_views" and self.table_analysis is None:
            raise ValueError("mounted table result requires table analysis")
        table_program_ids = {item.id for item in self.table_programs}
        if self.selected_table_program_id is not None and self.selected_table_program_id not in table_program_ids:
            raise ValueError("selected table program is unknown")
        if self.evaluated_table_program is not None and self.evaluated_table_program.raw_program.id not in table_program_ids:
            raise ValueError("evaluated table program is not in result programs")
        return self


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
    part_observation_id: str | None = None
    placement_status: Literal["hypothesis", "human_selected"] = "human_selected"
    placement_constraint_ids: tuple[str, ...] = ()


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


class TableDrawingPrimitive(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal["line", "rect", "dimension", "text"]
    points_mm: tuple[Point2D, ...]
    text: str | None = None
    value_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    state: Literal["observed", "calculated", "confirmed", "proposed", "unknown", "conflict"]
    dependency_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def numeric_dimension_is_honest(self) -> "TableDrawingPrimitive":
        if self.kind == "line" and len(self.points_mm) < 2:
            raise ValueError("line requires at least 2 points")
        expected_points = {"rect": 2, "dimension": 3, "text": 1}.get(self.kind)
        if expected_points is not None and len(self.points_mm) != expected_points:
            raise ValueError(f"{self.kind} requires exactly {expected_points} points")
        if self.kind == "dimension" and self.state in ("unknown", "conflict") and self.value_mm is not None:
            raise ValueError("unknown drawing dimension cannot contain a numeric value")
        return self


class TableSheetPlan(StrictModel):
    sheet_id: str = Field(min_length=1)
    kind: Literal["general", "component", "cut_sheet"]
    title: str = Field(min_length=1)
    component_id: str | None = None
    page: int = Field(gt=0)
    status: Literal["ready", "incomplete"]
    primitives: tuple[TableDrawingPrimitive, ...]
    warnings: tuple[str, ...] = ()


class TableDrawingPlan(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    drawing_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    coordinate_unit: Literal["mm"] = "mm"
    registry_versions: dict[str, str]
    overall_dimensions: TableOverallDimensions
    components: tuple[EvaluatedTableComponent, ...]
    occurrences: tuple[TableOccurrence, ...]
    placements: tuple[TablePlacement, ...]
    sheets: tuple[TableSheetPlan, ...]


class TableDrawingArtifactData(StrictModel):
    sheet_id: str
    format: Literal["svg", "dxf"]
    media_type: Literal["image/svg+xml", "application/dxf"]
    filename: str = Field(min_length=1)
    content: bytes


class TableDrawingExports(StrictModel):
    result_revision: int = Field(gt=0)
    program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[TableDrawingArtifactData, ...]


class TableDrawingFormatLink(StrictModel):
    format: Literal["svg", "dxf"]
    media_type: str
    url: str = Field(min_length=1)


class TableDrawingManifestSheet(StrictModel):
    sheet_id: str
    kind: Literal["general", "component", "cut_sheet"]
    title: str
    component_id: str | None = None
    page: int = Field(gt=0)
    result_revision: int = Field(gt=0)
    program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["ready", "incomplete"]
    warnings: tuple[str, ...] = ()
    formats: tuple[TableDrawingFormatLink, ...]


class TableDrawingManifest(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    run_id: str
    result_revision: int = Field(gt=0)
    program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheets: tuple[TableDrawingManifestSheet, ...]


class TableCostScope(StrictModel):
    material_tariff_id: str | None = None
    edge_scope: Literal["none", "all_exposed"] = "none"
    operation_tariff_ids: tuple[str, ...] = ()


class TableCostTariff(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    concept_type: Literal["fixed", "material_area", "material_volume", "edge", "operation", "labor", "finish"]
    scope: Literal["material", "edge", "operation"]
    rate_eur_per_unit: float = Field(ge=0, allow_inf_nan=False)
    rate_unit: Literal["EUR/m2", "EUR/m3", "EUR/m", "EUR/unit", "EUR/h"]
    synthetic: Literal[True] = True


class TableCostCatalog(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    catalog_version: str = Field(min_length=1)
    tariffs: tuple[TableCostTariff, ...]
    synthetic: Literal[True] = True

    @model_validator(mode="after")
    def tariff_ids_are_unique(self) -> "TableCostCatalog":
        ids = [item.id for item in self.tariffs]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate table tariff ids")
        return self


class TableCostConcept(StrictModel):
    id: str
    label: str
    concept_type: Literal["fixed", "material_area", "material_volume", "edge", "operation", "labor", "finish"]
    component_id: str | None = None
    occurrence_ids: tuple[str, ...] = ()
    formula: str
    quantity: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    quantity_unit: Literal["m2", "m3", "m", "unit", "h"]
    rate_eur_per_unit: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    rate_unit: Literal["EUR/m2", "EUR/m3", "EUR/m", "EUR/unit", "EUR/h"]
    amount_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    state: Literal["resolved", "unknown", "not_applicable"]
    required: bool
    dependency_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def amount_matches_state(self) -> "TableCostConcept":
        values = (self.quantity, self.rate_eur_per_unit, self.amount_eur)
        if self.state == "resolved" and any(value is None for value in values):
            raise ValueError("resolved cost concept requires quantity, rate and amount")
        if self.state != "resolved" and self.amount_eur is not None:
            raise ValueError("unresolved cost concept cannot contain an amount")
        return self


class TableCostEstimate(StrictModel):
    schema_version: Literal["0.5.0"] = "0.5.0"
    run_id: str | None = None
    result_revision: int = Field(gt=0)
    program_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str
    currency: Literal["EUR"] = "EUR"
    scope: TableCostScope
    concepts: tuple[TableCostConcept, ...]
    known_subtotal_eur: float = Field(ge=0, allow_inf_nan=False)
    grand_total_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    total_state: Literal["partial", "complete"]
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def total_is_not_partial_subtotal(self) -> "TableCostEstimate":
        required_unknown = any(item.required and item.state == "unknown" for item in self.concepts)
        if self.total_state == "partial" and self.grand_total_eur is not None:
            raise ValueError("partial estimate cannot expose a grand total")
        if self.total_state == "complete" and (self.grand_total_eur is None or required_unknown):
            raise ValueError("complete estimate requires all required concepts")
        return self


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


class DescriptorPartFeature(StrictModel):
    length_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    width_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    thickness_mm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    quantity: int | None = Field(default=None, gt=0)
    unknown_fields: tuple[Literal["length_mm", "width_mm", "thickness_mm", "quantity"], ...] = ()
    field_states: dict[
        Literal["length_mm", "width_mm", "thickness_mm", "quantity"],
        Literal["observed", "confirmed", "unknown"],
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def complete_field_states_when_present(self) -> "DescriptorPartFeature":
        expected = {"length_mm", "width_mm", "thickness_mm", "quantity"}
        if self.field_states and set(self.field_states) != expected:
            raise ValueError("field_states must cover every canonical part feature field")
        return self


class FurnitureDescriptorV2(StrictModel):
    descriptor_version: Literal["furniture-v2"] = "furniture-v2"
    family: Literal["rectangular_shelving", "unknown"]
    dimensions: DescriptorDimensions
    roles: tuple[RoleQuantity, ...]
    structure: Literal["top_base_between_sides", "top_base_cap_sides", "unknown"]
    material: str | None = None
    finish: str | None = None
    thicknesses_mm: tuple[float, ...]
    classification_status: Literal["hypothesis", "confirmed"]
    part_features: tuple[DescriptorPartFeature, ...] = ()
    unknown_fields: tuple[str, ...]


class TableDescriptorComponentFeature(StrictModel):
    role: Literal["tabletop", "side_support", "corner_support"]
    quantity: int = Field(gt=0)
    length_mm: float = Field(gt=0, allow_inf_nan=False)
    width_mm: float = Field(gt=0, allow_inf_nan=False)
    thickness_mm: float = Field(gt=0, allow_inf_nan=False)
    field_states: dict[
        Literal["quantity", "length_mm", "width_mm", "thickness_mm"],
        Literal["calculated", "confirmed"],
    ]

    @model_validator(mode="after")
    def states_are_complete(self) -> "TableDescriptorComponentFeature":
        if set(self.field_states) != {"quantity", "length_mm", "width_mm", "thickness_mm"}:
            raise ValueError("table descriptor field states must be complete")
        return self


class FurnitureDescriptorV3(StrictModel):
    descriptor_version: Literal["furniture-v3"] = "furniture-v3"
    family: Literal["rectangular_table"] = "rectangular_table"
    profile: Literal["rectangular_table_v1"] = "rectangular_table_v1"
    dimensions: DescriptorDimensions
    structure: Literal["side_support_table", "corner_support_table"]
    components: tuple[TableDescriptorComponentFeature, ...]
    material_tariff_id: str | None = None
    classification_status: Literal["confirmed"] = "confirmed"
    unknown_fields: tuple[str, ...] = ()


class EmbeddingMetadata(StrictModel):
    provider: Literal["openai"] = "openai"
    model: str = Field(min_length=1)
    dimensions: int = Field(gt=0)
    descriptor_version: Literal["furniture-v1", "furniture-v2", "furniture-v3"] = "furniture-v1"
    cache_key: str = Field(min_length=1)
    status: Literal["generated", "cache"]


class LibraryItem(StrictModel):
    schema_version: Literal["0.3.0"] = "0.3.0"
    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    label: str = Field(min_length=1)
    descriptor: FurnitureDescriptor | FurnitureDescriptorV2 | FurnitureDescriptorV3
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
    agent_selected_assembly_candidate_id: str | None = None
    agent_selected_table_program_id: str | None = None
    document_id: str | None = None
    input_kind: Literal["mounted_views_legacy", "separated_part_views", "mounted_orthographic_views"] = "mounted_views_legacy"


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


class InspectSeparatedPartArgs(StrictModel):
    candidate_revision: str = Field(min_length=1)
    part_observation_id: str = Field(min_length=1)


class SelectAssemblyCandidateArgs(StrictModel):
    candidate_revision: str = Field(min_length=1)
    assembly_candidate_id: str = Field(min_length=1)
